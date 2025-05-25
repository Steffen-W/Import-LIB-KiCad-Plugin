"""
KiCad Settings Paths and Application Interface Module

Provides utilities for detecting KiCad settings paths across different operating systems
and a simplified interface for interacting with KiCad applications.
"""

import sys
import platform
import logging
from typing import Optional, List, Callable, Dict, Any, Tuple
from pathlib import Path


class KiCadSettingsPaths:
    """Utility class for detecting KiCad settings paths across different operating systems."""

    @staticmethod
    def get_default_settings_path() -> Path:
        """Returns the default settings path for the current operating system."""
        system = platform.system()
        home = Path.home()

        if system == "Windows":
            return home / "AppData" / "Roaming" / "kicad"
        elif system == "Darwin":  # macOS
            return home / "Library" / "Preferences" / "kicad"
        else:  # Linux and Unix-like systems
            # Check XDG_CONFIG_HOME environment variable
            import os

            xdg_config = os.environ.get("XDG_CONFIG_HOME")
            if xdg_config:
                return Path(xdg_config) / "kicad"
            return home / ".config" / "kicad"

    @staticmethod
    def find_all_possible_paths() -> List[Path]:
        """Discovers all possible KiCad settings paths on the current system."""
        paths: List[Path] = []
        system = platform.system()
        home = Path.home()

        try:
            if system == "Windows":
                base_paths = [
                    home / "AppData" / "Roaming" / "kicad",
                    home / "AppData" / "Local" / "kicad",
                    Path("C:/ProgramData/kicad"),
                ]
                paths.extend(base_paths)

                # Version-specific subdirectories
                roaming_kicad = home / "AppData" / "Roaming" / "kicad"
                if roaming_kicad.exists():
                    for major in range(5, 12):
                        for minor in range(0, 10):
                            version_path = roaming_kicad / f"{major}.{minor}"
                            if version_path.exists():
                                paths.append(version_path)

            elif system == "Darwin":  # macOS
                paths.extend(
                    [
                        home / "Library" / "Preferences" / "kicad",
                        home / "Library" / "Application Support" / "kicad",
                    ]
                )

            else:  # Linux and Unix-like systems
                paths.extend(
                    [
                        home / ".config" / "kicad",
                        home / ".kicad",
                        Path("/usr/share/kicad"),
                        Path("/usr/local/share/kicad"),
                    ]
                )

                # Check XDG_CONFIG_HOME
                import os

                xdg_config = os.environ.get("XDG_CONFIG_HOME")
                if xdg_config:
                    xdg_kicad_path = Path(xdg_config) / "kicad"
                    if xdg_kicad_path not in paths:
                        paths.append(xdg_kicad_path)

        except (OSError, PermissionError) as e:
            print(f"Warning: Error accessing paths during discovery: {e}")

        return [path for path in paths if path.exists()]

    @staticmethod
    def find_actual_settings_path() -> Path:
        """
        Locates the actual KiCad settings path by searching for configuration files.
        Returns the default path if no actual settings are found.
        """
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
                    config_path = path / config_file
                    if config_path.is_file():
                        return path
            except (OSError, PermissionError):
                continue

        return KiCadSettingsPaths.get_default_settings_path()


class KiCadVersionInfo:
    """Container for KiCad version information."""

    def __init__(self, version_tuple: Tuple[int, int, int], full_version: str):
        self.major, self.minor, self.patch = version_tuple
        self.version_tuple = version_tuple
        self.full_version = full_version

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self) -> str:
        return f"KiCadVersionInfo({self.version_tuple}, '{self.full_version}')"


class KiCadProjectInfo:
    """Container for KiCad project information."""

    def __init__(
        self,
        name: Optional[str] = None,
        directory: Optional[Path] = None,
        board_filename: Optional[Path] = None,
    ):
        self.name = name
        self.directory = directory
        self.board_filename = board_filename

    @property
    def is_valid(self) -> bool:
        """Returns True if project information is available."""
        return any([self.name, self.directory, self.board_filename])

    @property
    def directory_str(self) -> Optional[str]:
        """Returns directory as string for backward compatibility."""
        return str(self.directory) if self.directory else None

    @property
    def board_filename_str(self) -> Optional[str]:
        """Returns board filename as string for backward compatibility."""
        return str(self.board_filename) if self.board_filename else None


