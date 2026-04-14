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
        self.last_fail_time = 0 # Timestamp of last failed probe

    def set_cosecha_name(self, name):
        self.cosecha_name = name
        logger.info(f"Camera controller harvest name updated to: {name}")

    def _ensure_dir(self, path):
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

    def check_available_cameras(self):
        """Probes basic indices to see what's actually available on the system."""
        # Fail fast if in cooldown
        if time.time() - self.last_fail_time < 60:
            return []
            
        available = []
        for idx in [0, 1]: # Only check primary indices to avoid hang
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
        
        # FAIL FAST: If we failed very recently, don't even try and block the thread
        cooldown_period = 60 # seconds
        time_since_fail = time.time() - self.last_fail_time
        if time_since_fail < cooldown_period:
            logger.info(f"[IDLE] Camera is in cooldown ({int(cooldown_period - time_since_fail)}s remaining).")
            return None

        max_attempts = 2 # Reduced from 5 to avoid blocking Flask
        for attempt in range(max_attempts):
            # Only try index 0 and 1 on Pi Zero to save time
            indices_to_try = [0, 1] if self.camera_index not in [0, 1] else [self.camera_index, 1 - self.camera_index]
            
            for idx in indices_to_try:
                # Try multiple backends: V4L2 first, then default
                backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
                for backend in backends:
                    try:
                        logger.info(f"[PROBE] Trying index {idx} with backend {backend}")
                        cap = cv2.VideoCapture(idx, backend)
                        if cap.isOpened():
                            # CRITICAL: Give camera a moment to initialize hardware buffers
                            # On Pi Zero, anything less than 1.5s can cause 'Protocol Error' with Redragon
                            time.sleep(1.5) 
                            
                            # LIMP MODE: Force 320x240 to save USB bandwidth on Pi Zero
                            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            
                            # Warm-up: Discard enough frames for AGC/AEC to fully converge.
                            # The Redragon/Sonix sensor needs ~25 frames (~1s at 30fps) to
                            # stabilize auto-exposure after opening. Fewer frames = overexposed captures.
                            for _ in range(25):
                                cap.grab()
                            
                            # Test if we can actually read a valid frame
                            success, frame = cap.read()
                            if success and frame is not None:
                                logger.info(f"[SUCCESS] Camera {idx} is UP at 320x240.")
                                self.camera_index = idx 
                                self.shared_camera = cap
                                return cap
                            else:
                                # Falling back to raw format if MJPEG failed
                                logger.warning(f"[RETRY] MJPEG failed on index {idx}, trying YUYV...")
                                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
                                success, frame = cap.read()
                                if success:
                                    logger.info(f"[SUCCESS] Camera {idx} is UP (YUYV fallback).")
                                    self.shared_camera = cap
                                    return cap
                                
                                logger.warning(f"[FAIL] Camera {idx} opened but failed to read frame.")
                                cap.release()
                        else:
                            # Faster fail if device won't even open
                            pass 
                    except Exception as e:
                        logger.warning(f"Error opening camera {idx}: {e}")
            
            # USB Recovery Sleep: Only if we haven't given up yet
            if attempt < max_attempts - 1:
                time.sleep(2.0)
        
        # Mark failure time to trigger cooldown
        self.last_fail_time = time.time()
        return None
                
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
                
            # Flush stale frames from the buffer before the real capture.
            # Even after _get_camera() warmup, OpenCV buffers up to BUFFERSIZE frames.
            # Reading immediately can yield an old (overexposed) frame from the warmup phase.
            # We grab-and-discard to force a fresh frame from the sensor.
            flush_count = 15 if release_needed else 3
            for _ in range(flush_count):
                camera.grab()
                
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
