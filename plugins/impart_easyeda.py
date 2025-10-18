# Simplified EasyEDA to KiCad importer
# Based on: https://github.com/uPesy/easyeda2kicad.py/blob/master/easyeda2kicad/__main__.py
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple, NamedTuple, Callable
from dataclasses import dataclass
import re

# Configure logging
logger = logging.getLogger(__name__)

try:
    from .kicad_cli import kicad_cli
except ImportError:
    from kicad_cli import kicad_cli

try:
    cli = kicad_cli()
    logger.info("✓ kicad_cli initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize kicad_cli: {e}")
    cli = None

current_dir = Path(__file__).resolve().parent
easyeda_submodule = current_dir / "easyeda2kicad"

if easyeda_submodule.exists():
    # Remove any conflicting easyeda2kicad modules from cache first
    modules_to_remove = [k for k in sys.modules.keys() if k.startswith("easyeda2kicad")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add git submodule path at the very beginning
    easyeda_str = str(easyeda_submodule)
    if easyeda_str not in sys.path:
        sys.path.insert(0, easyeda_str)

    logger.info(f"Using easyeda2kicad from: {easyeda_submodule}")

from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.easyeda.easyeda_importer import (
    EasyedaSymbolImporter,
    EasyedaFootprintImporter,
    Easyeda3dModelImporter,
    EeSymbol,
)
from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad
from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad
from easyeda2kicad.helpers import (
    KicadVersion,
    add_component_in_symbol_lib_file,
    id_already_in_symbol_lib,
    update_component_in_symbol_lib_file,
)

logger.info("Successfully imported easyeda2kicad modules")


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


class EasyEDAImporter:
    """EasyEDA to KiCad component importer - focused on new symbol format only"""

    def __init__(
        self, config: ImportConfig, print_func: Optional[Callable[[str], None]] = None
    ):
        """Initialize importer with configuration"""
        self.print_func = print_func or (lambda x: None)
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

    def _import_symbol(self, cad_data: dict) -> Tuple[bool, Optional[str]]:
        """Import symbol and return success status and component name"""
        try:
            importer = EasyedaSymbolImporter(easyeda_cp_cad_data=cad_data)
            easyeda_symbol: EeSymbol = importer.get_symbol()
            component_name = easyeda_symbol.info.name

            # Check if symbol library exists first, then check if symbol already exists
            if self.symbol_lib_path.exists():
                is_existing = id_already_in_symbol_lib(
                    lib_path=str(self.symbol_lib_path),
                    component_name=component_name,
                    kicad_version=KicadVersion.v6,
                )
            else:
                is_existing = False

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

            # Check if export was successful
            if not kicad_symbol_content:
                self._print(f"Failed to export symbol content for: {component_name}")
                return False, component_name

            # Add or update symbol in library
            if is_existing:
                logger.warning(
                    f"Using unsafe legacy update function for existing symbol: {component_name}"
                )
                update_component_in_symbol_lib_file(
                    lib_path=str(self.symbol_lib_path),
                    component_name=component_name,
                    component_content=kicad_symbol_content,
                    kicad_version=KicadVersion.v6,
                )
                self._print(f"Updated symbol: {component_name}")
            else:
                success = self.add_symbol_to_upgraded_lib(kicad_symbol_content)
                if success:
                    self._print(f"Added symbol: {component_name}")
                else:
                    self._print(f"Failed to add symbol: {component_name}")
                    return False, component_name

            return True, component_name

        except Exception as e:
            self._print(f"Failed to import symbol: {e}")
            logger.error(f"Symbol import failed: {e}")
            return False, None

    def get_kicad_lib_version(self, content: str) -> int:
        """Extract version number from KiCad symbol library. Returns 0 if not found."""
        if not content:
            return 0

        match = re.search(r"\(\s*version\s+(\d+)\s*\)", content[:200])
        return int(match.group(1)) if match else 0

    def add_symbol_to_upgraded_lib(self, symbol_content: str) -> bool:
        """Add symbol to library with automatic upgrade handling."""
        try:
            if not symbol_content:
                self._print("Error: Empty symbol content provided")
                return False

            complete_symbol_lib = f"""(kicad_symbol_lib
    (version 20211014)
    (generator https://github.com/uPesy/easyeda2kicad.py)
    {symbol_content}
)"""

            success, upgraded_symbol_lib, error = cli.upgrade_sym_lib_from_string(
                complete_symbol_lib
            )
            if not success:
                self._print(f"Failed to upgrade new symbol: {error}")
                return False

            if self.symbol_lib_path.exists():
                with open(self.symbol_lib_path, "r", encoding="utf-8") as f:
                    existing_lib = f.read()

                existing_version = self.get_kicad_lib_version(existing_lib)
                new_version = self.get_kicad_lib_version(upgraded_symbol_lib)

                if existing_version >= new_version:
                    upgraded_existing_lib = existing_lib
                else:
                    success, upgraded_existing_lib, error = (
                        cli.upgrade_sym_lib_from_string(existing_lib)
                    )
                    if not success:
                        self._print(f"Failed to upgrade existing library: {error}")
                        return False

                symbol_start = upgraded_symbol_lib.find("(symbol ")
                if symbol_start == -1:
                    self._print("Could not find symbol content in upgraded library")
                    return False

                symbol_content_to_add = upgraded_symbol_lib[
                    symbol_start : upgraded_symbol_lib.rfind(")")
                ].strip()

                last_paren_pos = upgraded_existing_lib.rfind(")")
                if last_paren_pos == -1:
                    self._print("Invalid existing library format")
                    return False

                final_lib = (
                    upgraded_existing_lib[:last_paren_pos].rstrip()
                    + "\n    "
                    + symbol_content_to_add
                    + "\n"
                    + upgraded_existing_lib[last_paren_pos:]
                )
            else:
                final_lib = upgraded_symbol_lib

            with open(self.symbol_lib_path, "w", encoding="utf-8") as f:
                f.write(final_lib)

            return True

        except Exception as e:
            self._print(f"Failed to add symbol to library: {e}")
            logger.error(f"Symbol library integration failed: {e}")
            return False

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
