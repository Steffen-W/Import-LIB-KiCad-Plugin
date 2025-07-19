# Simplified EasyEDA to KiCad importer
# Based on: https://github.com/uPesy/easyeda2kicad.py/blob/master/easyeda2kicad/__main__.py

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple, NamedTuple, Callable
from dataclasses import dataclass

# Configure logging
logger = logging.getLogger(__name__)

# Try to import required libraries
try:
    from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
    from easyeda2kicad.kicad.parameters_kicad_symbol import KicadVersion
    from easyeda2kicad.easyeda.parameters_easyeda import EeSymbol

    from easyeda2kicad.helpers import (
        add_component_in_symbol_lib_file,
        id_already_in_symbol_lib,
        update_component_in_symbol_lib_file,
    )

    from easyeda2kicad.easyeda.easyeda_importer import (
        Easyeda3dModelImporter,
        EasyedaFootprintImporter,
        EasyedaSymbolImporter,
    )

    from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad
    from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
    from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad

    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import easyeda2kicad dependencies: {e}")
    DEPENDENCIES_AVAILABLE = False


class ImportPaths(NamedTuple):
    """Container for all generated file paths"""

    symbol_lib: Optional[Path] = None
    footprint_file: Optional[Path] = None
    model_wrl: Optional[Path] = None
    model_step: Optional[Path] = None


@dataclass
class ImportConfig:
    """Configuration for import operations"""

    base_folder: Path
    lib_name: str = "EasyEDA"
    overwrite: bool = False
    lib_var: str = "${EASYEDA2KICAD}"


