#!/usr/bin/env python3
# dictation_client.py

import socket
import sys
import logging
import argparse
from config_manager import ConfigManager

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


def toggle_recording():
    response = send_daemon_command('TOGGLE')
    if response:
        if "started" in response.lower():
            send_tray_command('RECORDING_STARTED')
        elif "processed" in response.lower():
            send_tray_command('PROCESSED')


def list_devices():
    """List available audio devices by querying the daemon"""
    response = send_daemon_command('LIST_DEVICES')
    if response:
        print("\nAvailable Audio Devices:")
        print(response)


def handle_config(args):
    config = ConfigManager()

    if args.show:
        current_config = config.load_config()
        print("\nCurrent configuration:")
        for key, value in current_config.items():
            print(f"{key}: {value}")
        return

    if args.list_devices:
        list_devices()
        return

    updates = {}
    if args.hotkey:
        updates['hotkey'] = args.hotkey
    if args.device is not None:
        updates['audio_device'] = args.device
    if args.model:
        updates['model'] = args.model

    if updates:
        if config.update_config(**updates):
            print("Configuration updated successfully")
            # Notify daemon to reload configuration
            send_daemon_command('RELOAD_CONFIG')
            # Notify tray app to refresh its menu
            send_tray_command('CONFIG_CHANGED')
        else:
            print("Failed to update configuration")


def main():
    parser = argparse.ArgumentParser(description='Dictation Control')

    # Create a subparser for config commands
    subparsers = parser.add_subparsers(dest='command')

    # Config subcommand
    config_parser = subparsers.add_parser('config', help='Configure dictation settings')
    config_parser.add_argument('--hotkey', help='Set the activation hotkey')
    config_parser.add_argument('--device', type=int, help='Set the audio input device ID')
    config_parser.add_argument('--model', help='Set the Whisper model (tiny/base/small/medium/large-v3-turbo/distil-small.en/etc)')
    config_parser.add_argument('--list-devices', action='store_true', help='List available audio devices')
    config_parser.add_argument('--show', action='store_true', help='Show current configuration')

    # Discard subcommand
    subparsers.add_parser('discard', help='Discard current recording without transcribing')

    args = parser.parse_args()

    if args.command == 'config':
        handle_config(args)
    elif args.command == 'discard':
        response = send_daemon_command('DISCARD')
        if response:
            print(response)
    else:
        # Default behavior (toggle recording)
        toggle_recording()


if __name__ == "__main__":
    main()
