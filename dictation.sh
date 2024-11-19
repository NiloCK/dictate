#!/bin/bash
# dictation.sh

# Function to check if dictation is running
is_running() {
    if pgrep -f "dictation_daemon.py" > /dev/null; then
        return 0  # True in bash
    else
        return 1  # False in bash
    fi
}

# Check the current recording state
RECORDING_STATE_FILE="/tmp/dictation_state.json"
if [ -f "$RECORDING_STATE_FILE" ] && grep -q "true" "$RECORDING_STATE_FILE"; then
    # If recording, send STOP command
    python3 /usr/local/bin/dictation_client.py STOP
else
    # If not recording, send START command
    python3 /usr/local/bin/dictation_client.py START
fi
