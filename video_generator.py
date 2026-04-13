import os
import subprocess
import logging
import threading
from datetime import datetime
from config import TIMELAPSE_BASE_DIR, BASE_DIR

logger = logging.getLogger("Growberry.Video")

EXPORTS_DIR = os.path.join(BASE_DIR, "data", "exports")

class VideoGenerator:
    def __init__(self):
        if not os.path.exists(EXPORTS_DIR):
            os.makedirs(EXPORTS_DIR, exist_ok=True)
        self.is_exporting = False
        self.current_job = None

    def export_cosecha(self, cosecha_name, fps=10):
        """Starts an asynchronous export job for a specific harvest."""
        if self.is_exporting:
            return False, "An export is already in progress."
        
        thread = threading.Thread(target=self._run_export, args=(cosecha_name, fps))
        thread.start()
        return True, "Export started successfully."

    def _run_export(self, cosecha_name, fps):
        self.is_exporting = True
        self.current_job = cosecha_name
        
        try:
            cosecha_path = os.path.join(TIMELAPSE_BASE_DIR, cosecha_name)
            if not os.path.exists(cosecha_path):
                logger.error(f"Catalog for {cosecha_name} not found.")
                return

            # Collect all jpg images recursively
            all_images = []
            for root, dirs, files in os.walk(cosecha_path):
                for file in sorted(files):
                    if file.lower().endswith(('.jpg', '.jpeg')):
                        all_images.append(os.path.join(root, file))
            
            if not all_images:
                logger.error(f"No images found for {cosecha_name}")
                return

            # Create an ffmpeg manifest file
            manifest_path = os.path.join(EXPORTS_DIR, f"{cosecha_name}_manifest.txt")
            with open(manifest_path, 'w') as f:
                for img in all_images:
                    # FFmpeg concat demuxer needs escaped paths or just simple ones
                    f.write(f"file '{img}'\n")
                    f.write(f"duration {1/fps}\n")

            # Final Output Path
            output_filename = f"{cosecha_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"
            output_path = os.path.join(EXPORTS_DIR, output_filename)

            # FFmpeg Command
            # -f concat: use the manifest
            # -safe 0: allow absolute paths
            # -vcodec libx264: h264 encoding
            # -pix_fmt yuv420p: compatibility for most players
            # -y: overwrite
            cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0', 
                '-i', manifest_path, 
                '-vcodec', 'libx264', '-pix_fmt', 'yuv420p', 
                '-r', str(fps), output_path
            ]
            
            logger.info(f"Running FFmpeg: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Export successful: {output_path}")
            else:
                logger.error(f"FFmpeg error: {result.stderr}")

            # Cleanup manifest
            if os.path.exists(manifest_path):
                os.remove(manifest_path)

        except Exception as e:
            logger.error(f"Export failed: {e}")
        finally:
            self.is_exporting = False
            self.current_job = None

    def list_exports(self):
        """Lists all generated MP4 files in the exports directory."""
        if not os.path.exists(EXPORTS_DIR):
            return []
        
        files = []
        for file in sorted(os.listdir(EXPORTS_DIR), reverse=True):
            if file.endswith(".mp4"):
                stats = os.stat(os.path.join(EXPORTS_DIR, file))
                files.append({
                    "name": file,
                    "size": f"{stats.st_size / (1024*1024):.1f} MB",
                    "date": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
                })
        return files
