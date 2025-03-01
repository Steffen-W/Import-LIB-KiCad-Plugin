from pathlib import Path
import logging

from .kicad_cli import kicad_cli

logger = logging.getLogger(__name__)
cli = kicad_cli()


def find_old_lib_files(
    folder_path: str,
    libs: list[str] = ["Octopart", "Samacsys", "UltraLibrarian", "Snapeda", "EasyEDA"],
) -> list:

    folder_path = Path(folder_path).expanduser()
    found_files = {}

    if not folder_path.exists():
        return found_files

    for file in folder_path.iterdir():
        if not file.is_file():
            continue

        if not (file.name.endswith(".lib") or file.name.endswith(".kicad_sym")):
            continue

        for lib in libs:
            if file.name.startswith(lib):

                if lib in found_files:
                    entry = found_files[lib]
                else:
                    entry = {}

                # Check whether the file ends with ".lib"
                if file.name.endswith(".lib"):
                    entry["old_lib"] = file

                    blk_file = file.with_suffix(".lib.blk")
                    if blk_file.exists() and blk_file.is_file():
                        entry["old_lib_blk"] = blk_file  # backup file

                    dcm_file = file.with_suffix(".dcm")
                    if dcm_file.exists() and dcm_file.is_file():
                        entry["old_lib_dcm"] = dcm_file  # description file

                # Check whether the file with the old kicad v6 name exists
                elif file.name.endswith("_kicad_sym.kicad_sym"):
                    entry["oldV6"] = file

                    dcm_file = file.with_suffix(".dcm")
                    if dcm_file.exists() and dcm_file.is_file():
                        entry["oldV6_dcm"] = dcm_file  # description file

                    blk_file = file.with_suffix(".kicad_sym.blk")
                    if blk_file.exists() and blk_file.is_file():
                        entry["oldV6_blk"] = blk_file  # backup file

                # Check whether the file with the normal ".kicad_sym" extension exists
                elif file.name.endswith(".kicad_sym"):
                    entry["V6"] = file

                    dcm_file = file.with_suffix(".dcm")
                    if dcm_file.exists() and dcm_file.is_file():
                        entry["V6_dcm"] = dcm_file  # description file

                    blk_file = file.with_suffix(".kicad_sym.blk")
                    if blk_file.exists() and blk_file.is_file():
                        entry["V6_blk"] = blk_file  # backup file

                kicad_sym_file = file.with_name(lib + "_old_lib.kicad_sym")
                if kicad_sym_file.exists() and kicad_sym_file.is_file():
                    # Possible conversion name
                    entry["old_lib_kicad_sym"] = kicad_sym_file

                if entry:
                    found_files[lib] = entry
    return found_files


def convert_lib(SRC: Path, DES: Path, drymode=True):

    BLK_file = SRC.with_suffix(SRC.suffix + ".blk")  # Backup

    msg = []

    if drymode:
        msg.append([SRC.name, DES.name])
        msg.append([SRC.name, BLK_file.name])

    else:

        SRC_dcm = SRC.with_suffix(".dcm")
        DES_dcm = DES.with_suffix(".dcm")
        if DES_dcm.exists() and DES_dcm.is_file():
            return []

        if not cli.upgrade_sym_lib(SRC, DES) or not DES.exists():
            logger.error(f"converting {SRC.name} to {DES.name} produced an error")
            return []
        msg.append([SRC.stem, DES.stem])

        if SRC_dcm.exists() and SRC_dcm.is_file():
            SRC_dcm.rename(DES_dcm)

        SRC.rename(BLK_file)
        msg.append([SRC.name, BLK_file.name])

    return msg


def convert_lib_list(libs_dict, drymode=True):

    if not cli.exists():
        logger.error("kicad_cli not found! Conversion is not possible.")
        drymode = True

    convertlist = []
    for lib, paths in libs_dict.items():

        # if "V6" in paths:
        #     print(f"No conversion needed for {lib}.")

        if "old_lib" in paths:
            file = paths["old_lib"]
            if "V6" in paths or "oldV6" in paths:
                if "old_lib_kicad_sym" in paths:
                    logger.error(f"{lib} old_lib_kicad_sym already exists")
                else:
                    kicad_sym_file = file.with_name(file.stem + "_old_lib.kicad_sym")
                    res = convert_lib(SRC=file, DES=kicad_sym_file, drymode=drymode)
                    convertlist.extend(res)
            else:
                name_V6 = file.with_name(lib + ".kicad_sym")
                res = convert_lib(SRC=file, DES=name_V6, drymode=drymode)
                convertlist.extend(res)

        if "oldV6" in paths:
            file = paths["oldV6"]
            if "V6" in paths:
                logger.error(f"{lib} V6 already exists")
            else:
                name_V6 = file.with_name(lib + ".kicad_sym")
                res = convert_lib(SRC=file, DES=name_V6, drymode=drymode)
                convertlist.extend(res)
    return convertlist


if __name__ == "__main__":
    from pprint import pprint

    logging.basicConfig(level=logging.INFO)

    path = "~/KiCad"
    ret = find_old_lib_files(folder_path=path)
    if ret:
        print("#######################")
        pprint(ret)
        print("#######################")

    conv = convert_lib_list(ret, drymode=True)
    if conv:
        print("#######################")
        pprint(conv)
        print("#######################")
