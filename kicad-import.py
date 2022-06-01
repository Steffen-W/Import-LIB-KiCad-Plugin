#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles. Currently assembles just
# symbols and footptints. Tested with KiCad 5.1.12 for Ubuntu.
import pathlib
from enum import Enum
from pathlib import Path
from zipfile import Path

from typing import Tuple, Union, Any

from config import SRC_PATH, REMOTE_LIB_PATH, REMOTE_FOOTPRINTS_PATH, REMOTE_3DMODEL_PATH  # *CONFIGURE ME*
import argparse
import re
import readline
import zipfile
from os import stat


def xinput(prompt):
    # extended input to allow Emacs input backspace
    reply = input(prompt)
    index = reply.find('~') + 1
    return reply[index:]


class Select:
    """input() from select completions """

    def __init__(self, select):
        self._select = select
        readline.set_completer(self.complete)
        readline.set_pre_input_hook(None)

    def __call__(self, prompt):
        reply = xinput(prompt)
        readline.set_completer(lambda: None)
        return reply.strip()

    def complete(self, text, state):
        if state == 0:
            if text:
                self._pre = [s for s in self._select
                             if s and s.startswith(text)]
            else:
                self._pre = self._select[:]

        try:
            echo = self._pre[state]
        except IndexError:
            echo = None

        return echo


class REMOTE_TYPES(Enum):
    OCTOPART = 0
    SAMACSYS = 1
    ULTRA_LIBRARIAN = 2
    SNAPEDA = 3


class Catch(Exception):
    def __init__(self, value):
        self.catch = value
        super().__init__(self)


def unzip(root, suffix):
    """return zipfile.Path starting with root ending with suffix"""

    def zipper(parent):
        if parent.name.endswith(suffix):
            raise Catch(parent)
        elif parent.is_dir():
            for child in parent.iterdir():
                zipper(child)

    try:
        zipper(root)
    except Catch as error:
        return error.catch

    return None


def get_remote_info(root_path) -> Tuple[Path, Path, Path, Path, REMOTE_TYPES]:
    """
    :param root_path:
    :type root_path: Path
    :return: dcm_path, lib_path, footprint_path, model_path, remote_type
    """
    dcm_path = root_path / 'device_name.dcm'
    lib_path = root_path / 'device_name.lib'
    footprint_path = root_path / 'device_name.pretty'
    model_path = root_path / 'device_name.step'
    # todo fill in model path for OCTOPART
    if dcm_path.exists() and lib_path.exists() and footprint_path.exists():
        remote_type = REMOTE_TYPES.OCTOPART
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    directory = unzip(root_path, 'KiCad')
    if directory:
        dcm_path = unzip(directory, '.dcm')
        lib_path = unzip(directory, '.lib')
        footprint_path = directory
        # todo fill in model path for SAMACSYS
        assert dcm_path and lib_path, 'Not in samacsys format'
        remote_type = REMOTE_TYPES.SAMACSYS
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    directory = root_path / 'KiCAD'
    if directory.exists():
        dcm_path = unzip(directory, '.dcm')
        lib_path = unzip(directory, '.lib')
        footprint_path = unzip(directory, '.pretty')
        model_path = unzip(root_path, '.step')
        assert lib_path and footprint_path, 'Not in ultralibrarian format'
        remote_type = REMOTE_TYPES.ULTRA_LIBRARIAN
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    lib_path = unzip(root_path, '.lib')
    if lib_path:
        dcm_path = unzip(root_path, '.dcm')
        footprint_path = root_path
        model_path = root_path
        remote_type = REMOTE_TYPES.SNAPEDA
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    assert False, 'Unknown library zipfile'


def check_file(path: pathlib.Path):
    """
    Check if file exists, if not create parent directories and touch file
    :param path:
    """
    if not path.exists():
        if not path.parent.is_dir():
            path.parent.mkdir(parents=True)
        path.touch(mode=0o666)


