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

SOCKET_PATH = '/tmp/dictation_tray.sock'

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
        self.icon_state = "idle"  # Track the current icon state
        self.config_manager = ConfigManager()
        self.icon_thread = None
        self.icon_lock = threading.Lock()  # Protect icon operations
        self.last_icon_refresh = 0  # Time when icon was last refreshed

        # Add watchdog thread for icon health
        self.watchdog_thread = threading.Thread(target=self.icon_watchdog, daemon=True)
        self.watchdog_thread.start()

    def show_config_window(self):
        """Launch the configuration dialog"""
        subprocess.run(['dictation', 'config', '--show'])

    def set_model(self, model_name):
        """Change the Whisper model"""
        logging.info(f"Setting model to: {model_name}")
        try:
            result = subprocess.run(['/usr/local/bin/dictation', 'config', '--model', model_name], 
                                  capture_output=True, 
                                  text=True)
            if result.returncode == 0:
                logging.info(f"Model set successfully. Output: {result.stdout}")
            else:
                logging.error(f"Failed to set model. Error: {result.stderr}")
        except Exception as e:
            logging.error(f"Error executing dictation command: {e}")
        # Refresh menu to update checkmarks
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

    def list_audio_devices(self):
        """Show audio devices dialog"""
        subprocess.run(['dictation', 'config', '--list-devices'])

    def set_audio_device(self, device_id):
        """Set the audio input device"""
        logging.info(f"Setting audio device to: {device_id}")
        try:
            result = subprocess.run(['/usr/local/bin/dictation', 'config', '--device', str(device_id)],
                                  capture_output=True,
                                  text=True)
            if result.returncode != 0:
                logging.error(f"Failed to set audio device: {result.stderr}")
        except Exception as e:
            logging.error(f"Error setting audio device: {e}")
            
        # Update config cache and refresh menu to show the new selection
        self.config_manager.load_config()  # Reload config
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
            time.sleep(2)  # Give time for daemon to restart
            self.refresh_menu()
        except Exception as e:
            logging.error(f"Error restarting daemon: {e}")

    def test_daemon_connection(self):
        """Test connection to the daemon and refresh menu"""
        self.get_audio_devices()
        self.refresh_menu()

    def get_audio_devices(self):
        """Get list of audio devices from the daemon with fallback"""
        logging.info("Beginning audio device retrieval")
        daemon_socket = '/tmp/dictation.sock'
        logging.info(f"Will attempt to connect to daemon at {daemon_socket}")

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                logging.info("Socket created")
                client.settimeout(2.0)  # Add timeout to avoid hanging
                logging.info("Timeout set to 2.0 seconds")

                try:
                    logging.info(f"Attempting to connect to {daemon_socket}")
                    client.connect(daemon_socket)
                    logging.info("Successfully connected to dictation daemon socket")

                    command = 'LIST_DEVICES'
                    logging.info(f"Sending command: '{command}'")
                    client.send(command.encode('utf-8'))
                    logging.info("Command sent, waiting for response...")

                    response = client.recv(4096).decode('utf-8')
                    logging.info(f"Received response of length: {len(response)} bytes")

                    if response:
                        sample = response[:100] + ('...' if len(response) > 100 else '')
                        logging.info(f"Response sample: {sample}")
                    else:
                        logging.warning("Received empty response from daemon")

                    devices = []
                    logging.info("Beginning to parse device list")
                    for i, line in enumerate(response.splitlines()):
                        logging.debug(f"Processing line {i+1}: {line}")
                        if line.strip():
                            logging.debug(f"Line {i+1} is not empty, checking format")
                            # Extract ID and name
                            if "ID " in line and ":" in line:
                                logging.debug(f"Line {i+1} matches device format")
                                id_part = line.split(":", 1)[0].strip()
                                logging.debug(f"ID part: '{id_part}'")
                                device_id = id_part.replace("ID ", "").strip()
                                logging.debug(f"Extracted device_id string: '{device_id}'")

                                try:
                                    device_id = int(device_id)
                                    logging.debug(f"Converted device_id to int: {device_id}")
                                    is_active = "ACTIVE" in line
                                    logging.debug(f"Device active status: {is_active}")

                                    name_part = line.split(":", 1)[1].split("(")[0].strip()
                                    logging.debug(f"Extracted name: '{name_part}'")

                                    devices.append({
                                        'id': device_id,
                                        'name': name_part,
                                        'is_active': is_active
                                    })
                                    logging.debug(f"Added device {device_id} to list")
                                except ValueError:
                                    logging.warning(f"Could not convert '{device_id}' to integer on line {i+1}")
                                    continue
                            else:
                                logging.debug(f"Line {i+1} does not match device format, skipping")

                    logging.info(f"Successfully parsed {len(devices)} audio devices")
                    return devices

                except socket.timeout as e:
                    logging.warning(f"Connection timed out: {e}")
                    logging.warning("The daemon may be busy or not responding")
                    return []
                except ConnectionRefusedError as e:
                    logging.warning(f"Connection refused: {e}")
                    logging.warning("The dictation daemon may not be running")
                    return []
                except Exception as e:
                    logging.warning(f"Unexpected error during connection: {e}")
                    logging.warning("This could be due to socket permissions or other issues")
                    return []

        except Exception as e:
            logging.error(f"Critical error getting audio devices: {e}", exc_info=True)
            logging.error("This is likely a programming error rather than a connection issue")
            return []

    def refresh_menu(self):
        """Refresh the menu to update device list"""
        with self.icon_lock:
            if self.icon:
                try:
                    self.icon.menu = self.create_menu()
                    # Force menu update in pystray
                    if hasattr(self.icon, '_update_menu'):
                        self.icon._update_menu()
                except Exception as e:
                    logging.error(f"Error refreshing menu: {e}")
                    # If refresh fails, try to recreate the icon
                    self.recreate_icon()

    def create_menu(self):
        """Create the system tray context menu with fallback options"""
        try:
            config = self.config_manager.load_config()
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            config = {'model': 'base'}  # Default fallback

        # Create submenu for model selection
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

        # Create submenu for Language
        current_lang = config.get('language', 'en')
        language_menu = pystray.Menu(
            pystray.MenuItem("Auto-Detect", lambda: self.set_language("auto"),
                           checked=lambda item: current_lang == "auto"),
            pystray.MenuItem("English (en)", lambda: self.set_language("en"),
                           checked=lambda item: current_lang == "en"),
            pystray.MenuItem("French (fr)", lambda: self.set_language("fr"),
                           checked=lambda item: current_lang == "fr")
        )

        # Create submenu for Task
        current_task = config.get('task', 'transcribe')
        task_menu = pystray.Menu(
            pystray.MenuItem("Transcribe (Speech -> Text)", lambda: self.set_task("transcribe"),
                           checked=lambda item: current_task == "transcribe"),
            pystray.MenuItem("Translate (Speech -> English Text)", lambda: self.set_task("translate"),
                           checked=lambda item: current_task == "translate")
        )

        # Create dynamic submenu for audio devices
        devices = []
        max_retries = 4
        retry_delay = 2

        for attempt in range(max_retries):
            logging.info(f"Attempt {attempt+1}/{max_retries} to get audio devices")
            devices = self.get_audio_devices()
            if devices:
                logging.info(f"Successfully got {len(devices)} audio devices on attempt {attempt+1}")
                break
            else:
                logging.warning(f"No devices found on attempt {attempt+1}")
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error("All attempts to get audio devices failed")

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

        # If no devices found, show a message
        if not device_items:
            device_items.append(pystray.MenuItem("No devices found (daemon not running?)", lambda: None, enabled=False))
            # Add a menu item to refresh and test connection
            device_items.append(pystray.MenuItem("Test daemon connection", lambda: self.test_daemon_connection()))

        device_menu = pystray.Menu(*device_items)

        return pystray.Menu(
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
        with self.icon_lock:
            if self.icon:
                try:
                    self.icon.stop()
                except Exception as e:
                    logging.error(f"Error stopping icon: {e}")
                self.icon = None
        sys.exit(0)

    def icon_watchdog(self):
        """Monitor icon health and recreate when necessary"""
        while self.running:
            time.sleep(5)  # Check every 5 seconds

            with self.icon_lock:
                # If icon exists but thread is dead, recreate it
                if self.icon and (not self.icon_thread or not self.icon_thread.is_alive()):
                    logging.warning("Watchdog detected dead icon thread, recreating...")
                    self.recreate_icon()
                    continue

                # Check if systray manager is valid by using a safe method
                if self.icon:
                    try:
                        # Try a non-destructive operation that requires valid systray_manager
                        # This is a hack to detect if the underlying X11 connection is still valid
                        if hasattr(self.icon, '_update_title'):
                            self.icon._update_title()
                    except Exception as e:
                        if "assert self._systray_manager" in str(e) or "_systray_manager" in str(e):
                            logging.warning(f"Systray manager invalid, recreating icon: {e}")
                            self.recreate_icon()
                        else:
                            logging.error(f"Unexpected icon error: {e}")

    def update_icon(self, image_path, tooltip):
        """Common method to update or create the icon"""
        with self.icon_lock:
            # Record time of update for health check
            self.last_icon_refresh = time.time()

            try:
                image = Image.open(image_path)
                if self.icon:
                    try:
                        self.icon.icon = image
                        self.icon.title = tooltip  # Update tooltip as well
                    except Exception as e:
                        logging.error(f"Error updating icon: {e}")
                        self.recreate_icon(image_path, tooltip)
                else:
                    self.create_icon(image_path, tooltip)
            except Exception as e:
                logging.error(f"Error in update_icon: {e}")
                # Fall back to recreating the icon
                self.recreate_icon(image_path, tooltip)

    def create_icon(self, image_path, tooltip):
        """Create a new systray icon"""
        try:
            image = Image.open(image_path)

            # Stop any existing icon thread first
            if self.icon_thread and self.icon_thread.is_alive():
                logging.info("Waiting for previous icon thread to complete...")
                # We don't want to wait forever
                self.icon_thread.join(timeout=2.0)

            # Create the icon completely fresh
            self.icon = pystray.Icon(
                "Dictate",
                image,
                tooltip,
                menu=self.create_menu()
            )

            # Create new thread for the icon
            self.icon_thread = threading.Thread(target=self.run_icon, daemon=True)
            self.icon_thread.start()
            logging.info(f"Created new icon with tooltip: {tooltip}")
        except Exception as e:
            logging.error(f"Error creating icon: {e}")
            # Schedule a retry after delay
            threading.Timer(2.0, lambda: self.create_icon(image_path, tooltip)).start()

    def run_icon(self):
        """Run the icon in a way that catches errors"""
        try:
            if self.icon:
                self.icon.run()
                logging.info("Icon thread exiting normally")
        except Exception as e:
            logging.error(f"Error in icon thread: {e}")
        finally:
            # When icon thread exits for any reason, recreate after delay unless we're shutting down
            if self.running:
                logging.info("Scheduling icon recreation from run_icon")
                threading.Timer(1.0, lambda: self.recreate_icon()).start()

    def recreate_icon(self, image_path=None, tooltip=None):
        """Recreate the icon from scratch"""
        with self.icon_lock:
            # Use current state if not specified
            if image_path is None:
                if self.icon_state == "recording":
                    image_path = "/usr/local/bin/red-circle.png"
                    tooltip = "Recording..."
                elif self.icon_state == "processing":
                    image_path = "/usr/local/bin/grey-circle.png"
                    tooltip = "Processing..."
                else:  # idle
                    image_path = "/usr/local/bin/hollow-circle.png"
                    tooltip = "Idle"

            logging.info(f"Recreating icon with state: {self.icon_state}")

            # Stop the existing icon if it exists
            if self.icon:
                try:
                    self.icon.stop()
                except Exception as e:
                    logging.error(f"Error stopping existing icon: {e}")
                self.icon = None

            # Don't start a new icon creation if we're shutting down
            if not self.running:
                return

            # Create a new icon after a short delay - helps prevent race conditions
            def delayed_creation():
                if self.running:  # Check again in case we're shutting down
                    with self.icon_lock:
                        if self.icon is None:  # Only create if still needed
                            self.create_icon(image_path, tooltip)

            threading.Timer(0.5, delayed_creation).start()

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
        """Type text using pynput if available, else fallback to ydotool with unicode support"""
        if self.keyboard:
            try:
                logging.info("Typing with pynput")
                self.keyboard.type(text)
                self.keyboard.type(" ")
                return
            except Exception as e:
                logging.error(f"Pynput failed: {e}")
        
        # Fallback to ydotool
        logging.info("Falling back to ydotool")
        try:
            # Helper to type a chunk of text (ASCII only)
            def type_chunk(chunk):
                if not chunk: return
                subprocess.run(['ydotool', 'type', '--key-delay', '4', f"{chunk}"],
                             capture_output=True, text=True, check=True)

            # Helper to type a single unicode character via Ctrl+Shift+u
            def type_unicode(char):
                # Standard Linux Unicode entry: Ctrl+Shift+u, hex, Enter
                hex_code = f"{ord(char):x}"
                # Ctrl+Shift+u (29=L_Ctrl, 42=L_Shift, 22=u)
                subprocess.run(['ydotool', 'key', '29:1', '42:1', '22:1', '22:0', '42:0', '29:0'], check=True)
                # Hex code
                subprocess.run(['ydotool', 'type', '--key-delay', '2', hex_code], check=True)
                # Enter
                subprocess.run(['ydotool', 'key', '28:1', '28:0'], check=True)

            # Split text into ASCII and non-ASCII chunks
            current_chunk = ""
            for char in text:
                if char.isascii() and char.isprintable():
                    current_chunk += char
                else:
                    # Flush current chunk
                    type_chunk(current_chunk)
                    current_chunk = ""
                    # Type the unicode char
                    type_unicode(char)
            
            # Flush remaining chunk
            type_chunk(current_chunk)
            
            # Type a trailing space
            type_chunk(" ")
            
        except Exception as e:
            logging.error(f"ydotool fallback failed: {e}")


    def start(self):
        # Set up the socket for receiving commands
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)
        server.settimeout(5.0)  # Add timeout to accept() to allow periodic checks
        server.listen(1)

        self.show_idle_icon()
        logging.info("Starting with idle icon")

        while self.running:
            try:
                # Accept connections with timeout to allow checking icon state periodically
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    # Periodic health check handled by watchdog thread
                    continue

                try:
                    command = conn.recv(1024).decode('utf-8').strip()
                    logging.info(f"Received command: {command}")

                    if command == "RECORDING_STARTED":
                        logging.info("Switching to recording icon")
                        self.show_recording_icon()
                    elif command == "RECORDING_STOPPED":
                        logging.info("Switching to decoding icon")
                        self.show_decoding_icon()
                    elif command.startswith("PROCESSED"):
                        logging.info("Switching to idle icon")
                        self.show_idle_icon()
                    elif command.startswith("TYPE:"):
                        text_to_type = command[5:] # Remove TYPE: prefix
                        logging.info(f"Typing text: {text_to_type}")
                        self.type_text_robust(text_to_type)
                        # Ensure icon goes back to idle
                        self.show_idle_icon()
                    elif command == "CONFIG_CHANGED":
                        logging.info("Configuration changed, refreshing menu")
                        self.config_manager.load_config()  # Reload config
                        self.refresh_menu()
                    elif command == "QUIT":
                        logging.info("Quitting application")
                        self.quit_application()

                    try:
                        # Send response and handle possible broken pipe
                        conn.send("OK".encode('utf-8'))
                    except BrokenPipeError:
                        logging.warning("Broken pipe when responding to client")
                    except Exception as e:
                        logging.error(f"Error sending response: {e}")

                except Exception as e:
                    logging.error(f"Error handling command: {e}")
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                # Brief pause to avoid tight loop if there's a persistent error
                time.sleep(0.5)

        # Cleanup before exit
        try:
            server.close()
            os.unlink(SOCKET_PATH)
        except:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    trayService = TrayService()
    logging.info("Tray service started, waiting for commands...")
    trayService.start()
