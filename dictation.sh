#!/bin/bash

# Function to check if dictation is running
is_running() {
    if pgrep -f "dictation_script.py" > /dev/null; then
        return 0  # True in bash
    else
        return 1  # False in bash
    fi
}

# Check if the script is already running
if is_running; then
    # Stop dictation
    python3 /home/colin/dev/dictate/dictation_script.py --stop

    # Give it a moment to process
    sleep 2

    # If it's still running, force kill it
    if is_running; then
        pkill -f "dictation_script.py"
        notify-send "Dictation" "Forced to stop" -t 1000
    fi
else
    # Start dictation
    python3 /home/colin/dev/dictate/dictation_script.py --model base &
fi
