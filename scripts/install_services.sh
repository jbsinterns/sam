#!/bin/bash
# ==============================================================================
# SAM Rover - Automated Installer for Ubuntu 24.04/26.04 on Raspberry Pi
# Sets up systemd service, auto-boot, and Wi-Fi fallback timer.
# ==============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (e.g. sudo bash install_services.sh)"
  exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")

echo "[1/4] Installing Python system dependencies..."
apt-get update
apt-get install -y python3-pip python3-yaml python3-opencv network-manager

echo "[2/4] Installing Python requirements..."
pip3 install -r "${REPO_DIR}/requirements.txt" || true

echo "[3/4] Configuring systemd service for SAM..."
cp "${SCRIPT_DIR}/sam.service" /etc/systemd/system/sam.service
# Replace working directory with actual repo directory
sed -i "s|/home/ubuntu/raspberry|${REPO_DIR}|g" /etc/systemd/system/sam.service

systemctl daemon-reload
systemctl enable sam.service
systemctl restart sam.service

echo "[4/4] Setting up Wi-Fi fallback periodic check..."
chmod +x "${SCRIPT_DIR}/wifi_fallback.sh"
(crontab -l 2>/dev/null | grep -v "wifi_fallback.sh" ; echo "*/1 * * * * ${SCRIPT_DIR}/wifi_fallback.sh >/dev/null 2>&1") | crontab -

echo "=========================================================="
echo " SAM Rover Installation Complete!"
echo " Web Server running at: http://$(hostname -I | cut -d' ' -f1):8000"
echo " Service Status: sudo systemctl status sam.service"
echo "=========================================================="
