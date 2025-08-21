import logging
import subprocess
import sys
import platform
import threading
import time
from pathlib import Path
import pcbnew

try:
    import wx
except ImportError:
    print("Error: wx not available - plugin cannot run without wxPython")
    sys.exit(1)

plugin_dir = Path(__file__).resolve().parent
venv_dir = plugin_dir / "venv"
log_file = plugin_dir / "plugin_fallback.log"

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

logger = None
log_handler = None


def setup_logging():
    global logger, log_handler

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("impart_plugin")
        logger.setLevel(logging.DEBUG)

        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

        log_handler = logging.FileHandler(
            str(log_file), mode="w", encoding="utf-8", delay=False
        )

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s:%(filename)s:%(lineno)d]: %(message)s"
        )
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

        logger.info(f"Plugin initialization started on {platform.system()}")
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Plugin directory: {plugin_dir}")

        return True

    except Exception as e:
        print(f"Logging setup failed: {e}")
        return False


def cleanup_logging():
    global logger, log_handler

    try:
        if log_handler:
            log_handler.close()
            if logger:
                logger.removeHandler(log_handler)

        import gc

        gc.collect()

    except Exception as e:
        print(f"Logging cleanup failed: {e}")


def show_error_dialog(title, message):
    """Show error dialog with fallback to console."""
    try:
        app = wx.App() if not wx.GetApp() else None
        wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR)
        if app:
            app.Destroy()
    except Exception:
        print(f"Error: {title} - {message}")


