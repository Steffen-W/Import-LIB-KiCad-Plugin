"""
KiCad Import Plugin for library files from various sources.
Supports Octopart, Samacsys, Ultralibrarian, Snapeda and EasyEDA.
"""

import atexit
import os
import sys
import logging
from pathlib import Path
from time import sleep
from threading import Thread
from typing import Optional, List, Tuple, Any

# Setup paths for local imports
script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s:%(filename)s:%(lineno)d]: %(message)s",
    filename=script_dir / "plugin.log",
    filemode="a",
)


def quick_instance_check(port: int = 59999) -> bool:
    """Quick check if another instance is running without logging."""
    try:
        import socket

        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(1.0)
        client_socket.connect(("127.0.0.1", port))
        client_socket.close()
        return True
    except:
        return False


if __name__ == "__main__" and quick_instance_check():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s",
        filename=script_dir / "plugin.log",
        filemode="w",
    )

# Import dependencies
try:
    import wx

    logging.info("Successfully imported wx module")
except Exception as e:
    logging.exception("Failed to import wx module")
    raise

try:
    # Try relative imports first (when run as module)
    from .impart_gui import impartGUI
    from .FileHandler import FileHandler
    from .KiCad_Settings import KiCad_Settings
    from .ConfigHandler import ConfigHandler
    from .KiCadImport import LibImporter
    from .KiCadSettingsPaths import KiCadApp
    from .impart_migration import find_old_lib_files, convert_lib_list
    from .single_instance_manager import SingleInstanceManager

    logging.info("Successfully imported all local modules using relative imports")

except ImportError as e1:
    try:
        # Fallback to absolute imports (when run as script)
        from impart_gui import impartGUI
        from FileHandler import FileHandler
        from KiCad_Settings import KiCad_Settings
        from ConfigHandler import ConfigHandler
        from KiCadImport import LibImporter
        from KiCadSettingsPaths import KiCadApp
        from impart_migration import find_old_lib_files, convert_lib_list
        from single_instance_manager import SingleInstanceManager

        logging.info("Successfully imported all local modules using absolute imports")

    except ImportError as e2:
        logging.exception(
            "Failed to import local modules with both relative and absolute imports"
        )
        print(f"Relative import error: {e1}")
        print(f"Absolute import error: {e2}")
        print(f"Python path: {sys.path}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"Script directory: {script_dir}")
        raise e2

# Event handling
EVT_UPDATE_ID = wx.NewIdRef()


def EVT_UPDATE(win: wx.Window, func: Any) -> None:
    """Bind update event to window."""
    win.Connect(-1, -1, EVT_UPDATE_ID, func)


class ResultEvent(wx.PyEvent):
    """Custom event for thread communication."""

    def __init__(self, data: str) -> None:
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_UPDATE_ID)
        self.data = data


class FileDropTarget(wx.FileDropTarget):
    """Drop target for ZIP files on the text control."""

    def __init__(self, window, callback):
        wx.FileDropTarget.__init__(self)
        self.window = window
        self.callback = callback

    def OnDropFiles(self, x, y, filenames):
        """Called when files are dropped on the text control."""
        zip_files = [f for f in filenames if f.lower().endswith(".zip")]

        if zip_files:
            self.callback(zip_files)
            return True
        else:
            wx.MessageBox(
                "Only .zip files are supported!",
                "Invalid file type",
                wx.OK | wx.ICON_WARNING,
            )
            return False


class PluginThread(Thread):
    """Background thread for monitoring import status."""

    def __init__(self, wx_object: wx.Window, backend) -> None:
        Thread.__init__(self)
        self.wx_object = wx_object
        self.backend = backend
        self.stop_thread = False
        self.start()

    def run(self) -> None:
        """Main thread loop."""
        len_str = 0
        while not self.stop_thread:
            current_len = len(self.backend.print_buffer)
            if len_str != current_len:
                self.report(self.backend.print_buffer)
                len_str = current_len
            sleep(0.5)

    def report(self, status: str) -> None:
        """Send status update to main thread."""
        wx.PostEvent(self.wx_object, ResultEvent(status))


