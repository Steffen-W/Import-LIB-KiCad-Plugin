# Created with strong reference to:
# https://github.com/uPesy/easyeda2kicad.py/blob/master/easyeda2kicad/__main__.py

import os
import logging

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
        cad_data,
        output,
        overwrite=False,
        kicad_version=KicadVersion.v6,
        sym_lib_ext="kicad_sym",
    ):
        importer = EasyedaSymbolImporter(easyeda_cp_cad_data=cad_data)
        easyeda_symbol: EeSymbol = importer.get_symbol()

        is_id_already_in_symbol_lib = id_already_in_symbol_lib(
            lib_path=f"{output}.{sym_lib_ext}",
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
            footprint_lib_name=output.split("/")[-1].split(".")[0],
        )

        if is_id_already_in_symbol_lib:
            update_component_in_symbol_lib_file(
                lib_path=f"{output}.{sym_lib_ext}",
                component_name=easyeda_symbol.info.name,
                component_content=kicad_symbol_lib,
                kicad_version=kicad_version,
            )
        else:
            add_component_in_symbol_lib_file(
                lib_path=f"{output}.{sym_lib_ext}",
                component_content=kicad_symbol_lib,
                kicad_version=kicad_version,
            )

        self.print(f"Created Kicad symbol {easyeda_symbol.info.name}")
        print(f"Library path : {output}.{sym_lib_ext}")

    def import_Footprint(
        self, cad_data, output, overwrite=False, lib_name="EASYEDA2KICAD"
    ):
        importer = EasyedaFootprintImporter(easyeda_cp_cad_data=cad_data)
        easyeda_footprint = importer.get_footprint()

        is_id_already_in_footprint_lib = os.path.isfile(
            f"{output}.pretty/{easyeda_footprint.info.name}.kicad_mod"
        )

        if not overwrite and is_id_already_in_footprint_lib:
            self.print("Use overwrite option to replace the older footprint")
            return 1

        ki_footprint = ExporterFootprintKicad(footprint=easyeda_footprint)
        footprint_filename = f"{easyeda_footprint.info.name}.kicad_mod"
        footprint_path = f"{output}.pretty"
        model_3d_path = f"{output}.3dshapes".replace("\\", "/").replace("./", "/")

        model_3d_path = f"${{{lib_name}}}/EasyEDA.3dshapes"

        ki_footprint.export(
            footprint_full_path=f"{footprint_path}/{footprint_filename}",
            model_3d_path=model_3d_path,
        )

        self.print(f"Created Kicad footprint {easyeda_footprint.info.name}")
        print(f"Footprint path: {os.path.join(footprint_path, footprint_filename)}")

    def import_3D_Model(self, cad_data, output, overwrite=True):
        model_3d = Easyeda3dModelImporter(
            easyeda_cp_cad_data=cad_data, download_raw_3d_model=True
        ).output

        if not model_3d:
            self.print(f"No 3D model available for this component.")
            return

        exporter = Exporter3dModelKicad(model_3d=model_3d)

        if exporter.output or exporter.output_step:
            filename_wrl = f"{exporter.output.name}.wrl"
            filename_step = f"{exporter.output.name}.step"
            lib_path = f"{output}.3dshapes"

            filepath_wrl = os.path.join(lib_path, filename_wrl)
            filepath_step = os.path.join(lib_path, filename_step)

            formats = ""
            if os.path.exists(filepath_wrl) and not overwrite:
                self.print(
                    f"3D model (wrl) exists:Use overwrite option to replace the 3D model"
                )
                return
            else:
                formats += "wrl"

            if os.path.exists(filepath_step) and not overwrite:
                self.print(
                    f"3D model (wrl) exists:Use overwrite option to replace the 3D model"
                )
                return
            else:
                formats += ",step"

            exporter.export(lib_path=output)
            self.print(f"Created 3D model {exporter.output.name} ({formats})")
            if filename_wrl:
                print("3D model path (wrl): " + filepath_wrl)
            if filename_step:
                print("3D model path (step): " + filepath_step)

    def full_import(
        self,
        component_id="C2040",
        base_folder=False,
        overwrite=False,
        lib_var="KICAD_3RD_PARTY",
    ):

        base_folder = os.path.expanduser(base_folder)

        if not component_id.startswith("C"):
            self.print("lcsc_id should start by C.... example: C2040")
            return False

        if not os.path.isdir(base_folder):
            os.makedirs(base_folder, exist_ok=True)

        lib_name = "EasyEDA"
        output = f"{base_folder}/{lib_name}"

        # Create new footprint folder if it does not exist
        if not os.path.isdir(f"{output}.pretty"):
            os.mkdir(f"{output}.pretty")
            self.print(f"Create {lib_name}.pretty footprint folder in {base_folder}")

        # Create new 3d model folder if don't exist
        if not os.path.isdir(f"{output}.3dshapes"):
            os.mkdir(f"{output}.3dshapes")
            self.print(f"Create {lib_name}.3dshapes 3D model folder in {base_folder}")

        lib_extension = "kicad_sym"
        if not os.path.isfile(f"{output}.{lib_extension}"):
            with open(
                file=f"{output}.{lib_extension}", mode="w+", encoding="utf-8"
            ) as my_lib:
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
        self.import_Symbol(cad_data, output, overwrite=overwrite)
        # ---------------- FOOTPRINT -------------
        self.import_Footprint(cad_data, output, overwrite=overwrite, lib_name=lib_var)
        # ---------------- 3D MODEL --------------
        self.import_3D_Model(cad_data, output, overwrite=overwrite)
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    base_folder = "~/Documents/Kicad/EasyEDA"
    easyeda_import = easyeda2kicad_wrapper()
    easyeda_import.full_import(component_id="C2040", base_folder=base_folder)
