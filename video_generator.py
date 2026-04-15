import os
import subprocess
import logging
import threading
from datetime import datetime
from config import TIMELAPSE_BASE_DIR, BASE_DIR

logger = logging.getLogger("Growberry.Video")

EXPORTS_DIR = os.path.join(BASE_DIR, "data", "exports")

# Allowed resolutions for export
RESOLUTIONS = {
    "480p":  (854, 480),
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
}

# Font for FFmpeg drawtext overlay — DejaVuSans-Bold is available on Raspberry Pi OS
OVERLAY_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def _escape_ffmpeg_text(text):
    """Escape special characters for FFmpeg drawtext filter."""
    return text.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")


class VideoGenerator:
    def __init__(self):
        if not os.path.exists(EXPORTS_DIR):
            os.makedirs(EXPORTS_DIR, exist_ok=True)
        self.is_exporting = False
        self.current_job = None
        self.progress = 0          # 0–100
        self.progress_status = ""  # human-readable status

    def export_cosecha(self, cosecha_name, fps=10, date_from=None, date_to=None, resolution="720p"):
        """Starts an async export. resolution: '480p', '720p', or '1080p'."""
        if self.is_exporting:
            return False, "Export already in progress."
        thread = threading.Thread(
            target=self._run_export,
            args=(cosecha_name, fps, date_from, date_to, resolution),
            daemon=True
        )
        thread.start()
        return True, "Export started."

    def get_export_status(self):
        return {
            "is_exporting": self.is_exporting,
            "current_job": self.current_job,
            "progress": self.progress,
            "status": self.progress_status,
        }

    def _build_overlay_filter(self, res_w, res_h, brand_text, stats_text):
        """Build FFmpeg drawtext filter chain for HD overlay burned at export time."""
        font = OVERLAY_FONT
        # Font size relative to output height — legible at 480p through 1080p
        font_size = max(20, res_h // 28)
        box_h = font_size + 24  # padding
        y_pos = f"h-{box_h + 8}"

        brand_esc = _escape_ffmpeg_text(brand_text)
        stats_esc = _escape_ffmpeg_text(stats_text)

        # Left side — brand + harvest + day
        left = (
            f"drawtext=fontfile='{font}'"
            f":text='{brand_esc}'"
            f":fontsize={font_size}"
            f":fontcolor=white"
            f":x=20"
            f":y={y_pos}"
            f":box=1:boxcolor=0x1E2127CC:boxborderw=10"
        )

        # Right side — date/time
        right = (
            f"drawtext=fontfile='{font}'"
            f":text='{stats_esc}'"
            f":fontsize={font_size}"
            f":fontcolor=white"
            f":x=w-tw-20"
            f":y={y_pos}"
            f":box=1:boxcolor=0x1E2127CC:boxborderw=10"
        )

        return f"{left},{right}"

    def _run_export(self, cosecha_name, fps, date_from, date_to, resolution):
        self.is_exporting = True
        self.current_job = cosecha_name
        self.progress = 0
        self.progress_status = "Collecting frames..."

        try:
            fps = float(fps)
            res_w, res_h = RESOLUTIONS.get(resolution, (1280, 720))

            cosecha_path = os.path.join(TIMELAPSE_BASE_DIR, cosecha_name)
            if not os.path.exists(cosecha_path):
                logger.error(f"Harvest folder not found: {cosecha_name}")
                self.progress_status = "Error: harvest folder not found."
                return

            # Collect images within date range
            all_images = []
            date_folders = sorted([
                d for d in os.listdir(cosecha_path)
                if os.path.isdir(os.path.join(cosecha_path, d))
            ])
            for date_folder in date_folders:
                if date_from and date_folder < date_from:
                    continue
                if date_to and date_folder > date_to:
                    continue
                date_path = os.path.join(cosecha_path, date_folder)
                for file in sorted(os.listdir(date_path)):
                    if file.lower().endswith(('.jpg', '.jpeg')):
                        all_images.append(os.path.join(date_path, file))

            if not all_images:
                logger.error(f"No images for {cosecha_name} in range.")
                self.progress_status = "Error: no frames found."
                return

            total = len(all_images)
            logger.info(f"Exporting {total} frames @ {fps}fps → {res_w}x{res_h} [{resolution}]")
            self.progress_status = f"Building manifest ({total} frames)..."
            self.progress = 5

            # Build ffmpeg concat manifest
            manifest_path = os.path.join(EXPORTS_DIR, f"{cosecha_name}_manifest.txt")
            frame_duration = 1.0 / fps
            with open(manifest_path, 'w') as f:
                for img in all_images:
                    f.write(f"file '{img}'\n")
                    f.write(f"duration {frame_duration}\n")

            range_suffix = (
                f"_{date_from.replace('-','')}_to_{date_to.replace('-','')}"
                if date_from and date_to else ""
            )
            output_filename = f"{cosecha_name}{range_suffix}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"
            output_path = os.path.join(EXPORTS_DIR, output_filename)

            self.progress = 10
            self.progress_status = f"Encoding {total} frames → {res_w}x{res_h} {resolution}..."

            # ── Compute overlay text ──────────────────────────────────────────
            brand_text = f"GROWBERRY | {cosecha_name.upper()}"

            # Compute day number from date_from (or first image date)
            start_date_str = date_from or (date_folders[0] if date_folders else None)
            if start_date_str:
                try:
                    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                    # Day range: Day N → Day M
                    if date_from and date_to:
                        end_dt = datetime.strptime(date_to, "%Y-%m-%d")
                        day_start = max(1, (start_dt - datetime.strptime(start_date_str, "%Y-%m-%d")).days + 1) if date_from else 1
                        day_end = max(1, (end_dt - start_dt).days + 1)
                        brand_text += f" | DAY 1-{day_end}"
                except Exception:
                    pass

            export_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            stats_text = f"{total} frames | {fps:.0f}fps | {export_date}"

            # ── FFmpeg filter chain ───────────────────────────────────────────
            # Scale with letterbox + burn HD overlay at output resolution
            scale_pad = (
                f"scale={res_w}:{res_h}:force_original_aspect_ratio=decrease,"
                f"pad={res_w}:{res_h}:(ow-iw)/2:(oh-ih)/2:black"
            )
            overlay = self._build_overlay_filter(res_w, res_h, brand_text, stats_text)
            vf = f"{scale_pad},{overlay},format=yuv420p"

            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0',
                '-i', manifest_path,
                '-vf', vf,
                '-vcodec', 'libx264', '-preset', 'ultrafast',
                '-movflags', '+faststart',
                '-r', str(fps),
                output_path
            ]

            logger.info(f"FFmpeg: {' '.join(cmd)}")

            # Run and track progress via stderr
            proc = subprocess.Popen(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                text=True, bufsize=1
            )
            for line in proc.stderr:
                if 'frame=' in line:
                    try:
                        fc = int(line.split('frame=')[1].split()[0])
                        pct = min(10 + int((fc / total) * 85), 95)
                        self.progress = pct
                        self.progress_status = f"Encoding frame {fc}/{total}..."
                    except Exception:
                        pass

            proc.wait()

            if os.path.exists(manifest_path):
                os.remove(manifest_path)

            if proc.returncode == 0:
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(f"Export OK: {output_path} ({size_mb:.1f} MB)")
                self.progress = 100
                self.progress_status = f"Done! {output_filename} ({size_mb:.1f} MB)"
            else:
                logger.error("FFmpeg failed — check logs for drawtext/font errors.")
                self.progress_status = "Error: FFmpeg encoding failed."

        except Exception as e:
            logger.error(f"Export error: {e}")
            self.progress_status = f"Error: {e}"
        finally:
            self.is_exporting = False
            self.current_job = None

    def delete_video(self, filename):
        try:
            target_path = os.path.abspath(os.path.join(EXPORTS_DIR, filename))
            if not target_path.startswith(os.path.abspath(EXPORTS_DIR)):
                return False, "Unauthorized path"
            if os.path.exists(target_path):
                os.remove(target_path)
                return True, "Video deleted"
            return False, "File not found"
        except Exception as e:
            logger.error(f"Delete video failed: {e}")
            return False, str(e)

    def list_exports(self):
        """Lists all MP4 exports. Parses harvest name from filename prefix."""
        if not os.path.exists(EXPORTS_DIR):
            return []
        files = []
        for file in sorted(os.listdir(EXPORTS_DIR), reverse=True):
            if not file.endswith(".mp4"):
                continue
            stats = os.stat(os.path.join(EXPORTS_DIR, file))
            # Filename pattern: HarvestName_daterange_timestamp.mp4
            # Extract harvest = everything before the first date segment (8 digits)
            harvest = file.split('.')[0]  # strip .mp4
            # Find first underscore-separated segment that looks like a date (8 digits)
            parts = harvest.split('_')
            harvest_parts = []
            for part in parts:
                if part.isdigit() and len(part) == 8:
                    break
                harvest_parts.append(part)
            harvest_name = "_".join(harvest_parts) if harvest_parts else harvest

            files.append({
                "name": file,
                "harvest": harvest_name,
                "size": f"{stats.st_size / (1024*1024):.1f} MB",
                "date": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
            })
        return files
