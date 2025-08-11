import logging
from pathlib import Path
import pcbnew
import os
import sys


# Setup paths for local imports
script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s:%(filename)s:%(lineno)d]: %(message)s",
    filename=script_dir / "plugin.log",
    filemode="w",
)

logging.info("Successfully imported pcbnew module")


def setup_embedded_dependencies():
    """Setup embedded dependencies for old plugin API"""
    script_dir = Path(__file__).resolve().parent

    # Add embedded dependency paths
    dependency_paths = [
        script_dir / "lib" / "site-packages",
        script_dir / "lib",
    ]

    added_paths = []
    missing_deps = []

    for path in dependency_paths:
        path_str = str(path)
        if path.exists() and path_str not in sys.path:
            sys.path.insert(0, path_str)
            added_paths.append(path_str)

    if added_paths:
        logging.info(f"Old API: Added embedded dependency paths: {added_paths}")

    # Check critical dependencies
    dependencies = {
        "easyeda2kicad": "EasyEDA import functionality",
        "kiutils": "KiCad library utilities",
    }

    for dep_name, description in dependencies.items():
        try:
            __import__(dep_name)
            logging.info(f"✓ {dep_name} loaded successfully")
        except ImportError as e:
            missing_deps.append((dep_name, description, str(e)))
            logging.error(f"✗ {dep_name} not available: {e}")

    return missing_deps


def show_dependency_error(missing_deps):
    """Show dependency error using wx MessageBox"""
    try:
        import wx

        error_msg = "Missing Plugin Dependencies!\n\n"
        error_msg += "The following required dependencies are not available:\n\n"

        for dep_name, description, error in missing_deps:
            error_msg += f"• {dep_name}: {description}\n"

        error_msg += "\n" + "=" * 50 + "\n"
        error_msg += "Solutions:\n"
        error_msg += "1. Run the included 'install_dependencies.py' script\n"
        error_msg += "2. Install manually: pip install easyeda2kicad>=0.6.5\n"
        error_msg += "3. Re-download the plugin package with embedded dependencies\n\n"
        error_msg += "For kiutils, install from: github.com/Steffen-W/kiutils"

        # Create a temporary app if none exists
        app = None
        if not wx.GetApp():
            app = wx.App()

        dlg = wx.MessageDialog(
            None, error_msg, "Plugin Dependency Error", wx.OK | wx.ICON_ERROR
        )
        dlg.ShowModal()
        dlg.Destroy()

        if app:
            app.Destroy()

        return True

    except ImportError:
        # wx not available - fallback to console
        print("ERROR: Missing Plugin Dependencies!")
        for dep_name, description, error in missing_deps:
            print(f"  {dep_name}: {error}")
        return False


def try_auto_install_missing(missing_deps):
    """Try to auto-install missing dependencies"""
    if not missing_deps:
        return True

    success_count = 0
    script_dir = Path(__file__).resolve().parent
    target_dir = script_dir / "lib" / "site-packages"
    target_dir.mkdir(parents=True, exist_ok=True)

    for dep_name, description, error in missing_deps:
        try:
            if dep_name == "easyeda2kicad":
                import subprocess

                subprocess.check_call(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--target",
                        str(target_dir),
                        "--no-deps",
                        "easyeda2kicad>=0.6.5",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # Add to path and verify
                if str(target_dir) not in sys.path:
                    sys.path.insert(0, str(target_dir))

                import easyeda2kicad

                success_count += 1
                logging.info(f"✓ Auto-installed {dep_name}")

        except Exception as e:
            logging.error(f"✗ Auto-install failed for {dep_name}: {e}")

    return success_count == len(missing_deps)


class ActionImpartPlugin(pcbnew.ActionPlugin):
    """KiCad Action Plugin for library import."""

    def defaults(self) -> None:
        """Set plugin defaults."""
        plugin_dir = Path(__file__).resolve().parent
        self.plugin_dir = plugin_dir

        self.name = "impartGUI"
        self.category = "Import library files"
        self.description = "Import library files from Octopart, Samacsys, Ultralibrarian, Snapeda and EasyEDA"
        self.show_toolbar_button = True

        icon_path = plugin_dir / "icon.png"
        logging.info(icon_path)
        self.icon_file_name = str(icon_path)
        self.dark_icon_file_name = str(icon_path)

    def Run(self) -> None:
        """Run the plugin with dependency checking."""
        try:
            # Setup and check embedded dependencies (OLD API only)
            logging.info("Setting up dependencies for old plugin API...")
            missing_deps = setup_embedded_dependencies()

            if missing_deps:
                logging.error(
                    f"Missing dependencies: {[dep[0] for dep in missing_deps]}"
                )

                # Try auto-installation first
                if try_auto_install_missing(missing_deps):
                    logging.info("Successfully auto-installed missing dependencies")
                    # Re-check after auto-install
                    missing_deps = setup_embedded_dependencies()

                # If still missing dependencies, show error
                if missing_deps:
                    success = show_dependency_error(missing_deps)
                    if not success:
                        # Fallback error handling if wx fails
                        raise ImportError(
                            f"Missing dependencies: {[dep[0] for dep in missing_deps]}"
                        )
                    return

            # All dependencies available - proceed with plugin
            logging.info("All dependencies available - starting plugin")

            from .impart_action import ImpartFrontend

            frontend = ImpartFrontend()
            frontend.ShowModal()
            frontend.Destroy()

        except Exception as e:
            logging.exception("Failed to run plugin frontend")

            # Show error in wx if possible
            try:
                import wx

                app = None
                if not wx.GetApp():
                    app = wx.App()

                error_msg = (
                    f"Plugin Error!\n\n{str(e)}\n\nCheck plugin.log for details."
                )
                dlg = wx.MessageDialog(
                    None, error_msg, "Plugin Error", wx.OK | wx.ICON_ERROR
                )
                dlg.ShowModal()
                dlg.Destroy()

                if app:
                    app.Destroy()

            except ImportError:
                # wx not available
                print(f"Plugin Error: {e}")

            raise


ActionImpartPlugin().register()