class ImpartBackend:
    """Backend handler for the import plugin."""

    # Library names supported by the plugin
    SUPPORTED_LIBRARIES = [
        "Octopart",
        "Samacsys",
        "UltraLibrarian",
        "Snapeda",
        "EasyEDA",
    ]

    def __init__(self) -> None:
        """Initialize backend components."""
        logging.info("Initializing ImpartBackend")

        """Setup file paths."""
        self.config_path = os.path.join(os.path.dirname(__file__), "config.ini")

        """Initialize core components."""
        try:
            self.kicad_app = KiCadApp(prefer_ipc=True, min_version="8.0.4")
            self.config = ConfigHandler(self.config_path)
            self.kicad_settings = KiCad_Settings(self.kicad_app.settings_path)

            self.folder_handler = FileHandler(
                ".", min_size=1_000, max_size=50_000_000, file_extension=".zip"
            )

            self.importer = LibImporter()
            # Create a wrapper function that matches the expected signature
            self.importer.print = lambda txt: self.print_to_buffer(txt)

            logging.info("Successfully initialized all backend components")
            logging.info(f"KiCad settings path: {self.kicad_settings.SettingPath}")

        except Exception as e:
            logging.exception("Failed to initialize backend components")
            raise

        """Initialize control flags."""
        self.run_thread = False
        self.auto_import = False
        self.overwrite_import = False
        self.import_old_format = False
        self.local_lib = False
        self.auto_lib = False
        self.print_buffer = ""

        """Check initial configuration and version."""
        try:
            self.kicad_app.check_min_version(output_func=self.print_to_buffer)
        except Exception as e:
            logging.warning(f"Failed to check KiCad version: {e}")

        if not self.config.config_is_set:
            self._print_initial_warnings()

    def _print_initial_warnings(self) -> None:
        """Print initial configuration warnings."""
        warning_msg = (
            "Warning: The path where the libraries should be saved has not been "
            "adjusted yet. Maybe you use the plugin in this version for the first time."
        )

        info_msg = (
            "If this plugin is being used for the first time, settings in KiCad are "
            "required. The settings are checked at the end of the import process. "
            "For easy setup, auto setting can be activated."
        )

        self.print_to_buffer(warning_msg)
        self.print_to_buffer(info_msg)
        self.print_to_buffer("\n" + "=" * 50 + "\n")

    def print_to_buffer(self, *args: Any) -> None:
        """Add text to print buffer."""
        for text in args:
            self.print_buffer += str(text) + "\n"

    def find_and_import_new_files(self) -> None:
        """Monitor directory for new files and import them."""
        src_path = self.config.get_SRC_PATH()

        if not os.path.isdir(src_path):
            self.print_to_buffer(f"Source path does not exist: {src_path}")
            return

        while True:
            new_files = self.folder_handler.get_new_files(src_path)

            for lib_file in new_files:
                self._import_single_file(lib_file)

            if not self.run_thread:
                break
            sleep(1)

    def _import_single_file(self, lib_file: str) -> None:
        """Import a single library file."""
        try:
            # Convert string to Path for import_all function
            lib_path = Path(lib_file)
            result = self.importer.import_all(
                lib_path,
                overwrite_if_exists=self.overwrite_import,
                import_old_format=self.import_old_format,
            )
            # Handle potential None result
            if result and len(result) > 0:
                self.print_to_buffer(result[0])

        except AssertionError as e:
            self.print_to_buffer(f"Assertion Error: {e}")
        except Exception as e:
            error_msg = f"Import Error: {e}\nPython version: {sys.version}"
            self.print_to_buffer(error_msg)
            logging.exception("Import failed")
        finally:
            self.print_to_buffer("")


