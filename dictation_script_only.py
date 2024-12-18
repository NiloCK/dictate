#!/usr/bin/env python3
import sys
import whisper
import sounddevice as sd
import numpy as np
import threading
import time
from pynput.keyboard import Controller
import queue
import argparse
from tempfile import NamedTemporaryFile
import torch

# This script is for model testing purposes. Run directly, speak,
# and the transcribed text will be printed to the console.
#
# Close via ctrl-C

class DictationSystem:
    def __init__(self, model_name="base", device=None):
        # Initialize Whisper model
        self.model = whisper.load_model(model_name, device=device)
        self.keyboard = Controller()
        self.recording = False
        self.audio_queue = queue.Queue()

        # Audio parameters
        self.sample_rate = 16000
        self.dtype = np.float32

    def callback(self, indata, frames, time, status):
        """Callback for sounddevice to capture audio"""
        if status:
            print(status, file=sys.stderr)
        if self.recording:
            self.audio_queue.put(indata.copy())

    def start_recording(self):
        """Start recording audio"""
        self.recording = True
        self.audio_data = []

        # Start the audio stream
        with sd.InputStream(callback=self.callback,
                          channels=1,
                          samplerate=self.sample_rate,
                          dtype=self.dtype):
            while self.recording:
                try:
                    data = self.audio_queue.get(timeout=0.1)
                    self.audio_data.append(data)
                except queue.Empty:
                    continue

    def stop_recording(self):
        """Stop recording and process the audio"""
        self.recording = False
        if not self.audio_data:
            return ""

        # Combine all audio chunks
        audio = np.concatenate(self.audio_data, axis=0)
        print(f"Processing audio: length={len(audio)}, max={np.max(audio)}, min={np.min(audio)}")

        # Use Whisper to transcribe
        result = self.model.transcribe(audio.flatten(), language="en")
        return result["text"].strip()

    def type_text(self, text):
        """Type the transcribed text"""
        if text:
            self.keyboard.type(text + " ")

def main():
    parser = argparse.ArgumentParser(description="Whisper-based dictation system")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"],
                      help="Whisper model to use")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu",
                      help="Device to run the model on (cuda/cpu)")
    args = parser.parse_args()

    print(f"Initializing dictation system with {args.model} model on {args.device}")
    dictation = DictationSystem(args.model, args.device)

    # Add this debug section
    devices = sd.query_devices()
    print("\nAvailable audio devices:")
    print(devices)
    print("\nDefault input device:")
    print(sd.query_devices(kind='input'))

    print("\nPress Ctrl+C to stop recording and transcribe")
    try:
        dictation.start_recording()
    except KeyboardInterrupt:
        text = dictation.stop_recording()
        print("\nTranscribed text:", text)
        dictation.type_text(text)

    print("Press Ctrl+C to stop recording and transcribe")
    try:
        dictation.start_recording()
    except KeyboardInterrupt:
        text = dictation.stop_recording()
        print("\nTranscribed text:", text)
        dictation.type_text(text)

if __name__ == "__main__":
    main()
