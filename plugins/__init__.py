import logging
import subprocess
import sys
import platform
from pathlib import Path
import pcbnew

# Plugin setup
plugin_dir = Path(__file__).resolve().parent
venv_dir = plugin_dir / "venv"
log_file = plugin_dir / "plugin.log"

# Platform-specific paths
IS_WINDOWS = platform.system().lower() == "windows"
VENV_PYTHON = (
    venv_dir
    / ("Scripts" if IS_WINDOWS else "bin")
    / ("python.exe" if IS_WINDOWS else "python")
)
VENV_PIP = (
    venv_dir
    / ("Scripts" if IS_WINDOWS else "bin")
    / ("pip.exe" if IS_WINDOWS else "pip")
)

# Setup logging
try:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s [%(name)s:%(filename)s:%(lineno)d]: %(message)s",
        filename=str(log_file),
        filemode="w",
        force=True,
    )
    logging.info(f"Plugin initialization started on {platform.system()}")
    logging.info(f"Python executable: {sys.executable}")
    logging.info(f"Plugin directory: {plugin_dir}")
except Exception as e:
    print(f"Logging setup failed: {e}")


def show_error_dialog(title, message):
    """Show error dialog with fallback to console."""
    try:
        import wx

        app = wx.App() if not wx.GetApp() else None
        wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR)
        if app:
            app.Destroy()
    except Exception:
        print(f"Error: {title} - {message}")