def dcm_import(device: str, device_name: str, remote_type: REMOTE_TYPES, dcm_path: pathlib.Path):
    """
    # .dcm file parsing
    # Note this reads in the existing dcm file for the particular remote repo, and tries to catch any duplicates
    # before overwriting or creating duplicates. It reads the existing dcm file line by line and simply copy+paste
    # each line if nothing will be overwritten or duplicated. If something could be overwritten or duplicated, the
    # terminal will prompt whether to overwrite or to keep the existing content and ignore the new file contents.
    """


    # Array of values defining all attributes of .dcm file
    dcm_attributes = dcm_path.read_text().splitlines() if dcm_path else [
        '#', '# ' + device, '#', '$CMP ' + device_name, 'D', 'F', '$ENDCMP']

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
                if not component_name.startswith(device_name):
                    return 'Unexpected device in', dcm_path.name
                dcm_attributes[attribute_idx] = attribute.replace(component_name, device_name, 1)
                index_start = attribute_idx
            else:
                index_header_start = None
        elif index_end is None:
            if attribute.startswith('$CMP '):
                return 'Multiple devices in', dcm_path.name
            elif attribute.startswith('$ENDCMP'):
                index_end = attribute_idx + 1
            elif attribute.startswith('D'):
                description = attribute[2:].strip()
                description = input('Device description [{0}]: '.format(description)) or description
                if description:
                    dcm_attributes[attribute_idx] = 'D ' + description
            elif attribute.startswith('F'):
                datasheet = attribute[2:].strip()
                if datasheet:
                    dcm_attributes[attribute_idx] = 'F ' + datasheet
    if index_end is None:
        return device_name, 'not found in', dcm_path.name

    dcm_file_read = REMOTE_LIB_PATH / (remote_type.name + '.dcm')
    dcm_file_write = REMOTE_LIB_PATH / (remote_type.name + '.dcm~')
    overwrite_existing = overwrote_existing = False

    check_file(dcm_file_read)
    check_file(dcm_file_write)

    with dcm_file_read.open('rt') as readfile:
        with dcm_file_write.open('wt') as writefile:

            if stat(dcm_file_read).st_size == 0:
                # todo Handle appending to empty file
                with dcm_file_read.open('wt') as template_file:
                    template = ["EESchema-DOCLIB  Version 2.0", "#End Doc Library"]
                    template_file.writelines(line + '\n' for line in template)
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
                    if component_name.startswith(device_name):
                        overwrite_existing = input(device_name + ' definition already exists in ' + str(
                            dcm_file_read) + ', replace it? [Yes]: ') or "Yes"
                        if overwrite_existing not in ('y', 'yes', 'Yes', 'Y', 'YES'):
                            return None
                        writefile.write('\n'.join(dcm_attributes[index_start:index_end]) + '\n')
                        overwrote_existing = True
                    else:
                        writefile.write(line)
                elif overwrite_existing:
                    if line.startswith('$ENDCMP'):
                        overwrite_existing = False
                else:
                    writefile.write(line)

    dcm_file_write.replace(dcm_file_read)


def model_import(model_path: pathlib.Path, zf: zipfile.ZipFile) -> Union[pathlib.Path, None]:
    # --------------------------------------------------------------------------------------------------------
    # 3D Model file extraction
    # --------------------------------------------------------------------------------------------------------
    if not REMOTE_3DMODEL_PATH.is_dir():
        REMOTE_3DMODEL_PATH.mkdir(parents=True)

    for model_dir_item in model_path.iterdir():
        if model_dir_item.name.endswith('.step'):
            if (REMOTE_3DMODEL_PATH / model_dir_item.name).exists():
                overwrite_existing = input("Model already exists at " + str(
                    REMOTE_3DMODEL_PATH / model_dir_item.name) + ". Overwrite existing model? [Yes]: ") or "Yes"
                if overwrite_existing not in ('y', 'yes', 'Yes', 'Y', 'YES'):
                    return None

            zf.extract(model_dir_item.name, REMOTE_3DMODEL_PATH)
            return model_dir_item


