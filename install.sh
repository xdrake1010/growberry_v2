#!/bin/bash

# Configuration
APP_NAME="growberry"
SERVICE_FILE="${APP_NAME}.service"
INSTALL_DIR=$(pwd)
PYTHON_VENV="${INSTALL_DIR}/venv"

echo "--- Growberry Systemd Installation ---"

# 1. Create Virtual Environment if it doesn't exist
if [ ! -d "$PYTHON_VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PYTHON_VENV"
fi

# 2. Install dependencies
echo "Installing dependencies..."
"$PYTHON_VENV/bin/pip" install --upgrade pip
"$PYTHON_VENV/bin/pip" install -r requirements.txt

# 3. Update Service File with Absolute Paths
echo "Configure service file..."
cp "$SERVICE_FILE" "${SERVICE_FILE}.tmp"
sed -i "s|WorkingDirectory=.*|WorkingDirectory=${INSTALL_DIR}|" "${SERVICE_FILE}.tmp"
sed -i "s|ExecStart=.*|ExecStart=${PYTHON_VENV}/bin/python ${INSTALL_DIR}/app.py|" "${SERVICE_FILE}.tmp"

# 4. Install Service
echo "Registering systemd service..."
sudo cp "${SERVICE_FILE}.tmp" "/etc/systemd/system/${SERVICE_FILE}"
rm "${SERVICE_FILE}.tmp"

# 5. Reload and Enable
echo "Starting and enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_FILE"
sudo systemctl restart "$SERVICE_FILE"

echo "------------------------------------------------"
echo "Installing WiFi Watchdog..."
sudo cp wifi_watchdog.sh /usr/local/sbin/growberry_wifi_watchdog.sh
sudo chmod +x /usr/local/sbin/growberry_wifi_watchdog.sh
sudo cp growberry-wifi-watchdog.service /etc/systemd/system/
sudo cp growberry-wifi-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now growberry-wifi-watchdog.timer

echo "------------------------------------------------"
echo "Installation complete!"
echo "Check status with: sudo systemctl status $SERVICE_FILE"
echo "See logs with: journalctl -u $SERVICE_FILE -f"
echo "------------------------------------------------"
