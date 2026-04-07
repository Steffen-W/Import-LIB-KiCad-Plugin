# Simplified EasyEDA to KiCad importer
# Based on: https://github.com/uPesy/easyeda2kicad.py/blob/master/easyeda2kicad/__main__.py
from __future__ import annotations

import gzip
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NamedTuple

# Configure logging
logger = logging.getLogger(__name__)

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

from easyeda2kicad.easyeda.easyeda_api import EasyedaApi  # noqa: E402
from easyeda2kicad.easyeda.easyeda_importer import (  # noqa: E402
    Easyeda3dModelImporter,
    EasyedaFootprintImporter,
    EasyedaSymbolImporter,
)
from easyeda2kicad.easyeda.parameters_easyeda import EeFootprint  # noqa: E402
from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad  # noqa: E402
from easyeda2kicad.kicad.export_kicad_footprint import (  # noqa: E402
    ExporterFootprintKicad,
)
from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad  # noqa: E402

logger.info("Successfully imported easyeda2kicad modules")


class ImportPaths(NamedTuple):
    """Container for all generated file paths"""

    symbol_lib: Path | None = None
    footprint_file: Path | None = None
    model_wrl: Path | None = None
    model_step: Path | None = None


@dataclass
class ImportConfig:
    """Configuration for import operations"""

    base_folder: Path
    lib_name: str = "EasyEDA"
    overwrite: bool = False
    lib_var: str = "${EASYEDA2KICAD}"
    prefer_step: bool = False
    compress_models: bool = False


