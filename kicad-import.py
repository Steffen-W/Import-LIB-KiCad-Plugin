#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles. Currently assembles just
# symbols and footptints. Tested with KiCad 5.1.12 for Ubuntu.
import pathlib
import traceback
from enum import Enum
from pathlib import Path
from zipfile import Path
from pprint import pprint

from typing import Tuple, Union, Any

from config import SRC_PATH, REMOTE_LIB_PATH, REMOTE_FOOTPRINTS_PATH, REMOTE_3DMODEL_PATH  # *CONFIGURE ME*
import argparse
import re
import readline
import zipfile
from os import stat


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
    Octopart = 0
    Samacsys = 1
    Ulatra_Librarian = 2
    Snapeda = 3


class Catch(Exception):
    def __init__(self, value):
        self.catch = value
        super().__init__(self)


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


def exception_handler(e: Exception):
    traceback.print_exception(type(e), e, e.__traceback__)

    print(e.args)
    print("So far the following have been modified: " + "\n")
    pprint(modified_objects.dict)

    decision = input("Attempt to undo these modifications? [No]") or "No"
    if decision in ('y', 'yes', 'Yes', 'Y', 'YES'):
        # todo handle any reversing file operations here
        pass



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


def get_remote_info(zf: zipfile.ZipFile) -> Tuple[Path, Path, Path, Path, REMOTE_TYPES]:
    """
    :param root_path:
    :type root_path: Path
    :return: dcm_path, lib_path, footprint_path, model_path, remote_type
    """
    root_path = zipfile.Path(zf)
    dcm_path = root_path / 'device.dcm'
    lib_path = root_path / 'device.lib'
    footprint_path = root_path / 'device.pretty'
    model_path = root_path / 'device.step'
    # todo fill in model path for OCTOPART
    if dcm_path.exists() and lib_path.exists() and footprint_path.exists():
        remote_type = REMOTE_TYPES.Octopart
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    directory = unzip(root_path, 'KiCad')
    if directory:
        dcm_path = unzip(directory, '.dcm')
        lib_path = unzip(directory, '.lib')
        footprint_path = directory
        # todo fill in model path for SAMACSYS
        assert dcm_path and lib_path, 'Not in samacsys format'
        remote_type = REMOTE_TYPES.Samacsys
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    directory = root_path / 'KiCAD'
    if directory.exists():
        dcm_path = unzip(directory, '.dcm')
        lib_path = unzip(directory, '.lib')
        footprint_path = unzip(directory, '.pretty')
        model_path = unzip(root_path, '.step')
        assert lib_path and footprint_path, 'Not in ultralibrarian format'
        remote_type = REMOTE_TYPES.Ulatra_Librarian
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    lib_path = unzip(root_path, '.lib')
    if lib_path:
        dcm_path = unzip(root_path, '.dcm')
        footprint_path = root_path
        model_path = unzip(root_path, '.step')
        remote_type = REMOTE_TYPES.Snapeda
        return dcm_path, lib_path, footprint_path, model_path, remote_type

    assert False, 'Unknown library zipfile'


def import_dcm(device: str, remote_type: REMOTE_TYPES, dcm_path: pathlib.Path) -> \
        Tuple[Union[pathlib.Path, None], Union[pathlib.Path, None]]:
    """
    # .dcm file parsing
    # Note this reads in the existing dcm file for the particular remote repo, and tries to catch any duplicates
    # before overwriting or creating duplicates. It reads the existing dcm file line by line and simply copy+paste
    # each line if nothing will be overwritten or duplicated. If something could be overwritten or duplicated, the
    # terminal will prompt whether to overwrite or to keep the existing content and ignore the new file contents.
    :returns: dcm_file_read, dcm_file_write
    """

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
                dcm_attributes[attribute_idx] = attribute.replace(component_name, device, 1)
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
                description = input('Device description [{0}]: '.format(description)) or description
                if description:
                    dcm_attributes[attribute_idx] = 'D ' + description
            elif attribute.startswith('F'):
                datasheet = attribute[2:].strip()
                if datasheet:
                    dcm_attributes[attribute_idx] = 'F ' + datasheet
    if index_end is None:
        raise Warning(device + 'not found in ' + dcm_path.name)

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
                    if component_name.startswith(device):
                        overwrite_existing = input(device + ' definition already exists in ' + str(
                            dcm_file_read) + ', replace it? [Yes]: ') or "Yes"
                        if overwrite_existing not in ('y', 'yes', 'Yes', 'Y', 'YES'):
                            print("Import of dcm skipped")
                            return dcm_file_read, dcm_file_write
                        writefile.write('\n'.join(dcm_attributes[index_start:index_end]) + '\n')
                        overwrote_existing = True
                    else:
                        writefile.write(line)
                elif overwrite_existing:
                    if line.startswith('$ENDCMP'):
                        overwrite_existing = False
                else:
                    writefile.write(line)

    return dcm_file_read, dcm_file_write


