#!/usr/bin/env python3
# dictation_client.py

import socket
import sys
import os

SOCKET_PATH = '/tmp/dictation.sock'

def send_command():
    os.system(f'notify-send "Dictation Client" "sending command" -t 1000')
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(SOCKET_PATH)
            client.send('TOGGLE'.encode('utf-8'))
            response = client.recv(1024).decode('utf-8')
            print(response)
            os.system(f'notify-send "Dictation Client" "Server response: {response}" -t 1000')
    except Exception as e:
        print(f"Error: {e}")
        os.system(f'notify-send "Dictation Client Error" "{str(e)}" -t 2000')

if __name__ == "__main__":
    os.system(f'notify-send "Dictation Client Called" -t 1000')
    # if len(sys.argv) != 2 or sys.argv[1] not in ["START", "STOP"]:
    #     print("Usage: dictation_client.py [START|STOP]")
    #     sys.exit(1)

    send_command()
