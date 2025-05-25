import os
import sys
import platform
import logging
from typing import Optional, List, Callable


class KiCadSettingsPaths:
    """Utility class for detecting KiCad settings paths across different operating systems."""

    @staticmethod
    def get_default_settings_path() -> str:
        """Returns the default settings path for the current operating system."""
        system = platform.system()

        if system == "Windows":
            appdata = os.environ.get("APPDATA")
            return (
                os.path.join(appdata, "kicad")
                if appdata
                else os.path.expanduser("~/AppData/Roaming/kicad")
            )
        elif system == "Darwin":  # macOS
            return os.path.expanduser("~/Library/Preferences/kicad")
        else:  # Linux and Unix-like systems
            xdg_config = os.environ.get("XDG_CONFIG_HOME")
            return (
                os.path.join(xdg_config, "kicad")
                if xdg_config
                else os.path.expanduser("~/.config/kicad")
            )

    @staticmethod
    def find_all_possible_paths() -> List[str]:
        """Discovers all possible KiCad settings paths on the current system."""
        paths = []
        system = platform.system()

        try:
            if system == "Windows":
                paths.extend(
                    [
                        os.path.expanduser("~/AppData/Roaming/kicad"),
                        os.path.expanduser("~/AppData/Local/kicad"),
                        "C:/ProgramData/kicad",
                    ]
                )
                # Version-specific subdirectories
                for major in range(5, 12):
                    for minor in range(0, 10):
                        version_path = os.path.expanduser(
                            f"~/AppData/Roaming/kicad/{major}.{minor}"
                        )
                        if os.path.exists(version_path):
                            paths.append(version_path)

            elif system == "Darwin":  # macOS
                paths.extend(
                    [
                        os.path.expanduser("~/Library/Preferences/kicad"),
                        os.path.expanduser("~/Library/Application Support/kicad"),
                    ]
                )

            else:  # Linux and Unix-like systems
                paths.extend(
                    [
                        os.path.expanduser("~/.config/kicad"),
                        os.path.expanduser("~/.kicad"),
                        "/usr/share/kicad",
                        "/usr/local/share/kicad",
                    ]
                )
                xdg_config = os.environ.get(
                    "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
                )
                xdg_kicad_path = os.path.join(xdg_config, "kicad")
                if xdg_kicad_path not in paths:
                    paths.append(xdg_kicad_path)

        except (OSError, PermissionError) as e:
            print(f"Warning: Error accessing paths during discovery: {e}")

        return [path for path in paths if os.path.exists(path)]

    @staticmethod
    def find_actual_settings_path() -> Optional[str]:
        """Locates the actual KiCad settings path by searching for configuration files."""
        possible_paths = KiCadSettingsPaths.find_all_possible_paths()
        config_files = [
            "kicad_common.json",
            "eeschema.json",
            "pcbnew.json",
            "kicad.json",
        ]

        for path in possible_paths:
            try:
                for config_file in config_files:
                    if os.path.isfile(os.path.join(path, config_file)):
                        return path
            except (OSError, PermissionError):
                continue

        return KiCadSettingsPaths.get_default_settings_path()


