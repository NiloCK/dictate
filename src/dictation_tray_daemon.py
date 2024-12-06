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

    def create_menu(self):
        """Create the system tray context menu"""
        config = self.config_manager.load_config()

        # Create submenu for model selection
        model_menu = pystray.Menu(
            pystray.MenuItem("tiny", lambda: self.set_model("tiny"),
                           checked=lambda item: config['model'] == "tiny"),
            pystray.MenuItem("base", lambda: self.set_model("base"),
                           checked=lambda item: config['model'] == "base"),
            pystray.MenuItem("small", lambda: self.set_model("small"),
                           checked=lambda item: config['model'] == "small"),
            pystray.MenuItem("medium", lambda: self.set_model("medium"),
                           checked=lambda item: config['model'] == "medium"),
            pystray.MenuItem("large", lambda: self.set_model("large"),
                           checked=lambda item: config['model'] == "large")
        )

        return pystray.Menu(
            pystray.MenuItem("Configuration", self.show_config_window),
            pystray.MenuItem("Model", model_menu),
            pystray.MenuItem("Audio Devices", self.list_audio_devices),
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
