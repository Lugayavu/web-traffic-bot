import yaml
import os

class ConfigHandler:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config_data = self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        with open(self.config_file, 'r') as file:
            config = yaml.safe_load(file)
        self.validate_config(config)
        return config

    def validate_config(self, config):
        required_keys = ['key1', 'key2', 'key3']  # Change these to your actual required keys
        for key in required_keys:
            if key not in config:
                raise KeyError(f"Missing required config key: {key}")

    def get(self, key):
        return self.config_data.get(key)

    def set(self, key, value):
        self.config_data[key] = value
        self.save_config()

    def save_config(self):
        with open(self.config_file, 'w') as file:
            yaml.safe_dump(self.config_data, file)
