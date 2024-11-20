#!/usr/bin/env python3
# dictation_daemon.py

import sys
import whisper
import sounddevice as sd
import numpy as np
import threading
import time
import queue
import torch
import os
import socket
import threading
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/dictation_daemon.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

SOCKET_PATH = '/tmp/dictation.sock'

def download_model(model_name):
    """Download the model before starting the system"""
    logging.info(f"Downloading model: {model_name}")
    whisper_cache = os.path.join('/var/cache', 'whisper')

    # Ensure cache directory exists
    os.makedirs(whisper_cache, exist_ok=True)

    try:
        model = whisper.load_model(model_name, download_root=whisper_cache)
        logging.info("Model loaded successfully!")
        return model
    except RuntimeError as e:
        logging.error(f"Error loading model: {e}")
        logging.info("Attempting to download model...")
        # maybe: add explicit download code here
        raise
    except KeyboardInterrupt:
        logging.info("\nModel download interrupted. Please try again.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error downloading model: {e}", exc_info=True)
        raise

class DictationSystem:
    def __init__(self, model_name="base", device=None):
        logging.info(f"Initializing DictationSystem")

        self.model = download_model(model_name)
        self.recording = False
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000
        self.dtype = np.float32
        self.recording_thread = None

    def handle_toggle(self):
        logging.info("Received TOGGLE command")
        if not self.recording:
            self.recording_thread = threading.Thread(target=self.start_recording)
            self.recording_thread.start()
            return "Recording started"
        else:
            self.recording = False
            if self.recording_thread:
                self.recording_thread.join()
            text = self.stop_recording()
            self.type_text(text)
            self.audio_data = []  # Clear the audio data after processing
            self.audio_queue.queue.clear()  # Clear the queue
            return f'Processed: "{text}"'

    def callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        if self.recording:
            self.audio_queue.put(indata.copy())

    def start_recording(self):
        """Start recording audio"""
        logging.info("Recording audio...")
        self.recording = True
        self.audio_data = []
        self.audio_queue.queue.clear()

        with sd.InputStream(callback=self.callback,
                          channels=1,
                          samplerate=self.sample_rate,
                          dtype=self.dtype):
            while self.recording:  # Simplified loop condition
                try:
                    data = self.audio_queue.get(timeout=0.1)
                    self.audio_data.append(data)
                except queue.Empty:
                    continue

    def stop_recording(self):
        """Stop recording and process the audio"""
        logging.info("Stopping recording")
        self.recording = False

        if not self.audio_data:
            return ""

        # Combine all audio chunks
        audio = np.concatenate(self.audio_data, axis=0)
        logging.info(f"Processing audio: length={len(audio)}, max={np.max(audio)}, min={np.min(audio)}")

        # Use Whisper to transcribe
        try:
            result = self.model.transcribe(audio.flatten(), language="en")
            logging.info(f"Transcription result: {result}")
            text = result["text"].strip()
            logging.info(f"Processed text: {text}")
            return text
        except Exception as e:
            logging.error(f"Transcription error: {e}", exc_info=True)
            return ""

    def type_text(self, text):
        """Type the transcribed text using ydotool"""
        if text:
            try:
                logging.info(f"Attempting to type text: {text}")
                os.system(f'ydotool type "{text} "')
                logging.info("Text typed successfully")
            except Exception as e:
                logging.info(f"Error typing text: {e}", exc_info=True)

def run_service():
    # Remove socket if it exists
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass

    # Create Unix domain socket
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)  # Allow all users to send commands
    server.listen(1)

    dictation = DictationSystem()

    print("Dictation service started, waiting for commands...")

    while True:
        conn, addr = server.accept()
        try:
            command = conn.recv(1024).decode('utf-8').strip()
            # notify-send debug statement
            logging.info(f'Received command: {command}')
            if command == "TOGGLE":
                response = dictation.handle_toggle()
            else:
                response = "Invalid command"

            conn.send(response.encode('utf-8'))
        finally:
            conn.close()

if __name__ == "__main__":
    run_service()
