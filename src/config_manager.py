import os
import json

class ConfigManager:
    DEFAULT_CONFIG = {
        "hotkey": "ctrl+alt+d",  # Default hotkey
        "audio_device": None,     # Will be auto-detected if None
        "model": "base"          # Default Whisper model
    }

    def __init__(self):
        # Get user config directory (works on Linux, macOS, Windows)
        self.config_dir = os.path.join(
            os.environ.get(
                'XDG_CONFIG_HOME',
                os.path.join(os.path.expanduser('~'), '.config')
            ),
            'dictation'
        )
        self.config_file = os.path.join(self.config_dir, 'config.json')
        self.ensure_config_exists()

    def ensure_config_exists(self):
        """Create config directory and file if they don't exist"""
        os.makedirs(self.config_dir, exist_ok=True)
        if not os.path.exists(self.config_file):
            self.save_config(self.DEFAULT_CONFIG)

    def load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                # Merge with defaults to ensure all fields exist
                return {**self.DEFAULT_CONFIG, **config}
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.DEFAULT_CONFIG

    def save_config(self, config):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def update_config(self, **kwargs):
        """Update specific configuration values"""
        config = self.load_config()
        config.update(kwargs)
        return self.save_config(config)
