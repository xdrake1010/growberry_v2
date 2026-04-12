import cv2
import os
import time
from datetime import datetime
from config import TIMELAPSE_BASE_DIR

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
             # Skip or handle capture if streaming? 
             # On a Pi, opening the index 0 twice won't work. We might skip if someone is watching live.
             # For now, let's assume we skip if streaming.
             print("Skipping timelapse capture (Camera is being viewed live).")
             return False

        today_str = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")
        
        target_dir = os.path.join(TIMELAPSE_BASE_DIR, self.cosecha_name, today_str)
        self._ensure_dir(target_dir)
        
        filename = f"{timestamp}.jpg"
        filepath = os.path.join(target_dir, filename)

        try:
            camera = cv2.VideoCapture(0)
            # Give camera a moment to adjust brightness/focus
            camera.read()
            time.sleep(0.5) 
            success, frame = camera.read()
            if success:
                cv2.imwrite(filepath, frame)
            camera.release()
            return success
        except Exception as e:
            print(f"Error capturing timelapse: {e}")
            return False

    def generate_live_stream(self):
        """Generator for the MJPEG stream to serve to the web interface"""
        self.is_streaming = True
        camera = cv2.VideoCapture(0)
        try:
            # Let's lower resolution to save RAM & Bandwidth
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            while True:
                success, frame = camera.read()
                if not success:
                    break
                
                # Compress heavily for the live web feed
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                # Tiny sleep to drop FPS and save CPU
                time.sleep(0.1) 
        finally:
            self.is_streaming = False
            camera.release()