class EasyEDAImporter:
    """EasyEDA to KiCad component importer"""

    def __init__(self, config: ImportConfig, print_func: Callable[[str], None] | None = None):
        self.print_func = print_func or (lambda _: None)
        self.config = config
        self.config.base_folder = Path(self.config.base_folder).expanduser()
        self.api = EasyedaApi()

        self.symbol_lib_path = self.config.base_folder / f"{self.config.lib_name}.kicad_sym"
        self.footprint_dir = self.config.base_folder / f"{self.config.lib_name}.pretty"
        self.model_dir = self.config.base_folder / f"{self.config.lib_name}.3dshapes"

    def _print(self, message: str) -> None:
        self.print_func(message)

    def _ensure_directories(self) -> None:
        self.config.base_folder.mkdir(parents=True, exist_ok=True)
        self.footprint_dir.mkdir(exist_ok=True)
        self.model_dir.mkdir(exist_ok=True)

    def _import_symbol(self, cad_data: dict[str, Any]) -> tuple[bool, str | None]:
        """Import symbol and return success status and component name."""
        try:
            easyeda_symbol = EasyedaSymbolImporter(easyeda_cp_cad_data=cad_data).get_symbol()
            component_name = easyeda_symbol.info.name

            exporter = ExporterSymbolKicad(
                symbol=easyeda_symbol,
                lib_path=str(self.symbol_lib_path),
            )
            if not exporter.save_to_lib(
                lib_path=str(self.symbol_lib_path),
                footprint_lib_name=self.config.lib_name,
                overwrite=self.config.overwrite,
            ):
                self._print(f"Symbol '{component_name}' already exists.")
                return False, component_name

            if easyeda_symbol.sub_symbols:
                self._print(
                    f"Imported {len(easyeda_symbol.sub_symbols)} sub-symbols for: {component_name}"
                )
            self._print(f"Saved symbol: {component_name}")
            return True, component_name

        except Exception as e:
            self._print(f"Failed to import symbol: {e}")
            logger.error(f"Symbol import failed: {e}")
            return False, None

    def _import_footprint(self, ee_footprint: EeFootprint, model_ext: str = "wrl") -> Path | None:
        """Export footprint to .kicad_mod and return the file path."""
        try:
            footprint_file = self.footprint_dir / f"{ee_footprint.info.name}.kicad_mod"

            if footprint_file.exists() and not self.config.overwrite:
                self._print(f"Footprint already exists: {footprint_file.name}")
                return None

            model_3d_path = f"{self.config.lib_var}/{self.config.lib_name}.3dshapes"
            ExporterFootprintKicad(footprint=ee_footprint).export(
                footprint_full_path=str(footprint_file),
                model_3d_path=model_3d_path,
                model_3d_extension=model_ext,
            )
            self._print(f"Created footprint: {footprint_file.name}")
            return footprint_file

        except Exception as e:
            self._print(f"Failed to import footprint: {e}")
            logger.error(f"Footprint import failed: {e}")
            return None

    def _import_3d_model(self, cad_data: dict[str, Any]) -> tuple[Path | None, Path | None]:
        """Download and export 3D model. Returns (wrl_path, step_path).

        When compress_models is True, STEP is saved as .step.gz (gzip),
        natively supported by KiCad >= 6.0. WRL is not compressed.
        """
        try:
            model_3d = Easyeda3dModelImporter(
                easyeda_cp_cad_data=cad_data,
                download_raw_3d_model=True,
                api=self.api,
            ).output

            if model_3d is None:
                self._print("No 3D model available for this component.")
                return None, None

            exporter = Exporter3dModelKicad(model_3d=model_3d)
            if not exporter.output:
                self._print("No 3D model available for this component.")
                return None, None

            model_name = exporter.output.name

            # When compression is on, check for already-compressed files before exporting
            if not self.config.overwrite and self.config.compress_models:
                step_gz = self.model_dir / f"{model_name}.step.gz"
                if step_gz.exists():
                    self._print("3D model files already exist.")
                    wrl_path = self.model_dir / f"{model_name}.wrl"
                    return wrl_path if wrl_path.exists() else None, step_gz

            if not exporter.export(output_dir=str(self.model_dir), overwrite=self.config.overwrite):
                self._print("3D model files already exist.")
                return None, None

            wrl_path = self.model_dir / f"{model_name}.wrl"
            step_path = self.model_dir / f"{model_name}.step"

            wrl: Path | None = wrl_path if wrl_path.exists() else None
            step: Path | None = step_path if step_path.exists() else None

            if self.config.compress_models and step:
                gz_path = step.parent / (step.name + ".gz")
                with (
                    open(step, "rb") as f_in,
                    gzip.open(gz_path, "wb", compresslevel=9) as f_out,
                ):
                    f_out.write(f_in.read())
                step.unlink()
                step = gz_path

            if wrl:
                self._print(f"Created 3D model (WRL): {wrl.name}")
            if step:
                self._print(f"Created 3D model (STEP): {step.name}")

            return wrl, step

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

        if not component_id.startswith("C"):
            error_msg = (
                f"Invalid component ID: '{component_id}' (must start with 'C', e.g., 'C2040')"
            )
            self._print(error_msg)
            raise ValueError(error_msg)

        self._ensure_directories()

        try:
            cad_data = self.api.get_cad_data_of_component(lcsc_id=component_id)
            if not cad_data:
                error_msg = f"Failed to fetch CAD data for component {component_id}"
                self._print(error_msg)
                raise RuntimeError(error_msg)

            # Parse footprint for footprint export
            ee_footprint = EasyedaFootprintImporter(easyeda_cp_cad_data=cad_data).get_footprint()

            symbol_ok, _ = self._import_symbol(cad_data)
            wrl_path, step_path = self._import_3d_model(cad_data)
            use_step = self.config.prefer_step and step_path is not None
            if use_step and step_path:
                model_ext = "step.gz" if self.config.compress_models else "step"
            else:
                model_ext = "wrl"
            footprint_path = self._import_footprint(ee_footprint, model_ext=model_ext)

            result = ImportPaths(
                symbol_lib=self.symbol_lib_path if symbol_ok else None,
                footprint_file=footprint_path,
                model_wrl=wrl_path,
                model_step=step_path,
            )

            created_files = sum(1 for path in result if path)
            if created_files > 0:
                self._print(
                    f"EasyEDA import completed successfully! ({created_files} files created)"
                )
            else:
                self._print("EasyEDA import completed, but no new files were created")

            return result

        except Exception as e:
            self._print(f"EasyEDA import failed: {e}")
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

    config = ImportConfig(
        base_folder=Path("~/Documents/Kicad/EasyEDA"),
        lib_name="EasyEDA",
        overwrite=False,
    )

    try:
        paths = import_easyeda_component("C2040", config, print)

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