def import_all(zip_file: pathlib.Path):
    """zip is a pathlib.Path to import the symbol from"""
    if not zipfile.is_zipfile(zip_file):
        return None

    device = zip_file.name[:-4]
    # Request user input, but default to device if nothing entered
    device_name = input('Generic device name [{0}]: '.format(device)) or device
    if device_name == '':
        return None

    with zipfile.ZipFile(zip_file) as zf:
        root: Path = zipfile.Path(zf)

        dcm_path, lib_path, footprint_path, model_path, remote_type = get_remote_info(root)

        dcm_import(device, device_name, remote_type, dcm_path)

        found_model = model_import(model_path, zf)
        # --------------------------------------------------------------------------------------------------------
        # Footprint file parsing
        # todo it doesn't look like this handles duplicates like the other parsing sections
        # --------------------------------------------------------------------------------------------------------
        for footprint_path_item in footprint_path.iterdir():
            if footprint_path_item.name.endswith('.kicad_mod') or footprint_path_item.name.endswith('.mod'):
                footprint = footprint_path_item.read_text()

                footprint_write_path = (REMOTE_FOOTPRINTS_PATH / (remote_type.name + '.pretty'))
                footprint_file_read = footprint_write_path / footprint_path_item.name
                footprint_file_write = footprint_write_path / (footprint_path_item.name + "~")

                if found_model:
                    footprint.splitlines()
                    model = ["  (model \"" + "${REMOTE_3DMODEL_DIR}/" + found_model.name + "\"",
                             "    (offset (xyz 0 0 0))", "    (scale (xyz 1 1 1))", "    (rotate (xyz 0 0 0))", "  )"]

                    overwrite_existing = overwrote_existing = False

                    if footprint_file_read.exists():
                        overwrite_existing = input(
                            "Footprint already exists at " + str(footprint_file_read) + ". Overwrite existing footprint? [Yes]: ") or "Yes"
                        if overwrite_existing not in ('y', 'yes', 'Yes', 'Y', 'YES'):
                            return 'OK:', footprint_path_item.name, 'already in', footprint_file_read.name

                    check_file(footprint_file_read)

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
                                    writefile.writelines(model_line + '\n' for model_line in model)
                                    writefile.write(line)
                                    break
                                else:
                                    writefile.write(line)

                else:
                    with footprint_file_read.open('wt') as wr:
                        wr.write(footprint)

        # --------------------------------------------------------------------------------------------------------
        # .lib file parsing
        # Note this reads in the existing lib file for the particular remote repo, and tries to catch any duplicates
        # before overwriting or creating duplicates. It reads the existing dcm file line by line and simply copy+paste
        # each line if nothing will be overwritten or duplicated. If something could be overwritten or duplicated, the
        # terminal will prompt whether to overwrite or to keep the existing content and ignore the new file contents.
        # --------------------------------------------------------------------------------------------------------
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
                    component_name = line.split()[1]
                    if not component_name.startswith(device_name):
                        return 'Unexpected device in', lib_path.name
                    lib_lines[line_idx] = line.replace(component_name, device_name, 1)
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
                    lib_lines[line_idx] = line.replace(device, device_name, 1)
            elif line.startswith('DEF '):
                return 'Multiple devices in', lib_path.name
        if index_end is None:
            return device, 'not found in', lib_path.name

        lib_file_read = REMOTE_LIB_PATH / (remote_type.name + '.lib')
        lib_file_write = REMOTE_LIB_PATH / (remote_type.name + '.lib~')
        overwrite_existing = overwrote_existing = False

        check_file(lib_file_read)
        check_file(lib_file_write)

        with lib_file_read.open('rt') as readfile:
            with lib_file_write.open('wt') as writefile:

                if stat(lib_file_read).st_size == 0:
                    # todo Handle appending to empty file
                    with lib_file_read.open('wt') as template_file:
                        template = ["EESchema-LIBRARY Version 2.4", "#encoding utf-8", "# End Library"]
                        template_file.writelines(line + '\n' for line in template)
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
                        if component_name.startswith(device_name):
                            # Ask if you want to overwrite existing component
                            yes = input(device_name + ' lib already in ' + str(lib_file_read) + ', replace it? [Yes]: ') or "Yes"
                            overwrite_existing = yes and 'yes'.startswith(yes.lower())
                            if not overwrite_existing:
                                return 'OK:', device_name, 'already in', lib_file_read
                            writefile.write('\n'.join(lib_lines[index_start:index_end]) + '\n')
                            overwrote_existing = True
                        else:
                            writefile.write(line)
                    elif overwrite_existing:
                        if line.startswith('ENDDEF'):
                            overwrite_existing = False
                    else:
                        writefile.write(line)

        footprint_file_write.replace(footprint_file_read)
        lib_file_write.replace(lib_file_read)


    return 'OK:',


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        epilog='Note, empty input: invites clipboard content, if available.')
    parser.add_argument('--zap', action='store_true',
                        help='delete source zipfile after assembly')
    arg = parser.parse_args()

    readline.set_completer_delims('\t')
    readline.parse_and_bind('tab: complete')
    readline.set_auto_history(False)

    try:
        zips = [zip_file.name for zip_file in SRC_PATH.glob('*.zip')]
        chosen_zip: pathlib.Path = SRC_PATH / Select(zips)('Library zip file: ')
        response = import_all(chosen_zip)
        if response:
            print(*response)
            if arg.zap and response[0] == 'OK:':
                chosen_zip.unlink()
    except EOFError:
        print('EOF')
    except Exception as e:
        print(*e.args)
    exit(0)
