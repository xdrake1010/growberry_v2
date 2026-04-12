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

    def _ensure_dir(self, path):
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

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
            camera = cv2.VideoCapture(0)
            if not camera.isOpened():
                logger.error("Could not open camera for timelapse")
                return False
                
            # Give camera a moment to adjust brightness/focus
            camera.read()
            time.sleep(0.5) 
            success, frame = camera.read()
            if success:
                cv2.imwrite(filepath, frame)
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
        camera = cv2.VideoCapture(0)
        try:
            # Let's lower resolution to save RAM & Bandwidth
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            while True:
                success, frame = camera.read()
                if not success:
                    logger.warning("Failed to read frame during stream")
                    break
                
                # Compress heavily for the live web feed
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                # Tiny sleep to drop FPS and save CPU
                time.sleep(0.1) 
        finally:
            logger.info("Stopping live stream...")
            self.is_streaming = False
            camera.release()