class ProgressDialog:
    def __init__(self):
        self.dialog = None
        self.progress_bar = None
        self.status_text = None
        self.log_text = None
        self.start_button = None
        self.close_button = None
        self.app = None
        self.should_close = False
        self.setup_failed = False
        self.setup_running = False
        self.setup_success = False

    def create_dialog(self):
        try:
            self.app = wx.App() if not wx.GetApp() else None

            self.dialog = wx.Dialog(
                None,
                title="impartGUI - Environment Setup",
                style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            )
            self.dialog.SetSize(600, 500)

            sizer = wx.BoxSizer(wx.VERTICAL)

            title = wx.StaticText(
                self.dialog, label="impartGUI Plugin - Environment Setup"
            )
            title_font = title.GetFont()
            title_font.SetWeight(wx.FONTWEIGHT_BOLD)
            title_font.SetPointSize(12)
            title.SetFont(title_font)
            sizer.Add(title, 0, wx.ALL | wx.CENTER, 10)

            explanation = wx.StaticText(
                self.dialog,
                label=(
                    "This is the fallback solution (pcbnew). Dependencies must be installed.\n"
                    "Click 'Start Integration' to begin setup.\n\n"
                    "Alternative: Use the KiCad IPC API instead:\n"
                    "Settings → Plugins → Activate KiCad API"
                ),
            )
            explanation.Wrap(550)
            sizer.Add(explanation, 0, wx.ALL | wx.EXPAND, 10)

            self.status_text = wx.StaticText(self.dialog, label="Ready to start...")
            sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 10)
            self.status_text.Hide()

            self.progress_bar = wx.Gauge(self.dialog, range=100)
            sizer.Add(self.progress_bar, 0, wx.ALL | wx.EXPAND, 10)
            self.progress_bar.Hide()

            log_label = wx.StaticText(self.dialog, label="Details:")
            sizer.Add(log_label, 0, wx.ALL, 10)

            self.log_text = wx.TextCtrl(
                self.dialog, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP
            )
            self.log_text.SetFont(
                wx.Font(
                    9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL
                )
            )
            sizer.Add(self.log_text, 1, wx.ALL | wx.EXPAND, 10)
            self.log_text.SetValue(
                "Click 'Start Integration' to begin the setup process."
            )

            button_sizer = wx.BoxSizer(wx.HORIZONTAL)

            self.start_button = wx.Button(self.dialog, label="Start Integration")
            self.start_button.Bind(wx.EVT_BUTTON, self.on_start_clicked)
            button_sizer.Add(self.start_button, 0, wx.ALL, 5)

            self.close_button = wx.Button(self.dialog, wx.ID_CLOSE, "Close")
            self.close_button.Bind(wx.EVT_BUTTON, self.on_close_clicked)
            button_sizer.Add(self.close_button, 0, wx.ALL, 5)

            sizer.Add(button_sizer, 0, wx.ALL | wx.CENTER, 10)

            self.dialog.SetSizer(sizer)
            self.dialog.Center()

            self.dialog.Bind(wx.EVT_CLOSE, self.on_close)

            logger.info("Progress dialog created")
            return True

        except Exception as e:
            logger.error(f"Failed to create progress dialog: {e}")
            return False

    def on_start_clicked(self, event):
        if self.setup_running:
            return

        self.setup_running = True
        self.setup_failed = False
        self.setup_success = False

        self.start_button.Enable(False)
        self.close_button.Enable(False)

        self.status_text.SetLabel("Starting environment setup...")
        self.status_text.Show()
        self.progress_bar.Show()
        self.progress_bar.SetValue(0)
        self.dialog.Layout()

        self.log_text.Clear()
        self.add_log("Starting virtual environment setup...")

        setup_thread = threading.Thread(target=self._run_setup)
        setup_thread.daemon = True
        setup_thread.start()

    def _run_setup(self):
        try:
            success = ensure_venv(self)
            wx.CallAfter(self._setup_completed, success)
        except Exception as e:
            logger.error(f"Setup thread error: {e}")
            wx.CallAfter(self._setup_completed, False, str(e))

    def _setup_completed(self, success, error_msg=None):
        self.setup_running = False
        self.setup_success = success
        self.setup_failed = not success

        if success:
            self.update_status("Setup completed successfully!", 100)
            self.add_log("✓ Environment setup completed successfully!")
            self.add_log("You can now close this dialog and the plugin will start.")

            self.close_button.SetLabel("Continue")
            self.close_button.Enable(True)

        else:
            self.update_status("Setup failed!", 0)
            self.progress_bar.SetValue(0)

            if error_msg:
                self.add_log(f"✗ ERROR: Setup failed: {error_msg}")

            log_diagnostic_info()

            self.add_log(
                "Please activate KiCad IPC API to avoid relying on the fallback solution:"
            )
            self.add_log("Settings → Plugins → Activate KiCad API")
            self.add_log("You can retry the setup or close this dialog.")

            self.close_button.SetLabel("Close")
            self.close_button.Enable(True)
            self.start_button.SetLabel("Retry Setup")
            self.start_button.Enable(True)

    def on_close_clicked(self, event):
        if self.setup_running:
            # Ask user if they want to cancel
            dlg = wx.MessageDialog(
                self.dialog,
                "Setup is still running. Do you want to cancel?",
                "Cancel Setup",
                wx.YES_NO | wx.ICON_QUESTION,
            )
            result = dlg.ShowModal()
            dlg.Destroy()

            if result == wx.ID_YES:
                self.setup_running = False
                self.should_close = True
                self.dialog.Close()
        else:
            self.should_close = True
            self.dialog.Close()

    def on_close(self, event):
        if self.setup_running:
            return
        event.Skip()

    def update_status(self, message, progress=None):
        try:
            wx.CallAfter(self._update_status_safe, message, progress)
        except Exception as e:
            logger.error(f"Failed to update status: {e}")

    def add_log(self, message):
        try:
            wx.CallAfter(self._add_log_safe, message)
        except Exception as e:
            logger.error(f"Failed to add log: {e}")

    def _update_status_safe(self, message, progress):
        try:
            if self.status_text:
                self.status_text.SetLabel(message)
            if progress is not None and self.progress_bar:
                self.progress_bar.SetValue(progress)
            self.dialog.Layout()
            self.dialog.Update()
            wx.SafeYield()
        except Exception as e:
            logger.error(f"Failed to update status safely: {e}")

    def _add_log_safe(self, message):
        try:
            if self.log_text:
                self.log_text.AppendText(message + "\n")
                # Scroll to bottom
                self.log_text.SetInsertionPointEnd()
                wx.SafeYield()
        except Exception as e:
            logger.error(f"Failed to add log safely: {e}")


