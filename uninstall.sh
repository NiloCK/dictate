#!/bin/bash

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

echo "Stopping and disabling services..."
systemctl stop dictation_tray
systemctl disable dictation_tray
systemctl stop dictation
systemctl disable dictation

echo "Removing systemd service files..."
rm -f /etc/systemd/system/dictation.service
rm -f /etc/systemd/system/dictation_tray.service
systemctl daemon-reload

echo "Removing executables and icons..."
rm -f /usr/local/bin/dictation_daemon.py
rm -f /usr/local/bin/dictation_client.py
rm -f /usr/local/bin/dictation_tray_daemon.py
rm -f /usr/local/bin/dictation.sh
rm -f /usr/local/bin/red-circle.png
rm -f /usr/local/bin/grey-circle.png

echo "Removing virtual environment and dependencies..."
rm -rf /opt/dictation_venv

echo "Removing whisper cache and models..."
rm -rf /var/cache/whisper

echo "Removing socket if it exists..."
rm -f /tmp/dictation_tray.sock
rm -f /tmp/dictation.sock

echo "Uninstallation complete"
