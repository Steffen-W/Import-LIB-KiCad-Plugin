"""
KiCad Import Plugin for library files from various sources.
Supports Octopart, Samacsys, Ultralibrarian, Snapeda and EasyEDA.
"""

import os
import sys
import traceback
import logging
from pathlib import Path
from time import sleep
from threading import Thread
from typing import Optional, List, Tuple, Any

# Fix module path issues for debugging and standalone execution
if __name__ == "__main__":
    # When running as main script, add parent directory to path
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    # Add project root to Python path if not already there
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Also add current directory for local imports
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s:%(filename)s:%(lineno)d]: %(message)s",
    filename=Path(__file__).resolve().parent / "plugin.log",
    filemode="w",
)


# Setup virtual environment path
def setup_virtual_env() -> None:
    """Setup virtual environment Python path if available."""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        logging.info(f"Venv: {os.path.basename(venv)} {version}")
        venv_site_packages = os.path.join(venv, "lib", version, "site-packages")
        if venv_site_packages in sys.path:
            sys.path.remove(venv_site_packages)
        sys.path.insert(0, venv_site_packages)
    else:
        logging.warning("No virtual environment active.")


# Setup script directory for imports
def setup_script_path() -> None:
    """Add script directory to Python path for local imports."""
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    logging.debug(f"Script directory added to path: {script_dir}")


try:
    setup_virtual_env()
    # setup_script_path()
    import wx

    logging.info("Successfully imported wx module")
except Exception as e:
    logging.exception("Failed to import wx module")
    raise

try:
    import impart_gui
    import FileHandler
    import KiCad_Settings
    import ConfigHandler
    import KiCadImport
    import KiCadSettingsPaths
    import impart_migration

    # Alle benötigten Klassen/Funktionen zuweisen
    impartGUI = impart_gui.impartGUI
    FileHandler = FileHandler.FileHandler
    KiCad_Settings = KiCad_Settings.KiCad_Settings
    ConfigHandler = ConfigHandler.ConfigHandler
    LibImporter = KiCadImport.LibImporter
    KiCadApp = KiCadSettingsPaths.KiCadApp
    find_old_lib_files = impart_migration.find_old_lib_files
    convert_lib_list = impart_migration.convert_lib_list

    logging.info("Successfully imported all local modules using direct imports")

except ImportError as e:
    logging.exception("Failed to import local modules")
    print(f"Import error: {e}")
    print(f"Python path: {sys.path}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script directory: {Path(__file__).resolve().parent}")
    raise

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


class PluginThread(Thread):
    """Background thread for monitoring import status."""

    def __init__(self, wx_object: wx.Window) -> None:
        Thread.__init__(self)
        self.wx_object = wx_object
        self.stop_thread = False
        self.start()

    def run(self) -> None:
        """Main thread loop."""
        len_str = 0
        while not self.stop_thread:
            current_len = len(backend_handler.print_buffer)
            if len_str != current_len:
                self.report(backend_handler.print_buffer)
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
        self.print_to_buffer("\n" + "=" * 30 + "\n")

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
        dest_path = backend.config.get_DEST_PATH()
        msg += backend.kicad_settings.check_GlobalVar(dest_path, add_if_possible)
    else:
        logging.info("TODO: Implement project-specific library check")

    for lib_name in ImpartBackend.SUPPORTED_LIBRARIES:
        msg += _check_single_library(backend, lib_name, add_if_possible)

    return msg


def _check_single_library(
    backend: ImpartBackend, lib_name: str, add_if_possible: bool
) -> str:
    """Check a single library for import."""
    dest_path = backend.config.get_DEST_PATH()
    msg = ""

    # Check for symbol libraries
    symbol_variants = [
        f"{lib_name}.kicad_sym",
        f"{lib_name}_kicad_sym.kicad_sym",
        f"{lib_name}_old_lib.kicad_sym",
    ]

    for variant in symbol_variants:
        lib_path = os.path.join(dest_path, variant)
        if os.path.isfile(lib_path):
            msg += backend.kicad_settings.check_symbollib(variant, add_if_possible)
            break

    # Check for footprint libraries
    footprint_path = os.path.join(dest_path, f"{lib_name}.pretty")
    if os.path.isdir(footprint_path):
        msg += backend.kicad_settings.check_footprintlib(lib_name, add_if_possible)

    return msg