def check_library_import(backend: ImpartBackend, add_if_possible: bool = True) -> str:
    """Check and potentially add libraries to KiCad settings."""
    msg = ""

    if backend.local_lib:
        project_dir = backend.kicad_app.get_project_dir()
        if not project_dir:
            return "\nLocal library mode enabled but no KiCad project available."

        try:
            kicad_settings = KiCad_Settings(str(project_dir), path_prefix="${KIPRJMOD}")
            dest_path = project_dir
            logging.info("Project-specific library check completed")
        except Exception as e:
            logging.error(f"Failed to read project settings: {e}")
            return "\nCould not read project library settings."
    else:
        kicad_settings = backend.kicad_settings
        dest_path = backend.config.get_DEST_PATH()
        msg = kicad_settings.check_GlobalVar(dest_path, add_if_possible)

    for lib_name in ImpartBackend.SUPPORTED_LIBRARIES:
        msg += _check_single_library(
            kicad_settings, lib_name, dest_path, add_if_possible
        )

    return msg


def _check_single_library(
    kicad_settings: KiCad_Settings,
    lib_name: str,
    dest_path: str,
    add_if_possible: bool,
) -> str:
    """Check a single library for import."""
    msg = ""

    # Check for symbol libraries
    symbol_variants = [
        f"{lib_name}.kicad_sym",
        f"{lib_name}_kicad_sym.kicad_sym",
        f"{lib_name}_old_lib.kicad_sym",
    ]

    for variant in symbol_variants:
        if os.path.isfile(os.path.join(dest_path, variant)):
            msg += kicad_settings.check_symbollib(variant, add_if_possible)
            break

    # Check for footprint libraries
    if os.path.isdir(os.path.join(dest_path, f"{lib_name}.pretty")):
        msg += kicad_settings.check_footprintlib(lib_name, add_if_possible)

    return msg


instance_manager = SingleInstanceManager()  # Create global instance manager

# Register cleanup handler to ensure IPC server stops on exit
atexit.register(instance_manager.stop_server)


