"""
net_manager.py
Handles system-level toggling between NetworkManager (WiFi client) and hostapd (AP mode).
Used by both the web backend (to toggle manually) and the boot watchdog.
"""
import os
import subprocess
import time
import logging

logger = logging.getLogger("Growberry.NetManager")

def _run(cmd):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def is_ap_active():
    """Checks if hostapd is currently running."""
    success, out, _ = _run("systemctl is-active hostapd")
    return success and out == "active"

def start_ap_mode():
    """
    Disconnects from current WiFi, releases wlan0 from NetworkManager,
    sets static IP, starts hostapd and dnsmasq.
    """
    logger.info("Starting AP Mode...")
    
    # Optional: ensure WiFi isn't trying to auto-connect
    _run("nmcli radio wifi off")
    time.sleep(1)
    
    # We must explicitly release wlan0 from wpa_supplicant/NetworkManager so hostapd can bind
    _run("rfkill unblock wlan")
    
    # Kill any holding wpa_supplicant directly just in case nmcli radio didn't clear it
    _run("killall wpa_supplicant")
    
    # Interface up
    _run("ip link set wlan0 up")
    
    # Set static IP for the AP gateway
    _run("ip addr add 192.168.4.1/24 dev wlan0")
    
    # Start AP services
    s1, _, err1 = _run("systemctl start hostapd")
    s2, _, err2 = _run("systemctl start dnsmasq")
    
    if s1:
        logger.info("AP Mode Active (192.168.4.1)")
        return True, "AP started"
    else:
        # Revert IP if failed
        _run("ip addr flush dev wlan0")
        logger.error(f"Failed to start AP: {err1}")
        return False, f"Failed: {err1}"

def stop_ap_mode():
    """
    Stops AP services, flushes static IP, hands wlan0 back to NetworkManager.
    """
    logger.info("Stopping AP Mode, reverting to WiFi Client...")
    
    _run("systemctl stop hostapd")
    _run("systemctl stop dnsmasq")
    
    # Clear static IP
    _run("ip addr flush dev wlan0")
    
    # Restore NM
    _run("nmcli radio wifi on")
    
    # Try connecting to any saved known network
    # NetworkManager will usually auto-connect once radio is on
    time.sleep(2)
    s, out, err = _run("nmcli device connect wlan0")
    
    logger.info("AP Mode stopped.")
    return True, "AP stopped"

def has_wifi_connection():
    """Fast check if we have a valid WiFi IP."""
    s, out, _ = _run("ip -4 addr show wlan0")
    return "inet " in out