def run_subprocess_safe(cmd, timeout=300, **kwargs):
    """Run subprocess with proper cleanup and error handling"""
    process = None
    try:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
        kwargs.setdefault("universal_newlines", True)
        if sys.platform == "win32":
            kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)

        process = subprocess.Popen(cmd, **kwargs)
        stdout, stderr = process.communicate(timeout=timeout)
        return_code = process.returncode

        return type(
            "Result",
            (),
            {"returncode": return_code, "stdout": stdout, "stderr": stderr},
        )()

    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            try:
                process.communicate(timeout=5)
            except:
                pass
        raise
    except Exception:
        if process and process.poll() is None:
            process.kill()
        raise
    finally:
        if process:
            try:
                if hasattr(process, "stdout") and process.stdout:
                    process.stdout.close()
                if hasattr(process, "stderr") and process.stderr:
                    process.stderr.close()
                if hasattr(process, "stdin") and process.stdin:
                    process.stdin.close()
            except:
                pass


def check_venv_ready():
    """Check if virtual environment is ready to use"""
    pyvenv_cfg = venv_dir / "pyvenv.cfg"

    if not (pyvenv_cfg.exists() and VENV_PYTHON.exists()):
        return False

    # Find site-packages directory
    if IS_WINDOWS:
        site_packages_dirs = list(venv_dir.glob("Lib/site-packages"))
    else:
        site_packages_dirs = list(venv_dir.glob("lib/python*/site-packages"))

    if not site_packages_dirs:
        return False

    site_packages = site_packages_dirs[0]

    # Check for required dependencies
    required_deps = ["pydantic", "requests"]
    for dep in required_deps:
        if not (site_packages / dep).exists():
            return False

    return True


def get_python_command():
    """Get the appropriate Python command for the current platform"""
    if IS_WINDOWS:
        for cmd in ["python", "python3"]:
            try:
                result = run_subprocess_safe([cmd, "--version"], timeout=10)
                if result.returncode == 0:
                    return cmd, result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError, OSError):
                continue
        raise RuntimeError("Neither 'python' nor 'python3' command available")
    else:
        try:
            result = run_subprocess_safe([sys.executable, "--version"], timeout=10)
            return sys.executable, result.stdout.strip()
        except Exception:
            return sys.executable, f"Python {sys.version.split()[0]}"


