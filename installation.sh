#!/bin/bash

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

echo "Cleaning prior installation..."

systemctl stop dictation 2>/dev/null
systemctl disable dictation 2>/dev/null
systemctl stop dictation_tray
systemctl disable dictation_tray

rm -f /usr/local/bin/dictation_daemon.py
rm -f /usr/local/bin/dictation_client.py
rm -f /usr/local/bin/dictation_tray_daemon.py
rm -f /usr/local/bin/dictation.sh
rm -f /etc/systemd/system/dictation.service

# Create virtual environment
VENV_PATH="/opt/dictation_venv"
python3 -m venv "$VENV_PATH"

# Install required python packages
"$VENV_PATH/bin/pip" install openai-whisper sounddevice numpy torch scipy pystray Pillow


# install required linux tools ... ydotool, ... ? (todo)


# place files
cp ./src/dictation_daemon.py /usr/local/bin/
cp ./src/dictation_tray_daemon.py /usr/local/bin/
cp ./src/dictation_client.py /usr/local/bin/
cp ./src/dictation.sh /usr/local/bin/
cp ./red-circle.png /usr/local/bin/
cp ./grey-circle.png /usr/local/bin/

chmod +x /usr/local/bin/dictation_daemon.py
chmod +x /usr/local/bin/dictation_tray_daemon.py
chmod +x /usr/local/bin/dictation_client.py
chmod +x /usr/local/bin/dictation.sh

# set up working dir for models

mkdir -p /var/cache/whisper
chmod 755 /var/cache/whisper

# Install systemd services
cat > /etc/systemd/system/dictation.service << EOL
[Unit]
Description=Dictation Service
After=network.target

[Service]
ExecStart=$VENV_PATH/bin/python /usr/local/bin/dictation_daemon.py
Environment=HOME=/root  # or wherever you want the models to be stored
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
After=network.target

[Service]
ExecStart=$VENV_PATH/bin/python /usr/local/bin/dictation_tray_daemon.py
Environment=HOME=/root
Environment=XDG_CACHE_HOME=/var/cache/whisper
Environment=DISPLAY=:0
Restart=always
RestartSec=3
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
EOL

# register and run the services
echo "Enabling and starting dictation services..."
systemctl daemon-reload
systemctl enable dictation
systemctl start dictation
systemctl enable dictation_tray
systemctl start dictation_tray

echo "Installation complete. Check status with 'systemctl status dictation'"
