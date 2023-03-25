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
        DEST_PATH = pathlib.Path.home() / 'KiCad'

    def set_DEST_PATH(self, DEST_PATH_=pathlib.Path.home() / 'KiCad'):
        self.DEST_PATH = pathlib.Path(DEST_PATH_)

    def get_remote_info(self, zf: zipfile.ZipFile) -> Tuple[Path, Path, Path, Path, REMOTE_TYPES]:
        """
        :param root_path:
        :type root_path: Path
        :return: dcm_path, lib_path, footprint_path, model_path, remote_type
        """
        root_path = zipfile.Path(zf)
        self.dcm_path = root_path / 'device.dcm'
        self.lib_path = root_path / 'device.lib'
        self.footprint_path = root_path / 'device.pretty'
        self.model_path = root_path / 'device.step'
        # todo fill in model path for OCTOPART
        if self.dcm_path.exists() and self.lib_path.exists() and self.footprint_path.exists():
            remote_type = REMOTE_TYPES.Octopart
            return self.dcm_path, self.lib_path, self.footprint_path, self.model_path, remote_type

        directory = unzip(root_path, 'KiCad')
        if directory:
            self.dcm_path = unzip(directory, '.dcm')
            self.lib_path = unzip(directory, '.lib')
            self.footprint_path = directory
            model_path_tmp = unzip(root_path, '3D')
            self.model_path = unzip(model_path_tmp, '.step')
            if not self.model_path:
                self.model_path = unzip(model_path_tmp, '.stp')
            assert self.dcm_path and self.lib_path, 'Not in samacsys format'
            remote_type = REMOTE_TYPES.Samacsys
            return self.dcm_path, self.lib_path, self.footprint_path, self.model_path, remote_type

        directory = root_path / 'KiCAD'
        if directory.exists():
            self.dcm_path = unzip(directory, '.dcm')
            self.lib_path = unzip(directory, '.lib')
            self.footprint_path = unzip(directory, '.pretty')
            self.model_path = unzip(root_path, '.step')
            if not self.model_path:
                self.model_path = unzip(root_path, '.stp')
            assert self.lib_path and self.footprint_path, 'Not in ultralibrarian format'
            remote_type = REMOTE_TYPES.UltraLibrarian
            return self.dcm_path, self.lib_path, self.footprint_path, self.model_path, remote_type

        self.lib_path = unzip(root_path, '.lib')
        if self.lib_path:
            self.dcm_path = unzip(root_path, '.dcm')
            self.footprint_path = root_path
            self.model_path = unzip(root_path, '.step')
            remote_type = REMOTE_TYPES.Snapeda
            return self.dcm_path, self.lib_path, self.footprint_path, self.model_path, remote_type
        elif (unzip(root_path, '.kicad_sym').exists()):
            assert False, 'Not in Snapeda format (only KiCad v4 format is supported)'

        assert False, 'Unknown library zipfile'

    def import_dcm(self, device: str, remote_type: REMOTE_TYPES, dcm_path: pathlib.Path, overwrite_if_exists=True) -> \
            Tuple[Union[pathlib.Path, None], Union[pathlib.Path, None]]:
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
        dcm_attributes = dcm_path.read_text().splitlines() if dcm_path else [
            '#', '# ' + device, '#', '$CMP ' + device, 'D', 'F', '$ENDCMP']

        # Find which lines contain the component information (ignore the rest).
        index_start = None
        index_end = None
        index_header_start = None

        for attribute_idx, attribute in enumerate(dcm_attributes):
            if index_start is None:
                if attribute.startswith('#'):
                    if attribute.strip() == '#' and index_header_start is None:
                        index_header_start = attribute_idx  # header start
                elif attribute.startswith('$CMP '):
                    component_name = attribute[5:].strip()
                    if not component_name.startswith(device):
                        raise Warning('Unexpected device in ' + dcm_path.name)
                    dcm_attributes[attribute_idx] = attribute.replace(
                        component_name, device, 1)
                    index_start = attribute_idx
                else:
                    index_header_start = None
            elif index_end is None:
                if attribute.startswith('$CMP '):
                    raise Warning('Multiple devices in ' + dcm_path.name)
                elif attribute.startswith('$ENDCMP'):
                    index_end = attribute_idx + 1
                elif attribute.startswith('D'):
                    description = attribute[2:].strip()
                    if description:
                        dcm_attributes[attribute_idx] = 'D ' + description
                elif attribute.startswith('F'):
                    datasheet = attribute[2:].strip()
                    if datasheet:
                        dcm_attributes[attribute_idx] = 'F ' + datasheet
        if index_end is None:
            raise Warning(device + 'not found in ' + dcm_path.name)

        dcm_file_read = self.DEST_PATH / (remote_type.name + '.dcm')
        dcm_file_write = self.DEST_PATH / (remote_type.name + '.dcm~')
        overwrite_existing = overwrote_existing = False

        check_file(dcm_file_read)
        check_file(dcm_file_write)

        with dcm_file_read.open('rt') as readfile:
            with dcm_file_write.open('wt') as writefile:

                if stat(dcm_file_read).st_size == 0:
                    # todo Handle appending to empty file
                    with dcm_file_read.open('wt') as template_file:
                        template = ["EESchema-DOCLIB  Version 2.0",
                                    "#End Doc Library"]
                        template_file.writelines(
                            line + '\n' for line in template)
                        template_file.close()

                for line in readfile:
                    if re.match('# *end ', line, re.IGNORECASE):
                        if not overwrote_existing:
                            writefile.write('\n'.join(
                                dcm_attributes[index_start if index_header_start is None else index_header_start:
                                            index_end]) + '\n')
                        writefile.write(line)
                        break
                    elif line.startswith('$CMP '):
                        component_name = line[5:].strip()
                        if component_name.startswith(device):
                            if (overwrite_if_exists):
                                overwrite_existing = True
                                self.print("Overwrite existing dcm")
                            else:
                                overwrite_existing = False
                                self.print("Import of dcm skipped")
                                self.dcm_skipped = True
                                return dcm_file_read, dcm_file_write
                            writefile.write(
                                '\n'.join(dcm_attributes[index_start:index_end]) + '\n')
                            overwrote_existing = True
                        else:
                            writefile.write(line)
                    elif overwrite_existing:
                        if line.startswith('$ENDCMP'):
                            overwrite_existing = False
                    else:
                        writefile.write(line)

        return dcm_file_read, dcm_file_write

    def import_model(self, model_path: pathlib.Path, remote_type: REMOTE_TYPES, overwrite_if_exists) -> Union[pathlib.Path, None]:
        # --------------------------------------------------------------------------------------------------------
        # 3D Model file extraction
        # --------------------------------------------------------------------------------------------------------

        if not model_path:
            return False

        write_file = self.DEST_PATH / \
            (remote_type.name + '.3dshapes') / model_path.name

        self.model_skipped = False

        if write_file.exists():
            if (overwrite_if_exists):
                overwrite_existing = True
                self.print("Overwrite existing 3d model")
            else:
                self.print("Import of 3d model skipped")
                self.model_skipped = True
                return model_path

        if model_path.is_file():
            check_file(write_file)
            write_file.write_bytes(model_path.read_bytes())
            modified_objects.append(write_file, Modification.EXTRACTED_FILE)

        return model_path

    def import_footprint(self, remote_type: REMOTE_TYPES, footprint_path: pathlib.Path, found_model: pathlib.Path, overwrite_if_exists=True) -> \
            Tuple[Union[pathlib.Path, None], Union[pathlib.Path, None]]:
        """
        # Footprint file parsing
        :returns: footprint_file_read, footprint_file_write
        """

        footprint_file_read = None
        footprint_file_write = None
        self.footprint_skipped = False

        footprint_path_item_tmp = None
        for footprint_path_item in footprint_path.iterdir():  # try to use only newer file
            if footprint_path_item.name.endswith('.kicad_mod'):
                footprint_path_item_tmp = footprint_path_item
                break
            elif footprint_path_item.name.endswith('.mod'):
                footprint_path_item_tmp = footprint_path_item

        footprint_path_item = footprint_path_item_tmp
        if footprint_path_item.name.endswith('mod'):
            footprint = footprint_path_item.read_text()

            footprint_write_path = (
                self.DEST_PATH / (remote_type.name + '.pretty'))
            footprint_file_read = footprint_write_path / footprint_path_item.name
            footprint_file_write = footprint_write_path / \
                (footprint_path_item.name + "~")

            check_file(footprint_file_read)
            if found_model:
                footprint.splitlines()
                model = ["  (model \"" + "${KICAD_3RD_PARTY}/" + remote_type.name + '.3dshapes/' + found_model.name + "\"",
                         "    (offset (xyz 0 0 0))", "    (scale (xyz 1 1 1))", "    (rotate (xyz 0 0 0))", "  )"]

                overwrite_existing = overwrote_existing = False

                if footprint_file_read.exists():
                    if (overwrite_if_exists):
                        overwrite_existing = True
                        self.print("Overwrite existing footprint")
                    else:
                        self.print("Import of footprint skipped")
                        self.footprint_skipped = True
                        return footprint_file_read, footprint_file_write

                with footprint_file_read.open('wt') as wr:
                    wr.write(footprint)
                    overwrote_existing = True

                check_file(footprint_file_write)

                with footprint_file_read.open('rt') as readfile:
                    with footprint_file_write.open('wt') as writefile:

                        if stat(footprint_file_read).st_size == 0:
                            # todo Handle appending to empty file?
                            pass

                        lines = readfile.readlines()

                        for line_idx, line in enumerate(lines):
                            if line_idx == len(lines) - 1:
                                writefile.writelines(
                                    model_line + '\n' for model_line in model)
                                writefile.write(line)
                                break
                            else:
                                writefile.write(line)

            else:
                with footprint_file_read.open('wt') as wr:
                    wr.write(footprint)

        return footprint_file_read, footprint_file_write

    def import_lib(self, remote_type: REMOTE_TYPES, lib_path: pathlib.Path, overwrite_if_exists=True) -> \
            Tuple[str, Union[pathlib.Path, None], Union[pathlib.Path, None]]:
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
        lib_lines = lib_path.read_text().splitlines()

        # Find which lines contain the component information in file to be imported
        index_start = None
        index_end = None
        index_header_start = None
        for line_idx, line in enumerate(lib_lines):
            if index_start is None:
                if line.startswith('#'):
                    if line.strip() == '#' and index_header_start is None:
                        index_header_start = line_idx  # header start
                elif line.startswith('DEF '):
                    device = line.split()[1]
                    index_start = line_idx
                else:
                    index_header_start = None
            elif index_end is None:
                if line.startswith("F2"):
                    footprint = line.split()[1]
                    footprint = footprint.strip("\"")
                    lib_lines[line_idx] = line.replace(
                        footprint, remote_type.name + ":" + footprint, 1)
                elif line.startswith('ENDDEF'):
                    index_end = line_idx + 1
                elif line.startswith('F1 '):
                    lib_lines[line_idx] = line.replace(device, device, 1)
            elif line.startswith('DEF '):
                raise Warning('Multiple devices in ' + lib_path.name)
        if index_end is None:
            raise Warning(device + ' not found in ' + lib_path.name)

        lib_file_read = self.DEST_PATH / (remote_type.name + '.lib')
        lib_file_write = self.DEST_PATH / (remote_type.name + '.lib~')
        overwrite_existing = overwrote_existing = False

        check_file(lib_file_read)
        check_file(lib_file_write)

        with lib_file_read.open('rt') as readfile:
            with lib_file_write.open('wt') as writefile:

                if stat(lib_file_read).st_size == 0:
                    # todo Handle appending to empty file
                    with lib_file_read.open('wt') as template_file:
                        template = ["EESchema-LIBRARY Version 2.4",
                                    "#encoding utf-8", "# End Library"]
                        template_file.writelines(
                            line + '\n' for line in template)
                        template_file.close()

                # For each line in the existing lib file (not the file being read from the zip. The lib file you will
                # add it to.)
                for line in readfile:
                    # Is this trying to match ENDDRAW, ENDDEF, End Library or any of the above?
                    if re.match('# *end ', line, re.IGNORECASE):
                        # If you already overwrote the new info don't add it to the end
                        if not overwrote_existing:
                            writefile.write(
                                '\n'.join(lib_lines[index_start if index_header_start is None else index_header_start:
                                                    index_end]) + '\n')
                        writefile.write(line)
                        break
                    # Catch start of new component definition
                    elif line.startswith('DEF '):
                        component_name = line.split()[1]
                        # Catch if the currently read component matches the name of the component you are planning to
                        # write
                        if component_name.startswith(device):
                            # Ask if you want to overwrite existing component

                            if (overwrite_if_exists):
                                overwrite_existing = True
                                self.print("Overwrite existing lib")
                            else:
                                overwrite_existing = False
                                self.print("Import of lib skipped")
                                self.lib_skipped = True
                                return device, lib_file_read, lib_file_write
                            writefile.write(
                                '\n'.join(lib_lines[index_start:index_end]) + '\n')
                            overwrote_existing = True
                        else:
                            writefile.write(line)
                    elif overwrite_existing:
                        if line.startswith('ENDDEF'):
                            overwrite_existing = False
                    else:
                        writefile.write(line)

        return device, lib_file_read, lib_file_write

    def import_all(self, zip_file: pathlib.Path, overwrite_if_exists=True):
        """zip is a pathlib.Path to import the symbol from"""
        if not zipfile.is_zipfile(zip_file):
            return None
        self.print("Import: " + zip_file)

        with zipfile.ZipFile(zip_file) as zf:
            dcm_path, lib_path, footprint_path, model_path, remote_type = self.get_remote_info(
                zf)

            device, lib_file_read, lib_file_write = self.import_lib(
                remote_type, lib_path, overwrite_if_exists)

            dcm_file_read, dcm_file_write = self.import_dcm(
                device, remote_type, dcm_path, overwrite_if_exists)

            found_model = self.import_model(
                model_path, remote_type, overwrite_if_exists)

            footprint_file_read, footprint_file_write = self.import_footprint(
                remote_type, footprint_path, found_model, overwrite_if_exists)

            # replace read files with write files only after all operations succeeded
            if dcm_file_write.exists() and not self.dcm_skipped:
                dcm_file_write.replace(dcm_file_read)
            elif dcm_file_write.exists():
                remove(dcm_file_write)

            if lib_file_write.exists() and not self.lib_skipped:
                lib_file_write.replace(lib_file_read)
            elif lib_file_write.exists():
                remove(lib_file_write)

            if footprint_file_write.exists() and not self.footprint_skipped:
                footprint_file_write.replace(footprint_file_read)
            elif footprint_file_write.exists():
                remove(footprint_file_write)

        return 'OK',