class ImpartFrontend(impartGUI):
    """
    Frontend GUI supporting both IPC singleton and fallback modes.

    - IPC mode: Singleton behavior with window focus on subsequent launches
    - Fallback mode: Direct execution from PCBNew, always creates new instance
    Each instance gets a fresh backend with clean state.
    """

    def __init__(self, fallback_mode: bool = False) -> None:
        super().__init__(None)
        self.fallback_mode = fallback_mode

        # Log the mode
        if self.fallback_mode:
            logging.info("Running in FALLBACK MODE (called from pcbnew)")
        else:
            logging.info("Running in NORMAL MODE (direct execution)")

        # Register with instance manager only if not in fallback mode
        if not self.fallback_mode:
            if not instance_manager.register_frontend(self):
                # Another instance already exists - this shouldn't happen
                logging.warning(
                    "Frontend instance already exists - destroying this one"
                )
                self.Destroy()
                return
        else:
            logging.info("Fallback mode: Skipping IPC server registration")

        # Set window icon
        try:
            icon_path = Path(__file__).resolve().parent / "icon.png"
            if icon_path.exists():
                icon = wx.Icon(str(icon_path), wx.BITMAP_TYPE_PNG)
                self.SetIcon(icon)
        except Exception as e:
            logging.warning(f"Could not set window icon: {e}")

        self.backend = create_backend_handler()
        self.thread: Optional[PluginThread] = None

        self._setup_gui()
        self._setup_events()
        self._start_monitoring_thread()
        self._print_initial_paths()

    def _setup_gui(self) -> None:
        """Initialize GUI components."""
        self.kicad_project = self.backend.kicad_app.get_project_dir()

        # Set initial values
        self.m_dirPicker_sourcepath.SetPath(self.backend.config.get_SRC_PATH())
        self.m_dirPicker_librarypath.SetPath(self.backend.config.get_DEST_PATH())

        # Set checkboxes
        self.m_autoImport.SetValue(self.backend.auto_import)
        self.m_overwrite.SetValue(self.backend.overwrite_import)
        self.m_check_autoLib.SetValue(self.backend.auto_lib)
        self.m_check_import_all.SetValue(self.backend.import_old_format)
        self.m_checkBoxLocalLib.SetValue(self.backend.local_lib)

        self._update_button_label()
        self._check_migration_possible()

        # Add drag & drop support
        self._setup_drag_drop()
        self._add_drag_drop_hint()

    def _setup_events(self) -> None:
        """Setup event handlers."""
        EVT_UPDATE(self, self.update_display)

    def _setup_drag_drop(self) -> None:
        """Configure drag & drop for the text control."""
        drop_target = FileDropTarget(self.m_text, self._on_files_dropped)
        self.m_text.SetDropTarget(drop_target)

        self.m_text.SetToolTip(
            "Drag ZIP files here for direct import\n"
            "Supported: Samacsys, UltraLibrarian, Snapeda"
        )

    def _add_drag_drop_hint(self) -> None:
        """Add visual hint for drag & drop functionality."""
        hint_text = "Tip: You can drag ZIP files directly into this window!"
        self.backend.print_to_buffer(hint_text)
        self.backend.print_to_buffer("=" * 50)

    def _on_files_dropped(self, zip_files: List[str]) -> None:
        """Callback when ZIP files are dropped on the text control."""
        self.backend.print_to_buffer(
            f"\n{len(zip_files)} file(s) received via drag & drop:"
        )

        for zip_file in zip_files:
            self.backend.print_to_buffer(f"  • {os.path.basename(zip_file)}")

        self.backend.print_to_buffer("")
        self._import_dropped_files(zip_files)

    def _import_dropped_files(self, zip_files: List[str]) -> None:
        """Import files received via drag & drop."""
        self._update_backend_settings()

        for zip_file in zip_files:
            self.backend._import_single_file(zip_file)

        # Check library settings after import
        self._check_and_show_library_warnings()

    def _start_monitoring_thread(self) -> None:
        """Start the monitoring thread."""
        self.thread = PluginThread(self, self.backend)

    def _print_initial_paths(self) -> None:
        """Print initial source and destination paths."""
        src_path = self.backend.config.get_SRC_PATH()

        if self.backend.local_lib and self.kicad_project:
            dest_path = self.kicad_project
            lib_mode = "Local Project Library"
        else:
            dest_path = self.backend.config.get_DEST_PATH()
            lib_mode = "Global Library"

        self.backend.print_to_buffer(f"Library Mode: {lib_mode}")
        self.backend.print_to_buffer(f"Source Directory: {src_path}")
        self.backend.print_to_buffer(f"Destination Directory: {dest_path}")
        self.backend.print_to_buffer("=" * 50)

    def _print_path_change(self, change_type: str, new_value: str = "") -> None:
        """Print path change information."""
        if change_type == "library_mode":
            if self.backend.local_lib and self.kicad_project:
                dest_path = self.kicad_project
                lib_mode = "Local Project Library"
            else:
                dest_path = self.backend.config.get_DEST_PATH()
                lib_mode = "Global Library"

            self.backend.print_to_buffer(f"New Library Mode: {lib_mode}")
            self.backend.print_to_buffer(f"New Destination Directory: {dest_path}")
        elif change_type == "source":
            self.backend.print_to_buffer(f"New Source Directory: {new_value}")
        elif change_type == "destination":
            if not self.backend.local_lib:
                self.backend.print_to_buffer(f"New Destination Directory: {new_value}")

    def _update_button_label(self) -> None:
        """Update the main button label based on current state."""
        if self.backend.run_thread:
            self.m_button.Label = "automatic import / press to stop"
        else:
            self.m_button.Label = "Start"

    def update_display(self, status: ResultEvent) -> None:
        """Update the text display with new status."""
        self.m_text.SetValue(status.data)
        self.m_text.SetInsertionPointEnd()

    def m_checkBoxLocalLibOnCheckBox(self, event: wx.CommandEvent) -> None:
        """Handle local library checkbox change."""
        old_local_lib = self.backend.local_lib
        self.backend.local_lib = self.m_checkBoxLocalLib.IsChecked()
        self.m_dirPicker_librarypath.Enable(not self.backend.local_lib)

        # Print change information
        if old_local_lib != self.backend.local_lib:
            self._print_path_change("library_mode")

        event.Skip()

    def on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close event with robust cleanup."""
        try:
            if not self.backend.run_thread:
                # No automatic import active: Always close everything completely
                self._safe_cleanup(close_ipc=not self.fallback_mode)
                logging.info("No auto import: Closing everything completely")
                event.Skip()

            elif self.fallback_mode:
                # Fallback mode + auto import: Close GUI but keep background thread
                choice = self._confirm_background_process()
                if choice == "cancel":
                    event.Veto()
                    return
                elif choice == "background":
                    self._safe_cleanup(close_ipc=False, stop_backend=False)
                    logging.info(
                        "Fallback mode: GUI closed, background thread continues"
                    )
                    event.Skip()  # Close GUI completely
                    return
                else:  # choice == "close"
                    self._safe_cleanup(close_ipc=False, stop_backend=True)
                    logging.info("Fallback mode: Everything stopped")
                    event.Skip()

            else:
                # IPC mode + auto import: Minimize window, keep everything running
                choice = self._confirm_background_process()
                if choice == "cancel":
                    event.Veto()
                    return
                elif choice == "background":
                    self._safe_cleanup(close_ipc=False, stop_backend=False)
                    if not self.IsIconized():
                        self.Iconize(True)
                    # self.Hide()
                    logging.info(
                        "IPC mode: Frontend minimized, running in background with IPC active"
                    )
                    event.Veto()  # Prevent actual closing
                    return
                else:  # choice == "close"
                    self._safe_cleanup(close_ipc=True, stop_backend=True)
                    logging.info("IPC mode: Everything stopped")
                    event.Skip()

        except Exception as e:
            logging.exception(f"Error during close event: {e}")
            # Force cleanup on any exception
            try:
                self._safe_cleanup(close_ipc=not self.fallback_mode, stop_backend=True)
            except Exception:
                pass
            event.Skip()

    def _safe_cleanup(self, close_ipc: bool = True, stop_backend: bool = True) -> None:
        """Perform safe cleanup with error handling."""
        try:
            self._save_settings()
        except Exception as e:
            logging.warning(f"Failed to save settings during cleanup: {e}")

        if stop_backend:
            try:
                self.backend.run_thread = False
            except Exception as e:
                logging.warning(f"Failed to stop backend thread: {e}")

        try:
            if self.thread:
                self.thread.stop_thread = True
        except Exception as e:
            logging.warning(f"Failed to stop monitoring thread: {e}")

        if close_ipc:
            try:
                instance_manager.stop_server()
            except Exception as e:
                logging.warning(f"Failed to stop IPC server: {e}")

    def _confirm_background_process(self) -> str:
        """Confirm what to do when background process is running."""
        msg = (
            "Import process runs in automatic mode.\n\n"
            "• HIDE: Keep running, hide window\n"
            "• STOP: Stop import and close\n"
            "• CANCEL: Back to window"
        )

        dlg = wx.MessageDialog(
            None,
            msg,
            "Import Running",
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
        )

        dlg.SetYesNoLabels("&Hide", "&Stop")

        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            return "background"
        elif result == wx.ID_NO:
            return "close"
        else:
            return "cancel"

    def _save_settings(self) -> None:
        """Save current settings to backend."""
        self.backend.auto_import = self.m_autoImport.IsChecked()
        self.backend.overwrite_import = self.m_overwrite.IsChecked()
        self.backend.auto_lib = self.m_check_autoLib.IsChecked()
        self.backend.import_old_format = self.m_check_import_all.IsChecked()
        self.backend.local_lib = self.m_checkBoxLocalLib.IsChecked()

    def BottonClick(self, event: wx.CommandEvent) -> None:
        """Handle main button click."""
        self._update_backend_settings()

        if self.backend.run_thread:
            self._stop_import()
        else:
            self._start_import()

        event.Skip()

    def _update_backend_settings(self) -> None:
        """Update backend with current GUI settings."""
        if self.backend.local_lib:
            if not self.kicad_project:
                return
            self.backend.importer.set_DEST_PATH(Path(self.kicad_project))
            kicad_link = "${KIPRJMOD}"
        else:
            dest_path = self.backend.config.get_DEST_PATH()
            if dest_path:
                self.backend.importer.set_DEST_PATH(Path(dest_path))
            kicad_link = "${KICAD_3RD_PARTY}"

        self.backend.importer.KICAD_3RD_PARTY_LINK = kicad_link

        # Handle overwrite setting change
        overwrite_changed = (
            self.m_overwrite.IsChecked() and not self.backend.overwrite_import
        )
        if overwrite_changed:
            self.backend.folder_handler.known_files = set()

        self._save_settings()

    def _stop_import(self) -> None:
        """Stop the import process."""
        self.backend.run_thread = False
        self.m_button.Label = "Start"

    def _start_import(self) -> None:
        """Start the import process."""
        self.backend.run_thread = False
        self.backend.find_and_import_new_files()
        self.m_button.Label = "Start"

        if self.backend.auto_import:
            self.backend.run_thread = True
            self.m_button.Label = "automatic import / press to stop"

            import_thread = Thread(target=self.backend.find_and_import_new_files)
            import_thread.start()

        self._check_and_show_library_warnings()

    def _check_and_show_library_warnings(self) -> None:
        """Check library settings and show warnings if needed."""
        add_if_possible = self.m_check_autoLib.IsChecked()
        msg = check_library_import(self.backend, add_if_possible)

        if msg:
            self._show_library_warning(msg)

    def _show_library_warning(self, msg: str) -> None:
        """Show library configuration warning dialog."""
        full_msg = (
            f"{msg}\n\n"
            "More information can be found in the README for the integration into KiCad.\n"
            "github.com/Steffen-W/Import-LIB-KiCad-Plugin\n"
            "Some configurations require a KiCad restart to be detected correctly."
        )

        dlg = wx.MessageDialog(None, full_msg, "WARNING", wx.OK | wx.ICON_WARNING)

        if dlg.ShowModal() == wx.ID_OK:
            separator = "\n" + "=" * 50 + "\n"
            self.backend.print_to_buffer(separator + full_msg + separator)

    def DirChange(self, event: wx.CommandEvent) -> None:
        """Handle directory path changes."""
        # Get old values for comparison
        old_src = self.backend.config.get_SRC_PATH()
        old_dest = self.backend.config.get_DEST_PATH()

        # Update paths
        new_src = self.m_dirPicker_sourcepath.GetPath()
        new_dest = self.m_dirPicker_librarypath.GetPath()

        self.backend.config.set_SRC_PATH(new_src)
        self.backend.config.set_DEST_PATH(new_dest)
        self.backend.folder_handler.known_files = set()

        if old_src != new_src:
            self._print_path_change("source", new_src)
        if old_dest != new_dest:
            self._print_path_change("destination", new_dest)

        self._check_migration_possible()
        event.Skip()

    def ButtomManualImport(self, event: wx.CommandEvent) -> None:
        """Handle manual EasyEDA import."""
        try:
            self._perform_easyeda_import()
        except Exception as e:
            error_msg = f"Error: {e}\nPython version: {sys.version}"
            self.backend.print_to_buffer(error_msg)
            logging.exception("Manual import failed")
        finally:
            event.Skip()

    def _perform_easyeda_import(self) -> None:
        """Perform EasyEDA component import."""
        try:
            from .impart_easyeda import import_easyeda_component, ImportConfig
        except ImportError:
            try:
                from impart_easyeda import import_easyeda_component, ImportConfig
            except ImportError as e:
                error_msg = f"Failed to import EasyEDA module: {e}\n\nThis usually means easyeda2kicad is not properly installed or has missing dependencies."
                self.backend.print_to_buffer(error_msg)
                logging.error(f"EasyEDA import module not available: {e}")

                wx.MessageBox(
                    f"EasyEDA Import Error!\n\n{error_msg}\n\n"
                    "Solutions:\n"
                    "1. Run 'install_dependencies.py' to reinstall dependencies\n"
                    "2. Check plugin.log for detailed error information\n"
                    "3. Restart KiCad after fixing dependencies",
                    "Import Error",
                    wx.OK | wx.ICON_ERROR,
                )
                return

        if self.backend.local_lib:
            if not self.kicad_project:
                self.backend.print_to_buffer(
                    "Error: Local library mode selected, but no KiCad project is open."
                )
                self.backend.print_to_buffer("Please either:")
                self.backend.print_to_buffer("  1. Open a KiCad project first, or")
                self.backend.print_to_buffer(
                    "  2. Uncheck 'Local Library' to use global library path"
                )
                logging.error(
                    "Local library mode selected but no KiCad project available"
                )
                return

            # Verify the project path exists and is valid
            project_path = Path(self.kicad_project)
            if not project_path.exists() or not project_path.is_dir():
                self.backend.print_to_buffer(
                    f"Error: KiCad project directory does not exist: {self.kicad_project}"
                )
                self.backend.print_to_buffer("Please check your KiCad project setup.")
                logging.error(f"KiCad project directory invalid: {self.kicad_project}")
                return

            path_variable = "${KIPRJMOD}"
            base_folder = project_path
        else:
            path_variable = "${KICAD_3RD_PARTY}"
            base_folder = self.backend.config.get_DEST_PATH()

        config = ImportConfig(
            base_folder=Path(base_folder),
            lib_name="EasyEDA",
            overwrite=self.m_overwrite.IsChecked(),
            lib_var=path_variable,
        )

        component_id = self.m_textCtrl2.GetValue().strip()

        try:
            paths = import_easyeda_component(
                component_id=component_id,
                config=config,
                print_func=self.backend.print_to_buffer,
            )
            self.backend.print_to_buffer("")
            logging.info(f"Successfully imported EasyEDA component {component_id}")

        except ValueError as e:
            error_msg = f"Invalid component ID {component_id}: {e}"
            logging.error(error_msg)
            wx.MessageBox(error_msg, "Invalid Component ID", wx.OK | wx.ICON_WARNING)

        except RuntimeError as e:
            error_msg = f"Runtime error importing {component_id}: {e}"
            logging.error(error_msg)
            wx.MessageBox(error_msg, "Import Error", wx.OK | wx.ICON_ERROR)

        except Exception as e:
            error_msg = f"Unexpected error during import: {e}"
            self.backend.print_to_buffer(error_msg)
            logging.exception(f"Unexpected error importing {component_id}")
            wx.MessageBox(error_msg, "Unexpected Error", wx.OK | wx.ICON_ERROR)

    def get_old_lib_files(self) -> dict:
        """Get list of old library files for migration."""
        lib_path = self.m_dirPicker_librarypath.GetPath()
        result = find_old_lib_files(
            folder_path=lib_path, libs=ImpartBackend.SUPPORTED_LIBRARIES
        )
        return result

    def _check_migration_possible(self) -> None:
        """Check if library migration is possible and show/hide button."""
        libs_to_migrate = self.get_old_lib_files()
        conversion_info = convert_lib_list(libs_to_migrate, drymode=True)

        if conversion_info:
            self.m_button_migrate.Show()
        else:
            self.m_button_migrate.Hide()

    def migrate_libs(self, event: wx.CommandEvent) -> None:
        """Handle library migration."""
        libs_to_migrate = self.get_old_lib_files()
        conversion_info = convert_lib_list(libs_to_migrate, drymode=True)

        if not conversion_info:
            self.backend.print_to_buffer("Error in migrate_libs()")
            return

        self._perform_migration(libs_to_migrate, conversion_info)
        self._check_migration_possible()
        event.Skip()

    def _perform_migration(
        self, libs_to_migrate: dict, conversion_info: List[Tuple]
    ) -> None:
        """Perform the actual library migration."""
        msg, lib_rename = self.backend.kicad_settings.prepare_library_migration(
            conversion_info
        )

        if not self._confirm_migration(msg):
            return

        self._execute_conversion(libs_to_migrate)

        if lib_rename:
            self._handle_library_renaming(msg, lib_rename)

    def _confirm_migration(self, msg: str) -> bool:
        """Confirm migration with user."""
        dlg = wx.MessageDialog(
            None, msg, "WARNING", wx.OK | wx.ICON_WARNING | wx.CANCEL
        )
        return dlg.ShowModal() == wx.ID_OK

    def _execute_conversion(self, libs_to_migrate: dict) -> None:
        """Execute the library conversion."""
        self.backend.print_to_buffer("Converted libraries:")
        conversion_results = convert_lib_list(libs_to_migrate, drymode=False)

        for old_path, new_path in conversion_results:
            if new_path.endswith(".blk"):
                self.backend.print_to_buffer(f"{old_path} rename to {new_path}")
            else:
                self.backend.print_to_buffer(f"{old_path} convert to {new_path}")

    def _handle_library_renaming(self, msg: str, lib_rename: List[dict]) -> None:
        """Handle library renaming in KiCad settings."""
        msg_lib = (
            "\nShould the change be made automatically? "
            "A restart of KiCad is then necessary to apply all changes."
        )

        dlg = wx.MessageDialog(
            None, msg + msg_lib, "WARNING", wx.OK | wx.ICON_WARNING | wx.CANCEL
        )

        if dlg.ShowModal() == wx.ID_OK:
            result_msg = self.backend.kicad_settings.execute_library_migration(
                lib_rename
            )
            self.backend.print_to_buffer(result_msg)
        else:
            self._show_manual_migration_instructions(lib_rename)

    def _show_manual_migration_instructions(self, lib_rename: List[dict]) -> None:
        """Show manual migration instructions."""
        if not lib_rename:
            return

        msg_summary = (
            "The following changes must be made to the list of imported Symbol libs:\n"
        )

        for item in lib_rename:
            msg_summary += f"\n{item['name']}: {item['oldURI']} \n-> {item['newURI']}"

        msg_summary += (
            "\n\nIt is necessary to adjust the settings of the imported "
            "symbol libraries in KiCad."
        )

        self.backend.print_to_buffer(msg_summary)


def create_backend_handler():
    """Create a new backend handler instance."""
    try:
        backend = ImpartBackend()
        logging.info("Created new backend handler")
        return backend
    except Exception as e:
        logging.exception("Failed to create backend handler")
        raise


if __name__ == "__main__":
    logging.info("Starting application in standalone mode")

    if instance_manager.is_already_running():
        logging.info("Plugin already running - focus command sent")
        # Wait a bit for the command to be processed
        import time

        time.sleep(0.5)
        sys.exit(0)

    try:
        app = wx.App()
        frontend = ImpartFrontend(fallback_mode=False)

        if not instance_manager.start_server(frontend):
            logging.warning("Failed to start IPC server - continuing anyway")

        frontend.ShowModal()
        frontend.Destroy()
        logging.info("Application finished successfully")

    except Exception as e:
        logging.exception("Failed to run standalone application")
        raise
    finally:
        instance_manager.stop_server()