class ImpartFrontend(impartGUI):
    """Frontend GUI for the import plugin."""

    def __init__(self) -> None:
        super().__init__(None)
        self.backend = backend_handler
        self.thread: Optional[PluginThread] = None

        self._setup_gui()
        self._setup_events()
        self._start_monitoring_thread()

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

    def _setup_events(self) -> None:
        """Setup event handlers."""
        EVT_UPDATE(self, self.update_display)

    def _start_monitoring_thread(self) -> None:
        """Start the monitoring thread."""
        self.thread = PluginThread(self)

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
        self.backend.local_lib = self.m_checkBoxLocalLib.IsChecked()
        self.m_dirPicker_librarypath.Enable(not self.backend.local_lib)
        event.Skip()

    def on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close event."""
        if self.backend.run_thread:
            if not self._confirm_background_process():
                return

        self._save_settings()
        if self.thread:
            self.thread.stop_thread = True
        event.Skip()

    def _confirm_background_process(self) -> bool:
        """Confirm closure when background process is running."""
        msg = (
            "The automatic import process continues in the background. "
            "If this is not desired, it must be stopped.\n"
            "As soon as the PCB Editor window is closed, the import process also ends."
        )

        dlg = wx.MessageDialog(
            None, msg, "WARNING: impart background process", wx.OK | wx.ICON_WARNING
        )

        return dlg.ShowModal() == wx.ID_OK

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
            separator = "\n" + "=" * 30 + "\n"
            self.backend.print_to_buffer(separator + full_msg + separator)

    def DirChange(self, event: wx.CommandEvent) -> None:
        """Handle directory path changes."""
        self.backend.config.set_SRC_PATH(self.m_dirPicker_sourcepath.GetPath())
        self.backend.config.set_DEST_PATH(self.m_dirPicker_librarypath.GetPath())
        self.backend.folder_handler.known_files = set()
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

    def ensure_easyeda_module(self):
        """Make sure that easyeda2kicad is available"""

        try:
            import easyeda2kicad

            return True
        except ImportError:
            pass

        self.backend.print_to_buffer("easyeda2kicad not found. Installing...")

        try:
            import subprocess
            import sys

            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "easyeda2kicad"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                self.backend.print_to_buffer("✓ easyeda2kicad installed successfully")

                try:
                    import easyeda2kicad

                    self.backend.print_to_buffer(
                        "✓ easyeda2kicad imported successfully"
                    )
                    return True
                except ImportError as e:
                    self.backend.print_to_buffer(f"✗ Import still failed: {e}")
                    return False
            else:
                self.backend.print_to_buffer(f"✗ Installation failed: {result.stderr}")
                return False

        except Exception as e:
            self.backend.print_to_buffer(f"✗ Installation error: {e}")
            return False

    def _perform_easyeda_import(self) -> None:
        """Perform EasyEDA component import."""
        if not self.ensure_easyeda_module():
            return

        try:
            from impart_easyeda import EasyEDAImporter, ImportConfig
        except ImportError as e:
            self.backend.print_to_buffer(f"Failed to import EasyEDA module: {e}")
            logging.error(f"EasyEDA import module not available: {e}")
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

        overwrite_enabled = self.m_overwrite.IsChecked()

        config = ImportConfig(
            base_folder=Path(base_folder),
            lib_name="EasyEDA",
            overwrite=overwrite_enabled,
            lib_var=path_variable,
        )

        component_id = self.m_textCtrl2.GetValue().strip()

        # Create custom logging handler that captures EasyEDA logs
        class EasyEDABufferHandler(logging.Handler):
            def __init__(self, print_buffer_func):
                super().__init__()
                self.print_buffer_func = print_buffer_func
                # Set a formatter for cleaner output
                formatter = logging.Formatter("%(message)s")
                self.setFormatter(formatter)

            def emit(self, record):
                try:
                    if record.name.startswith(
                        "impart_easyeda"
                    ) or record.name.startswith("easyeda2kicad"):
                        msg = self.format(record)
                        # Only show INFO, WARNING, ERROR levels in GUI
                        if record.levelno >= logging.INFO:
                            self.print_buffer_func(f"EasyEDA: {msg}")
                except Exception:
                    pass

        # Get the EasyEDA logger and configure it
        easyeda_logger = logging.getLogger("impart_easyeda")
        easyeda2kicad_logger = logging.getLogger("easyeda2kicad")

        # Create and add our custom handler
        buffer_handler = EasyEDABufferHandler(self.backend.print_to_buffer)
        buffer_handler.setLevel(logging.INFO)

        # Temporarily add handler to both potential logger names
        easyeda_logger.addHandler(buffer_handler)
        easyeda2kicad_logger.addHandler(buffer_handler)

        # Set appropriate log levels
        easyeda_logger.setLevel(logging.INFO)
        easyeda2kicad_logger.setLevel(logging.INFO)

        # Get existing main logger
        main_logger = logging.getLogger(__name__)

        self.backend.print_to_buffer("")
        self.backend.print_to_buffer(
            f"Try to import EasyEDA / LCSC Part#: {component_id}"
        )

        try:
            importer = EasyEDAImporter(config)
            paths = importer.import_component(component_id)

            # Log to main plugin file
            main_logger.info(f"Imported EasyEDA component {component_id}")

            # Print paths to buffer
            results_found = False
            for attr, label in [
                ("symbol_lib", "Symbol library"),
                ("footprint_file", "Footprint file"),
                ("model_wrl", "3D model (WRL)"),
                ("model_step", "3D model (STEP)"),
            ]:
                if path := getattr(paths, attr):
                    self.backend.print_to_buffer(f"  ✓ {label}: {path}")
                    main_logger.debug(f"EasyEDA {label}: {path}")
                    results_found = True
                else:
                    self.backend.print_to_buffer(f"  ✗ {label}: Not created")

            if results_found:
                self.backend.print_to_buffer("\nEasyEDA import completed successfully!")
            else:
                self.backend.print_to_buffer(
                    "\nEasyEDA import completed, but no files were generated."
                )

        except ValueError as e:
            error_msg = f"EasyEDA Error: {e}"
            self.backend.print_to_buffer(error_msg)
            main_logger.error(f"Failed to import {component_id}: {e}")

        except RuntimeError as e:
            error_msg = f"EasyEDA Runtime Error: {e}"
            self.backend.print_to_buffer(error_msg)
            main_logger.error(f"Runtime error importing {component_id}: {e}")

        except Exception as e:
            error_msg = f"EasyEDA Unexpected Error: {e}"
            self.backend.print_to_buffer(error_msg)
            main_logger.exception(f"Unexpected error importing {component_id}")

        finally:
            # Clean up: Remove our handlers to prevent memory leaks
            easyeda_logger.removeHandler(buffer_handler)
            easyeda2kicad_logger.removeHandler(buffer_handler)

            # Close the handler
            buffer_handler.close()

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


# Global backend instance
try:
    backend_handler = ImpartBackend()
    logging.info("Successfully created backend handler")
except Exception as e:
    logging.exception("Failed to create backend handler")
    raise

# KiCad Plugin Integration (SWIG)
try:
    import pcbnew

    logging.info("Successfully imported pcbnew module")

    class ActionImpartPlugin(pcbnew.ActionPlugin):
        """KiCad Action Plugin for library import."""

        def defaults(self) -> None:
            """Set plugin defaults."""
            plugin_dir = Path(__file__).resolve().parent
            self.resources_dir = (
                plugin_dir.parent.parent / "resources" / plugin_dir.name
            )
            self.plugin_dir = plugin_dir

            self.name = "impartGUI"
            self.category = "Import library files"
            self.description = "Import library files from Octopart, Samacsys, Ultralibrarian, Snapeda and EasyEDA"
            self.show_toolbar_button = True

            icon_path = self.resources_dir / "icon.png"
            self.icon_file_name = str(icon_path)
            self.dark_icon_file_name = str(icon_path)

        def Run(self) -> None:
            """Run the plugin."""
            try:
                frontend = ImpartFrontend()
                frontend.ShowModal()
                frontend.Destroy()
            except Exception as e:
                logging.exception("Failed to run plugin frontend")
                raise

except ImportError:
    logging.info("pcbnew module not available - running in standalone mode")

if __name__ == "__main__":
    logging.info("Starting application in standalone mode")
    try:
        app = wx.App()
        frame = wx.Frame(None, title="KiCad Plugin")
        frontend = ImpartFrontend()
        frontend.ShowModal()
        frontend.Destroy()
        logging.info("Application finished successfully")
    except Exception as e:
        logging.exception("Failed to run standalone application")
        raise
