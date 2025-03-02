#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles. Currently assembles just
# symbols and footptints. Tested with KiCad 7.0 for Ubuntu.
import pathlib
from enum import Enum
from zipfile import Path
from typing import Tuple, Union, Any
import re
import zipfile
from os import stat, remove
from os.path import isfile
import logging


if __name__ == "__main__":
    from kicad_cli import kicad_cli
    from s_expression_parse import parse_sexp, search_recursive, extract_properties
else:
    from .kicad_cli import kicad_cli
    from .s_expression_parse import parse_sexp, search_recursive, extract_properties

cli = kicad_cli()


class Modification(Enum):
    MKDIR = 0
    TOUCH_FILE = 1
    MODIFIED_FILE = 2
    EXTRACTED_FILE = 3


class ModifiedObject:
    def __init__(self):
        self.dict = {}

    def append(self, obj: pathlib.Path, modification: Modification):
        self.dict[obj] = modification


# keeps track of which files were modified in case an error occurs we can revert these changes before exiting
modified_objects = ModifiedObject()


def check_file(path: pathlib.Path):
    """
    Check if file exists, if not create parent directories and touch file
    :param path:
    """
    if not path.exists():
        if not path.parent.is_dir():
            path.parent.mkdir(parents=True)
            modified_objects.append(path.parent, Modification.MKDIR)
        path.touch(mode=0o666)
        modified_objects.append(path, Modification.TOUCH_FILE)


def unzip(root, suffix):
    """
    return zipfile.Path starting with root ending with suffix else return None
    """
    match = None

    def zipper(parent):
        if parent.name.endswith(suffix):
            return parent
        elif parent.is_dir():
            for child in parent.iterdir():
                match = zipper(child)
                if match:
                    return match

    match = zipper(root)

    return match


class REMOTE_TYPES(Enum):
    Octopart = 0
    Samacsys = 1
    UltraLibrarian = 2
    Snapeda = 3


