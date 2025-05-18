# Created with strong reference to:
# https://github.com/uPesy/easyeda2kicad.py/blob/master/easyeda2kicad/__main__.py

import logging
from pathlib import Path
from typing import Union, Optional

logging.basicConfig(level=logging.ERROR)

from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.kicad.parameters_kicad_symbol import KicadVersion
from easyeda2kicad.easyeda.parameters_easyeda import EeSymbol

from easyeda2kicad.helpers import add_component_in_symbol_lib_file
from easyeda2kicad.helpers import id_already_in_symbol_lib
from easyeda2kicad.helpers import update_component_in_symbol_lib_file

from easyeda2kicad.easyeda.easyeda_importer import Easyeda3dModelImporter
from easyeda2kicad.easyeda.easyeda_importer import EasyedaFootprintImporter
from easyeda2kicad.easyeda.easyeda_importer import EasyedaSymbolImporter

from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad
from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad


class easyeda2kicad_wrapper:

    def print(self, txt):
        print("easyeda:" + txt)

    def import_Symbol(
        self,
        cad_data: dict,
        output: Path,
        overwrite: bool = False,
        kicad_version: KicadVersion = KicadVersion.v6,
        sym_lib_ext: str = "kicad_sym",
    ):
        importer = EasyedaSymbolImporter(easyeda_cp_cad_data=cad_data)
        easyeda_symbol: EeSymbol = importer.get_symbol()

        lib_file = output.with_suffix(f".{sym_lib_ext}")

        is_id_already_in_symbol_lib = id_already_in_symbol_lib(
            lib_path=str(lib_file),
            component_name=easyeda_symbol.info.name,
            kicad_version=kicad_version,
        )

        if not overwrite and is_id_already_in_symbol_lib:
            self.print("Use overwrite option to update the older symbol")
            return 1

        exporter = ExporterSymbolKicad(
            symbol=easyeda_symbol, kicad_version=kicad_version
        )
        kicad_symbol_lib = exporter.export(
            footprint_lib_name=output.name,
        )

        if is_id_already_in_symbol_lib:
            update_component_in_symbol_lib_file(
                lib_path=str(lib_file),
                component_name=easyeda_symbol.info.name,
                component_content=kicad_symbol_lib,
                kicad_version=kicad_version,
            )
        else:
            add_component_in_symbol_lib_file(
                lib_path=str(lib_file),
                component_content=kicad_symbol_lib,
                kicad_version=kicad_version,
            )

        self.print(f"Created Kicad symbol {easyeda_symbol.info.name}")
        print(f"Library path : {lib_file}")

    def import_Footprint(
        self, cad_data, output: Path, overwrite=False, lib_name="${EASYEDA2KICAD}"
    ):
        importer = EasyedaFootprintImporter(easyeda_cp_cad_data=cad_data)
        easyeda_footprint = importer.get_footprint()

        footprint_path = output.parent / f"{output.name}.pretty"
        footprint_file = footprint_path / f"{easyeda_footprint.info.name}.kicad_mod"

        if not overwrite and footprint_file.exists():
            self.print("Use overwrite option to replace the older footprint")
            return 1

        ki_footprint = ExporterFootprintKicad(footprint=easyeda_footprint)
        model_3d_path = f"{lib_name}/EasyEDA.3dshapes"

        ki_footprint.export(
            footprint_full_path=str(footprint_file),
            model_3d_path=model_3d_path,
        )

        self.print(f"Created Kicad footprint {easyeda_footprint.info.name}")
        print(f"Footprint path: {footprint_file}")

    def import_3D_Model(self, cad_data, output_path: Path, overwrite=True):
        model_3d = Easyeda3dModelImporter(
            easyeda_cp_cad_data=cad_data, download_raw_3d_model=True
        ).output

        if not model_3d:
            self.print(f"No 3D model available for this component.")
            return

        exporter = Exporter3dModelKicad(model_3d=model_3d)

        if exporter.output or exporter.output_step:
            model_dir = output_path.parent / f"{output_path.name}.3dshapes"

            output_name = exporter.output.name if exporter.output else "model"
            filepath_wrl = model_dir / f"{output_name}.wrl"
            filepath_step = model_dir / f"{output_name}.step"
            formats = []

            if filepath_wrl.exists() and not overwrite:
                self.print(
                    "3D model (wrl) exists: Use overwrite option to replace the 3D model"
                )
                return
            else:
                formats.append("wrl")

            if filepath_step.exists() and not overwrite:
                self.print(
                    "3D model (step) exists: Use overwrite option to replace the 3D model"
                )
                return
            else:
                formats.append("step")

            exporter.export(lib_path=str(output_path))

            formats_str = ", ".join(formats)
            model_name = exporter.output.name if exporter.output else output_name
            self.print(f"Created 3D model {model_name} ({formats_str})")

            if "wrl" in formats:
                print(f"3D model path (wrl): {filepath_wrl}")
            if "step" in formats:
                print(f"3D model path (step): {filepath_step}")

    def full_import(
        self,
        component_id: str = "C2040",
        base_folder: Union[str, Path, None] = "~/Documents/Kicad/EasyEDA",
        overwrite: bool = False,
        lib_var: str = "${EASYEDA2KICAD}",
    ) -> int:
        if base_folder is None:
            base_folder = "~/Documents/Kicad/EasyEDA"

        base_folder = Path(base_folder).expanduser()

        if not component_id.startswith("C"):
            self.print("lcsc_id should start by C.... example: C2040")
            return False

        # Create the base directory if it does not exist
        base_folder.mkdir(parents=True, exist_ok=True)

        lib_name = "EasyEDA"
        output_path = base_folder / lib_name

        # Create new footprint folder if it does not exist
        footprint_dir = base_folder / f"{lib_name}.pretty"
        footprint_dir.mkdir(exist_ok=True)
        self.print(f"Create {lib_name}.pretty footprint folder in {base_folder}")

        # Create new 3d model folder if don't exist
        model_dir = base_folder / f"{lib_name}.3dshapes"
        model_dir.mkdir(exist_ok=True)
        self.print(f"Create {lib_name}.3dshapes 3D model folder in {base_folder}")

        # Create symbol library if it does not exist
        lib_extension = "kicad_sym"
        lib_file = base_folder / f"{lib_name}.{lib_extension}"

        if not lib_file.exists():
            with open(lib_file, mode="w+", encoding="utf-8") as my_lib:
                my_lib.write(
                    """\
                    (kicad_symbol_lib
                    (version 20211014)
                    (generator https://github.com/uPesy/easyeda2kicad.py)
                    )"""
                )
            self.print(f"Create {lib_name}.{lib_extension} symbol lib in {base_folder}")

        # Get CAD data of the component using easyeda API
        api = EasyedaApi()
        cad_data = api.get_cad_data_of_component(lcsc_id=component_id)

        # API returned no data
        if not cad_data:
            self.print(f"Failed to fetch data from EasyEDA API for part {component_id}")
            return 1

        # ---------------- SYMBOL ----------------
        self.import_Symbol(cad_data, output_path, overwrite=overwrite)
        # ---------------- FOOTPRINT -------------
        self.import_Footprint(
            cad_data, output_path, overwrite=overwrite, lib_name=lib_var
        )
        # ---------------- 3D MODEL --------------
        self.import_3D_Model(cad_data, output_path, overwrite=overwrite)
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    base_folder = "~/Documents/Kicad/EasyEDA"
    easyeda_import = easyeda2kicad_wrapper()
    easyeda_import.full_import(component_id="C2040", base_folder=base_folder)
