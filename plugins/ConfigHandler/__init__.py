import configparser
import io
import logging
from pathlib import Path
from typing import Optional, Union

try:
    from ..atomic_file import atomic_write_text
except ImportError:
    from atomic_file import atomic_write_text  # type: ignore[import-not-found,no-redef]


class ConfigHandler:
    def __init__(self, config_path: Union[str, Path]) -> None:
        self.config = configparser.ConfigParser()
        self.config_path = config_path
        self.config_is_set = False

        self.defaults = {
            "SRC_PATH": str(Path.home() / "Downloads"),
            "DEST_PATH": str(Path.home() / "KiCad"),
        }

        try:
            if self.config.read(self.config_path):
                if "config" not in self.config:
                    self.config.add_section("config")

                for key, default_value in self.defaults.items():
                    if key not in self.config["config"] or not self.config["config"][key]:
                        self.config["config"][key] = default_value

                self.config_is_set = True
            else:
                self._create_default_config()
        except Exception as e:
            logging.error(f"Error when reading in the configuration: {e}")
            self._create_default_config()

        if not self.config_is_set:
            self.save_config()

    def _create_default_config(self) -> None:
        self.config = configparser.ConfigParser()
        self.config.add_section("config")

        for key, value in self.defaults.items():
            self.config["config"][key] = value

        self.config_is_set = False

    def get_SRC_PATH(self) -> str:
        return self.config["config"]["SRC_PATH"]

    def set_SRC_PATH(self, var: str) -> None:
        self.config["config"]["SRC_PATH"] = var
        self.save_config()

    def get_DEST_PATH(self) -> str:
        return self.config["config"]["DEST_PATH"]

    def set_DEST_PATH(self, var: str) -> None:
        self.config["config"]["DEST_PATH"] = var
        self.save_config()

    def get_value(self, key: str, section: str = "config") -> Optional[str]:
        try:
            return self.config[section][key]
        except KeyError:
            return None

    def set_value(self, key: str, value: str, section: str = "config") -> None:
        if section not in self.config:
            self.config.add_section(section)

        self.config[section][key] = value
        self.save_config()

    def save_config(self) -> None:
        try:
            buffer = io.StringIO()
            self.config.write(buffer)
            atomic_write_text(str(self.config_path), buffer.getvalue())
        except Exception as e:
            logging.error(f"Error saving the configuration: {e}")