def ensure_venv():
    """Cross-platform venv setup with kiutils support."""
    pyvenv_cfg = venv_dir / "pyvenv.cfg"

    logging.info(f"Checking virtual environment at: {venv_dir}")
    logging.info(f"Platform: {platform.system()}, Python path: {VENV_PYTHON}")

    # Check if venv exists and find site-packages
    site_packages = None
    if pyvenv_cfg.exists() and VENV_PYTHON.exists():
        if IS_WINDOWS:
            site_packages_dirs = list(venv_dir.glob("Lib/site-packages"))
        else:
            site_packages_dirs = list(venv_dir.glob("lib/python*/site-packages"))

        if site_packages_dirs:
            site_packages = site_packages_dirs[0]

            # Check if all required dependencies are installed
            required_deps = ["pydantic", "requests", "easyeda2kicad"]
            missing_deps = []

            for dep in required_deps:
                if not (site_packages / dep).exists():
                    missing_deps.append(dep)
                    logging.info(f"Missing dependency: {dep}")

            if not missing_deps:
                # All dependencies present - setup paths and return
                site_packages_str = str(site_packages)
                if site_packages_str not in sys.path:
                    sys.path.insert(0, site_packages_str)

                # Add kiutils path for bundled kiutils
                kiutils_src = plugin_dir / "kiutils" / "src"
                if kiutils_src.exists():
                    kiutils_str = str(kiutils_src)
                    if kiutils_str not in sys.path:
                        sys.path.insert(0, kiutils_str)
                        logging.info(f"✓ Added kiutils to sys.path: {kiutils_str}")

                logging.info(
                    f"✓ Using existing virtual environment: {site_packages_str}"
                )
                return True
            else:
                logging.info(f"Missing dependencies in existing venv: {missing_deps}")
                # Continue to install missing dependencies
        else:
            logging.warning("venv exists but no site-packages found, recreating...")

    # Need to create venv or install missing dependencies
    venv_exists = pyvenv_cfg.exists() and VENV_PYTHON.exists()

    if not venv_exists:
        logging.info("Creating new virtual environment...")
        try:
            # Determine Python command for venv creation
            if IS_WINDOWS:
                # Unter Windows: Verwende 'python' command
                python_cmd = "python"
                try:
                    # Test ob python verfügbar ist
                    test_result = subprocess.run(
                        [python_cmd, "--version"],
                        capture_output=True,
                        check=True,
                        timeout=30,
                    )
                    logging.info(
                        f"Using python command: {python_cmd} (version: {test_result.stdout.decode().strip()})"
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    python_cmd = "python3"
                    try:
                        test_result = subprocess.run(
                            [python_cmd, "--version"],
                            capture_output=True,
                            check=True,
                            timeout=30,
                        )
                        logging.info(
                            f"Using python3 command: {python_cmd} (version: {test_result.stdout.decode().strip()})"
                        )
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        logging.error(
                            "Neither 'python' nor 'python3' command available"
                        )
                        return False
            else:
                python_cmd = sys.executable
                logging.info(f"Using system Python: {python_cmd}")

            # Create venv
            logging.info(f"Running: {python_cmd} -m venv {venv_dir}")
            result = subprocess.run(
                [python_cmd, "-m", "venv", str(venv_dir)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                logging.error(f"venv creation failed: {result.stderr}")
                return False

            logging.info("✓ Virtual environment created")

            # Verify python exists
            if not VENV_PYTHON.exists():
                logging.error(f"venv python not found at: {VENV_PYTHON}")
                return False

            # Upgrade pip first (especially important on Windows)
            logging.info("Upgrading pip...")
            pip_upgrade = subprocess.run(
                [str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if pip_upgrade.returncode == 0:
                logging.info("✓ pip upgraded")
            else:
                logging.warning(f"pip upgrade warning: {pip_upgrade.stderr}")

        except subprocess.TimeoutExpired:
            logging.error("venv creation timed out")
            return False
        except Exception as e:
            logging.error(f"venv creation failed: {e}")
            return False
    else:
        logging.info("Virtual environment exists, installing missing dependencies...")

    # Install dependencies (always run this part if we get here)
    try:
        logging.info("Installing dependencies (pydantic, requests, easyeda2kicad)...")
        result = subprocess.run(
            [
                str(VENV_PYTHON),
                "-m",
                "pip",
                "install",
                "pydantic>=2.0.0",
                "requests>=2.0.0",
                "easyeda2kicad",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logging.error(f"Dependency installation failed: {result.stderr}")
            # Try without version constraints as fallback
            logging.info("Retrying without version constraints...")
            result = subprocess.run(
                [
                    str(VENV_PYTHON),
                    "-m",
                    "pip",
                    "install",
                    "pydantic",
                    "requests",
                    "easyeda2kicad",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logging.error(f"Fallback installation also failed: {result.stderr}")
                return False

        logging.info("✓ Dependencies installed successfully")

    except subprocess.TimeoutExpired:
        logging.error("Dependency installation timed out")
        return False
    except Exception as e:
        logging.error(f"Dependency installation failed: {e}")
        return False

    # Setup paths after successful installation
    try:
        # Find and add site-packages to path (cross-platform)
        if IS_WINDOWS:
            site_packages_dirs = list(venv_dir.glob("Lib/site-packages"))
        else:
            site_packages_dirs = list(venv_dir.glob("lib/python*/site-packages"))

        if site_packages_dirs:
            site_packages_str = str(site_packages_dirs[0])
            if site_packages_str not in sys.path:
                sys.path.insert(0, site_packages_str)
                logging.info(
                    f"✓ Added venv site-packages to sys.path: {site_packages_str}"
                )
        else:
            logging.error("No site-packages directory found after installation")
            return False

        # Add kiutils path for bundled kiutils
        kiutils_src = plugin_dir / "kiutils" / "src"
        if kiutils_src.exists():
            kiutils_str = str(kiutils_src)
            if kiutils_str not in sys.path:
                sys.path.insert(0, kiutils_str)
                logging.info(f"✓ Added kiutils to sys.path: {kiutils_str}")
        else:
            logging.warning(f"kiutils directory not found at: {kiutils_src}")

        # Add plugin directory to path for local imports
        plugin_dir_str = str(plugin_dir)
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)
            logging.info(f"✓ Added plugin directory to sys.path: {plugin_dir_str}")

        logging.info("✓ Virtual environment setup completed")

        # Verify imports work
        try:
            import pydantic

            logging.info(f"✓ pydantic {pydantic.__version__} available")
        except ImportError as e:
            logging.warning(f"⚠ pydantic import failed: {e}")

        try:
            import requests

            logging.info(f"✓ requests {requests.__version__} available")
        except ImportError as e:
            logging.warning(f"⚠ requests import failed: {e}")

        try:
            import easyeda2kicad

            logging.info(f"✓ easyeda2kicad available")
        except ImportError as e:
            logging.warning(f"⚠ easyeda2kicad import failed: {e}")

        try:
            from kiutils.libraries import LibTable, Library

            logging.info("✓ kiutils.libraries available")
        except ImportError as e:
            logging.warning(f"⚠ kiutils.libraries import failed: {e}")

        return True

    except Exception as e:
        logging.error(f"Path setup failed: {e}")
        return False


class ActionImpartPlugin(pcbnew.ActionPlugin):
    """KiCad Action Plugin for library import with virtual environment."""

    def defaults(self):
        self.name = "impartGUI (fallback pcbnew)"
        self.category = "Import library files"
        self.description = "Import library files from Octopart, Samacsys, Ultralibrarian, Snapeda and EasyEDA"
        self.show_toolbar_button = True

        icon_path = plugin_dir / "icon.png"
        self.icon_file_name = str(icon_path)
        self.dark_icon_file_name = str(icon_path)

    def Run(self):
        """Run the plugin with virtual environment setup."""
        try:
            logging.info("Plugin started")

            # Setup virtual environment and dependencies
            if not ensure_venv():
                error_msg = (
                    "Virtual Environment Setup Failed\n\n"
                    "The plugin could not set up its virtual environment.\n"
                    "This is required for proper dependency management.\n\n"
                    f"Check log file for details: {log_file}"
                )
                show_error_dialog("Environment Setup Failed", error_msg)
                return

            logging.info("Virtual environment ready - starting plugin frontend")

            # Import and run the main plugin
            from .impart_action import ImpartFrontend

            frontend = ImpartFrontend()
            frontend.ShowModal()
            frontend.Destroy()

            logging.info("Plugin completed")

        except Exception as e:
            # Handle all errors with detailed information
            logging.exception("Plugin error occurred")

            import traceback

            full_traceback = traceback.format_exc()
            logging.error(f"Full traceback:\n{full_traceback}")

            detailed_msg = (
                f"Plugin Error Details:\n\n"
                f"Error: {str(e)}\n"
                f"Type: {type(e).__name__}\n\n"
                f"Check log file for full traceback:\n{log_file}\n\n"
                f"Full error:\n{full_traceback}"
            )

            show_error_dialog("Plugin Error", detailed_msg)


ActionImpartPlugin().register()
