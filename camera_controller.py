import cv2
import os
import time
import logging
from datetime import datetime
from config import TIMELAPSE_BASE_DIR

logger = logging.getLogger("Growberry.Camera")

class CameraController:
    def __init__(self, cosecha_name="default"):
        self.cosecha_name = cosecha_name
        self.is_streaming = False
        self.camera_index = 0  # Default to 0, will probe if it fails

    def _ensure_dir(self, path):
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

    def _get_camera(self):
        """Attempts to open the camera with preferred backends and settings."""
        # Try preferred index first, then probe others if it fails
        indices_to_try = [self.camera_index] + [i for i in range(5) if i != self.camera_index]
        
        for idx in indices_to_try:
            # We use CAP_V4L2 for better compatibility/performance on Pi/Linux
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                # Set format to MJPG to reduce USB bandwidth and memory overhead
                # This is critical for avoiding 'Failed to allocate memory' on Pi Zero 2 W
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                
                # Set lower resolution immediately to save memory
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                # Set buffer size to 1 to avoid lag
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                self.camera_index = idx # Remember working index
                return cap
        return None

    def capture_timelapse_frame(self):
        """Captures a single frame safely and saves it to the timelapse directory structure."""
        if self.is_streaming:
             logger.info("Skipping timelapse capture (Camera is being viewed live).")
             return False

        today_str = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")
        
        target_dir = os.path.join(TIMELAPSE_BASE_DIR, self.cosecha_name, today_str)
        self._ensure_dir(target_dir)
        
        filename = f"{timestamp}.jpg"
        filepath = os.path.join(target_dir, filename)

        logger.info(f"Capturing timelapse frame: {filename}")
        try:
            camera = self._get_camera()
            if camera is None:
                logger.error("Could not find or open any camera for timelapse")
                return False
                
            # Give camera a moment to adjust brightness/focus
            time.sleep(1.0) 
            success, frame = camera.read()
            
            if success:
                # Save with good quality for timelapse
                cv2.imwrite(filepath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                logger.info(f"Saved timelapse frame to {filepath}")
            else:
                logger.error("Failed to read frame from camera")
            
            camera.release()
            return success
        except Exception as e:
            logger.error(f"Error capturing timelapse: {e}")
            return False

    def generate_live_stream(self):
        """Generator for the MJPEG stream to serve to the web interface"""
        logger.info("Starting live stream...")
        self.is_streaming = True
        
        camera = self._get_camera()
        if camera is None:
            logger.error("Could not find or open any camera for streaming")
            self.is_streaming = False
            return

        try:
            retry_count = 0
            while self.is_streaming:
                success, frame = camera.read()
                if not success:
                    logger.warning(f"Failed to read frame during stream (retry {retry_count}/5)")
                    retry_count += 1
                    if retry_count > 5:
                        break
                    time.sleep(0.5) # Give hardware a moment to recover
                    continue
                
                retry_count = 0 # Reset on success
                
                # Compress heavily for the live web feed to save bandwidth
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                # drop FPS to save CPU on Pi Zero (approx 10 FPS)
                time.sleep(0.1) 
        finally:
            logger.info("Stopping live stream...")
            self.is_streaming = False
            if camera:
                camera.release()