def import_model(model_path: pathlib.Path, remote_type: REMOTE_TYPES) -> Union[pathlib.Path, None]:
    # --------------------------------------------------------------------------------------------------------
    # 3D Model file extraction
    # --------------------------------------------------------------------------------------------------------
    write_file = REMOTE_3DMODEL_PATH / "3rd-party" / model_path.name

    if write_file.exists():
        overwrite_existing = input("Model already exists at " + str(
            REMOTE_3DMODEL_PATH / model_path.name) + ". Overwrite existing model? [Yes]: ") or "Yes"
        if overwrite_existing not in ('y', 'yes', 'Yes', 'Y', 'YES'):
            print("Import of model skipped")
            return None

    if model_path.is_file():
        check_file(write_file)
        write_file.write_bytes(model_path.read_bytes())
        modified_objects.append(REMOTE_3DMODEL_PATH / model_path.name, Modification.EXTRACTED_FILE)
        print("Import of model succeeded")

    return model_path


def import_footprint(remote_type: REMOTE_TYPES, footprint_path: pathlib.Path, found_model: pathlib.Path) -> \
        Tuple[Union[pathlib.Path, None], Union[pathlib.Path, None]]:
    """
    # Footprint file parsing
    :returns: footprint_file_read, footprint_file_write
    """

    footprint_file_read = None
    footprint_file_write = None

    for footprint_path_item in footprint_path.iterdir():
        if footprint_path_item.name.endswith('.kicad_mod') or footprint_path_item.name.endswith('.mod'):
            footprint = footprint_path_item.read_text()

            footprint_write_path = (REMOTE_FOOTPRINTS_PATH / (remote_type.name + '.pretty'))
            footprint_file_read = footprint_write_path / footprint_path_item.name
            footprint_file_write = footprint_write_path / (footprint_path_item.name + "~")

            if found_model:
                footprint.splitlines()
                model = ["  (model \"" + "${KICAD6_3RD_PARTY}/" + found_model.name + "\"",
                         "    (offset (xyz 0 0 0))", "    (scale (xyz 1 1 1))", "    (rotate (xyz 0 0 0))", "  )"]

                overwrite_existing = overwrote_existing = False

                if footprint_file_read.exists():
                    overwrite_existing = input(
                        "Footprint already exists at " + str(
                            footprint_file_read) + ". Overwrite existing footprint? [Yes]: ") or "Yes"
                    if overwrite_existing not in ('y', 'yes', 'Yes', 'Y', 'YES'):
                        print("Import of footprint skipped")
                        return footprint_file_read, footprint_file_write

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

    return footprint_file_read, footprint_file_write


def import_lib(device: str, remote_type: REMOTE_TYPES, lib_path: pathlib.Path) -> \
        Tuple[Union[pathlib.Path, None], Union[pathlib.Path, None]]:
    """
    .lib file parsing
    Note this reads in the existing lib file for the particular remote repo, and tries to catch any duplicates
    before overwriting or creating duplicates. It reads the existing dcm file line by line and simply copy+paste
    each line if nothing will be overwritten or duplicated. If something could be overwritten or duplicated, the
    terminal will prompt whether to overwrite or to keep the existing content and ignore the new file contents.
    :returns: lib_file_read, lib_file_write
    """

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
                if not component_name.startswith(device):
                    raise Warning('Unexpected device in ' + lib_path.name)
                lib_lines[line_idx] = line.replace(component_name, device, 1)
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
                    if component_name.startswith(device):
                        # Ask if you want to overwrite existing component
                        yes = input(
                            device + ' lib already in ' + str(lib_file_read) + ', replace it? [Yes]: ') or "Yes"
                        overwrite_existing = yes and 'yes'.startswith(yes.lower())
                        if not overwrite_existing:
                            print("Import of lib skipped")
                            return lib_file_read, lib_file_write
                        writefile.write('\n'.join(lib_lines[index_start:index_end]) + '\n')
                        overwrote_existing = True
                    else:
                        writefile.write(line)
                elif overwrite_existing:
                    if line.startswith('ENDDEF'):
                        overwrite_existing = False
                else:
                    writefile.write(line)

    return lib_file_read, lib_file_write


def import_all(zip_file: pathlib.Path):
    """zip is a pathlib.Path to import the symbol from"""
    if not zipfile.is_zipfile(zip_file):
        return None

    device = zip_file.name[:-4]

    with zipfile.ZipFile(zip_file) as zf:
        dcm_path, lib_path, footprint_path, model_path, remote_type = get_remote_info(zf)

        dcm_file_read, dcm_file_write = import_dcm(device, remote_type, dcm_path)

        found_model = import_model(model_path, remote_type)

        footprint_file_read, footprint_file_write = import_footprint(remote_type, footprint_path, found_model)

        lib_file_read, lib_file_write = import_lib(device, remote_type, lib_path)

        # replace read files with write files only after all operations succeeded
        dcm_file_write.replace(dcm_file_read)
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
        exception_handler(e)
    exit(0)
