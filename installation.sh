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

# Clean user services
if [ -n "$ACTUAL_USER" ]; then
    # Check if user exists and has systemd running
    if id "$ACTUAL_USER" &>/dev/null && \
       [ -d "/run/user/$(id -u $ACTUAL_USER)" ]; then
        sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) \
            systemctl --user stop dictation_tray 2>/dev/null
        sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) \
            systemctl --user disable dictation_tray 2>/dev/null
        # Remove user service file
        rm -f /home/$ACTUAL_USER/.config/systemd/user/dictation_tray.service
    fi
fi

rm -f /usr/local/bin/dictation_daemon.py
rm -f /usr/local/bin/dictation_client.py
rm -f /usr/local/bin/dictation_tray_daemon.py
rm -f /usr/local/bin/dictation.sh
rm -f /usr/local/bin/dictation
rm -f /usr/local/bin/config_manager.py
rm -f /etc/systemd/system/dictation.service
rm -f /etc/systemd/system/dictation_tray.service

# Remove system-level tray service if it exists
systemctl stop dictation_tray 2>/dev/null
systemctl disable dictation_tray 2>/dev/null
rm -f /etc/systemd/system/dictation_tray.service

# Install python3-venv if not already installed
echo "Checking for Python venv package..."
PYTHON_VERSION=$(python3 --version | awk '{print $2}' | cut -d. -f1-2)
if ! dpkg -l | grep -q "python3-venv"; then
    echo "Installing python3-venv package..."
    # Try version-specific package first, then fall back to generic
    if apt-cache show python${PYTHON_VERSION}-venv >/dev/null 2>&1; then
        apt-get update && apt-get install -y python${PYTHON_VERSION}-venv
    else
        apt-get update && apt-get install -y python3-venv
    fi
fi

# Install system dependencies
echo "Installing system dependencies..."
apt-get update && apt-get install -y portaudio19-dev libportaudio2 x11-xserver-utils dbus-x11 python3-xlib ydotool ydotoold

# Create virtual environment
VENV_PATH="/opt/dictation_venv"
echo "Creating Python virtual environment at $VENV_PATH..."
python3 -m venv "$VENV_PATH"

# Set permissions for the virtual environment
chown -R $ACTUAL_USER:$ACTUAL_USER "$VENV_PATH"

# Install required python packages
echo "Installing required Python packages..."
sudo -u $ACTUAL_USER "$VENV_PATH/bin/pip" install --upgrade pip
sudo -u $ACTUAL_USER "$VENV_PATH/bin/pip" install faster-whisper sounddevice numpy torch scipy pystray Pillow pynput

# Place files
cp ./src/dictation_daemon.py /usr/local/bin/
cp ./src/dictation_tray_daemon.py /usr/local/bin/
cp ./src/dictation_client.py /usr/local/bin/
cp ./src/config_manager.py /usr/local/bin/
cp ./src/dictation.sh /usr/local/bin/dictation
cp ./red-circle.png /usr/local/bin/
cp ./grey-circle.png /usr/local/bin/
cp ./hollow-circle.png /usr/local/bin/

# Set executable permissions
chmod +x /usr/local/bin/dictation_daemon.py
chmod +x /usr/local/bin/dictation_tray_daemon.py
chmod +x /usr/local/bin/config_manager.py
chmod +x /usr/local/bin/dictation_client.py
chmod +x /usr/local/bin/dictation

# Create symlinks for legacy/alternative command names
ln -sf /usr/local/bin/dictation /usr/local/bin/dictate
ln -sf /usr/local/bin/dictation /usr/local/bin/dictation.sh

# Set proper permissions for icons
chmod 644 /usr/local/bin/red-circle.png
chmod 644 /usr/local/bin/grey-circle.png
chown $ACTUAL_USER:$ACTUAL_USER /usr/local/bin/red-circle.png
chown $ACTUAL_USER:$ACTUAL_USER /usr/local/bin/grey-circle.png

