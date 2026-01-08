#!/usr/bin/env python3
# dictation_tray_daemon.py

import socket
import sys
import os
import pystray
from PIL import Image
import threading
import logging
import time
from config_manager import ConfigManager
import subprocess

try:
    from pynput.keyboard import Controller
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
except Exception:
    PYNPUT_AVAILABLE = False

SOCKET_PATH = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'dictation_tray.sock')

class TrayService:
    def __init__(self):
        self.icon = None
        if PYNPUT_AVAILABLE:
            try:
                self.keyboard = Controller()
            except Exception:
                self.keyboard = None
        else:
            self.keyboard = None
            
        self.running = True
        self.icon_state = "idle"
        self.config_manager = ConfigManager()
        self.icon_lock = threading.Lock()
        
        # State for icon appearance
        self.current_image_path = "/usr/local/bin/hollow-circle.png"
        self.current_tooltip = "Idle"
        
        self.cached_devices = []
        self.last_device_refresh = 0
        
        # Initial device fetch
        threading.Thread(target=self.refresh_devices_background, daemon=True).start()

    def refresh_devices_background(self):
        """Fetch devices in the background to avoid hanging the UI"""
        devices = self.get_audio_devices()
        if devices:
            self.cached_devices = devices
            self.last_device_refresh = time.time()
            # If the icon exists, nudge it to refresh the menu next time it's opened
            if self.icon:
                try:
                    self.icon.menu = self.create_menu()
                except Exception:
                    pass

    def show_config_window(self):
        """Launch the configuration dialog"""
        subprocess.run(['dictation', 'config', '--show'])

    def set_model(self, model_name):
        """Change the Whisper model"""
        logging.info(f"Setting model to: {model_name}")
        try:
            subprocess.run(['/usr/local/bin/dictation', 'config', '--model', model_name], 
                                  capture_output=True, 
                                  text=True)
        except Exception as e:
            logging.error(f"Error executing dictation command: {e}")
        self.config_manager.load_config()
        self.refresh_menu()

    def set_language(self, language):
        """Change the language"""
        logging.info(f"Setting language to: {language}")
        try:
            subprocess.run(['/usr/local/bin/dictation', 'config', '--language', language], capture_output=True)
        except Exception as e:
            logging.error(f"Error setting language: {e}")
        self.config_manager.load_config()
        self.refresh_menu()

    def set_task(self, task):
        """Change the task"""
        logging.info(f"Setting task to: {task}")
        try:
            subprocess.run(['/usr/local/bin/dictation', 'config', '--task', task], capture_output=True)
        except Exception as e:
            logging.error(f"Error setting task: {e}")
        self.config_manager.load_config()
        self.refresh_menu()

    def set_audio_device(self, device_id):
        """Set the audio input device"""
        logging.info(f"Setting audio device to: {device_id}")
        try:
            subprocess.run(['/usr/local/bin/dictation', 'config', '--device', str(device_id)],
                                  capture_output=True,
                                  text=True)
        except Exception as e:
            logging.error(f"Error setting audio device: {e}")
            
        self.config_manager.load_config()
        self.refresh_menu()

    def discard_recording(self):
        """Discard the current recording"""
        logging.info("Discarding recording via tray")
        try:
            subprocess.run(['/usr/local/bin/dictation', 'discard'], capture_output=True)
        except Exception as e:
            logging.error(f"Error discarding recording: {e}")

    def restart_daemon(self):
        """Restart the dictation daemon"""
        try:
            subprocess.run(['systemctl', '--user', 'restart', 'dictation'])
            logging.info("Dictation daemon restart requested")
            time.sleep(2)
            self.refresh_menu()
        except Exception as e:
            logging.error(f"Error restarting daemon: {e}")

    def test_daemon_connection(self):
        """Test connection to the daemon and refresh menu"""
        self.get_audio_devices()
        self.refresh_menu()

    def toggle_recording(self):
        """Toggle recording via the daemon"""
        logging.info("Toggling recording via tray")
        try:
            subprocess.run(['/usr/local/bin/dictation'], capture_output=True)
        except Exception as e:
            logging.error(f"Error toggling recording: {e}")

    def get_audio_devices(self):
        """Get list of audio devices from the daemon with fallback"""
        daemon_socket = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'dictation.sock')
        logging.info(f"Will attempt to connect to daemon at {daemon_socket}")
        
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(3.0) # Increased timeout
                client.connect(daemon_socket)
                client.send('LIST_DEVICES'.encode('utf-8'))
                response = client.recv(16384).decode('utf-8') # Increased buffer

                logging.info(f"Device list response length: {len(response)}")
                
                devices = []
                for line in response.splitlines():
                    if line.strip() and "ID " in line and ":" in line:
                        try:
                            id_part = line.split(":", 1)[0].strip()
                            device_id = int(id_part.replace("ID ", "").strip())
                            is_active = "ACTIVE" in line
                            name_part = line.split(":", 1)[1].split("(")[0].strip()
                            
                            devices.append({
                                'id': device_id,
                                'name': name_part,
                                'is_active': is_active
                            })
                        except ValueError:
                            continue
                
                logging.info(f"Parsed {len(devices)} devices")
                return devices

        except Exception as e:
            logging.warning(f"Error getting audio devices: {e}")
            return []

    def refresh_menu(self):
        """Refresh the menu to update device list"""
        if self.icon:
            try:
                self.icon.menu = self.create_menu()
            except Exception as e:
                logging.error(f"Error refreshing menu: {e}")

    def create_menu(self):
        """Create the system tray context menu"""
        try:
            config = self.config_manager.load_config()
        except Exception:
            config = {'model': 'base'}

        # Model Menu
        model_menu = pystray.Menu(
            pystray.MenuItem("OpenAI Tiny (Fastest, ~150MB)", lambda: self.set_model("tiny"),
                           checked=lambda item: config.get('model') == "tiny"),
            pystray.MenuItem("OpenAI Base (Default, ~200MB)", lambda: self.set_model("base"),
                           checked=lambda item: config.get('model') == "base"),
            pystray.MenuItem("OpenAI Small (Balanced, ~500MB)", lambda: self.set_model("small"),
                           checked=lambda item: config.get('model') == "small"),
            pystray.MenuItem("OpenAI Medium (High Acc, ~1.5GB)", lambda: self.set_model("medium"),
                           checked=lambda item: config.get('model') == "medium"),
            pystray.MenuItem("OpenAI Large-v3-Turbo (Best Acc, ~1.6GB)", lambda: self.set_model("large-v3-turbo"),
                           checked=lambda item: config.get('model') == "large-v3-turbo"),
            pystray.MenuItem("Distil-Whisper Small (Fast, English, ~350MB)", lambda: self.set_model("distil-small.en"),
                           checked=lambda item: config.get('model') == "distil-small.en"),
            pystray.MenuItem("Distil-Whisper Medium (Acc, English, ~750MB)", lambda: self.set_model("distil-medium.en"),
                           checked=lambda item: config.get('model') == "distil-medium.en")
        )

        # Language Menu
        current_lang = config.get('language', 'en')
        language_menu = pystray.Menu(
            pystray.MenuItem("Auto-Detect", lambda: self.set_language("auto"),
                           checked=lambda item: current_lang == "auto"),
            pystray.MenuItem("English (en)", lambda: self.set_language("en"),
                           checked=lambda item: current_lang == "en"),
            pystray.MenuItem("French (fr)", lambda: self.set_language("fr"),
                           checked=lambda item: current_lang == "fr")
        )

        # Task Menu
        current_task = config.get('task', 'transcribe')
        task_menu = pystray.Menu(
            pystray.MenuItem("Transcribe (Speech -> Text)", lambda: self.set_task("transcribe"),
                           checked=lambda item: current_task == "transcribe"),
            pystray.MenuItem("Translate (Speech -> English Text)", lambda: self.set_task("translate"),
                           checked=lambda item: current_task == "translate")
        )

        # Device Menu
        devices = self.cached_devices
        if not devices or (time.time() - self.last_device_refresh > 30):
            threading.Thread(target=self.refresh_devices_background, daemon=True).start()

        device_items = []
        current_device_id = config.get('audio_device')

        for device in devices:
            device_id = device['id']
            device_items.append(
                pystray.MenuItem(
                    f"{device['name']} (ID: {device_id})",
                    lambda item, id=device_id: self.set_audio_device(id),
                    checked=lambda item, id=device_id: id == current_device_id or device.get('is_active', False)
                )
            )

        if not device_items:
            device_items.append(pystray.MenuItem("No devices found", lambda: None, enabled=False))
            device_items.append(pystray.MenuItem("Test connection", lambda: self.test_daemon_connection()))

        device_menu = pystray.Menu(*device_items)

        return pystray.Menu(
            pystray.MenuItem("Toggle Recording", lambda: self.toggle_recording()),
            pystray.MenuItem("Configuration", self.show_config_window),
            pystray.MenuItem("Discard Recording", lambda: self.discard_recording()),
            pystray.MenuItem("Model", model_menu),
            pystray.MenuItem("Language", language_menu),
            pystray.MenuItem("Task", task_menu),
            pystray.MenuItem("Audio Devices", device_menu),
            pystray.MenuItem("Refresh Devices", lambda: self.refresh_menu()),
            pystray.MenuItem("Restart Daemon", lambda: self.restart_daemon()),
            pystray.MenuItem("Quit", self.quit_application)
        )

    def quit_application(self):
        """Quit the application"""
        self.running = False
        if self.icon:
            self.icon.stop()
        sys.exit(0)

    def update_icon(self, image_path, tooltip):
        """Update the icon's appearance"""
        self.current_image_path = image_path
        self.current_tooltip = tooltip
        
        if self.icon:
            try:
                # Update in-place
                self.icon.icon = Image.open(image_path)
                self.icon.title = tooltip
            except Exception as e:
                logging.error(f"Error updating icon in-place: {e}")

    def show_recording_icon(self):
        self.icon_state = "recording"
        self.update_icon("/usr/local/bin/red-circle.png", "Recording...")

    def show_decoding_icon(self):
        self.icon_state = "processing"
        self.update_icon("/usr/local/bin/grey-circle.png", "Processing...")

    def show_idle_icon(self):
        self.icon_state = "idle"
        self.update_icon("/usr/local/bin/hollow-circle.png", "Idle")

    def type_text_robust(self, text):
        """Type text using pynput if available, else fallback to ydotool"""
        is_wayland = os.environ.get('XDG_SESSION_TYPE') == 'wayland' or os.environ.get('WAYLAND_DISPLAY') is not None
        
        if self.keyboard and not is_wayland:
            try:
                logging.info("Typing with pynput")
                self.keyboard.type(text)
                self.keyboard.type(" ")
                return
            except Exception as e:
                logging.error(f"Pynput failed: {e}")
        
        # Fallback to ydotool
        logging.info("Using ydotool for typing")
        try:
            # Helper to type a chunk of text
            def type_chunk(chunk):
                if not chunk: return
                subprocess.run(['ydotool', 'type', '--key-delay', '4', f"{chunk}"],
                             capture_output=True, text=True, check=True)

            # Helper to type unicode via Linux hex entry
            def type_unicode(char):
                try:
                    hex_code = f"{ord(char):x}"
                    # Ctrl+Shift+u
                    subprocess.run(['ydotool', 'key', '29:1', '42:1', '22:1', '22:0', '42:0', '29:0'], check=True)
                    # Hex code
                    subprocess.run(['ydotool', 'type', '--key-delay', '2', hex_code], check=True)
                    # Enter
                    subprocess.run(['ydotool', 'key', '28:1', '28:0'], check=True)
                except Exception as e:
                    logging.error(f"Error typing unicode char '{char}': {e}")

            current_chunk = ""
            for char in text:
                if char.isascii() and char.isprintable():
                    current_chunk += char
                else:
                    type_chunk(current_chunk)
                    current_chunk = ""
                    type_unicode(char)
            
            type_chunk(current_chunk)
            type_chunk(" ")
            
        except Exception as e:
            logging.error(f"ydotool fallback failed: {e}")

    def run_socket_server(self):
        """Background thread for handling socket commands"""
        logging.info(f"Tray daemon starting socket server at: {SOCKET_PATH}")
        try:
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
        except OSError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)
        server.settimeout(2.0)
        server.listen(1)

        logging.info("Socket server started")

        while self.running:
            try:
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    continue

                try:
                    # Use a larger buffer for transcription text
                    command = conn.recv(16384).decode('utf-8').strip()
                    if not command:
                        continue
                        
                    logging.info(f"Received command of length: {len(command)}")

                    if command == "RECORDING_STARTED":
                        self.show_recording_icon()
                    elif command == "RECORDING_STOPPED":
                        self.show_decoding_icon()
                    elif command.startswith("PROCESSED"):
                        self.show_idle_icon()
                    elif command.startswith("TYPE:"):
                        text = command[5:]
                        self.type_text_robust(text)
                        self.show_idle_icon()
                    elif command == "CONFIG_CHANGED":
                        self.config_manager.load_config()
                        self.refresh_menu()
                    elif command == "QUIT":
                        self.quit_application()

                    try:
                        conn.send("OK".encode('utf-8'))
                    except:
                        pass
                finally:
                    conn.close()

            except Exception as e:
                logging.error(f"Error in socket loop: {e}")
                time.sleep(0.5)

        try:
            server.close()
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
        except:
            pass

    def run(self):
        """Main entry point - runs icon on main thread"""
        # Start socket server in background
        server_thread = threading.Thread(target=self.run_socket_server, daemon=True)
        server_thread.start()
        
        logging.info("Starting main icon loop")
        
        while self.running:
            try:
                image = Image.open(self.current_image_path)
                self.icon = pystray.Icon(
                    "Dictate",
                    image,
                    self.current_tooltip,
                    menu=self.create_menu()
                )
                
                # run() is blocking
                self.icon.run()
                
                # If run() returns, it was stopped. 
                # If self.running is still True, we might want to restart it 
                # (though usually we just exit).
                if not self.running:
                    break
                time.sleep(1)
                    
            except Exception as e:
                logging.error(f"Critical error in icon loop: {e}")
                time.sleep(2)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = TrayService()
    service.run()