#!/usr/bin/env python3
# dictation_client.py

import socket
import sys

SOCKET_PATH = '/tmp/dictation.sock'

def send_command(command):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(SOCKET_PATH)
            client.send(command.encode('utf-8'))
            response = client.recv(1024).decode('utf-8')
            print(response)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["START", "STOP"]:
        print("Usage: dictation_client.py [START|STOP]")
        sys.exit(1)
    
    send_command(sys.argv[1])
