#!/usr/bin/env python3
# dictation_daemon.py

import sys
import subprocess
from faster_whisper import WhisperModel
import sounddevice as sd
import numpy as np
import threading
import time
import queue
import os
import socket
import threading
import logging
import signal
import sys
import json
from pathlib import Path
from config_manager import ConfigManager

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


class AudioDeviceHandler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.sample_rate = 16000  # desired rate
        self.dtype = np.float32

    def list_devices(self):
        """List all available audio input devices"""
        devices = sd.query_devices()
        input_devices = []

        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                input_devices.append({
                    'id': i,
                    'name': device['name'],
                    'channels': device['max_input_channels'],
                    'default_sr': device['default_samplerate'],
                    'is_default': device == sd.query_devices(kind='input'),
                    'hostapi': device['hostapi']
                })

        self.logger.info("Available input devices:")
        for dev in input_devices:
            self.logger.info(f"ID {dev['id']}: {dev['name']} "
                           f"(channels: {dev['channels']}, "
                           f"default sr: {dev['default_sr']}, "
                           f"default: {dev['is_default']}, "
                           f"hostapi: {dev['hostapi']})")

        return input_devices

    def is_hardware_device(self, device_info):
        """Check if this is likely a real hardware device"""
        name = device_info['name'].lower()
        # Filter out ALSA plugins and virtual devices
        virtual_indicators = [
            'sysdefault', 'default', 'samplerate', 'speexrate',
            'upmix', 'vdownmix', 'null', 'dummy', 'loop'
        ]
        return not any(x in name for x in virtual_indicators)

    def _test_device(self, device_id, channels, sample_rate):
        """Test if a device configuration works and actually receives audio"""
        try:
            test_duration = 0.1  # seconds
            recorded_frames = []

            def callback(indata, frames, time, status):
                if status:
                    self.logger.warning(f"Status: {status}")
                recorded_frames.append(indata.copy())

            with sd.InputStream(
                device=device_id,
                channels=channels,
                samplerate=sample_rate,
                dtype=self.dtype,
                callback=callback,
                blocksize=int(sample_rate * test_duration)
            ) as stream:
                sd.sleep(int(test_duration * 1000))

            if recorded_frames:
                audio = np.concatenate(recorded_frames, axis=0)
                audio_level = np.abs(audio).mean()

                self.logger.info(f"Device {device_id} test - "
                               f"Audio level: {audio_level}, "
                               f"Shape: {audio.shape}, "
                               f"Sample rate: {sample_rate}")

                return True

            return False

        except Exception as e:
            self.logger.debug(f"Device {device_id} test failed: {e}")
            return False

    def create_input_stream(self, callback):
        """Create and return an InputStream with the current configuration"""
        return sd.InputStream(
            callback=callback,
            device=self.device_id,
            channels=self.channels,
            samplerate=self.sample_rate,
            dtype=self.dtype
        )

    def get_working_device(self):
        """Find a working input device configuration."""
        devices = self.list_devices()

        # First try hardware devices
        hardware_devices = [d for d in devices if self.is_hardware_device(d)]
        self.logger.info(f"Found {len(hardware_devices)} hardware devices")

        # Try hardware devices first
        for device in hardware_devices:
            device_id = device['id']
            original_sr = int(device['default_sr'])

            # Try with device's native sample rate first
            if self._test_device(device_id, 2, original_sr):
                self.sample_rate = original_sr  # Update instance sample rate
                self.device_id = device_id      # Store the working device ID
                self.channels = 2               # Store the working channel count
                self.logger.info(f"Found working hardware device {device_id} "
                                f"at {original_sr} Hz")
                return device_id, 2

            # Try with our desired sample rate
            if self._test_device(device_id, 2, self.sample_rate):
                self.device_id = device_id
                self.channels = 2
                self.logger.info(f"Found working hardware device {device_id} "
                                f"at {self.sample_rate} Hz")
                return device_id, 2

        # If no hardware devices work, try virtual devices as fallback
        self.logger.warning("No hardware devices working, trying virtual devices")
        for device in devices:
            device_id = device['id']
            if self._test_device(device_id, 1, self.sample_rate):
                self.device_id = device_id
                self.channels = 1
                self.logger.info(f"Found working virtual device {device_id}")
                return device_id, 1

        raise RuntimeError("No working audio input device found")