def ensure_easyeda_module(print_func: Callable[[str], None]) -> bool:
    try:
        import easyeda2kicad

        return True
    except ImportError:
        pass

    print_func("easyeda2kicad not found. Attempting installation...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "easyeda2kicad"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            print_func("easyeda2kicad installed successfully")

            # Try to import again
            try:
                import easyeda2kicad

                print_func("easyeda2kicad imported successfully")

                # Reload the global DEPENDENCIES_AVAILABLE flag
                global DEPENDENCIES_AVAILABLE
                DEPENDENCIES_AVAILABLE = True

                return True
            except ImportError as e:
                print_func(f"Import still failed after installation: {e}")
                return False
        else:
            print_func(f"Installation failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print_func("Installation timed out after 120 seconds")
        return False
    except Exception as e:
        print_func(f"Installation error: {e}")
        return False


class EasyEDAImporter:
    """EasyEDA to KiCad component importer - focused on new symbol format only"""

    def __init__(
        self, config: ImportConfig, print_func: Optional[Callable[[str], None]] = None
    ):
        """Initialize importer with configuration"""
        self.print_func = print_func or (lambda x: None)

        if not DEPENDENCIES_AVAILABLE:
            raise RuntimeError("Required easyeda2kicad library not available")

        self.config = config
        self.config.base_folder = Path(self.config.base_folder).expanduser()
        self.api = EasyedaApi()

        # Paths that will be used
        self.symbol_lib_path = (
            self.config.base_folder / f"{self.config.lib_name}.kicad_sym"
        )
        self.footprint_dir = self.config.base_folder / f"{self.config.lib_name}.pretty"
        self.model_dir = self.config.base_folder / f"{self.config.lib_name}.3dshapes"

    def _print(self, message: str) -> None:
        """Print message using the provided print function"""
        self.print_func(message)

    def _ensure_directories(self) -> None:
        """Create necessary directories"""
        self.config.base_folder.mkdir(parents=True, exist_ok=True)
        self.footprint_dir.mkdir(exist_ok=True)
        self.model_dir.mkdir(exist_ok=True)
        logger.debug(f"Ensured directories exist in {self.config.base_folder}")

    def _ensure_symbol_library(self) -> None:
        """Create symbol library file if it doesn't exist"""
        if not self.symbol_lib_path.exists():
            with open(self.symbol_lib_path, "w", encoding="utf-8") as f:
                f.write(
                    """\
(kicad_symbol_lib
    (version 20211014)
    (generator https://github.com/uPesy/easyeda2kicad.py)
)"""
                )
            self._print(f"Created new symbol library: {self.symbol_lib_path}")

    def _import_symbol(self, cad_data: dict) -> Tuple[bool, Optional[str]]:
        """Import symbol and return success status and component name"""
        try:
            importer = EasyedaSymbolImporter(easyeda_cp_cad_data=cad_data)
            easyeda_symbol: EeSymbol = importer.get_symbol()
            component_name = easyeda_symbol.info.name

            # Check if symbol already exists
            is_existing = id_already_in_symbol_lib(
                lib_path=str(self.symbol_lib_path),
                component_name=component_name,
                kicad_version=KicadVersion.v6,
            )

            if is_existing and not self.config.overwrite:
                self._print(f"Symbol '{component_name}' already exists.")
                return False, component_name

            # Export symbol
            exporter = ExporterSymbolKicad(
                symbol=easyeda_symbol, kicad_version=KicadVersion.v6
            )
            kicad_symbol_content = exporter.export(
                footprint_lib_name=self.config.lib_name
            )

            # Add or update symbol in library
            if is_existing:
                update_component_in_symbol_lib_file(
                    lib_path=str(self.symbol_lib_path),
                    component_name=component_name,
                    component_content=kicad_symbol_content,
                    kicad_version=KicadVersion.v6,
                )
                self._print(f"Updated symbol: {component_name}")
            else:
                add_component_in_symbol_lib_file(
                    lib_path=str(self.symbol_lib_path),
                    component_content=kicad_symbol_content,
                    kicad_version=KicadVersion.v6,
                )
                self._print(f"Added new symbol: {component_name}")

            return True, component_name

        except Exception as e:
            self._print(f"Failed to import symbol: {e}")
            logger.error(f"Symbol import failed: {e}")
            return False, None

    def _import_footprint(self, cad_data: dict) -> Optional[Path]:
        """Import footprint and return the file path"""
        try:
            importer = EasyedaFootprintImporter(easyeda_cp_cad_data=cad_data)
            easyeda_footprint = importer.get_footprint()

            footprint_file = (
                self.footprint_dir / f"{easyeda_footprint.info.name}.kicad_mod"
            )

            if footprint_file.exists() and not self.config.overwrite:
                self._print(f"Footprint already exists: {footprint_file.name}")
                return None

            exporter = ExporterFootprintKicad(footprint=easyeda_footprint)
            model_3d_path = f"{self.config.lib_var}/{self.config.lib_name}.3dshapes"

            exporter.export(
                footprint_full_path=str(footprint_file),
                model_3d_path=model_3d_path,
            )

            self._print(f"Created footprint: {footprint_file.name}")
            return footprint_file

        except Exception as e:
            self._print(f"Failed to import footprint: {e}")
            logger.error(f"Footprint import failed: {e}")
            return None

    def _import_3d_model(self, cad_data: dict) -> Tuple[Optional[Path], Optional[Path]]:
        """Import 3D model and return paths to wrl and step files"""
        try:
            model_3d = Easyeda3dModelImporter(
                easyeda_cp_cad_data=cad_data, download_raw_3d_model=True
            ).output

            if not model_3d:
                self._print("No 3D model available for this component.")
                return None, None

            exporter = Exporter3dModelKicad(model_3d=model_3d)

            if not (exporter.output or exporter.output_step):
                self._print("No exportable 3D model found.")
                return None, None

            output_name = exporter.output.name if exporter.output else "model"
            filepath_wrl = self.model_dir / f"{output_name}.wrl"
            filepath_step = self.model_dir / f"{output_name}.step"

            # Check existing files
            if not self.config.overwrite:
                if filepath_wrl.exists() or filepath_step.exists():
                    self._print("3D model files already exist.")
                    return None, None

            # Export models
            exporter.export(
                lib_path=str(self.config.base_folder / self.config.lib_name)
            )

            wrl_path = filepath_wrl if filepath_wrl.exists() else None
            step_path = filepath_step if filepath_step.exists() else None

            if wrl_path:
                self._print(f"Created 3D model (WRL): {wrl_path.name}")
            if step_path:
                self._print(f"Created 3D model (STEP): {step_path.name}")

            return wrl_path, step_path

        except Exception as e:
            self._print(f"Failed to import 3D model: {e}")
            logger.error(f"3D model import failed: {e}")
            return None, None

    def import_component(self, component_id: str) -> ImportPaths:
        """
        Import a component and all its assets.
        Returns ImportPaths with all created file paths.
        """
        self._print(f"Starting import for EasyEDA/LCSC component: {component_id}")

        # Validate component ID
        if not component_id.startswith("C"):
            error_msg = f"Invalid component ID: '{component_id}' (must start with 'C', e.g., 'C2040')"
            self._print(error_msg)
            raise ValueError(error_msg)

        # Ensure directories exist
        self._ensure_directories()
        self._ensure_symbol_library()

        try:
            # Fetch CAD data
            cad_data = self.api.get_cad_data_of_component(lcsc_id=component_id)

            if not cad_data:
                error_msg = f"Failed to fetch CAD data for component {component_id}"
                self._print(error_msg)
                raise RuntimeError(error_msg)

            # Import all parts
            symbol_ok, component_name = self._import_symbol(cad_data)
            footprint_path = self._import_footprint(cad_data)
            wrl_path, step_path = self._import_3d_model(cad_data)

            # Prepare result
            result = ImportPaths(
                symbol_lib=self.symbol_lib_path if symbol_ok else None,
                footprint_file=footprint_path,
                model_wrl=wrl_path,
                model_step=step_path,
            )

            # Final status
            created_files = sum(
                1
                for path in [
                    result.symbol_lib,
                    result.footprint_file,
                    result.model_wrl,
                    result.model_step,
                ]
                if path
            )

            if created_files > 0:
                self._print(
                    f"EasyEDA import completed successfully! ({created_files} files created)"
                )
            else:
                self._print("EasyEDA import completed, but no new files were created")

            return result

        except Exception as e:
            error_msg = f"EasyEDA import failed: {e}"
            self._print(error_msg)
            logger.error(f"Component import failed for {component_id}: {e}")
            raise


def import_easyeda_component(
    component_id: str, config: ImportConfig, print_func: Callable[[str], None]
) -> ImportPaths:
    if not ensure_easyeda_module(print_func):
        raise RuntimeError(
            "easyeda2kicad module is not available and could not be installed"
        )

    importer = EasyEDAImporter(config, print_func)
    return importer.import_component(component_id)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def print_to_console(message):
        print(message)

    config = ImportConfig(
        base_folder=Path("~/Documents/Kicad/EasyEDA"),
        lib_name="EasyEDA",
        overwrite=False,
    )

    # Import a component
    try:
        paths = import_easyeda_component("C2040", config, print_to_console)

        # Access the paths
        if paths.symbol_lib:
            print(f"Symbol was written to library: {paths.symbol_lib}")

        if paths.footprint_file:
            print(f"Footprint was created at: {paths.footprint_file}")

        if paths.model_wrl or paths.model_step:
            print("3D models were created:")
            if paths.model_wrl:
                print(f"  WRL: {paths.model_wrl}")
            if paths.model_step:
                print(f"  STEP: {paths.model_step}")

    except Exception as e:
        print(f"Import failed: {e}")
