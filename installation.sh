#!/bin/bash

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

# Get the actual desktop user
ACTUAL_USER=$(who | awk '{print $1}' | head -n 1)
if [ -z "$ACTUAL_USER" ]; then
    ACTUAL_USER=$SUDO_USER
fi

if [ -z "$ACTUAL_USER" ]; then
    echo "Could not determine the desktop user"
    exit 1
fi

echo "Installing for desktop user: $ACTUAL_USER"

echo "Cleaning prior installation..."

systemctl stop dictation 2>/dev/null
systemctl disable dictation 2>/dev/null
systemctl stop dictation_tray 2>/dev/null
systemctl disable dictation_tray 2>/dev/null

rm -f /usr/local/bin/dictation_daemon.py
rm -f /usr/local/bin/dictation_client.py
rm -f /usr/local/bin/dictation_tray_daemon.py
rm -f /usr/local/bin/dictation.sh
rm -f /etc/systemd/system/dictation.service
rm -f /etc/systemd/system/dictation_tray.service

# Create virtual environment
VENV_PATH="/opt/dictation_venv"
python3 -m venv "$VENV_PATH"

# Set permissions for the virtual environment
chown -R $ACTUAL_USER:$ACTUAL_USER "$VENV_PATH"

# Install required python packages
sudo -u $ACTUAL_USER "$VENV_PATH/bin/pip" install openai-whisper sounddevice numpy torch scipy pystray Pillow

# Place files
cp ./src/dictation_daemon.py /usr/local/bin/
cp ./src/dictation_tray_daemon.py /usr/local/bin/
cp ./src/dictation_client.py /usr/local/bin/
cp ./src/dictation.sh /usr/local/bin/
cp ./red-circle.png /usr/local/bin/
cp ./grey-circle.png /usr/local/bin/

# Set executable permissions
chmod +x /usr/local/bin/dictation_daemon.py
chmod +x /usr/local/bin/dictation_tray_daemon.py
chmod +x /usr/local/bin/dictation_client.py
chmod +x /usr/local/bin/dictation.sh

# Set proper permissions for icons
chmod 644 /usr/local/bin/red-circle.png
chmod 644 /usr/local/bin/grey-circle.png
chown $ACTUAL_USER:$ACTUAL_USER /usr/local/bin/red-circle.png
chown $ACTUAL_USER:$ACTUAL_USER /usr/local/bin/grey-circle.png

# Set up working dir for models
mkdir -p /var/cache/whisper
chmod 755 /var/cache/whisper
chown $ACTUAL_USER:$ACTUAL_USER /var/cache/whisper

# Make sure the socket directory is accessible
chmod 1777 /tmp

# Install systemd services
cat > /etc/systemd/system/dictation.service << EOL
[Unit]
Description=Dictation Service
After=network.target

[Service]
ExecStart=$VENV_PATH/bin/python /usr/local/bin/dictation_daemon.py
Environment=HOME=/root
Environment=XDG_CACHE_HOME=/var/cache/whisper
User=root
Group=root
Restart=always
RestartSec=3
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
EOL

cat > /etc/systemd/system/dictation_tray.service << EOL
[Unit]
Description=Dictation Tray Service
After=graphical-session.target

[Service]
Type=simple
ExecStart=$VENV_PATH/bin/python /usr/local/bin/dictation_tray_daemon.py
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$ACTUAL_USER/.Xauthority
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER)
User=$ACTUAL_USER
Group=$ACTUAL_USER
Restart=always
RestartSec=3
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=graphical-session.target
EOL

# Set permissions for service files
chmod 644 /etc/systemd/system/dictation.service
chmod 644 /etc/systemd/system/dictation_tray.service

# Register and run the services
echo "Enabling and starting dictation services..."
systemctl daemon-reload
systemctl enable dictation
systemctl start dictation
systemctl enable dictation_tray
systemctl start dictation_tray

echo "Installation complete. Check status with 'systemctl status dictation' and 'systemctl status dictation_tray'"
echo "If the tray icon doesn't appear, you may need to log out and back in, or restart the dictation_tray service."
