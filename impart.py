#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded Octopart,
# Samacsys, Ultralibrarian and Snapeda zipfiles. Currently assembles just
# symbols and footptints. Tested with KiCad 5.1.12 for Ubuntu.

from mydirs import SRC_PATH, LIB_PATH     # *CONFIGURE ME*
import argparse
import clipboard
import re
import readline
import shutil
import zipfile
from os import stat


def Xinput(prompt):
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
        reply = Xinput(prompt)
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


REMOTE_TYPES = {0: 'octopart', 1: 'samacsys', 2: 'ultralibrarian', 3: 'snapeda'}


class Catch(Exception):
    def __init__(self, value):
        self.catch = value
        super().__init__(self)


def Zipper(root, suffix):
    """return zipfile.Path starting with root ending with suffix"""
    def zipper(parent):
        if parent.name.endswith(suffix):
            raise Catch(parent)
        elif parent.is_dir():
            for child in parent.iterdir():
                zipper(child)

    try:
        zipper(root)
    except Catch as e:
        return e.catch

    return None


def Impart(zip):
    """zip is a pathlib.Path to import the symbol from"""
    if not zipfile.is_zipfile(zip):
        return None

    device = zip.name[:-4]
    # Request user input, but default to device if nothing entered
    device_name = input('Generic device name [{0}]: '.format(device)) or device
    if device_name == '':
        return None

    # Identify format based on directory structure
    with zipfile.ZipFile(zip) as zf:
        root = zipfile.Path(zf)

        while True:
            dcm_path = root / 'device_name.dcm'
            lib_path = root / 'device_name.lib'
            footprint_dir_path = root / 'device_name.pretty'
            if dcm_path.exists() and lib_path.exists() and footprint_dir_path.exists():
                remote_type = 0         # OCTOPART
                break

            dir = Zipper(root, 'KiCad')
            if dir:
                dcm_path = Zipper(dir, '.dcm')
                lib_path = Zipper(dir, '.lib')
                footprint_dir_path = dir
                assert dcm_path and lib_path, 'Not in samacsys format'
                remote_type = 1         # SAMACSYS
                break

            dir = root / 'KiCAD'
            if dir.exists():
                dcm_path = Zipper(dir, '.dcm')
                lib_path = Zipper(dir, '.lib')
                footprint_dir_path = Zipper(dir, '.pretty')
                assert lib_path and footprint_dir_path, 'Not in ultralibrarian format'
                remote_type = 2         # ULTRALIBRARIAN
                break

            lib_path = Zipper(root, '.lib')
            if lib_path:
                dcm_path = Zipper(root, '.dcm')
                footprint_dir_path = root
                remote_type = 3         # SNAPEDA
                break

            assert False, 'Unknown library zipfile'

        # --------------------------------------------------------------------------------------------------------
        # .dcm file parsing
        # Note this reads in the existing dcm file for the particular remote repo, and tries to catch any duplicates
        # before overwriting or creating duplicates. It reads the existing dcm file line by line and simply copy+paste
        # each line if nothing will be overwritten or duplicated. If something could be overwritten or duplicated, the
        # terminal will prompt whether to overwrite or to keep the existing content and ignore the new file contents.
        # --------------------------------------------------------------------------------------------------------
        # Array of values defining all attributes of .dcm file
        dcm_attributes = dcm_path.read_text().splitlines() if dcm_path else [
            '#', '# ' + device, '#', '$CMP ' + device_name, 'D', 'F', '$ENDCMP']

        print('Adding', device_name, 'to', REMOTE_TYPES[remote_type])

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
                    datasheet = input('Datasheet URL [{0}]: '.format(datasheet)) or datasheet
                    if datasheet:
                        dcm_attributes[attribute_idx] = 'F ' + datasheet
        if index_end is None:
            return device_name, 'not found in', dcm_path.name

        dcm_file_read = LIB_PATH / (REMOTE_TYPES[remote_type] + '.dcm')
        dcm_file_write = LIB_PATH / (REMOTE_TYPES[remote_type] + '.dcm~')
        overwrite_existing = overwrote_existing = False
        if not dcm_file_read.exists():
            dcm_file_read.touch(mode=0o666)
        if not dcm_file_write.exists():
            dcm_file_write.touch(mode=0o666)

        with dcm_file_read.open('rt') as readfile:
            with dcm_file_write.open('wt') as writefile:

                if (stat(dcm_file_read).st_size == 0):
                    # todo Handle appending to empty file
                    with dcm_file_read.open('wt') as template_file:
                        template = ["EESchema-DOCLIB  Version 2.0", "#End Doc Library"]
                        template_file.writelines(line + '\n' for line in template)
                        template_file.close()

                for line in readfile:
                    if re.match('# *end ', line, re.IGNORECASE):
                        if not overwrote_existing:
                            writefile.write('\n'.join(dcm_attributes[index_start if index_header_start is None else index_header_start:
                                                   index_end]) + '\n')
                        writefile.write(line)
                        break
                    elif line.startswith('$CMP '):
                        component_name = line[5:].strip()
                        if component_name.startswith(device_name):
                            yes = input(device_name + ' in ' + dcm_file_read.name + ', replace it? [Yes]: ') or "Yes"
                            overwrite_existing = yes and 'yes'.startswith(yes.lower()) #todo should also accept y or Y
                            if not overwrite_existing:
                                return 'OK:', device_name, 'already in', dcm_file_read.name
                            writefile.write('\n'.join(dcm_attributes[index_start:index_end]) + '\n')
                            overwrote_existing = True
                        else:
                            writefile.write(line)
                    elif overwrite_existing:
                        if line.startswith('$ENDCMP'):
                            overwrite_existing = False
                    else:
                        writefile.write(line)

        # --------------------------------------------------------------------------------------------------------
        # Footprint file parsing
        # todo it doesn't look like this handles duplicates like the other parsing sections
        # --------------------------------------------------------------------------------------------------------
        pretty = 0
        footprint_name = None
        for footprint_dir_item in footprint_dir_path.iterdir():
            if footprint_dir_item.name.endswith('.kicad_mod') or footprint_dir_item.name.endswith('.mod'):
                pretty += 1
                footprint_name = footprint_dir_item.name # todo what happens if you have more than one footprint? This will save the last one only.
                footprint_lines = footprint_dir_item.read_text()

                if not (LIB_PATH / (REMOTE_TYPES[remote_type] + '.pretty')).is_dir():
                    (LIB_PATH / (REMOTE_TYPES[remote_type] + '.pretty')).mkdir(parents=True)

                if not (LIB_PATH / (REMOTE_TYPES[remote_type] + '.pretty') / footprint_dir_item.name).exists():
                    (LIB_PATH / (REMOTE_TYPES[remote_type] + '.pretty') / footprint_dir_item.name).touch(mode=0o666)

                with (LIB_PATH / (REMOTE_TYPES[remote_type] + '.pretty') / footprint_dir_item.name).open('wt') as wr:
                    wr.write(footprint_lines)
        print('footprints:', pretty)


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
        index_footprint = None
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
                        footprint, REMOTE_TYPES[remote_type] + ":" + footprint, 1)
                    index_footprint = line_idx
                elif line.startswith('ENDDEF'):
                    index_end = line_idx + 1
                elif line.startswith('F1 '):
                    lib_lines[line_idx] = line.replace(device, device_name, 1)
            elif line.startswith('DEF '):
                return 'Multiple devices in', lib_path.name
        if index_end is None:
            return device, 'not found in', lib_path.name

        lib_file_read = LIB_PATH / (REMOTE_TYPES[remote_type] + '.lib')
        lib_file_write = LIB_PATH / (REMOTE_TYPES[remote_type] + '.lib~')
        overwrite_existing = overwrote_existing = False

        if not lib_file_read.exists():
            lib_file_read.touch(mode=0o666)
        if not lib_file_write.exists():
            lib_file_write.touch(mode=0o666)

        with lib_file_read.open('rt') as readfile:
            with lib_file_write.open('wt') as writefile:

                if (stat(lib_file_read).st_size == 0):
                    # todo Handle appending to empty file
                    with lib_file_read.open('wt') as template_file:
                        template = ["EESchema-LIBRARY Version 2.4", "#encoding utf-8", "# End Library"]
                        template_file.writelines(line + '\n' for line in template)
                        template_file.close()

                # For each line in the existing lib file (not the file being read from the zip. The lib file you will add it to.)
                for line in readfile:
                    # Is this trying to match ENDDRAW, ENDDEF, End Library or any of the above?
                    if re.match('# *end ', line, re.IGNORECASE):
                        # If you already overwrote the new info don't add it to the end
                        if not overwrote_existing:
                            writefile.write('\n'.join(lib_lines[index_start if index_header_start is None else index_header_start:
                                                   index_end]) + '\n')
                        writefile.write(line)
                        break
                    # Catch start of new component definition
                    elif line.startswith('DEF '):
                        component_name = line.split()[1]
                        # Catch if the currently read component matches the name of the component you are planning to write
                        if component_name.startswith(device_name):
                            # Ask if you want to overwrite existing component
                            yes = input(device_name + ' in ' + lib_file_read.name + ', replace it? [Yes]: ') or "Yes"
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

        dcm_file_write.replace(dcm_file_read)
        lib_file_write.replace(lib_file_read)

    return 'OK:',


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        epilog='Note, empty input: invites clipboard content, if available.')
    parser.add_argument('--init', action='store_true',
                        help='initialize library')
    parser.add_argument('--zap', action='store_true',
                        help='delete source zipfile after assembly')
    arg = parser.parse_args()

    readline.set_completer_delims('\t')
    readline.parse_and_bind('tab: complete')
    readline.set_auto_history(False)

    try:
        if arg.init:
            libras = list(REMOTE_TYPES.values())
            while libras:
                libra = Select(libras)('Erase/Initialize which library? ')
                if libra == '':
                    break
                assert libra in libras, 'Unknown library'

                dcm = LIB_PATH / (libra + '.dcm')
                if not dcm.exists():
                    dcm.touch(mode=0o666)

                with dcm.open('wt') as dcmf:
                    dcmf.writelines(['EESchema-DOCLIB  Version 2.0\n',
                                     '#End Doc Library\n'])
                dcm.chmod(0o660)

                lib = LIB_PATH / (libra + '.lib')
                if not lib.exists():
                    lib.touch(mode=0o666)
                with lib.open('wt') as libf:
                    libf.writelines(['EESchema-LIBRARY Version 2.4\n',
                                     '#encoding utf-8\n',
                                     '#End Library\n'])
                lib.chmod(0o660)

                pcb = LIB_PATH / (libra + '.pretty')
                shutil.rmtree(pcb, ignore_errors=True)
                pcb.mkdir(mode=0o770, parents=False, exist_ok=False)

                libras.remove(libra)

        zips = [zip.name for zip in SRC_PATH.glob('*.zip')]
        zip = SRC_PATH / Select(zips)('Library zip file: ')
        response = Impart(zip)
        if response:
            print(*response)
            if arg.zap and response[0] == 'OK:':
                zip.unlink()
    except EOFError:
        print('EOF')
    except Exception as e:
        print(*e.args)
    exit(0)
