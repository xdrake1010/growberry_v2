#!/usr/bin/env python3
"""
boot_net_check.py
Systemd service entrypoint. Runs on boot.
Waits for WiFi to connect. If no connection after 30 seconds, activates AP mode.
"""
import time
import logging
import sys
import os

# Add parent directory to path so we can import net_manager
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import net_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Growberry.BootCheck")

def main():
    logger.info("Growberry Network Watchdog started.")
    
    # Wait 30 seconds to give NetworkManager time to auto-connect to a known network on boot
    wait_seconds = 30
    logger.info(f"Waiting {wait_seconds}s for WiFi connection...")
    
    for i in range(wait_seconds):
        if net_manager.has_wifi_connection():
            logger.info("WiFi connection detected. System is online. Exiting watchdog.")
            return # Normal operation, exit script successfully
        time.sleep(1)
        
    logger.warning(f"No WiFi connection after {wait_seconds}s. Falling back to AP Mode.")
    success, msg = net_manager.start_ap_mode()
    
    if success:
        logger.info("AP Mode successfully engaged. Watchdog remaining active to prevent service restart loop.")
        # We KEEP the script running infinitely so the systemd service stays "active".
        # If the web UI stops AP mode, it will kill hostapd. We check for that.
        while True:
            time.sleep(10)
            if not net_manager.is_ap_active():
                logger.info("AP Mode is no longer active (disabled by user). Exiting watchdog.")
                break
    else:
        logger.error(f"Failed to engage AP Mode: {msg}")
        sys.exit(1)

if __name__ == "__main__":
    main()
