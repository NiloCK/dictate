# Dictate

A Linux-based voice dictation system using OpenAI's Whisper model for speech-to-text conversion and automatic text input.

## Overview

This system provides real-time voice dictation capabilities by:
- Recording audio from your system's microphone
- Converting speech to text using Whisper
- Automatically typing the recognized text using ydotool

## Prerequisites

- Linux system with systemd
- Python 3.x
- Root access for installation
- microphone
- ydotool installed

## Installation

Either:

```bash
curl -sSL https://raw.githubusercontent.com/nilock/dictate/main/remote_install.sh | bash
```

Or:

1. Clone this repository:
```bash
git clone https://github.com/nilock/dictate
cd dictate
```

2. Run the installation script as root:
```bash
sudo ./installation.sh
```

This will:
- Create a Python virtual environment in `/opt/dictation_venv`
- Install required Python packages
- Set up the dictation service
- Start the service automatically

## Usage

1. Start/stop dictation using the provided script:
```bash
dictation.sh
```

It is useful to set up a system hot-key to point to this script at its installation destination: `/usr/local/bin/dictation.sh`

2. When activated:
   - Speak
   - Run the command again to stop recording
   - The recognized text will be automatically typed at your cursor position

3. Check service status:
```bash
systemctl status dictation
```

4. View logs:
```bash
journalctl -u dictation -f
```

## Components

- `dictation_daemon.py`: Background service handling audio recording and transcription
- `dictation_client.py`: Client interface for sending commands to the daemon
- `dictation.sh`: Convenient shell script wrapper
- `installation.sh`: System setup and service installation

## Configuration

The system uses Whisper's "base" model by default. You can modify `dictation_daemon.py` to use different models:

## Troubleshooting

1. Check service status:
```bash
systemctl status dictation
```

2. Review logs:
```bash
tail -f /tmp/dictation_daemon.log
```

3. Test audio recording:
```bash
python3 dictation_script_only.py
```

## Debug Files

The system saves the last recording as `/tmp/last_recording.wav` for debugging purposes.

## Development

A standalone testing script (`dictation_script_only.py`) is provided for development and testing purposes.

The following is useful to redeploy locally:

```bash
sudo bash ./installation.sh && sudo journalctl -u dictation -f
```


## Dependencies

- openai-whisper
- sounddevice
- numpy
- torch
- scipy
- pynput

## License

GPL-3.0

## Contributing

Sure, go nuts.
