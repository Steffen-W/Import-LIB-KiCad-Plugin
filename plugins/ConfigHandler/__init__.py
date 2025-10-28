import configparser
from pathlib import Path
import logging


class ConfigHandler:
    def __init__(self, config_path):
        self.config = configparser.ConfigParser()
        self.config_path = config_path
        self.config_is_set = False

        self.defaults = {
            "SRC_PATH": str(Path.home() / "Downloads"),
            "DEST_PATH": str(Path.home() / "KiCad"),
            "LOCAL_LIB_ENABLED": "True",
            "LOCAL_LIB_SUBFOLDER": "Lib",
            "CUSTOM_LIB_ENABLED": "True",
            "CUSTOM_LIB_NAME": "Custom",
        }

        try:
            if self.config.read(self.config_path):
                if "config" not in self.config:
                    self.config.add_section("config")

                for key, default_value in self.defaults.items():
                    if (
                        key not in self.config["config"]
                        or not self.config["config"][key]
                    ):
                        self.config["config"][key] = str(default_value)

                self.config_is_set = True
            else:
                self._create_default_config()
        except Exception as e:
            logging.error(f"Error when reading in the configuration: {e}")
            self._create_default_config()

        if not self.config_is_set:
            self.save_config()

    def _create_default_config(self):
        self.config = configparser.ConfigParser()
        self.config.add_section("config")

        for key, value in self.defaults.items():
            self.config["config"][key] = str(value)

        self.config_is_set = False

    def get_SRC_PATH(self):
        return self.config["config"]["SRC_PATH"]

    def set_SRC_PATH(self, var):
        self.config["config"]["SRC_PATH"] = str(var)
        self.save_config()

    def get_DEST_PATH(self):
        return self.config["config"]["DEST_PATH"]

    def set_DEST_PATH(self, var):
        self.config["config"]["DEST_PATH"] = str(var)
        self.save_config()

    def get_value(self, key, section="config"):
        try:
            return self.config[section][key]
        except KeyError:
            return None

    def set_value(self, key, value, section="config"):
        if section not in self.config:
            self.config.add_section(section)

        self.config[section][key] = str(value)
        self.save_config()

    def get_bool(self, key, section="config", fallback=False):
        try:
            return self.config.getboolean(section, key)
        except (ValueError, KeyError):
            return fallback

    def set_bool(self, key, value, section="config"):
        self.set_value(key, "True" if value else "False", section)

    def save_config(self):
        try:
            with open(self.config_path, "w") as configfile:
                self.config.write(configfile)
        except Exception as e:
            logging.error(f"Error saving the configuration: {e}")
