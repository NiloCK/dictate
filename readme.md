# Dictate

Linux voice dictation system using `faster-whisper` (CTranslate2) for local speech-to-text conversion and automatic text input.

## Overview

This system provides real-time voice dictation capabilities by:
- Recording audio from your system's microphone.
- Converting speech to text using highly optimized local models (OpenAI Whisper & Distil-Whisper).
- Automatically typing the recognized text into any application using `pynput` (with `ydotool` fallback).
- Supporting multilingual dictation and translation (e.g., speak French -> type English).

## Features

- **Fast:** Uses `faster-whisper` backend with 8-bit quantization for <1s latency on modern CPUs.
- **SOTA Models:** Supports `large-v3-turbo`, `distil-whisper`, and standard OpenAI models.
- **System Tray Control:** Switch models, languages, and tasks (transcribe/translate) instantly from the tray.
- **Smart Typing:** Robust text injection handling Unicode characters (accents, emojis).
- **Audio Management:** "Discard Recording" feature to cancel bad takes.

## Prerequisites

- Linux system with `systemd`
- Python 3.x
- Root access for installation
- Microphone
- `ydotool` (installed automatically by script)

## Installation

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
- Install system dependencies (`ydotool`, `portaudio`, etc.)
- Create a Python virtual environment in `/opt/dictation_venv`
- Set up the background daemon (`dictation.service`) and tray app (`dictation_tray.service`)
- Configure permissions for `ydotool` (socket access)

## Usage

### Dictation
1. **Trigger:** Run `dictation` (or bind it to a hotkey like `Ctrl+Alt+D`).
2. **Speak:** The tray icon turns **Red**.
3. **Stop:** Run `dictation` again. The tray icon turns **Grey** (processing), then types the text.

### Control
- **Tray Menu:** Right-click the system tray icon to:
    - **Discard Recording:** Cancel the current audio without typing.
    - **Model:** Select between speed (`tiny`, `distil-small.en`) and accuracy (`large-v3-turbo`).
    - **Language:** Force English (`en`), French (`fr`), or Auto-Detect.
    - **Task:** Choose **Transcribe** (Input Language -> Input Language) or **Translate** (Input Language -> English).
- **CLI:** You can also control it via terminal:
  ```bash
  dictation config --model large-v3-turbo
  dictation config --language fr --task translate
  dictation discard
  ```

### Hotkey Setup
Bind the command `/usr/local/bin/dictation` to a custom keyboard shortcut in your desktop environment (GNOME, KDE, i3, etc.).

## Troubleshooting

1. **Check Status:**
   ```bash
   systemctl status dictation
   systemctl --user status dictation_tray
   ```

2. **View Logs:**
   - Daemon (Recording/Transcribing): `tail -f /tmp/dictation_daemon.log`
   - Tray (Typing/UI): `journalctl --user -u dictation_tray -f`

3. **Typing Issues:**
   If text appears as numbers or gibberish (e.g. `fran242...`), ensure `ydotool` is working or try restarting the tray service to re-attempt `pynput` connection.

## Configuration

Configuration is stored in `~/.config/dictation/config.json`.
You can edit this manually or use the CLI/Tray to update it.

## Dependencies

- `faster-whisper`
- `sounddevice`
- `numpy`
- `pynput`
- `pystray`
- `ydotool` (System package)

## License

GPL-3.0
