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
import os

def download_model(model_name):
    """Download the model before starting the system"""
    print(f"Downloading/Loading the {model_name} model...")
    try:
        model = whisper.load_model(model_name)
        print("Model ready!")
        return model
    except KeyboardInterrupt:
        print("\nModel download interrupted. Please try again.")
        sys.exit(1)

class DictationSystem:
    def __init__(self, model_name="base", device=None):
        # Initialize Whisper model
        self.model = download_model(model_name)
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
        print("Recording... Press Ctrl+C to stop and transcribe.")

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

        print("\nProcessing audio...")
        # Combine all audio chunks
        audio = np.concatenate(self.audio_data, axis=0)

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

    try:
        dictation = DictationSystem(args.model, args.device)
        dictation.start_recording()
    except KeyboardInterrupt:
        print("\nStopping recording...")
        text = dictation.stop_recording()
        print("\nTranscribed text:", text)
        dictation.type_text(text)
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
