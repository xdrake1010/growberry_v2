import subprocess
import cv2
import os
import time
import logging
import threading
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
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
        self._probing = False   # Prevents concurrent probes (race condition guard)
        self.flip_mode = 'none' # Persisted flip: none | h | v | both

    def set_cosecha_name(self, name):
        self.cosecha_name = name
        logger.info(f"Camera controller harvest name updated to: {name}")

    def set_flip(self, mode):
        """Sets the persistent flip mode applied to both live stream and timelapse captures."""
        valid = ('none', 'h', 'v', 'both')
        self.flip_mode = mode if mode in valid else 'none'
        logger.info(f"Camera flip mode set to: {self.flip_mode}")

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

    def _get_camera(self, width=320, height=240):
        """Attempts to open the camera with preferred backends and settings.
        Includes a retry loop to handle transient USB disconnects (EMI).
        Expects self.lock to be held by caller.
        """
        # If already opened at the REQUESTED resolution, return it
        if self.shared_camera is not None:
             try:
                 if self.shared_camera.isOpened():
                     current_w = self.shared_camera.get(cv2.CAP_PROP_FRAME_WIDTH)
                     current_h = self.shared_camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
                     if int(current_w) == width and int(current_h) == height:
                         return self.shared_camera
                     else:
                         # Resolution mismatch, need to re-open
                         logger.info(f"[RES-CHANGE] Switching from {current_w}x{current_h} to {width}x{height}")
                         self.shared_camera.release()
                         self.shared_camera = None
             except:
                 self.shared_camera = None
        
        # FAIL FAST: If we failed very recently, don't even try and block the thread
        cooldown_period = 60 # seconds
        time_since_fail = time.time() - self.last_fail_time
        if time_since_fail < cooldown_period:
            logger.info(f"[IDLE] Camera is in cooldown ({int(cooldown_period - time_since_fail)}s remaining).")
            return None

        # RACE CONDITION GUARD: Only one thread may probe the camera at a time.
        # If another thread is already probing, wait briefly then check if camera is ready.
        if self._probing:
            logger.info("[PROBE] Another thread is already probing. Waiting...")
            for _ in range(20):  # Wait up to 20s
                time.sleep(1)
                if self.shared_camera is not None:
                    return self.shared_camera
                if not self._probing:
                    break
            return self.shared_camera  # May be None if still failed

        self._probing = True
        try:
            # First, ensure the uvcvideo kernel module is healthy
            self._ensure_uvcvideo_driver()

            # Always probe at low resolution first (YUYV @ 640x480 can timeout on USB)
            # then set the requested resolution after confirming the camera works.
            PROBE_W, PROBE_H = 320, 240

            max_attempts = 2
            for attempt in range(max_attempts):
                indices_to_try = [0, 1] if self.camera_index not in [0, 1] else [self.camera_index, 1 - self.camera_index]

                for idx in indices_to_try:
                    try:
                        logger.info(f"[PROBE] Trying index {idx} at {PROBE_W}x{PROBE_H} (YUYV)")
                        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                        if not cap.isOpened():
                            logger.info(f"[PROBE] Cannot open camera index {idx}.")
                            continue

                        time.sleep(0.5)

                        # IMPORTANT: This camera (IMC Networks 13d3:5120) only supports YUYV, NOT MJPG.
                        # Setting MJPG causes immediate select() timeouts. Use YUYV.
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, PROBE_W)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, PROBE_H)
                        cap.set(cv2.CAP_PROP_FPS, 10)  # Conservative FPS for YUYV on Pi
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                        # Warm-up flush
                        for _ in range(3):
                            cap.grab()

                        success, frame = cap.read()
                        if success and frame is not None:
                            # Now switch to requested resolution if different
                            if width != PROBE_W or height != PROBE_H:
                                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                                for _ in range(3): cap.grab()  # flush after resize

                            actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                            actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                            logger.info(f"[SUCCESS] Camera {idx} is UP at {actual_w}x{actual_h} (YUYV).")
                            self.camera_index = idx
                            self.shared_camera = cap
                            return cap
                        else:
                            logger.warning(f"[PROBE] Camera {idx} opened but failed to read frame.")
                            cap.release()
                    except Exception as e:
                        logger.warning(f"Error opening camera {idx}: {e}")

                if attempt < max_attempts - 1:
                    logger.info(f"[RETRY] Attempt {attempt+1} failed, retrying in 2s...")
                    time.sleep(2.0)

            self.last_fail_time = time.time()
            self._reset_usb()
            return None
        finally:
            self._probing = False

    def _ensure_uvcvideo_driver(self):
        """Ensures the uvcvideo kernel module is loaded and /dev/video0 exists.
        This recovers from the driver being deregistered (e.g. after USB errors).
        """
        try:
            has_video0 = os.path.exists('/dev/video0')
            if not has_video0:
                logger.warning("[SYSTEM] /dev/video0 missing — reloading uvcvideo driver...")
                subprocess.run(['sudo', 'modprobe', '-r', 'uvcvideo'], timeout=5)
                time.sleep(1)
                subprocess.run(['sudo', 'modprobe', 'uvcvideo'], timeout=5)
                time.sleep(2)
                if os.path.exists('/dev/video0'):
                    logger.info("[SYSTEM] uvcvideo reloaded successfully — /dev/video0 is back.")
                else:
                    logger.error("[SYSTEM] /dev/video0 still missing after driver reload.")
        except Exception as e:
            logger.error(f"[SYSTEM] Failed to reload uvcvideo: {e}")

    def _reset_usb(self):
        """Triggers system-level USB reset for the camera."""
        script_path = os.path.join(os.path.dirname(__file__), "usb_reset.sh")
        if os.path.exists(script_path):
            try:
                logger.warning("[SYSTEM] Camera protocol error. Resetting USB bus...")
                subprocess.run(["sudo", script_path], check=True, timeout=15)
                time.sleep(3) # Wait for re-enumeration
            except Exception as e:
                logger.error(f"Failed to reset USB: {e}")
        else:
            logger.error(f"Reset script not found: {script_path}")
                
        return None

    def _draw_metadata_overlay(self, frame, metadata):
        """Draws a professional HD legend at the bottom using PIL for high-quality anti-aliased text."""
        try:
            h, w = frame.shape[:2]
            
            # 1. Convert OpenCV BGR to PIL RGB
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img, "RGBA")
            
            # 2. Draw Bottom Bar - Matte Dark Gray
            bar_height = int(h * 0.08)
            # Use a slightly transparent solid bar for a more premium look
            draw.rectangle([0, h - bar_height, w, h], fill=(30, 33, 39, 200)) # Dark charcoal
            
            # 3. Text setup - Using OpenSans-Bold for maximum clarity
            font_path = "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf"
            if not os.path.exists(font_path):
                # Fallback to a standard font if OpenSans is missing
                font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            
            # Calculate font size based on height
            font_size = max(12, int(h / 20))
            try:
                font = ImageFont.truetype(font_path, font_size)
            except:
                font = ImageFont.load_default()

            # 4. Prepare Content
            harvest_name = metadata.get("harvest", self.cosecha_name).upper()
            temp = f"{metadata.get('temp', '--')}C"
            hum = f"{metadata.get('hum', '--')}%"
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            start_date_str = metadata.get("start_date")
            day_text = ""
            if start_date_str:
                try:
                    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                    diff_days = (datetime.now() - start_dt).days + 1
                    day_text = f" | DAY {max(1, diff_days)}"
                except: pass

            brand_text = f"GROWBERRY | {harvest_name}{day_text}"
            stats_str = f"{temp} | {hum} | {time_str}"
            
            if w < 600:
                # 2 lines for Limp Mode (320x240)
                bar_height = int(h * 0.16)
                draw.rectangle([0, h - bar_height, w, h], fill=(30, 33, 39, 200)) # Dark charcoal
                
                text_y_top = h - bar_height + (bar_height // 4) - (font_size // 2)
                text_y_bot = h - (bar_height // 4) - (font_size // 2)
                
                try:
                    tw_brand = draw.textbbox((0, 0), brand_text, font=font)[2]
                    tw_stats = draw.textbbox((0, 0), stats_str, font=font)[2]
                except:
                    tw_brand = draw.textsize(brand_text, font=font)[0]
                    tw_stats = draw.textsize(stats_str, font=font)[0]
                
                draw.text(((w - tw_brand)//2, text_y_top), brand_text, font=font, fill=(255, 255, 255, 255))
                draw.text(((w - tw_stats)//2, text_y_bot), stats_str, font=font, fill=(255, 255, 255, 255))
            else:
                # Standard 1 line for HD (720p+)
                bar_height = int(h * 0.08)
                draw.rectangle([0, h - bar_height, w, h], fill=(30, 33, 39, 200)) # Dark charcoal
                
                text_y = h - (bar_height // 2) - (font_size // 2) - 2
                draw.text((20, text_y), brand_text, font=font, fill=(255, 255, 255, 255))
                
                try:
                    tw = draw.textbbox((0, 0), stats_str, font=font)[2]
                except:
                    tw = draw.textsize(stats_str, font=font)[0]
                    
                draw.text((w - tw - 20, text_y), stats_str, font=font, fill=(255, 255, 255, 255))
            
            # 6. Convert back to OpenCV BGR
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            
        except Exception as e:
            logger.error(f"Error drawing HD overlay: {e}")
            return frame

    def capture_timelapse_frame(self, metadata=None):
        """Captures a single frame and saves a clean JPEG (no overlay).
        The overlay is burned by FFmpeg at export time for full HD quality."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%H%M%S")
        
        target_dir = os.path.join(TIMELAPSE_BASE_DIR, self.cosecha_name, today_str)
        self._ensure_dir(target_dir)
        
        filename = f"{timestamp}.jpg"
        filepath = os.path.join(target_dir, filename)

        logger.info(f"Capturing timelapse frame: {filename}")
        
        release_needed = False
        
        try:
            # Parse requested resolution from metadata, default 640x480
            res_str = metadata.get("resolution", "640x480") if metadata else "640x480"
            w, h = map(int, res_str.split('x'))
            
            with self.lock:
                camera = self._get_camera(width=w, height=h)
                release_needed = False
            
            if camera is None:
                logger.error("Could not find or open any camera for timelapse")
                return False
                
            # Flush stale buffer frames before capture
            flush_count = 15 if release_needed else 3
            for _ in range(flush_count):
                camera.grab()
                
            success, frame = camera.read()

            if success:
                # Apply flip if configured (same setting as live stream)
                FLIP_CODES = {'h': 1, 'v': 0, 'both': -1}
                flip_code = FLIP_CODES.get(self.flip_mode)
                if flip_code is not None:
                    frame = cv2.flip(frame, flip_code)

                # Save clean frame — overlay is burned by FFmpeg at export time
                cv2.imwrite(filepath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                logger.info(f"Saved clean timelapse frame: {filepath}")
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

    def generate_live_stream(self, width=640, height=480, flip='none'):
        """Generator for the MJPEG stream. Accepts resolution and flip params.
        flip: 'none' | 'h' (horizontal) | 'v' (vertical) | 'both'
        """
        # Map flip mode to cv2.flip() flipCode
        FLIP_CODES = {'h': 1, 'v': 0, 'both': -1}
        flip_code = FLIP_CODES.get(flip, None)  # None = no flip
        with self.lock:
            self.client_count += 1
            self.is_streaming = True
            logger.info(f"Client connected at {width}x{height}. Total: {self.client_count}")
        
        try:
            with self.lock:
                camera = self._get_camera(width=width, height=height)
            
            if camera is None:
                logger.error("Could not find or open any camera for streaming")
                yield (b'--frame\r\n'
                       b'Content-Type: text/plain\r\n\r\n' + b'Camera Unavailable' + b'\r\n')
                return

            retry_count = 0
            while self.is_streaming:
                with self.lock:
                    if self.shared_camera is None or not self.shared_camera.isOpened():
                        break
                    success, frame = self.shared_camera.read()
                
                if not success:
                    logger.warning(f"Failed to read stream frame (retry {retry_count}/5)")
                    retry_count += 1
                    if retry_count > 5:
                        break
                    time.sleep(0.5)
                    continue
                
                retry_count = 0

                # Apply flip transform if requested
                if flip_code is not None:
                    frame = cv2.flip(frame, flip_code)

                # Compress for web — heavier at higher res to balance bandwidth
                quality = 60 if width >= 1280 else 55
                ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                # Cap FPS: ~5fps at HD, ~10fps at SD to save CPU on Pi Zero
                time.sleep(0.2 if width >= 1280 else 0.1)
        except Exception as e:
            logger.error(f"Error in live stream generator: {e}")
        finally:
            with self.lock:
                self.client_count -= 1
                logger.info(f"Client disconnected. Remaining: {self.client_count}")
                if self.client_count <= 0:
                    self.client_count = 0
                    self.is_streaming = False
                    if self.shared_camera:
                        logger.info("Closing shared camera handle.")
                        self.shared_camera.release()
                        self.shared_camera = None