def download_model(model_name):
    """Download/Load the model using faster-whisper"""
    logging.info(f"Loading faster-whisper model: {model_name}")
    # faster-whisper stores models in a specific cache, usually ~/.cache/huggingface/hub
    # We can rely on its default caching or specify download_root.
    # The original code used /var/cache/whisper. faster-whisper doesn't use the same format.
    # We will let faster-whisper manage its own cache for now, or use the standard HF cache.
    
    try:
        # device="auto" checks for CUDA/ROCM, else CPU
        # compute_type="int8" is efficient for CPU and supported on GPU
        model = WhisperModel(model_name, device="auto", compute_type="int8")
        logging.info("Model loaded successfully!")
        return model
    except Exception as e:
        logging.error(f"Error loading model: {e}", exc_info=True)
        raise


class DictationSystem:
    def __init__(self):
        logging.info("Initializing DictationSystem")
        # Check if ydotool is available
        try:
            subprocess.run(['ydotool', '--help'], capture_output=True, text=True)
        except FileNotFoundError:
            logging.warning("ydotool not found! Text typing functionality will not work.")
            sys.exit(1)
        self.config = ConfigManager()
        self.load_configuration()

    def load_configuration(self):
        """Load or reload configuration"""
        config_data = self.config.load_config()

        # Initialize audio handler
        self.audio_handler = AudioDeviceHandler()

        # Set model from config
        model_name = config_data.get('model', 'base')
        self.model = download_model(model_name)

        # Configure audio device
        configured_device = config_data.get('audio_device')
        if configured_device is not None:
            try:
                if self.audio_handler._test_device(configured_device, 2, self.audio_handler.sample_rate):
                    self.device_id = configured_device
                    self.channels = 2
                else:
                    raise RuntimeError("Configured device doesn't work")
            except Exception as e:
                logging.warning(f"Configured device {configured_device} failed: {e}")
                self.device_id, self.channels = self.audio_handler.get_working_device()
                self.config.update_config(audio_device=self.device_id)
        else:
            self.device_id, self.channels = self.audio_handler.get_working_device()
            self.config.update_config(audio_device=self.device_id)

        self.sample_rate = self.audio_handler.sample_rate
        self.recording = False
        self.audio_queue = queue.Queue()
        self.recording_thread = None

    def handle_toggle(self):
        logging.info("Received TOGGLE command")
        if not self.recording:
            self.recording_thread = threading.Thread(target=self.start_recording)
            self.recording_thread.start()
            return "RECORDING_STARTED"
        else:
            self.recording = False
            if self.recording_thread:
                self.recording_thread.join()
            text = self.stop_recording()
            self.type_text(text)
            self.audio_data = []  # Clear the audio data after processing
            self.audio_queue.queue.clear()  # Clear the queue
            return f'PROCESSED: "{text}"'

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

        try:
            with self.audio_handler.create_input_stream(self.callback) as stream:
                logging.info("Successfully opened audio stream")

                while self.recording:
                    try:
                        data = self.audio_queue.get(timeout=0.1)
                        # if np.max(np.abs(data)) > 0.0001:  # Threshold for noise
                        self.audio_data.append(data)
                    except queue.Empty:
                        continue

        except Exception as e:
            logging.error(f"Error recording audio: {str(e)}")
            self.recording = False

    def stop_recording(self):
        """Stop recording and process the audio"""
        logging.info("Stopping recording")
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

            # Save debug WAV file at original sample rate
            try:
                import scipy.io.wavfile as wav
                wav.write('/tmp/last_recording.wav', self.sample_rate,
                            (audio * 32767).astype(np.int16))
                logging.info(f"Saved debug audio file to /tmp/last_recording.wav "
                            f"at {self.sample_rate} Hz")
            except Exception as e:
                logging.error(f"Error saving debug audio: {e}")

            # Resample for Whisper if needed
            if self.sample_rate != 16000:
                logging.info(f"Resampling audio from {self.sample_rate} Hz to 16000 Hz")
                from scipy import signal
                audio = signal.resample(audio,
                                        int(len(audio) * 16000 / self.sample_rate))
                logging.info(f"Resampled audio shape: {audio.shape}")

            # Use Whisper to transcribe
            # faster-whisper returns a tuple (segments, info)
            segments, info = self.model.transcribe(audio, language="en", beam_size=5)
            
            # Combine segments into a single string
            text_segments = [segment.text for segment in segments]
            text = " ".join(text_segments).strip()
            
            logging.info(f"Transcription result: {text}")
            return text

        except Exception as e:
            logging.error(f"Error processing audio: {e}", exc_info=True)
            return ""

    def type_text(self, text):
        """Type the transcribed text using ydotool"""
        if text:
            logging.info(f"Attempting to type text: {text}")
            try:
                # Use subprocess instead of os.system to better handle errors
                import subprocess
                result = subprocess.run(['ydotool', 'type', '--key-delay', '4', f"{text} "],
                                       capture_output=True, text=True, check=True)
                logging.info("Text typed successfully")
            except FileNotFoundError:
                logging.error("ydotool command not found. Please install ydotool.")
            except subprocess.CalledProcessError as e:
                logging.error(f"Error typing text: {e}")
                logging.error(f"Command output: {e.stderr}")
            except Exception as e:
                logging.error(f"Unexpected error typing text: {e}", exc_info=True)

    def handle_discard(self):
        logging.info("Received DISCARD command")
        if self.recording:
            self.recording = False
            if self.recording_thread:
                self.recording_thread.join()
            
            # Clear data
            self.audio_data = []
            self.audio_queue.queue.clear()
            
            # Notify tray to go back to idle
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as tray_sock:
                    tray_sock.connect(TRAY_SOCKET_PATH)
                    tray_sock.send("PROCESSED".encode('utf-8'))
            except Exception as e:
                logging.error(f"Failed to notify tray service: {e}")
                
            return "RECORDING_DISCARDED"
        else:
            return "NOT_RECORDING"

    def handle_command(self, command):
        """Handle various commands from the client"""
        if command == "TOGGLE":
            return self.handle_toggle()
        elif command == "DISCARD":
            return self.handle_discard()
        elif command == "LIST_DEVICES":
            return self.handle_list_devices()
        elif command == "RELOAD_CONFIG":
            return self.handle_reload_config()
        else:
            return "Invalid command"

    def handle_list_devices(self):
        """Return a formatted list of audio devices"""
        devices = self.audio_handler.list_devices()
        response = []
        for dev in devices:
            status = "ACTIVE" if dev['id'] == self.device_id else ""
            response.append(
                f"ID {dev['id']}: {dev['name']} "
                f"(channels: {dev['channels']}, "
                f"default sr: {dev['default_sr']}, "
                f"default: {dev['is_default']}) {status}"
            )
        return "\n".join(response)

    def handle_reload_config(self):
        """Reload configuration"""
        try:
            self.load_configuration()
            return "Configuration reloaded successfully"
        except Exception as e:
            logging.error(f"Error reloading configuration: {e}")
            return f"Error reloading configuration: {str(e)}"


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

            response = dictation.handle_command(command)
            conn.send(response.encode('utf-8'))
        except Exception as e:
            logging.error(f"Error handling command: {e}")
            try:
                conn.send(f"Error: {str(e)}".encode('utf-8'))
            except:
                pass
        finally:
            conn.close()

if __name__ == "__main__":
    run_service()