class import_lib:
    def print(self, txt):
        print("->" + txt)

    def __init__(self):
        self.KICAD_3RD_PARTY_LINK = "${KICAD_3RD_PARTY}"

    def set_DEST_PATH(self, DEST_PATH_=pathlib.Path.home() / "KiCad"):
        self.DEST_PATH = pathlib.Path(DEST_PATH_)

    def cleanName(self, name):
        invalid = '<>:"/\\|?* '
        name = name.strip()
        for char in invalid:  # remove invalid characters
            name = name.replace(char, "_")
        return name

    def get_remote_info(
        self, zf: zipfile.ZipFile
    ) -> Tuple[Path, Path, Path, Path, REMOTE_TYPES]:
        """
        :param root_path:
        :type root_path: Path
        :return: dcm_path, lib_path, footprint_path, model_path, remote_type
        """
        self.footprint_name = None

        root_path = zipfile.Path(zf)
        self.dcm_path = root_path / "device.dcm"
        self.lib_path = root_path / "device.lib"
        self.footprint_path = root_path / "device.pretty"
        self.model_path = root_path / "device.step"
        # todo fill in model path for OCTOPART
        if (
            self.dcm_path.exists()
            and self.lib_path.exists()
            and self.footprint_path.exists()
        ):
            remote_type = REMOTE_TYPES.Octopart
            return (
                self.dcm_path,
                self.lib_path,
                self.footprint_path,
                self.model_path,
                remote_type,
            )

        self.lib_path_new = unzip(root_path, ".kicad_sym")

        directory = unzip(root_path, "KiCad")
        if directory:
            self.dcm_path = unzip(directory, ".dcm")
            self.lib_path = unzip(directory, ".lib")
            self.footprint_path = directory
            self.model_path = unzip(root_path, ".step")
            if not self.model_path:
                self.model_path = unzip(root_path, ".stp")

            assert self.dcm_path and (
                self.lib_path or self.lib_path_new
            ), "Not in samacsys format"
            remote_type = REMOTE_TYPES.Samacsys
            return (
                self.dcm_path,
                self.lib_path,
                self.footprint_path,
                self.model_path,
                remote_type,
            )

        directory = root_path / "KiCAD"
        if directory.exists():
            self.dcm_path = unzip(directory, ".dcm")
            self.lib_path = unzip(directory, ".lib")
            self.footprint_path = unzip(directory, ".pretty")
            self.model_path = unzip(root_path, ".step")
            if not self.model_path:
                self.model_path = unzip(root_path, ".stp")

            assert (
                self.lib_path or self.lib_path_new
            ) and self.footprint_path, "Not in ultralibrarian format"
            remote_type = REMOTE_TYPES.UltraLibrarian
            return (
                self.dcm_path,
                self.lib_path,
                self.footprint_path,
                self.model_path,
                remote_type,
            )

        footprint = unzip(root_path, ".kicad_mod")
        self.lib_path = unzip(root_path, ".lib")
        if self.lib_path or self.lib_path_new:
            self.dcm_path = unzip(root_path, ".dcm")
            # self.footprint_path = root_path
            self.footprint_path = None
            if footprint:
                self.footprint_path = footprint.parent
            self.model_path = unzip(root_path, ".step")
            remote_type = REMOTE_TYPES.Snapeda

            assert (
                self.lib_path or self.lib_path_new
            ) and self.footprint_path, "Not in Snapeda format"
            return (
                self.dcm_path,
                self.lib_path,
                self.footprint_path,
                self.model_path,
                remote_type,
            )

        if footprint or self.lib_path_new:
            assert False, "Unknown library zipfile"
        else:
            assert False, "zipfile is probably not a library to import"

    def import_dcm(
        self,
        device: str,
        remote_type: REMOTE_TYPES,
        dcm_path: pathlib.Path,
        overwrite_if_exists=True,
        file_ending="",
    ) -> Tuple[Union[pathlib.Path, None], Union[pathlib.Path, None]]:
        """
        # .dcm file parsing
        # Note this reads in the existing dcm file for the particular remote repo, and tries to catch any duplicates
        # before overwriting or creating duplicates. It reads the existing dcm file line by line and simply copy+paste
        # each line if nothing will be overwritten or duplicated. If something could be overwritten or duplicated, the
        # terminal will prompt whether to overwrite or to keep the existing content and ignore the new file contents.
        :returns: dcm_file_read, dcm_file_write
        """

        self.dcm_skipped = False

        # Array of values defining all attributes of .dcm file
        dcm_attributes = (
            dcm_path.read_text(encoding="utf-8").splitlines()
            if dcm_path
            else ["#", "# " + device, "#", "$CMP " + device, "D", "F", "$ENDCMP"]
        )

        # Find which lines contain the component information (ignore the rest).
        index_start = None
        index_end = None
        index_header_start = None

        for attribute_idx, attribute in enumerate(dcm_attributes):
            if index_start is None:
                if attribute.startswith("#"):
                    if attribute.strip() == "#" and index_header_start is None:
                        index_header_start = attribute_idx  # header start
                elif attribute.startswith("$CMP "):
                    component_name = attribute[5:].strip()
                    if not self.cleanName(component_name) == self.cleanName(device):
                        raise Warning("Unexpected device in " + dcm_path.name)
                    dcm_attributes[attribute_idx] = attribute.replace(
                        component_name, device, 1
                    )
                    index_start = attribute_idx
                else:
                    index_header_start = None
            elif index_end is None:
                if attribute.startswith("$CMP "):
                    raise Warning("Multiple devices in " + dcm_path.name)
                elif attribute.startswith("$ENDCMP"):
                    index_end = attribute_idx + 1
                elif attribute.startswith("D"):
                    description = attribute[2:].strip()
                    if description:
                        dcm_attributes[attribute_idx] = "D " + description
                elif attribute.startswith("F"):
                    datasheet = attribute[2:].strip()
                    if datasheet:
                        dcm_attributes[attribute_idx] = "F " + datasheet
        if index_end is None:
            raise Warning(device + "not found in " + dcm_path.name)

        dcm_file_read = self.DEST_PATH / (remote_type.name + file_ending + ".dcm")

        dcm_file_write = self.DEST_PATH / (remote_type.name + ".dcm~")
        overwrite_existing = overwrote_existing = False

        check_file(dcm_file_read)
        check_file(dcm_file_write)

        with dcm_file_read.open("rt", encoding="utf-8") as readfile:
            with dcm_file_write.open("wt", encoding="utf-8") as writefile:
                if stat(dcm_file_read).st_size == 0:
                    # todo Handle appending to empty file
                    with dcm_file_read.open("wt", encoding="utf-8") as template_file:
                        template = ["EESchema-DOCLIB  Version 2.0", "#End Doc Library"]
                        template_file.writelines(line + "\n" for line in template)
                        template_file.close()

                for line in readfile:
                    if re.match("# *end ", line, re.IGNORECASE):
                        if not overwrote_existing:
                            writefile.write(
                                "\n".join(
                                    dcm_attributes[
                                        (
                                            index_start
                                            if index_header_start is None
                                            else index_header_start
                                        ) : index_end
                                    ]
                                )
                                + "\n"
                            )
                        writefile.write(line)
                        break
                    elif line.startswith("$CMP "):
                        component_name = line[5:].strip()
                        if component_name.startswith(device):
                            if overwrite_if_exists:
                                overwrite_existing = True
                                self.print("Overwrite existing dcm")
                            else:
                                overwrite_existing = False
                                # self.print("Import of dcm skipped")
                                self.dcm_skipped = True
                                return dcm_file_read, dcm_file_write
                            writefile.write(
                                "\n".join(dcm_attributes[index_start:index_end]) + "\n"
                            )
                            overwrote_existing = True
                        else:
                            writefile.write(line)
                    elif overwrite_existing:
                        if line.startswith("$ENDCMP"):
                            overwrite_existing = False
                    else:
                        writefile.write(line)

        return dcm_file_read, dcm_file_write

    def import_model(
        self, model_path: pathlib.Path, remote_type: REMOTE_TYPES, overwrite_if_exists
    ) -> Union[pathlib.Path, None]:
        # --------------------------------------------------------------------------------------------------------
        # 3D Model file extraction
        # --------------------------------------------------------------------------------------------------------

        if not model_path:
            return False

        write_file = self.DEST_PATH / (remote_type.name + ".3dshapes") / model_path.name

        self.model_skipped = False

        if write_file.exists():
            if overwrite_if_exists:
                overwrite_existing = True
            else:
                self.print("Import of 3d model skipped")
                self.model_skipped = True
                return model_path

        if model_path.is_file():
            check_file(write_file)
            write_file.write_bytes(model_path.read_bytes())
            modified_objects.append(write_file, Modification.EXTRACTED_FILE)
            if overwrite_if_exists:
                self.print("Overwrite existing 3d model")
            else:
                self.print("Import 3d model")

        return model_path

    def import_footprint(
        self,
        remote_type: REMOTE_TYPES,
        footprint_path: pathlib.Path,
        found_model: pathlib.Path,
        overwrite_if_exists=True,
    ) -> Tuple[Union[pathlib.Path, None], Union[pathlib.Path, None]]:
        """
        # Footprint file parsing
        :returns: footprint_file_read, footprint_file_write
        """

        footprint_file_read = None
        footprint_file_write = None
        self.footprint_skipped = False

        footprint_path_item_tmp = None
        for (
            footprint_path_item
        ) in footprint_path.iterdir():  # try to use only newer file
            if footprint_path_item.name.endswith(".kicad_mod"):
                footprint_path_item_tmp = footprint_path_item
                break
            elif footprint_path_item.name.endswith(".mod"):
                footprint_path_item_tmp = footprint_path_item

        footprint_path_item = footprint_path_item_tmp
        if not footprint_path_item:
            self.print("No footprint found")
            return footprint_file_read, footprint_file_write

        if footprint_path_item.name.endswith("mod"):
            footprint = footprint_path_item.read_text(encoding="utf-8")

            footprint_write_path = self.DEST_PATH / (remote_type.name + ".pretty")
            footprint_file_read = footprint_write_path / footprint_path_item.name
            footprint_file_write = footprint_write_path / (
                footprint_path_item.name + "~"
            )

            if found_model:
                footprint.splitlines()
                model_path = f"{self.KICAD_3RD_PARTY_LINK}/{remote_type.name}.3dshapes/{found_model.name}"
                model = [
                    f'  (model "{model_path}"',
                    "    (offset (xyz 0 0 0))",
                    "    (scale (xyz 1 1 1))",
                    "    (rotate (xyz 0 0 0))",
                    "  )",
                ]

                overwrite_existing = overwrote_existing = False

                if footprint_file_read.exists():
                    if overwrite_if_exists:
                        overwrite_existing = True
                        self.print("Overwrite existing footprint")
                    else:
                        self.print("Import of footprint skipped")
                        self.footprint_skipped = True
                        return footprint_file_read, footprint_file_write

                check_file(footprint_file_read)
                with footprint_file_read.open("wt", encoding="utf-8") as wr:
                    wr.write(footprint)
                    overwrote_existing = True

                check_file(footprint_file_write)

                with footprint_file_read.open("rt", encoding="utf-8") as readfile:
                    with footprint_file_write.open("wt", encoding="utf-8") as writefile:
                        if stat(footprint_file_read).st_size == 0:
                            # todo Handle appending to empty file?
                            pass

                        lines = readfile.readlines()

                        write_3d_into_file = False
                        for line_idx, line in enumerate(lines):
                            if not write_3d_into_file and line_idx == len(lines) - 1:
                                writefile.writelines(
                                    model_line + "\n" for model_line in model
                                )
                                writefile.write(line)
                                break
                            elif line.strip().startswith(r"(model"):
                                writefile.write(model[0] + "\n")
                                write_3d_into_file = True
                            else:
                                writefile.write(line)
                    self.print("Import footprint")
            else:
                check_file(footprint_file_write)
                with footprint_file_write.open("wt", encoding="utf-8") as wr:
                    wr.write(footprint)
                    self.print("Import footprint")

        return footprint_file_read, footprint_file_write

    def import_lib(
        self,
        remote_type: REMOTE_TYPES,
        lib_path: pathlib.Path,
        overwrite_if_exists=True,
    ) -> Tuple[str, Union[pathlib.Path, None], Union[pathlib.Path, None]]:
        """
        .lib file parsing
        Note this reads in the existing lib file for the particular remote repo, and tries to catch any duplicates
        before overwriting or creating duplicates. It reads the existing dcm file line by line and simply copy+paste
        each line if nothing will be overwritten or duplicated. If something could be overwritten or duplicated, the
        terminal will prompt whether to overwrite or to keep the existing content and ignore the new file contents.
        :returns: device, lib_file_read, lib_file_write
        """

        self.lib_skipped = False

        device = None
        lib_lines = lib_path.read_text(encoding="utf-8").splitlines()

        # Find which lines contain the component information in file to be imported
        index_start = None
        index_end = None
        index_header_start = None
        for line_idx, line in enumerate(lib_lines):
            if index_start is None:
                if line.startswith("#"):
                    if line.strip() == "#" and index_header_start is None:
                        index_header_start = line_idx  # header start
                elif line.startswith("DEF "):
                    device = line.split()[1]
                    index_start = line_idx
                else:
                    index_header_start = None
            elif index_end is None:
                if line.startswith("F2"):
                    footprint = line.split()[1]
                    footprint = footprint.strip('"')
                    self.footprint_name = self.cleanName(footprint)
                    lib_lines[line_idx] = line.replace(
                        footprint, remote_type.name + ":" + self.footprint_name, 1
                    )
                elif line.startswith("ENDDEF"):
                    index_end = line_idx + 1
                elif line.startswith("F1 "):
                    lib_lines[line_idx] = line.replace(device, device, 1)
            elif line.startswith("DEF "):
                raise Warning("Multiple devices in " + lib_path.name)
        if index_end is None:
            raise Warning(device + " not found in " + lib_path.name)

        lib_file_read = self.DEST_PATH / (remote_type.name + ".lib")
        lib_file_write = self.DEST_PATH / (remote_type.name + ".lib~")
        overwrite_existing = overwrote_existing = overwritten = False

        check_file(lib_file_read)
        check_file(lib_file_write)

        with lib_file_read.open("rt", encoding="utf-8") as readfile:
            with lib_file_write.open("wt", encoding="utf-8") as writefile:
                if stat(lib_file_read).st_size == 0:
                    # todo Handle appending to empty file
                    with lib_file_read.open("wt", encoding="utf-8") as template_file:
                        template = [
                            "EESchema-LIBRARY Version 2.4",
                            "#encoding utf-8",
                            "# End Library",
                        ]
                        template_file.writelines(line + "\n" for line in template)
                        template_file.close()

                # For each line in the existing lib file (not the file being read from the zip. The lib file you will
                # add it to.)
                for line in readfile:
                    # Is this trying to match ENDDRAW, ENDDEF, End Library or any of the above?
                    if re.match("# *end ", line, re.IGNORECASE):
                        # If you already overwrote the new info don't add it to the end
                        if not overwrote_existing:
                            writefile.write(
                                "\n".join(
                                    lib_lines[
                                        (
                                            index_start
                                            if index_header_start is None
                                            else index_header_start
                                        ) : index_end
                                    ]
                                )
                                + "\n"
                            )
                        writefile.write(line)
                        break
                    # Catch start of new component definition
                    elif line.startswith("DEF "):
                        component_name = line.split()[1]
                        # Catch if the currently read component matches the name of the component you are planning to
                        # write
                        if component_name.startswith(device):
                            # Ask if you want to overwrite existing component

                            if overwrite_if_exists:
                                overwrite_existing = True
                                overwritten = True
                                self.print("Overwrite existing lib")
                            else:
                                self.print("Import of lib skipped")
                                self.lib_skipped = True
                                return device, lib_file_read, lib_file_write
                            writefile.write(
                                "\n".join(lib_lines[index_start:index_end]) + "\n"
                            )
                            overwrote_existing = True
                        else:
                            writefile.write(line)
                    elif overwrite_existing:
                        if line.startswith("ENDDEF"):
                            overwrite_existing = False
                    else:
                        writefile.write(line)
        if not overwritten:
            self.print("Import lib")
        return device, lib_file_read, lib_file_write

    def import_lib_new(
        self,
        remote_type: REMOTE_TYPES,
        lib_path: pathlib.Path,
        overwrite_if_exists=True,
    ) -> Tuple[str, Union[pathlib.Path, None], Union[pathlib.Path, None]]:
        symbol_name = None

        def extract_symbol_names(input_text):
            pattern = r'"(.*?)"'  # Searches for text in quotes
            # Searches for "(symbol" followed by text in quotes
            pattern = r'\(symbol\s+"(.*?)"'
            matches = re.findall(pattern, input_text)
            return matches

        symbol_name = None

        def replace_footprint_name(string, original_name, remote_type_name, new_name):
            escaped_original_name = re.escape(original_name)
            pattern = rf'\(property\s+"Footprint"\s+"{escaped_original_name}"'
            replacement = f'(property "Footprint" "{remote_type_name}:{new_name}"'
            modified_string = re.sub(pattern, replacement, string, flags=re.MULTILINE)
            return modified_string

        def extract_symbol_section_new(sexpression: str, symbol_name):
            pattern = re.compile(
                r'\(symbol "{}"(.*?)\)\n\)'.format(re.escape(symbol_name)), re.DOTALL
            )
            match = pattern.search(sexpression)
            if match:
                return f'(symbol "{symbol_name}"{match.group(1)})'
            return None

        RAW_text = lib_path.read_text(encoding="utf-8")  # new
        sexp_list = parse_sexp(RAW_text)  # new

        symbol_name = search_recursive(sexp_list, "symbol")  # new
        symbol_properties = extract_properties(sexp_list)  # new

        symbol_section = extract_symbol_section_new(RAW_text, symbol_name)

        Footprint_name_raw = symbol_properties["Footprint"]  # new
        self.footprint_name = self.cleanName(Footprint_name_raw)

        symbol_section = replace_footprint_name(
            symbol_section, Footprint_name_raw, remote_type.name, self.footprint_name
        )

        lib_file_read = self.DEST_PATH / (remote_type.name + ".kicad_sym")
        lib_file_read_old = self.DEST_PATH / (remote_type.name + "_kicad_sym.kicad_sym")
        lib_file_write = self.DEST_PATH / (remote_type.name + ".kicad_sym~")
        if isfile(lib_file_read_old) and not isfile(lib_file_read):
            lib_file_read = lib_file_read_old

        if not lib_file_read.exists():  # library does not yet exist
            with lib_file_write.open("wt", encoding="utf-8") as writefile:
                text = RAW_text.strip().split("\n")
                writefile.write(text[0] + "\n")
                writefile.write(symbol_section + "\n")
                writefile.write(text[-1])

            check_file(lib_file_read)
            self.print("Import kicad_sym")
            return symbol_name, lib_file_read, lib_file_write

        check_file(lib_file_read)

        lib_file_txt = lib_file_read.read_text(encoding="utf-8")
        existing_libs = extract_symbol_names(lib_file_txt)

        if symbol_name in existing_libs:
            if overwrite_if_exists:
                self.print("Overwrite existing kicad_sym is not implemented")  # TODO
            else:
                self.print("Import of kicad_sym skipped")

            return symbol_name, lib_file_read, lib_file_write

        closing_bracket = lib_file_txt.rfind(")")

        with lib_file_write.open("wt", encoding="utf-8") as writefile:
            writefile.write(lib_file_txt[:closing_bracket])
            writefile.write(symbol_section + "\n")
            writefile.write(lib_file_txt[closing_bracket:])

        self.print("Import kicad_sym")

        return symbol_name, lib_file_read, lib_file_write

    def import_all(
        self, zip_file: pathlib.Path, overwrite_if_exists=True, import_old_format=True
    ):
        """zip is a pathlib.Path to import the symbol from"""
        if not zipfile.is_zipfile(zip_file):
            return None

        self.print(f"Import: {zip_file}")

        with zipfile.ZipFile(zip_file) as zf:
            (
                dcm_path,
                lib_path,
                footprint_path,
                model_path,
                remote_type,
            ) = self.get_remote_info(zf)

            self.print("Identify " + remote_type.name)

            CompatibilityMode = False
            if lib_path and not self.lib_path_new:
                CompatibilityMode = True

                temp_path = self.DEST_PATH / "temp.lib"
                temp_path_new = self.DEST_PATH / "temp.kicad_sym"

                if temp_path.exists():
                    remove(temp_path)
                if temp_path_new.exists():
                    remove(temp_path_new)

                with temp_path.open("wt", encoding="utf-8") as writefile:
                    text = lib_path.read_text(encoding="utf-8")
                    writefile.write(text)

                if temp_path.exists() and cli.exists():
                    cli.upgrade_sym_lib(temp_path, temp_path_new)
                    self.print("compatibility mode: convert from .lib to .kicad_sym")

                if temp_path_new.exists() and temp_path_new.is_file():
                    self.lib_path_new = temp_path_new
                else:
                    self.print("error during conversion")

            if self.lib_path_new:
                device, lib_file_new_read, lib_file_new_write = self.import_lib_new(
                    remote_type, self.lib_path_new, overwrite_if_exists
                )

                file_ending = ""
                if "_kicad_sym" in lib_file_new_read.name:
                    file_ending = "_kicad_sym"

                dcm_file_new_read, dcm_file_new_write = self.import_dcm(
                    device,
                    remote_type,
                    dcm_path,
                    overwrite_if_exists,
                    file_ending=file_ending,
                )
                if not import_old_format:
                    lib_path = None

            if CompatibilityMode:
                if temp_path.exists():
                    remove(temp_path)
                if temp_path_new.exists():
                    remove(temp_path_new)

            if lib_path:
                device, lib_file_read, lib_file_write = self.import_lib(
                    remote_type, lib_path, overwrite_if_exists
                )

                dcm_file_read, dcm_file_write = self.import_dcm(
                    device, remote_type, dcm_path, overwrite_if_exists
                )

            found_model = self.import_model(
                model_path, remote_type, overwrite_if_exists
            )

            footprint_file_read, footprint_file_write = self.import_footprint(
                remote_type, footprint_path, found_model, overwrite_if_exists
            )

            # replace read files with write files only after all operations succeeded
            if self.lib_path_new:
                if lib_file_new_write.exists():
                    lib_file_new_write.replace(lib_file_new_read)

                if dcm_file_new_write.exists() and not self.dcm_skipped:
                    dcm_file_new_write.replace(dcm_file_new_read)
                elif dcm_file_new_write.exists():
                    remove(dcm_file_new_write)

            if lib_path:
                if dcm_file_write.exists() and not self.dcm_skipped:
                    dcm_file_write.replace(dcm_file_read)
                elif dcm_file_write.exists():
                    remove(dcm_file_write)

                if lib_file_write.exists() and not self.lib_skipped:
                    lib_file_write.replace(lib_file_read)
                elif lib_file_write.exists():
                    remove(lib_file_write)

            if (
                footprint_file_read
                and (self.footprint_name != footprint_file_read.stem)
                and not self.footprint_skipped
            ):
                self.print(
                    'Warning renaming footprint file "'
                    + footprint_file_read.stem
                    + '" to "'
                    + self.footprint_name
                    + '"'
                )

                if footprint_file_read.exists():
                    remove(footprint_file_read)
                footprint_file_read = footprint_file_read.parent / (
                    self.footprint_name + footprint_file_read.suffix
                )

            if (
                footprint_file_write
                and footprint_file_write.exists()
                and not self.footprint_skipped
            ):
                footprint_file_write.replace(footprint_file_read)
            elif footprint_file_write and footprint_file_write.exists():
                remove(footprint_file_write)

        return ("OK",)


