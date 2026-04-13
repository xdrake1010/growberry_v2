import cv2
import os
import time
import logging
import threading
import numpy as np
from datetime import datetime
from config import TIMELAPSE_BASE_DIR

logger = logging.getLogger("Growberry.Camera")

class CameraController:
    def __init__(self, cosecha_name="default"):
        self.cosecha_name = cosecha_name
        self.is_streaming = False
        self.camera_index = 0  # Default to 0, will probe if it fails
        self.lock = threading.Lock()
        self.client_count = 0
        self.shared_camera = None
        self.last_frame = None

    def set_cosecha_name(self, name):
        self.cosecha_name = name
        logger.info(f"Camera controller harvest name updated to: {name}")

    def _ensure_dir(self, path):
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

    def check_available_cameras(self):
        """Probes basic indices to see what's actually available on the system."""
        available = []
        for idx in range(10):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                available.append(idx)
                cap.release()
        return available

    def _get_camera(self):
        """Attempts to open the camera with preferred backends and settings.
        Includes a retry loop to handle transient USB disconnects (EMI).
        Expects self.lock to be held by caller.
        """
        # If already opened by another thread, return it
        if self.shared_camera is not None:
             try:
                 if self.shared_camera.isOpened():
                     return self.shared_camera
             except:
                 self.shared_camera = None

        max_attempts = 2
        for attempt in range(max_attempts):
            indices_to_try = [self.camera_index] + [i for i in range(5) if i != self.camera_index]
            
            for idx in indices_to_try:
                # Try multiple backends: V4L2 first, then default
                backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
                for backend in backends:
                    try:
                        logger.info(f"[PROBE] Trying index {idx} with backend {backend}")
                        cap = cv2.VideoCapture(idx, backend)
                        if cap.isOpened():
                            # Set format to MJPEG
                            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            
                            # Test if we can actually read a frame
                            success, frame = cap.read()
                            if success:
                                logger.info(f"[SUCCESS] Camera {idx} is UP and providing frames.")
                                self.camera_index = idx 
                                self.shared_camera = cap
                                return cap
                            else:
                                logger.warning(f"[FAIL] Camera {idx} opened but failed to read frame.")
                                cap.release()
                    except Exception as e:
                        logger.warning(f"Error opening camera {idx}: {e}")
            
            if attempt < max_attempts - 1:
                time.sleep(1.0)
                
        return None

    def _draw_metadata_overlay(self, frame, metadata):
        """Draws a professional semi-transparent legend at the bottom of the frame."""
        try:
            h, w = frame.shape[:2]
            overlay = frame.copy()
            
            # Bottom bar setup
            bar_height = int(h * 0.08)
            cv2.rectangle(overlay, (0, h - bar_height), (w, h), (0, 0, 0), -1)
            
            # Blend the black bar for semi-transparency
            alpha = 0.5
            frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
            
            # Text properties
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = h / 1000.0 * 0.7
            font_color = (255, 255, 255)
            thickness = 1
            
            # Content
            harvest_name = metadata.get("harvest", self.cosecha_name).upper()
            temp = f"{metadata.get('temp', '--')}C"
            hum = f"{metadata.get('hum', '--')}%"
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Draw Left: Harvest Name
            cv2.putText(frame, f"GROWBERRY | {harvest_name}", (20, h - int(bar_height/2) + 5), 
                        font, font_scale, font_color, thickness, cv2.LINE_AA)
            
            # Draw Right: Stats
            stats_str = f"{temp} | {hum} | {time_str}"
            text_size = cv2.getTextSize(stats_str, font, font_scale, thickness)[0]
            cv2.putText(frame, stats_str, (w - text_size[0] - 20, h - int(bar_height/2) + 5), 
                        font, font_scale, font_color, thickness, cv2.LINE_AA)
            
            return frame
        except Exception as e:
            logger.error(f"Error drawing overlay: {e}")
            return frame

    def capture_timelapse_frame(self, metadata=None):
        """Captures a single frame safely and saves it to the timelapse directory structure."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")
        
        target_dir = os.path.join(TIMELAPSE_BASE_DIR, self.cosecha_name, today_str)
        self._ensure_dir(target_dir)
        
        filename = f"{timestamp}.jpg"
        filepath = os.path.join(target_dir, filename)

        logger.info(f"Capturing timelapse frame: {filename}")
        
        camera = None
        release_needed = False
        
        try:
            with self.lock:
                if self.shared_camera is not None and self.shared_camera.isOpened():
                    camera = self.shared_camera
                    release_needed = False # Don't release if it's shared/streaming
                else:
                    camera = self._get_camera()
                    release_needed = True # Release if we opened it just for this
            
            if camera is None:
                logger.error("Could not find or open any camera for timelapse")
                return False
                
            # Give camera a moment to adjust brightness/focus if we just opened it
            if release_needed:
                time.sleep(1.0) 
                
            success, frame = camera.read()
            
            if success:
                # Apply metadata burn-in if provided
                if metadata:
                    frame = self._draw_metadata_overlay(frame, metadata)

                # Save with good quality for timelapse
                cv2.imwrite(filepath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                logger.info(f"Saved timelapse frame with metadata to {filepath}")
            else:
                logger.error("Failed to read frame from camera")
            
            if release_needed:
                with self.lock:
                    camera.release()
                    self.shared_camera = None
            
            return success
        except Exception as e:
            logger.error(f"Error capturing timelapse: {e}")
            return False

    def generate_live_stream(self):
        """Generator for the MJPEG stream to serve to the web interface"""
        with self.lock:
            self.client_count += 1
            self.is_streaming = True
            logger.info(f"Client connected. Total clients: {self.client_count}")
        
        camera = None
        try:
            # Re-probing sometimes helps if the driver hung
            with self.lock:
                camera = self._get_camera()
            
            if camera is None:
                logger.error("Could not find or open any camera for streaming")
                yield (b'--frame\r\n'
                       b'Content-Type: text/plain\r\n\r\n' + b'Camera Unavailable' + b'\r\n')
                return

            retry_count = 0
            while self.is_streaming:
                # Thread-safe read
                with self.lock:
                    if self.shared_camera is None or not self.shared_camera.isOpened():
                         break
                    success, frame = self.shared_camera.read()
                
                if not success:
                    logger.warning(f"Failed to read frame during stream (retry {retry_count}/5)")
                    retry_count += 1
                    if retry_count > 5:
                        break
                    time.sleep(0.5) 
                    continue
                
                retry_count = 0
                
                # Compress heavily for the live web feed
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                # Cap FPS to ~10 to save memory and CPU on Pi Zero
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in live stream generator: {e}")
        finally:
            with self.lock:
                self.client_count -= 1
                logger.info(f"Client disconnected. Remaining clients: {self.client_count}")
                if self.client_count <= 0:
                    self.client_count = 0
                    self.is_streaming = False
                    if self.shared_camera:
                        logger.info("Closing shared camera handle.")
                        self.shared_camera.release()
                        self.shared_camera = None
