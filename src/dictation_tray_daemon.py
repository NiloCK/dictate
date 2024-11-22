#!/usr/bin/env python3
# tray_daemon.py

import socket
import sys
import os
import pystray
from PIL import Image
import threading
import logging

SOCKET_PATH = '/tmp/dictation_tray.sock'

class TrayService:
    def __init__(self):
        self.icon = None
        self.running = True

    def start(self):
        # Remove socket if it exists
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass

        # Create Unix domain socket
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)
        server.listen(1)

        while self.running:
            conn, addr = server.accept()
            try:
                command = conn.recv(1024).decode('utf-8').strip()
                if command == "SHOW":
                    self.show_icon()
                elif command == "HIDE":
                    self.hide_icon()
                elif command == "QUIT":
                    self.running = False
                conn.send("OK".encode('utf-8'))
            finally:
                conn.close()

    def show_icon(self):
        if self.icon is None:
            image = Image.open("/usr/local/bin/red-circle.png")
            self.icon = pystray.Icon("Dictate", image, "Recording...")
            threading.Thread(target=self.icon.run, daemon=True).start()

    def hide_icon(self):
        if self.icon:
            self.icon.stop()
            self.icon = None

if __name__ == "__main__":
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass

    # Create Unix domain socket
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)  # Allow all users to send commands
    server.listen(1)

    trayService = TrayService()
    logging.info("Tray service started, waiting for commands...")

    while True:
        conn, addr = server.accept()
        try:
            command = conn.recv(1024).decode('utf-8').strip()
            logging.info(f'Received tray command: {command}')
            if command == "SHOW":
                trayService.show_icon()
            elif command == "HIDE":
                trayService.hide_icon()
            else:
                logging.error("Invalid tray command")
        except:
            conn.close()
            continue