def check_platform_requirements():
    """Check platform-specific requirements"""
    system = platform.system().lower()
    issues = []

    if system == "darwin":  # macOS
        if not sys.executable.endswith("framework/Versions"):
            issues.append("macOS: Framework Python recommended for wxPython GUI access")

    elif system == "linux":
        try:
            import subprocess

            creation_flags = (
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            result = subprocess.run(
                ["which", "gcc"], capture_output=True, creationflags=creation_flags
            )
            if result.returncode != 0:
                issues.append(
                    "Linux: GCC compiler not found, may be needed for package compilation"
                )
        except Exception:
            pass

    return issues


def ensure_venv(progress_dialog=None):
    """Ensure virtual environment is set up with required dependencies"""
    pyvenv_cfg = venv_dir / "pyvenv.cfg"

    logger.info(f"Checking virtual environment at: {venv_dir}")
    logger.info(f"Platform: {platform.system()}, Python path: {VENV_PYTHON}")

    if progress_dialog:
        progress_dialog.update_status("Checking virtual environment...", 10)

    # Check if venv exists and has dependencies
    if pyvenv_cfg.exists() and VENV_PYTHON.exists():
        if progress_dialog:
            progress_dialog.add_log(
                "Found existing virtual environment, checking dependencies..."
            )

        # Find site-packages
        if IS_WINDOWS:
            site_packages_dirs = list(venv_dir.glob("Lib/site-packages"))
        else:
            site_packages_dirs = list(venv_dir.glob("lib/python*/site-packages"))

        if site_packages_dirs:
            site_packages = site_packages_dirs[0]
            required_deps = ["pydantic", "requests"]
            missing_deps = [
                dep for dep in required_deps if not (site_packages / dep).exists()
            ]

            if not missing_deps:
                # All dependencies present, set up paths
                setup_python_paths(site_packages)

                if progress_dialog:
                    progress_dialog.update_status("Environment ready!", 100)
                    progress_dialog.add_log(
                        "✓ Using existing virtual environment with all dependencies"
                    )

                logger.info(f"✓ Using existing virtual environment: {site_packages}")
                return True
            else:
                logger.info(f"Missing dependencies in existing venv: {missing_deps}")
                if progress_dialog:
                    progress_dialog.add_log(
                        f"Missing dependencies: {', '.join(missing_deps)}"
                    )

    # Create or recreate venv
    venv_exists = pyvenv_cfg.exists() and VENV_PYTHON.exists()

    if not venv_exists:
        if progress_dialog:
            progress_dialog.update_status("Creating virtual environment...", 20)
            progress_dialog.add_log("Creating new virtual environment...")

        logger.info("Creating new virtual environment...")

        try:
            python_cmd, python_version = get_python_command()

            if progress_dialog:
                progress_dialog.add_log(f"Using: {python_version}")

            logger.info(f"Using python command: {python_cmd} ({python_version})")

            # Create venv
            logger.info(f"Running: {python_cmd} -m venv {venv_dir}")
            result = run_subprocess_safe(
                [python_cmd, "-m", "venv", str(venv_dir)], timeout=120
            )

            if result.returncode != 0:
                error_msg = f"venv creation failed: {result.stderr}"
                logger.error(error_msg)
                log_diagnostic_info()
                if progress_dialog:
                    progress_dialog.add_log(f"✗ ERROR: {error_msg}")
                return False

            logger.info("✓ Virtual environment created")
            if progress_dialog:
                progress_dialog.add_log("✓ Virtual environment created successfully")

            if not VENV_PYTHON.exists():
                error_msg = f"venv python not found at: {VENV_PYTHON}"
                logger.error(error_msg)
                if progress_dialog:
                    progress_dialog.add_log(f"✗ ERROR: {error_msg}")
                return False

        except Exception as e:
            error_msg = f"venv creation failed: {e}"
            logger.error(error_msg)
            log_diagnostic_info()
            if progress_dialog:
                progress_dialog.add_log(f"✗ ERROR: {error_msg}")
            return False

    # Upgrade pip
    if progress_dialog:
        progress_dialog.update_status("Upgrading pip...", 40)
        progress_dialog.add_log("Upgrading pip...")

    try:
        logger.info("Upgrading pip...")
        pip_upgrade = run_subprocess_safe(
            [str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], timeout=60
        )

        if pip_upgrade.returncode == 0:
            logger.info("✓ pip upgraded")
            if progress_dialog:
                progress_dialog.add_log("✓ pip upgraded successfully")
        else:
            logger.warning(f"pip upgrade warning: {pip_upgrade.stderr}")
            if progress_dialog:
                progress_dialog.add_log(f"⚠ pip upgrade warning: {pip_upgrade.stderr}")

    except Exception as e:
        logger.warning(f"pip upgrade failed: {e}")
        if progress_dialog:
            progress_dialog.add_log(f"⚠ pip upgrade failed: {e}")

    # Install dependencies
    if progress_dialog:
        progress_dialog.update_status("Installing dependencies...", 70)
        progress_dialog.add_log("Installing dependencies: pydantic, requests...")

    try:
        logger.info("Installing dependencies (pydantic, requests)...")

        # Try with version constraints first
        result = run_subprocess_safe(
            [
                str(VENV_PYTHON),
                "-m",
                "pip",
                "install",
                "pydantic>=2.0.0",
                "requests>=2.0.0",
            ],
            timeout=180,
        )

        if result.returncode != 0:
            logger.info("Retrying without version constraints...")
            if progress_dialog:
                progress_dialog.add_log(
                    "Retrying installation without version constraints..."
                )

            result = run_subprocess_safe(
                [str(VENV_PYTHON), "-m", "pip", "install", "pydantic", "requests"],
                timeout=180,
            )

            if result.returncode != 0:
                error_msg = f"Dependency installation failed: {result.stderr}"
                logger.error(error_msg)
                log_diagnostic_info()
                if progress_dialog:
                    progress_dialog.add_log(f"✗ ERROR: {error_msg}")
                return False

        logger.info("✓ Dependencies installed successfully")
        if progress_dialog:
            progress_dialog.add_log("✓ Dependencies installed successfully")

    except Exception as e:
        error_msg = f"Dependency installation failed: {e}"
        logger.error(error_msg)
        log_diagnostic_info()
        if progress_dialog:
            progress_dialog.add_log(f"✗ ERROR: {error_msg}")
        return False

    # Set up Python paths
    if progress_dialog:
        progress_dialog.update_status("Setting up Python paths...", 90)

    try:
        if IS_WINDOWS:
            site_packages_dirs = list(venv_dir.glob("Lib/site-packages"))
        else:
            site_packages_dirs = list(venv_dir.glob("lib/python*/site-packages"))

        if not site_packages_dirs:
            error_msg = "No site-packages directory found after installation"
            logger.error(error_msg)
            log_diagnostic_info()
            if progress_dialog:
                progress_dialog.add_log(f"✗ ERROR: {error_msg}")
            return False

        setup_python_paths(site_packages_dirs[0])

        # Verify imports
        verify_imports(progress_dialog)

        if progress_dialog:
            progress_dialog.update_status("Environment setup complete!", 100)

        logger.info("✓ Virtual environment setup completed")
        return True

    except Exception as e:
        error_msg = f"Path setup failed: {e}"
        logger.error(error_msg)
        log_diagnostic_info()
        if progress_dialog:
            progress_dialog.add_log(f"✗ ERROR: {error_msg}")
        return False


def setup_python_paths(site_packages):
    """Set up Python paths for the virtual environment"""
    site_packages_str = str(site_packages)
    if site_packages_str not in sys.path:
        sys.path.insert(0, site_packages_str)
        logger.info(f"✓ Added venv site-packages to sys.path: {site_packages_str}")

    plugin_dir_str = str(plugin_dir)
    if plugin_dir_str not in sys.path:
        sys.path.insert(0, plugin_dir_str)
        logger.info(f"✓ Added plugin directory to sys.path: {plugin_dir_str}")


def get_kicad_version():
    """Get KiCad version information"""
    try:
        return pcbnew.GetBuildVersion()
    except Exception:
        return "Unknown"


def get_disk_space():
    """Get available disk space in MB"""
    try:
        import shutil

        total, used, free = shutil.disk_usage(plugin_dir)
        return f"{free // (1024*1024)} MB free"
    except Exception:
        return "Unknown"


def check_write_permissions():
    """Check if plugin directory is writable"""
    try:
        test_file = plugin_dir / "test_write.tmp"
        test_file.write_text("test")
        test_file.unlink()
        return "OK"
    except Exception as e:
        return f"Failed: {e}"


def collect_diagnostic_info():
    """Collect system info for troubleshooting"""
    system_info = {
        "os": platform.platform(),
        "python": sys.version,
        "kicad_version": get_kicad_version(),
        "available_space": get_disk_space(),
        "permissions": check_write_permissions(),
    }

    # Add platform-specific info
    platform_issues = check_platform_requirements()
    if platform_issues:
        system_info["platform_warnings"] = "; ".join(platform_issues)

    return system_info


def log_diagnostic_info():
    """Log diagnostic information for troubleshooting"""
    try:
        diag = collect_diagnostic_info()
        logger.error("=== DIAGNOSTIC INFORMATION ===")
        for key, value in diag.items():
            logger.error(f"{key}: {value}")
        logger.error("==============================")
    except Exception as e:
        logger.error(f"Failed to collect diagnostic info: {e}")


def verify_imports(progress_dialog=None):
    """Verify that required modules can be imported"""
    try:
        import pydantic

        logger.info(f"✓ pydantic {pydantic.__version__} available")
    except ImportError as e:
        logger.warning(f"⚠ pydantic import failed: {e}")
        if progress_dialog:
            progress_dialog.add_log(f"⚠ pydantic import failed: {e}")

    try:
        import requests

        logger.info(f"✓ requests {requests.__version__} available")
    except ImportError as e:
        logger.warning(f"⚠ requests import failed: {e}")
        if progress_dialog:
            progress_dialog.add_log(f"⚠ requests import failed: {e}")


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
        progress_dialog = None

        try:
            setup_logging()
            logger.info("Plugin started")

            # Check if environment is already ready
            venv_ready = check_venv_ready()

            if venv_ready:
                logger.info(
                    "Virtual environment already ready, starting plugin directly"
                )

                # Set up paths for existing environment
                if IS_WINDOWS:
                    site_packages_dirs = list(venv_dir.glob("Lib/site-packages"))
                else:
                    site_packages_dirs = list(
                        venv_dir.glob("lib/python*/site-packages")
                    )

                if site_packages_dirs:
                    setup_python_paths(site_packages_dirs[0])

                self._start_plugin_frontend()

            else:
                progress_dialog = ProgressDialog()
                if progress_dialog.create_dialog():
                    progress_dialog.dialog.ShowModal()

                    if progress_dialog.setup_success:
                        progress_dialog.dialog.Destroy()
                        self._start_plugin_frontend()
                    else:
                        progress_dialog.dialog.Destroy()
                        logger.info("Setup was cancelled or failed")
                        return
                else:
                    error_msg = (
                        "Failed to create setup dialog.\n\n"
                        f"Check log file for details: {log_file}\n\n"
                        "Please activate KiCad IPC API to avoid the fallback solution."
                    )
                    show_error_dialog("Setup Dialog Error", error_msg)
                    return

        except Exception as e:
            logger.exception("Plugin error occurred")
            log_diagnostic_info()

            detailed_msg = (
                f"Plugin Error Details:\n\n"
                f"Error: {str(e)}\n"
                f"Type: {type(e).__name__}\n\n"
                f"Check log file for full details:\n{log_file}\n\n"
                f"Please activate KiCad IPC API to avoid the fallback solution.\n"
                f"Settings → Plugins → Activate KiCad API"
            )

            show_error_dialog("Plugin Error", detailed_msg)

        finally:
            try:
                if (
                    progress_dialog
                    and hasattr(progress_dialog, "dialog")
                    and progress_dialog.dialog
                ):
                    progress_dialog.dialog.Destroy()
            except:
                pass

            cleanup_logging()

    def _start_plugin_frontend(self):
        """Start the main plugin frontend"""
        try:
            logger.info("Starting plugin frontend")

            from .impart_action import ImpartFrontend

            frontend = ImpartFrontend(fallback_mode=True)
            frontend.ShowModal()
            frontend.Destroy()

            logger.info("Plugin stopped")

        except Exception as e:
            logger.exception("Frontend error occurred")
            log_diagnostic_info()

            error_msg = (
                f"Frontend Error:\n\n"
                f"Error: {str(e)}\n\n"
                f"Check log file for details: {log_file}"
            )

            show_error_dialog("Frontend Error", error_msg)


ActionImpartPlugin().register()
