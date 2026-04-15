"""
routes_system.py — System management routes (WiFi, OTA updates)
All routes registered under /api/system via blueprint.
"""
import subprocess
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger("Growberry.System")

system_bp = Blueprint('system', __name__)


def _run(cmd, timeout=12):
    """Run a shell command, return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", -1
    except Exception as e:
        return "", str(e), -1


# ──────────────────────────────────────────────────────────────────────────────
# WiFi Status
# ──────────────────────────────────────────────────────────────────────────────

@system_bp.route('/wifi/status', methods=['GET'])
def wifi_status():
    """Returns current WiFi connection info."""
    try:
        # Get active connection
        out, _, rc = _run("nmcli -t -f NAME,TYPE,DEVICE,STATE con show --active")
        wifi_con = None
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 4 and "wireless" in parts[1]:
                wifi_con = parts[0]
                break

        # Get interface details
        out2, _, _ = _run("nmcli -t -f GENERAL.CONNECTION,IP4.ADDRESS,WIFI-PROPERTIES.STRENGTH dev show wlan0")
        ssid = None
        ip = None
        signal = 0
        for line in out2.splitlines():
            if line.startswith("GENERAL.CONNECTION:"):
                ssid = line.split(":", 1)[1].strip() or wifi_con
            elif line.startswith("IP4.ADDRESS"):
                ip = line.split(":", 1)[1].strip().split("/")[0]
            elif line.startswith("WIFI-PROPERTIES.STRENGTH:"):
                try:
                    signal = int(line.split(":", 1)[1].strip())
                except ValueError:
                    signal = 0

        # Fallback: get SSID from iwconfig if nmcli doesn't have it
        if not ssid or ssid == "--":
            out3, _, _ = _run("iwconfig wlan0 2>/dev/null | grep 'ESSID'")
            if "ESSID:" in out3:
                try:
                    ssid = out3.split('ESSID:"')[1].split('"')[0]
                except Exception:
                    ssid = None

        connected = bool(ssid and ssid != "--" and ip)
        return jsonify({
            "connected": connected,
            "ssid": ssid if connected else None,
            "ip": ip,
            "signal": signal,
        })
    except Exception as e:
        logger.error(f"wifi_status error: {e}")
        return jsonify({"connected": False, "ssid": None, "ip": None, "signal": 0, "error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# WiFi Scan
# ──────────────────────────────────────────────────────────────────────────────

@system_bp.route('/wifi/scan', methods=['GET'])
def wifi_scan():
    """Returns list of visible WiFi networks."""
    try:
        # Force rescan (may take ~3s)
        _run("nmcli dev wifi rescan ifname wlan0", timeout=6)
        out, _, _ = _run(
            "nmcli -t -f SSID,SIGNAL,SECURITY,IN-USE dev wifi list ifname wlan0"
        )
        networks = []
        seen = set()
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            try:
                signal = int(parts[1].strip())
            except ValueError:
                signal = 0
            security = parts[2].strip()
            in_use = parts[3].strip() == "*"
            networks.append({
                "ssid": ssid,
                "signal": signal,
                "security": security if security else "Open",
                "in_use": in_use,
            })
        # Sort: current first, then by signal strength
        networks.sort(key=lambda n: (not n["in_use"], -n["signal"]))
        return jsonify(networks)
    except Exception as e:
        logger.error(f"wifi_scan error: {e}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# WiFi Connect
# ──────────────────────────────────────────────────────────────────────────────

@system_bp.route('/wifi/connect', methods=['POST'])
def wifi_connect():
    """Connect to a WiFi network. Body: {ssid, password}."""
    data = request.get_json() or {}
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "").strip()

    if not ssid:
        return jsonify({"status": "error", "message": "SSID is required"}), 400

    # Sanitize: prevent shell injection
    ssid_safe = ssid.replace("'", "\\'")

    if password:
        password_safe = password.replace("'", "\\'")
        cmd = f"nmcli dev wifi connect '{ssid_safe}' password '{password_safe}' ifname wlan0"
    else:
        cmd = f"nmcli dev wifi connect '{ssid_safe}' ifname wlan0"

    logger.info(f"Connecting to WiFi: {ssid}")
    out, err, rc = _run(cmd, timeout=30)

    if rc == 0:
        return jsonify({"status": "success", "message": f"Connected to {ssid}"})
    else:
        logger.error(f"WiFi connect failed: {err}")
        return jsonify({"status": "error", "message": err or "Connection failed"}), 500


# ──────────────────────────────────────────────────────────────────────────────
# WiFi Forget
# ──────────────────────────────────────────────────────────────────────────────

@system_bp.route('/wifi/forget', methods=['POST'])
def wifi_forget():
    """Forget (delete) a saved WiFi connection. Body: {ssid}."""
    data = request.get_json() or {}
    ssid = data.get("ssid", "").strip()
    if not ssid:
        return jsonify({"status": "error", "message": "SSID required"}), 400

    ssid_safe = ssid.replace("'", "\\'")
    out, err, rc = _run(f"nmcli con delete '{ssid_safe}'", timeout=10)
    if rc == 0:
        return jsonify({"status": "success", "message": f"Forgot {ssid}"})
    else:
        return jsonify({"status": "error", "message": err or "Failed to forget network"}), 500