def main(
    lib_file, lib_folder, overwrite=False, KICAD_3RD_PARTY_LINK="${KICAD_3RD_PARTY}"
):
    lib_folder = pathlib.Path(lib_folder)
    lib_file = pathlib.Path(lib_file)

    print("overwrite", overwrite)

    if not lib_folder.is_dir():
        print(f"Error destination folder {lib_folder} does not exist!")
        return 0

    if not lib_file.is_file():
        print(f"Error file {lib_folder} to be imported was not found!")
        return 0

    impart = import_lib()
    impart.KICAD_3RD_PARTY_LINK = KICAD_3RD_PARTY_LINK
    impart.set_DEST_PATH(lib_folder)
    try:
        (res,) = impart.import_all(lib_file, overwrite_if_exists=overwrite)
        print(res)
    except AssertionError as e:
        print(e)
    except Exception as e:
        print(e)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.ERROR)

    # Example: python plugins/KiCadImport.py --download-folder Demo/libs --lib-folder import_test

    parser = argparse.ArgumentParser(
        description="Import KiCad libraries from a file or folder."
    )

    # Create mutually exclusive arguments for file or folder
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--download-folder",
        help="Path to the folder with the zip files to be imported.",
    )
    group.add_argument("--download-file", help="Path to the zip file to import.")

    group.add_argument("--easyeda", help="Import easyeda part. example: C2040")

    parser.add_argument(
        "--lib-folder",
        required=True,
        help="Destination folder for the imported KiCad files.",
    )

    parser.add_argument(
        "--overwrite-if-exists",
        action="store_true",
        help="Overwrite existing files if they already exist",
    )

    parser.add_argument(
        "--path-variable",
        help="Example: if only project-specific '${KIPRJMOD}' standard is '${KICAD_3RD_PARTY}'",
    )

    args = parser.parse_args()

    lib_folder = pathlib.Path(args.lib_folder)

    if args.path_variable:
        path_variable = str(args.path_variable).strip()
    else:
        path_variable = "${KICAD_3RD_PARTY}"

    if args.download_file:
        main(
            lib_file=args.download_file,
            lib_folder=args.lib_folder,
            overwrite=args.overwrite_if_exists,
            KICAD_3RD_PARTY_LINK=path_variable,
        )
    elif args.download_folder:
        download_folder = pathlib.Path(args.download_folder)
        if not download_folder.is_dir():
            print(f"Error Source folder {download_folder} does not exist!")
        elif not lib_folder.is_dir():
            print(f"Error destination folder {lib_folder} does not exist!")
        else:
            for zip_file in download_folder.glob("*.zip"):
                if (
                    zip_file.is_file() and zip_file.stat().st_size >= 1024
                ):  # Check if it's a file and at least 1 KB
                    main(
                        lib_file=zip_file,
                        lib_folder=args.lib_folder,
                        overwrite=args.overwrite_if_exists,
                        KICAD_3RD_PARTY_LINK=path_variable,
                    )
    elif args.easyeda:
        if not lib_folder.is_dir():
            print(f"Error destination folder {lib_folder} does not exist!")
        else:
            component_id = str(args.easyeda).strip
            print("Try to import EeasyEDA /  LCSC Part# : ", component_id)
            from impart_easyeda import easyeda2kicad_wrapper

            easyeda_import = easyeda2kicad_wrapper()

            easyeda_import.full_import(
                component_id="C2040",
                base_folder=lib_folder,
                overwrite=False,
                lib_var=path_variable,
            )
