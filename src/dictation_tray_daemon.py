#!/usr/bin/env python3
# dictation_tray_daemon.py

import socket
import sys
import os
import pystray
from PIL import Image
import threading
import logging
from config_manager import ConfigManager
import subprocess

SOCKET_PATH = '/tmp/dictation_tray.sock'

class TrayService:
    def __init__(self):
        self.icon = None
        self.running = True
        self.config_manager = ConfigManager()

    def show_config_window(self):
        """Launch the configuration dialog"""
        subprocess.run(['dictation', 'config', '--show'])

    def set_model(self, model_name):
        """Change the Whisper model"""
        subprocess.run(['dictation', 'config', '--model', model_name])

    def list_audio_devices(self):
        """Show audio devices dialog"""
        subprocess.run(['dictation', 'config', '--list-devices'])

    def set_audio_device(self, device_id):
        """Set the audio input device"""
        subprocess.run(['dictation', 'config', '--device', str(device_id)])
        # Update config cache and refresh menu to show the new selection
        self.config_manager.load_config()  # Reload config
        self.refresh_menu()

    def get_audio_devices(self):
        """Get list of audio devices from the daemon with fallback"""
        logging.info("Beginning audio device retrieval")
        daemon_socket = '/tmp/dictation.sock'
        logging.info(f"Will attempt to connect to daemon at {daemon_socket}")

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                logging.info("Socket created")
                client.settimeout(2.0)  # Add timeout to avoid hanging
                logging.info("Timeout set to 2.0 seconds")

                try:
                    logging.info(f"Attempting to connect to {daemon_socket}")
                    client.connect(daemon_socket)
                    logging.info("Successfully connected to dictation daemon socket")

                    command = 'LIST_DEVICES'
                    logging.info(f"Sending command: '{command}'")
                    client.send(command.encode('utf-8'))
                    logging.info("Command sent, waiting for response...")

                    response = client.recv(4096).decode('utf-8')
                    logging.info(f"Received response of length: {len(response)} bytes")

                    if response:
                        sample = response[:100] + ('...' if len(response) > 100 else '')
                        logging.info(f"Response sample: {sample}")
                    else:
                        logging.warning("Received empty response from daemon")

                    devices = []
                    logging.info("Beginning to parse device list")
                    for i, line in enumerate(response.splitlines()):
                        logging.debug(f"Processing line {i+1}: {line}")
                        if line.strip():
                            logging.debug(f"Line {i+1} is not empty, checking format")
                            # Extract ID and name
                            if "ID " in line and ":" in line:
                                logging.debug(f"Line {i+1} matches device format")
                                id_part = line.split(":", 1)[0].strip()
                                logging.debug(f"ID part: '{id_part}'")
                                device_id = id_part.replace("ID ", "").strip()
                                logging.debug(f"Extracted device_id string: '{device_id}'")

                                try:
                                    device_id = int(device_id)
                                    logging.debug(f"Converted device_id to int: {device_id}")
                                    is_active = "ACTIVE" in line
                                    logging.debug(f"Device active status: {is_active}")

                                    name_part = line.split(":", 1)[1].split("(")[0].strip()
                                    logging.debug(f"Extracted name: '{name_part}'")

                                    devices.append({
                                        'id': device_id,
                                        'name': name_part,
                                        'is_active': is_active
                                    })
                                    logging.debug(f"Added device {device_id} to list")
                                except ValueError:
                                    logging.warning(f"Could not convert '{device_id}' to integer on line {i+1}")
                                    continue
                            else:
                                logging.debug(f"Line {i+1} does not match device format, skipping")

                    logging.info(f"Successfully parsed {len(devices)} audio devices")
                    return devices

                except socket.timeout as e:
                    logging.warning(f"Connection timed out: {e}")
                    logging.warning("The daemon may be busy or not responding")
                    return []
                except ConnectionRefusedError as e:
                    logging.warning(f"Connection refused: {e}")
                    logging.warning("The dictation daemon may not be running")
                    return []
                except Exception as e:
                    logging.warning(f"Unexpected error during connection: {e}")
                    logging.warning("This could be due to socket permissions or other issues")
                    return []

        except Exception as e:
            logging.error(f"Critical error getting audio devices: {e}", exc_info=True)
            logging.error("This is likely a programming error rather than a connection issue")
            return []


    def refresh_menu(self):
        """Refresh the menu to update device list"""
        if self.icon:
            self.icon.menu = self.create_menu()
            # Force menu update in pystray
            if hasattr(self.icon, '_update_menu'):
                self.icon._update_menu()

    def create_menu(self):
        """Create the system tray context menu with fallback options"""
        try:
            config = self.config_manager.load_config()
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            config = {'model': 'base'}  # Default fallback

        # Create submenu for model selection
        model_menu = pystray.Menu(
            pystray.MenuItem("tiny", lambda: self.set_model("tiny"),
                           checked=lambda item: config.get('model') == "tiny"),
            pystray.MenuItem("base", lambda: self.set_model("base"),
                           checked=lambda item: config.get('model') == "base"),
            pystray.MenuItem("small", lambda: self.set_model("small"),
                           checked=lambda item: config.get('model') == "small"),
            pystray.MenuItem("medium", lambda: self.set_model("medium"),
                           checked=lambda item: config.get('model') == "medium"),
            pystray.MenuItem("large", lambda: self.set_model("large"),
                           checked=lambda item: config.get('model') == "large")
        )



        # Create dynamic submenu for audio devices
        devices = []
        max_retries = 4
        retry_delay = 2

        for attempt in range(max_retries):
            logging.info(f"Attempt {attempt+1}/{max_retries} to get audio devices")
            devices = self.get_audio_devices()
            if devices:
                logging.info(f"Successfully got {len(devices)} audio devices on attempt {attempt+1}")
                break
            else:
                logging.warning(f"No devices found on attempt {attempt+1}")
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                else:
                    logging.error("All attempts to get audio devices failed")


        device_items = []
        current_device_id = config.get('audio_device')

        for device in devices:
            device_id = device['id']
            device_items.append(
                pystray.MenuItem(
                    f"{device['name']} (ID: {device_id})",
                    lambda item, id=device_id: self.set_audio_device(id),
                    checked=lambda item, id=device_id: id == current_device_id or device.get('is_active', False)
                )
            )

        # If no devices found, show a message
        if not device_items:
            device_items.append(pystray.MenuItem("No devices found (daemon not running?)", lambda: None, enabled=False))
            # Add a menu item to refresh and test connection
            device_items.append(pystray.MenuItem("Test daemon connection", lambda: self.test_daemon_connection()))

        device_menu = pystray.Menu(*device_items)

        return pystray.Menu(
            pystray.MenuItem("Configuration", self.show_config_window),
            pystray.MenuItem("Model", model_menu),
            pystray.MenuItem("Audio Devices", device_menu),
            pystray.MenuItem("Refresh Devices", lambda: self.refresh_menu()),
            pystray.MenuItem("Restart Daemon", lambda: self.restart_daemon()),
            pystray.MenuItem("Quit", self.quit_application)
        )


    def quit_application(self):
        """Quit the application"""
        if self.icon:
            self.icon.stop()
        self.running = False
        sys.exit(0)

    def update_icon(self, image_path, tooltip):
        """Common method to update or create the icon"""
        image = Image.open(image_path)
        if self.icon:
            self.icon.icon = image
            self.icon.title = tooltip  # Update tooltip as well
        else:
            self.icon = pystray.Icon(
                "Dictate",
                image,
                tooltip,
                menu=self.create_menu()
            )
            threading.Thread(target=self.icon.run, daemon=True).start()

    def show_recording_icon(self):
        self.update_icon("/usr/local/bin/red-circle.png", "Recording...")

    def show_decoding_icon(self):
        self.update_icon("/usr/local/bin/grey-circle.png", "Processing...")

    def show_idle_icon(self):
        self.update_icon("/usr/local/bin/hollow-circle.png", "Idle")

    def start(self):
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)
        server.listen(1)
        self.show_idle_icon()
        logging.info("Starting with idle icon")

        while self.running:
            conn, addr = server.accept()
            try:
                command = conn.recv(1024).decode('utf-8').strip()
                logging.info(f"Received command: {command}")

                if command == "RECORDING_STARTED":
                    logging.info("Switching to recording icon")
                    self.show_recording_icon()
                elif command == "RECORDING_STOPPED":
                    logging.info("Switching to decoding icon")
                    self.show_decoding_icon()
                elif command.startswith("PROCESSED"):
                    logging.info("Switching to idle icon")
                    self.show_idle_icon()
                elif command == "CONFIG_CHANGED":
                    logging.info("Configuration changed, refreshing menu")
                    self.config_manager.load_config()  # Reload config
                    self.refresh_menu()
                elif command == "QUIT":
                    logging.info("Quitting application")
                    self.quit_application()
                conn.send("OK".encode('utf-8'))
            except Exception as e:
                logging.error(f"Error handling command: {e}")
            finally:
                conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    trayService = TrayService()
    logging.info("Tray service started, waiting for commands...")
    trayService.start()
