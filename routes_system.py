"""
routes_system.py — System management routes (WiFi, OTA updates)
All routes registered under /api/system via blueprint.
"""
import subprocess
import logging
import net_manager
from flask import Blueprint, jsonify, request

logger = logging.getLogger("Growberry.System")

system_bp = Blueprint('system', __name__)


def _run(cmd, timeout=12, cwd=None):
    """Run a shell command, return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd
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
        # Get SSID and IP from wlan0 device details
        out, _, _ = _run("nmcli -t -f GENERAL.CONNECTION,IP4.ADDRESS dev show wlan0")
        ssid = None
        ip = None
        for line in out.splitlines():
            if line.startswith("GENERAL.CONNECTION:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "--":
                    ssid = val
            elif line.startswith("IP4.ADDRESS"):
                val = line.split(":", 1)[1].strip()
                if val:
                    ip = val.split("/")[0]

        # Get signal strength from scan cache (fast, no rescan)
        signal = 0
        out2, _, _ = _run("nmcli -t -f SSID,SIGNAL dev wifi list ifname wlan0")
        for line in out2.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[0].strip() == ssid:
                try:
                    signal = int(parts[1].strip())
                except ValueError:
                    pass
                break

        connected = bool(ssid and ip)
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


# ──────────────────────────────────────────────────────────────────────────────
# AP Mode Management
# ──────────────────────────────────────────────────────────────────────────────

@system_bp.route('/wifi/ap/status', methods=['GET'])
def ap_status():
    """Check if AP mode is currently active."""
    return jsonify({"ap_active": net_manager.is_ap_active()})

@system_bp.route('/wifi/ap/start', methods=['POST'])
def ap_start():
    """Activate AP Mode manually."""
    success, msg = net_manager.start_ap_mode()
    if success:
        return jsonify({"status": "success", "message": "AP Mode active"})
    else:
        return jsonify({"status": "error", "message": msg}), 500

@system_bp.route('/wifi/ap/stop', methods=['POST'])
def ap_stop():
    """Stop AP Mode and return to WiFi client mode."""
    success, msg = net_manager.stop_ap_mode()
    if success:
        return jsonify({"status": "success", "message": "AP Mode stopped"})
    else:
        return jsonify({"status": "error", "message": msg}), 500

# ──────────────────────────────────────────────────────────────────────────────
# OTA Updates
# ──────────────────────────────────────────────────────────────────────────────

@system_bp.route('/update/version', methods=['GET'])
def get_version():
    """Returns the current git branch and commit hash."""
    repo_dir = "/home/xdrake/growberry_v2"
    branch_out, _, _ = _run("git rev-parse --abbrev-ref HEAD", cwd=repo_dir)
    commit_out, _, _ = _run("git rev-parse --short HEAD", cwd=repo_dir)
    msg_out, _, _ = _run("git log -1 --pretty=%B", cwd=repo_dir)
    
    return jsonify({
        "branch": branch_out or "unknown",
        "commit": commit_out or "unknown",
        "message": msg_out.strip() if msg_out else ""
    })

@system_bp.route('/update/pull', methods=['POST'])
def update_system():
    """Pulls latest changes and schedules a service restart."""
    data = request.get_json() or {}
    branch = data.get("branch", "master").strip()
    repo_dir = "/home/xdrake/growberry_v2"
    
    # 1. Fetch
    out, err, rc = _run("git fetch origin", cwd=repo_dir)
    if rc != 0:
        return jsonify({"status": "error", "message": f"Fetch failed: {err}"}), 500
        
    # 2. Backup user data (db + json configs)
    _run("cp plants_config.json plants_config.json.bak", cwd=repo_dir)
    _run("cp growberry.db growberry.db.bak", cwd=repo_dir)
        
    # 3. Reset hard to the new origin/branch
    out2, err2, rc2 = _run(f"git reset --hard origin/{branch}", cwd=repo_dir)
    if rc2 != 0:
        return jsonify({"status": "error", "message": f"Reset failed: {err2}"}), 500
        
    # 4. Restore user data (since git reset will delete them if they become untracked)
    _run("mv plants_config.json.bak plants_config.json", cwd=repo_dir)
    _run("mv growberry.db.bak growberry.db", cwd=repo_dir)
        
    # 5. Schedule a restart in 2 seconds so this HTTP request has time to return
    # We use nohup to detach it completely.
    try:
        subprocess.Popen(
            "sleep 2 && sudo systemctl restart growberry",
            shell=True,
            start_new_session=True
        )
        return jsonify({
            "status": "success", 
            "message": "Update applied successfully. System is restarting...",
            "details": out2
        })
    except Exception as e:
         return jsonify({"status": "error", "message": f"Updated, but restart failed: {str(e)}"}), 500