class KiCadApp:
    """
    Simplified KiCad application interface with direct property access.

    All properties are loaded during initialization and can be accessed directly:
    - app.connection_type: "IPC", "SWIG", or "FALLBACK"
    - app.settings_path: Path to KiCad settings directory
    - app.version: Version tuple (e.g., (9, 0, 0))
    - app.full_version: Full version string with build info
    - app.project_name: Current project name (if available)
    - app.project_dir: Current project directory (if available)
    - app.board_filename: Current board filename (if available)
    - app.is_connected: Boolean indicating if KiCad connection is available
    """

    def __init__(self, prefer_ipc: bool = True, min_version: str = "8.0.0"):
        """
        Initializes the KiCad application interface and loads all properties.

        Args:
            prefer_ipc (bool): Whether to prefer IPC API over SWIG bindings
            min_version (str): Minimum required KiCad version
        """
        self.min_version = min_version
        self.connection_type = "FALLBACK"
        self.pcbnew = None
        self.kicad_ipc = None
        self.kipy_errors = None

        # Initialize all properties with default values
        self.settings_path = KiCadSettingsPaths.find_actual_settings_path()
        self.version = None
        self.full_version = "Unknown"
        self.project_name = None
        self.project_dir = None
        self.board_filename = None
        self.is_connected = False

        # Try to establish connection and load properties
        if prefer_ipc and self._try_init_ipc():
            self.connection_type = "IPC"
            self.is_connected = True
            self._load_ipc_properties()
        elif self._try_init_swig():
            self.connection_type = "SWIG"
            self.is_connected = True
            self._load_swig_properties()
        else:
            print(
                "Warning: Neither IPC API nor SWIG bindings available. Limited functionality."
            )

    def _setup_venv_path(self) -> None:
        """Sets up virtual environment path for IPC API imports."""
        try:
            venv = os.environ.get("VIRTUAL_ENV")
            if venv:
                version = f"python{sys.version_info.major}.{sys.version_info.minor}"
                venv_site_packages = os.path.join(venv, "lib", version, "site-packages")
                if venv_site_packages in sys.path:
                    sys.path.remove(venv_site_packages)
                sys.path.insert(0, venv_site_packages)
        except Exception as e:
            logging.exception("Error setting up virtual environment path")

    def _try_init_ipc(self) -> bool:
        """Attempts to initialize IPC API connection."""
        try:
            self._setup_venv_path()
            from kipy import KiCad, errors

            self.kipy_errors = errors
            self.kicad_ipc = KiCad()

            # Test connection
            self.kicad_ipc.get_version()
            return True

        except Exception as e:
            print(f"IPC API initialization failed: {e}")
            return False

    def _try_init_swig(self) -> bool:
        """Attempts to initialize SWIG (pcbnew) connection."""
        try:
            import pcbnew

            self.pcbnew = pcbnew
            return True
        except ImportError:
            print("SWIG bindings (pcbnew) not available")
            return False
        except Exception as e:
            print(f"SWIG initialization failed: {e}")
            return False

    def _load_ipc_properties(self) -> None:
        """Loads all properties using IPC API."""
        try:
            # Version information
            version_info = self.kicad_ipc.get_version()
            self.version = (version_info.major, version_info.minor, version_info.patch)
            self.full_version = version_info.full_version

            # Project and board information
            try:
                board = self.kicad_ipc.get_board()
                self.board_filename = board.name

                project = board.get_project()
                self.project_name = project.name
                self.project_dir = project.path

            except self.kipy_errors.ApiError:
                # No PCB open - this is normal
                pass
            except Exception as e:
                print(f"Warning: Could not load project information: {e}")

        except Exception as e:
            print(f"Error loading IPC properties: {e}")

    def _load_swig_properties(self) -> None:
        """Loads all properties using SWIG (pcbnew)."""
        try:
            # Settings path
            self.settings_path = self.pcbnew.SETTINGS_MANAGER().GetUserSettingsPath()

            # Version information
            version_str = self.pcbnew.Version()
            self.version = self._version_to_tuple(version_str)
            self.full_version = self.pcbnew.FullVersion()

            # Board and project information
            try:
                board = self.pcbnew.GetBoard()
                self.board_filename = board.GetFileName()

                if self.board_filename:
                    self.project_dir = os.path.dirname(self.board_filename)
                    self.project_name = os.path.splitext(
                        os.path.basename(self.board_filename)
                    )[0]

            except Exception as e:
                print(f"Warning: Could not load board information: {e}")

        except Exception as e:
            print(f"Error loading SWIG properties: {e}")

    def _version_to_tuple(self, version_str: str) -> Optional[tuple]:
        """Converts a version string to a tuple of integers."""
        try:
            clean_version = version_str.split("-")[0]
            return tuple(map(int, clean_version.split(".")))
        except (ValueError, AttributeError, TypeError):
            return None

    def get_board_filename(self) -> Optional[str]:
        """Returns the filename of the current board (legacy method)."""
        return self.board_filename

    def get_project_dir(self) -> Optional[str]:
        """Returns the directory of the current KiCad project (legacy method)."""
        return self.project_dir

    def path_settings(self) -> str:
        """Returns the settings path (legacy method)."""
        return self.settings_path

    def check_min_version(self, output_func: Callable[[str], None] = print) -> bool:
        """
        Checks if the current KiCad version meets the minimum required version.

        Args:
            output_func (callable): Function for outputting messages (default: print)

        Returns:
            bool: True if version is sufficient, False otherwise
        """
        try:
            min_version_tuple = self._version_to_tuple(self.min_version)

            if not self.version or self.version < min_version_tuple:
                output_func(f"KiCad Version: {self.full_version}")
                output_func(f"Minimum required KiCad version is {self.min_version}")
                output_func("This may limit the functionality of the plugin.")
                return False

            return True

        except Exception as e:
            print(f"Error during KiCad version check: {e}")
            return False

    def refresh_project_info(self) -> None:
        """
        Refreshes project and board information.
        Useful when project has changed after initialization.
        """
        if self.connection_type == "IPC":
            self._load_ipc_project_info()
        elif self.connection_type == "SWIG":
            self._load_swig_project_info()

    def _load_ipc_project_info(self) -> None:
        """Refreshes project info using IPC API."""
        try:
            board = self.kicad_ipc.get_board()
            self.board_filename = board.name

            project = board.get_project()
            self.project_name = project.name
            self.project_dir = project.path

        except self.kipy_errors.ApiError:
            self.board_filename = None
            self.project_name = None
            self.project_dir = None
        except Exception as e:
            print(f"Error refreshing IPC project info: {e}")

    def _load_swig_project_info(self) -> None:
        """Refreshes project info using SWIG."""
        try:
            board = self.pcbnew.GetBoard()
            self.board_filename = board.GetFileName()

            if self.board_filename:
                self.project_dir = os.path.dirname(self.board_filename)
                self.project_name = os.path.splitext(
                    os.path.basename(self.board_filename)
                )[0]
            else:
                self.project_dir = None
                self.project_name = None

        except Exception as e:
            print(f"Error refreshing SWIG project info: {e}")

    def get_info(self) -> dict:
        """Returns all loaded information as a dictionary."""
        return {
            "connection_type": self.connection_type,
            "is_connected": self.is_connected,
            "settings_path": self.settings_path,
            "version": self.version,
            "full_version": self.full_version,
            "project_name": self.project_name,
            "project_dir": self.project_dir,
            "board_filename": self.board_filename,
            "min_version": self.min_version,
            "version_sufficient": self.check_min_version(lambda x: None),
        }

    def print_info(self) -> None:
        """Prints a formatted summary of all loaded information."""
        print("=== KiCad Application Information ===")
        print(f"Connection Type: {self.connection_type}")
        print(f"Connected: {self.is_connected}")
        print(f"Settings Path: {self.settings_path}")
        print(f"Version: {self.full_version}")

        if self.check_min_version(lambda x: None):
            print("✓ Version meets requirements")
        else:
            print("⚠ Version may be insufficient")

        if self.is_connected:
            print("\n=== Project Information ===")
            if self.project_name:
                print(f"Project Name: {self.project_name}")
            if self.project_dir:
                print(f"Project Directory: {self.project_dir}")
            if self.board_filename:
                print(f"Board Filename: {self.board_filename}")
            if not any([self.project_name, self.project_dir, self.board_filename]):
                print("No project currently open or accessible")


# Ersetzt die alte connect_kicad() Funktion
def connect_kicad():
    """Legacy function for backward compatibility."""
    app = KiCadApp(prefer_ipc=True)
    if app.connection_type == "IPC":
        return app.kicad_ipc
    else:
        print("Not connected to KiCad IPC API")
        return None


def main():
    """Example usage of the simplified KiCad application interface."""
    # Initialize KiCad app - all properties are loaded automatically
    app = KiCadApp(prefer_ipc=True, min_version="9.0.0")

    # Direct access to all properties
    print(f"Connection: {app.connection_type}")
    print(f"Project: {app.project_name}")
    print(f"Directory: {app.project_dir}")

    # Or print complete information
    app.print_info()

    # Check version requirements
    if app.check_min_version():
        print("Ready to proceed with plugin functionality")
    else:
        print("Version check failed")

    # Refresh project info if needed
    app.refresh_project_info()


if __name__ == "__main__":
    main()