# Create config directory and set permissions
CONFIG_DIR="/home/$ACTUAL_USER/.config/dictation"
mkdir -p "$CONFIG_DIR"
chown -R $ACTUAL_USER:$ACTUAL_USER "$CONFIG_DIR"

# Create initial config if it doesn't exist
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    cat > "$CONFIG_DIR/config.json" << EOL
{
    "hotkey": "ctrl+alt+d",
    "audio_device": null,
    "model": "base"
}
EOL
    chown $ACTUAL_USER:$ACTUAL_USER "$CONFIG_DIR/config.json"
fi

# Set up working dir for models
mkdir -p /var/cache/whisper
chmod 755 /var/cache/whisper
chown $ACTUAL_USER:$ACTUAL_USER /var/cache/whisper

# Make sure the socket directory is accessible
chmod 1777 /tmp

# Ensure ydotool daemon is running and accessible
echo "Configuring ydotool..."
# Kill any existing user instances to be clean
killall ydotoold 2>/dev/null

# Create a systemd service for ydotoold
cat > /etc/systemd/system/ydotoold.service << EOL
[Unit]
Description=ydotoold - backend for ydotool
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/ydotoold
# Ensure the socket has correct permissions after starting
ExecStartPost=/bin/sh -c 'sleep 1 && chmod 666 /tmp/.ydotool_socket'
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOL

systemctl daemon-reload
systemctl enable ydotoold
systemctl restart ydotoold

# Give it a moment to create the socket
sleep 2

# Set permissions on the ydotool socket again just in case
if [ -e "/tmp/.ydotool_socket" ]; then
    chmod 666 /tmp/.ydotool_socket
    echo "ydotool socket permissions set."
else
    echo "WARNING: ydotool socket not found at /tmp/.ydotool_socket"
fi

# Install systemd services
cat > /etc/systemd/system/dictation.service << EOL
[Unit]
Description=Dictation Service
After=network.target

[Service]
ExecStart=$VENV_PATH/bin/python /usr/local/bin/dictation_daemon.py
Environment=HOME=/root
Environment=XDG_CACHE_HOME=/var/cache/whisper
Environment=XDG_CONFIG_HOME=/home/$ACTUAL_USER/.config
User=root
Group=root
Restart=always
RestartSec=3
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
EOL

# Set up user-level systemd service for the tray
echo "Setting up user-level systemd service for tray icon..."
mkdir -p /home/$ACTUAL_USER/.config/systemd/user/
cat > /home/$ACTUAL_USER/.config/systemd/user/dictation_tray.service << EOL
[Unit]
Description=Dictation Tray Service
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$VENV_PATH/bin/python /usr/local/bin/dictation_tray_daemon.py
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_SESSION_TYPE=wayland
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u $ACTUAL_USER)/bus
Restart=on-failure
RestartSec=3
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=graphical-session.target
EOL

chown -R $ACTUAL_USER:$ACTUAL_USER /home/$ACTUAL_USER/.config/systemd/

# Set permissions for service files
chmod 644 /etc/systemd/system/dictation.service

# Register and run the services
echo "Enabling and starting dictation services..."
systemctl daemon-reload
systemctl enable dictation
systemctl start dictation

loginctl enable-linger $ACTUAL_USER
sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) systemctl --user daemon-reload
sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) systemctl --user enable dictation_tray.service
sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) systemctl --user start dictation_tray.service

# Check if services started successfully
echo "Verifying services..."
if systemctl is-active --quiet dictation; then
    echo "✓ Dictation service started successfully"
else
    echo "✗ Dictation service failed to start"
    echo "Check logs with: journalctl -u dictation"
fi

if sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) systemctl --user is-active --quiet dictation_tray; then
    echo "✓ Dictation tray service started successfully"
else
    echo "✗ Dictation tray service failed to start"
    echo "Check logs with: sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) systemctl --user status dictation_tray"
fi

echo "Installation complete."

if ! systemctl is-active --quiet dictation ||
   ! sudo -u $ACTUAL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $ACTUAL_USER) systemctl --user is-active --quiet dictation_tray; then
    echo "Some services failed to start. Review the errors above and check logs for more details."
fi
