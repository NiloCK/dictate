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
import signal
import sys

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/dictation_daemon.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

SOCKET_PATH = '/tmp/dictation.sock'
TRAY_SOCKET_PATH = '/tmp/dictation_tray.sock'

def download_model(model_name):
    """Download the model before starting the system"""
    logging.info(f"Downloading model: {model_name}")
    whisper_cache = os.path.join('/var/cache', 'whisper')

    # Ensure cache directory exists
    os.makedirs(whisper_cache, exist_ok=True)

    try:
        model = whisper.load_model(model_name, download_root=whisper_cache, device=None)
        logging.info("Model loaded successfully!")
        return model
    except RuntimeError as e:
        logging.error(f"Error loading model: {e}")
        logging.info("Attempting to download model...")
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

        # List available audio devices
        devices = sd.query_devices()
        logging.info(f"Available audio devices:\n{devices}")

        # Get default input device
        default_device = sd.query_devices(kind='input')
        logging.info(f"Default input device:\n{default_device}")

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

        # Try multiple device configurations
        devices_to_try = [
            {"device": 0, "channels": 2},  # First ALSA device (hw:0,0) with 2 channels
            {"device": 4, "channels": 4},  # Device with 4 input channels (hw:0,6)
            {"device": 5, "channels": 4},  # Alternative 4-channel device (hw:0,7)
        ]

        for device_config in devices_to_try:
            try:
                logging.info(f"Attempting to open device {device_config['device']} "
                            f"with {device_config['channels']} channels")

                with sd.InputStream(
                    callback=self.callback,
                    device=device_config['device'],
                    channels=device_config['channels'],
                    samplerate=self.sample_rate,
                    dtype=self.dtype
                ) as stream:
                    logging.info(f"Successfully opened audio stream with device {device_config['device']}")

                    while self.recording:
                        try:
                            data = self.audio_queue.get(timeout=0.1)
                            current_max = np.max(np.abs(data))

                            if current_max > 0.0001:  # Threshold for noise
                                self.audio_data.append(data)

                        except queue.Empty:
                            continue

                    return

            except Exception as e:
                logging.error(f"Error with device {device_config['device']}: {str(e)}")
                continue

        logging.error("Failed to open any audio device")
        self.recording = False

    def stop_recording(self):
        """Stop recording and process the audio"""
        logging.info("Stopping recording")
        # inform the tray service that recording has stopped
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as tray_sock:
                tray_sock.connect(TRAY_SOCKET_PATH)
                tray_sock.send("RECORDING_STOPPED".encode('utf-8'))
        except Exception as e:
            logging.error(f"Failed to notify tray service: {e}")


        if not self.audio_data:
            logging.warning("No audio data collected")
            return ""

        try:
            # Combine all audio chunks
            audio = np.concatenate(self.audio_data, axis=0)

            # If we have multiple channels, take the mean
            if len(audio.shape) > 1 and audio.shape[1] > 1:
                audio = np.mean(audio, axis=1)

            # Normalize the audio
            max_amp = np.max(np.abs(audio))
            if max_amp > 0:
                audio = audio / max_amp * 0.95

            logging.info(f"Processing audio: length={len(audio)}, "
                        f"max={np.max(audio)}, min={np.min(audio)}")

            # Save debug WAV file
            try:
                import scipy.io.wavfile as wav
                wav.write('/tmp/last_recording.wav', self.sample_rate,
                            (audio * 32767).astype(np.int16))
                logging.info("Saved debug audio file to /tmp/last_recording.wav")
            except Exception as e:
                logging.error(f"Error saving debug audio: {e}")

            # Use Whisper to transcribe
            result = self.model.transcribe(audio, language="en")
            text = result["text"].strip()
            logging.info(f"Transcription result: {result}")
            return text

        except Exception as e:
            logging.error(f"Error processing audio: {e}", exc_info=True)
            return ""

    def type_text(self, text):
        """Type the transcribed text using ydotool"""
        if text:
            try:
                logging.info(f"Attempting to type text: {text}")
                os.system(f'ydotool type --key-delay 4 "{text} "')
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