class KiCadApp:
    """
    Simplified KiCad application interface with direct property access.

    All properties are loaded during initialization and can be accessed directly:
    - app.connection_type: "IPC", "SWIG", or "FALLBACK"
    - app.settings_path: Path to KiCad settings directory
    - app.version_info: KiCadVersionInfo object with version details
    - app.project_info: KiCadProjectInfo object with project details
    - app.is_connected: Boolean indicating if KiCad connection is available
    """

    def __init__(self, prefer_ipc: bool = True, min_version: str = "8.0.0"):
        """
        Initializes the KiCad application interface and loads all properties.

        Args:
            prefer_ipc: Whether to prefer IPC API over SWIG bindings
            min_version: Minimum required KiCad version
        """
        self.min_version = min_version
        self.connection_type: str = "FALLBACK"
        self.pcbnew: Optional[Any] = None
        self.kicad_ipc: Optional[Any] = None
        self.kipy_errors: Optional[Any] = None

        # Initialize all properties with default values
        self.settings_path: Path = KiCadSettingsPaths.find_actual_settings_path()
        self.version_info: Optional[KiCadVersionInfo] = None
        self.project_info: KiCadProjectInfo = KiCadProjectInfo()
        self.is_connected: bool = False

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
            import os

            venv = os.environ.get("VIRTUAL_ENV")
            if venv:
                venv_path = Path(venv)
                version = f"python{sys.version_info.major}.{sys.version_info.minor}"
                venv_site_packages = venv_path / "lib" / version / "site-packages"

                venv_site_packages_str = str(venv_site_packages)
                if venv_site_packages_str in sys.path:
                    sys.path.remove(venv_site_packages_str)
                sys.path.insert(0, venv_site_packages_str)
        except Exception as e:
            logging.exception("Error setting up virtual environment path: %s", e)

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

        except ImportError:
            print("KiCad IPC API not available")
            return False
        except Exception as e:
            print(f"KiCad IPC API initialization failed: {e}")
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
        if not self.kicad_ipc or not self.kipy_errors:
            return

        try:
            # Version information
            version_info = self.kicad_ipc.get_version()
            version_tuple = (version_info.major, version_info.minor, version_info.patch)
            self.version_info = KiCadVersionInfo(
                version_tuple, version_info.full_version
            )

            # Project and board information
            self._load_ipc_project_info()

        except Exception as e:
            print(f"Error loading IPC properties: {e}")

    def _load_swig_properties(self) -> None:
        """Loads all properties using SWIG (pcbnew)."""
        if not self.pcbnew:
            return

        try:
            # Settings path
            settings_manager = self.pcbnew.SETTINGS_MANAGER()
            settings_path_str = settings_manager.GetUserSettingsPath()
            self.settings_path = Path(settings_path_str)

            # Version information
            version_str = self.pcbnew.Version()
            version_tuple = self._version_to_tuple(version_str)
            full_version = self.pcbnew.FullVersion()
            self.version_info = KiCadVersionInfo(version_tuple, full_version)

            # Board and project information
            self._load_swig_project_info()

        except Exception as e:
            print(f"Error loading SWIG properties: {e}")

    def _version_to_tuple(self, version_str: str) -> Tuple[int, int, int]:
        """Converts a version string to a tuple of integers."""
        try:
            clean_version = version_str.split("-")[0]
            parts = clean_version.split(".")
            # Ensure we have at least 3 parts
            while len(parts) < 3:
                parts.append("0")
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, AttributeError, TypeError, IndexError):
            return (0, 0, 0)

    def _load_ipc_project_info(self) -> None:
        """Loads project info using IPC API."""
        if not self.kicad_ipc or not self.kipy_errors:
            return

        try:
            board = self.kicad_ipc.get_board()
            board_filename = Path(board.name) if board.name else None

            project = board.get_project()
            project_name = project.name
            project_dir = Path(project.path) if project.path else None

            self.project_info = KiCadProjectInfo(
                name=project_name, directory=project_dir, board_filename=board_filename
            )

        except self.kipy_errors.ApiError:
            # No PCB open - this is normal
            self.project_info = KiCadProjectInfo()
        except Exception as e:
            print(f"Warning: Could not load project information: {e}")
            self.project_info = KiCadProjectInfo()

    def _load_swig_project_info(self) -> None:
        """Loads project info using SWIG."""
        if not self.pcbnew:
            return

        try:
            board = self.pcbnew.GetBoard()
            board_filename_str = board.GetFileName()

            project_name = None
            project_dir = None
            board_filename = None

            if board_filename_str:
                board_filename = Path(board_filename_str)
                project_dir = board_filename.parent
                project_name = board_filename.stem

            self.project_info = KiCadProjectInfo(
                name=project_name, directory=project_dir, board_filename=board_filename
            )

        except Exception as e:
            print(f"Warning: Could not load board information: {e}")
            self.project_info = KiCadProjectInfo()

    @property
    def version(self) -> Optional[Tuple[int, int, int]]:
        """Returns version tuple."""
        return self.version_info.version_tuple if self.version_info else None

    @property
    def full_version(self) -> str:
        """Returns full version string."""
        return self.version_info.full_version if self.version_info else "Unknown"

    @property
    def project_name(self) -> Optional[str]:
        """Returns project name."""
        return self.project_info.name

    @property
    def project_dir(self) -> Optional[str]:
        """Returns project directory as string."""
        return self.project_info.directory_str

    @property
    def board_filename(self) -> Optional[str]:
        """Returns board filename as string."""
        return self.project_info.board_filename_str

    def get_board_filename(self) -> Optional[str]:
        """Returns the filename of the current board."""
        return self.board_filename

    def get_project_dir(self) -> Optional[str]:
        """Returns the directory of the current KiCad project."""
        return self.project_dir

    def path_settings(self) -> str:
        """Returns the settings path as string."""
        return str(self.settings_path)

    def check_min_version(self, output_func: Callable[[str], None] = print) -> bool:
        """
        Checks if the current KiCad version meets the minimum required version.

        Args:
            output_func: Function for outputting messages (default: print)

        Returns:
            True if version is sufficient, False otherwise
        """
        try:
            min_version_tuple = self._version_to_tuple(self.min_version)

            if (
                not self.version_info
                or self.version_info.version_tuple < min_version_tuple
            ):
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

    def get_info(self) -> Dict[str, Any]:
        """Returns all loaded information as a dictionary."""
        return {
            "connection_type": self.connection_type,
            "is_connected": self.is_connected,
            "settings_path": str(self.settings_path),
            "version": self.version,
            "full_version": self.full_version,
            "project_name": self.project_name,
            "project_dir": self.project_dir,
            "board_filename": self.board_filename,
            "min_version": self.min_version,
            "version_sufficient": self.check_min_version(lambda x: None),
            "project_valid": self.project_info.is_valid,
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
            if self.project_info.is_valid:
                if self.project_name:
                    print(f"Project Name: {self.project_name}")
                if self.project_dir:
                    print(f"Project Directory: {self.project_dir}")
                if self.board_filename:
                    print(f"Board Filename: {self.board_filename}")
            else:
                print("No project currently open or accessible")


def connect_kicad() -> Optional[Any]:
    """
    Connect to KiCad IPC API

    Returns:
        KiCad IPC connection object or None if not available
    """
    app = KiCadApp(prefer_ipc=True)
    if app.connection_type == "IPC":
        return app.kicad_ipc
    else:
        print("Not connected to KiCad IPC API")
        return None


def main() -> None:
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
    if not app.check_min_version():
        print("Version check failed")

    # Refresh project info if needed
    app.refresh_project_info()


if __name__ == "__main__":
    main()
