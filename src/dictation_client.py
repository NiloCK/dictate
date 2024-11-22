#!/usr/bin/env python3
# dictation_client.py

import socket
import sys
import logging

DAEMON_SOCKET = '/tmp/dictation.sock'
TRAY_SOCKET = '/tmp/dictation_tray.sock'

def send_tray_command(command):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(TRAY_SOCKET)
            client.send(command.encode('utf-8'))
            return client.recv(1024).decode('utf-8')
    except Exception as e:
        logging.error(f"Error communicating with tray service: {e}")

def send_daemon_command(command):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(DAEMON_SOCKET)
            client.send(command.encode('utf-8'))
            response = client.recv(1024).decode('utf-8')
            return response
    except Exception as e:
        logging.error(f"Error communicating with daemon: {e}")

def main():
    response = send_daemon_command('TOGGLE')
    if response:
        if "started" in response.lower():
            send_tray_command('SHOW')
        elif "processed" in response.lower():
            send_tray_command('HIDE')

if __name__ == "__main__":
    main()
