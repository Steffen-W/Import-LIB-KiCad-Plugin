import logging
import platform
import sys
from pathlib import Path

import pcbnew

try:
    import wx
except ImportError:
    print("Error: wx not available - plugin cannot run without wxPython")
    sys.exit(1)

plugin_dir = Path(__file__).resolve().parent
log_file = plugin_dir / "plugin_fallback.log"

# Initialize logger immediately - it will be configured later in setup_logging()
logger = logging.getLogger("impart_plugin")
log_handler: logging.FileHandler | None = None


def setup_logging():
    """Setup logging for the plugin"""
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
    """Clean up logging resources"""
    try:
        if log_handler:
            log_handler.close()
            if logger:
                logger.removeHandler(log_handler)

        import gc

        gc.collect()

    except Exception as e:
        print(f"Logging cleanup failed: {e}")


def setup_submodule_paths():
    """Set up Python paths for git submodules"""
    try:
        # Add kiutils submodule path
        kiutils_path = plugin_dir / "kiutils" / "src"
        if kiutils_path.exists():
            kiutils_str = str(kiutils_path)
            if kiutils_str not in sys.path:
                sys.path.insert(0, kiutils_str)
                logger.info(f"✓ Added kiutils to sys.path: {kiutils_str}")

        # Add easyeda2kicad submodule path
        easyeda2kicad_path = plugin_dir / "easyeda2kicad"
        if easyeda2kicad_path.exists():
            easyeda2kicad_str = str(easyeda2kicad_path)
            if easyeda2kicad_str not in sys.path:
                sys.path.insert(0, easyeda2kicad_str)
                logger.info(f"✓ Added easyeda2kicad to sys.path: {easyeda2kicad_str}")

        # Add plugin directory itself
        plugin_dir_str = str(plugin_dir)
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)
            logger.info(f"✓ Added plugin directory to sys.path: {plugin_dir_str}")

        logger.info("✓ All submodule paths configured successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to setup submodule paths: {e}")
        return False


def show_error_dialog(title, message):
    """Show error dialog with fallback to console"""
    try:
        app = wx.App() if not wx.GetApp() else None
        wx.MessageBox(message, title, wx.OK | wx.ICON_ERROR)
        if app:
            app.Destroy()
    except Exception:
        print(f"Error: {title} - {message}")


class ActionImpartPlugin(pcbnew.ActionPlugin):
    """KiCad Action Plugin for library import using git submodules."""

    def defaults(self):
        self.name = "impartGUI (fallback pcbnew)"
        self.category = "Import library files"
        self.description = "Import library files from Octopart, Samacsys, Ultralibrarian, Snapeda and EasyEDA"
        self.show_toolbar_button = True

        icon_path = plugin_dir / "icon.png"
        self.icon_file_name = str(icon_path)
        self.dark_icon_file_name = str(icon_path)

    def Run(self):
        """Run the plugin with git submodules."""
        try:
            setup_logging()
            logger.info("Plugin started")

            # Set up paths for git submodules (no venv needed)
            if not setup_submodule_paths():
                error_msg = (
                    "Failed to set up submodule paths.\n\n"
                    f"Check log file for details: {log_file}\n\n"
                    "Ensure git submodules are properly initialized:\n"
                    "git submodule update --init --recursive"
                )
                show_error_dialog("Submodule Setup Error", error_msg)
                return

            # Start plugin frontend directly
            self._start_plugin_frontend()

        except Exception as e:
            logger.exception("Plugin error occurred")

            detailed_msg = (
                f"Plugin Error Details:\n\n"
                f"Error: {str(e)}\n"
                f"Type: {type(e).__name__}\n\n"
                f"Check log file for full details:\n{log_file}\n\n"
            )

            show_error_dialog("Plugin Error", detailed_msg)

        finally:
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

            error_msg = (
                f"Frontend Error:\n\n"
                f"Error: {str(e)}\n\n"
                f"Check log file for details: {log_file}"
            )

            show_error_dialog("Frontend Error", error_msg)


ActionImpartPlugin().register()
