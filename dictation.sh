#!/bin/bash

# Create a notification that recording is starting
notify-send "Dictation" "Starting recording..." -t 1000

# Run the Python script
python3 /path/to/dictation_script.py --model base

# Create a notification that recording has stopped
notify-send "Dictation" "Transcription complete" -t 1000
