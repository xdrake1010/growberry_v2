#!/bin/bash
# install_ap.sh - Configures hostapd and dnsmasq for Growberry full AP fallback

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install_ap.sh)"
  exit 1
fi

echo "Updating apt and installing dependencies..."
apt-get update
# Prevent services from starting automatically right after installation
systemctl mask hostapd
systemctl mask dnsmasq
DEBIAN_FRONTEND=noninteractive apt-get install -y hostapd dnsmasq iproute2 wget

echo "Stopping services..."
systemctl stop hostapd
systemctl stop dnsmasq
systemctl unmask hostapd
systemctl unmask dnsmasq

# Disable them from starting on boot. Our custom python service will handle them.
systemctl disable hostapd
systemctl disable dnsmasq

# Create configuration backups
[ -f /etc/dnsmasq.conf ] && mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig

echo "Configuring dnsmasq..."
cat > /etc/dnsmasq.d/growberry-ap.conf << 'EOF'
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
# Captive portal redirection
address=/#/192.168.4.1
EOF

echo "Configuring hostapd..."
HOSTNAME=$(hostname)
cat > /etc/hostapd/hostapd.conf << EOF
interface=wlan0
driver=nl80211
ssid=Growberry-${HOSTNAME}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=growberry123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

echo "Configuring default hostapd config path..."
sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|g' /etc/default/hostapd

echo "Installing boot fallback service..."
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

cat > /etc/systemd/system/growberry-net.service << EOF
[Unit]
Description=Growberry Network Fallback Watchdog
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 ${DIR}/boot_net_check.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable growberry-net.service

echo "Done! Run 'sudo systemctl start growberry-net.service' or reboot to test."
