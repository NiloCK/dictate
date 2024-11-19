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
import signal
import tempfile
import json

# Global flag for recording state
RECORDING_STATE_FILE = os.path.join(tempfile.gettempdir(), 'dictation_state.json')

def get_state():
    try:
        with open(RECORDING_STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"recording": False}

def set_state(recording):
    with open(RECORDING_STATE_FILE, 'w') as f:
        json.dump({"recording": recording}, f)

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
        self.model = download_model(model_name)
        self.keyboard = Controller()
        self.recording = False
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000
        self.dtype = np.float32

    def callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        if self.recording:
            self.audio_queue.put(indata.copy())

    def start_recording(self):
        """Start recording audio"""
        self.recording = True
        self.audio_data = []
        set_state(True)
        os.system('notify-send "Dictation" "Recording started" -t 1000')

        with sd.InputStream(callback=self.callback,
                          channels=1,
                          samplerate=self.sample_rate,
                          dtype=self.dtype):
            while self.recording and get_state()["recording"]:
                try:
                    data = self.audio_queue.get(timeout=0.1)
                    self.audio_data.append(data)
                except queue.Empty:
                    continue

    def stop_recording(self):
        """Stop recording and process the audio"""
        self.recording = False
        set_state(False)
        os.system('notify-send "Dictation" "Processing audio..." -t 1000')

        if not self.audio_data:
            return ""

        # Combine all audio chunks
        audio = np.concatenate(self.audio_data, axis=0)

        # Use Whisper to transcribe
        result = self.model.transcribe(audio.flatten(), language="en")
        return result["text"].strip()

    def type_text(self, text):
        """Type the transcribed text"""
        if text:
            self.keyboard.type(text + " ")
            os.system(f'notify-send "Dictation" "Transcribed: {text[:50]}..." -t 2000')

def start_dictation():
    set_state(True)
    parser = argparse.ArgumentParser(description="Whisper-based dictation system")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"],
                      help="Whisper model to use")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu",
                      help="Device to run the model on (cuda/cpu)")
    args = parser.parse_args()

    try:
        dictation = DictationSystem(args.model, args.device)
        dictation.start_recording()
        text = dictation.stop_recording()
        if text:
            dictation.type_text(text)
    except Exception as e:
        os.system(f'notify-send "Dictation Error" "{str(e)}" -t 2000')
        print(f"\nError: {str(e)}")
        sys.exit(1)

def stop_dictation():
    set_state(False)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stop":
        stop_dictation()
    else:
        start_dictation()
