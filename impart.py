#!/usr/bin/env python3
# coding: utf-8

# Assembles local KiCad component libraries from downloaded octopart,
# samacsys, ultralibrarian and snapeda zipfiles. Currently assembles just
# the symbols and the footptints only.

from pathlib import Path
import argparse
import clipboard
import re
import readline
import shutil
import signal
import zipfile

SRC = Path.home() / 'Desktop'
LIB = Path.home() / 'private/edn/kicad-libs'


def Signal(signum, stack):
    raise UserWarning('CTRL-C')


class Pretext:
    """input() with inserted text"""
    def __init__(self, pretext):
        self._pretext = pretext
        readline.set_completer(lambda: None)
        readline.set_pre_input_hook(self.insert)
        clipboard.copy('')

    def __call__(self, prompt):
        reply = input(prompt + (': ' if self._pretext else ' [=clipboard]: '))
        if reply == '':
            text = clipboard.paste()
            if text:
                clipboard.copy('')
                self._pretext = text.replace('\n', ' ')
                reply = input(prompt + ': ')
        readline.set_pre_input_hook(None)

        index = reply.find('~') + 1  # ~ clears line when running Emacs
        return reply[index:]

    def insert(self):
        readline.insert_text(self._pretext)
        readline.redisplay()


class Select:
    """input() from select completions """
    def __init__(self, select):
        self._select = select
        readline.set_completer(self.complete)
        readline.set_pre_input_hook(None)

    def __call__(self, prompt):
        reply = input(prompt)
        readline.set_completer(lambda: None)
        return reply

    def complete(self, text, state):
        if state == 0:
            if text:
                self._pre = [s for s in self._select
                             if s and s.startswith(text)]
            else:
                self._pre = self._select[:]
        try:
            reply = self._pre[state]
        except IndexError:
            reply = None

        index = reply.find('~') + 1
        return reply[index:]


PRJ = {0: 'octopart', 1: 'samacsys', 2: 'ultralibrarian', 3: 'snapeda'}


def Impart(zip):
    """given the zipfile path"""
    if not zipfile.is_zipfile(zip):
        return None

    # Library detection heuristics:

    tail = zip.name.rfind('_') + 1
    if tail:
        if zip.name.startswith('LIB_'):
            prj = 1             # samacsys
        elif zip.name.startswith('ul_'):
            prj = 2             # ultralibrarian
        else:
            prj = 0             # octopart
    else:
        prj = 3                 # snapeda

    device = zip.name[tail:-4]
    eec = Pretext(device)('Generic device name')
    if eec == '':
        eec = device
    print('Adding', eec, 'to', PRJ[prj])

    Update = False

    with zipfile.ZipFile(zip) as zf:
        root = zipfile.Path(zf)

        if prj < 2:
            if prj == 0:
                desc = root / 'eec.dcm'
                symb = root / 'eec.lib'
                food = root / 'eec.pretty'
            elif prj == 1:
                desc = root / device / 'KiCad' / (device + '.dcm')
                symb = root / device / 'KiCad' / (device + '.lib')
                food = root / device / 'KiCad'
            txt = desc.read_text().splitlines()
        else:
            if prj == 2:
                path = root / 'KiCAD'
                for dir in path.iterdir():
                    if dir.is_dir():
                        break
                symb = dir / (dir.name + '.lib')
                food = dir / 'footprints.pretty'
            else:
                symb = root / (device + '.lib')
                food = root
            txt = ['#', '# '+device, '#', '$CMP '+device, 'D', 'F', '$ENDCMP']

        stx = None
        etx = None
        hsh = None
        for no, tx in enumerate(txt):
            if stx is None:
                if tx.startswith('#'):
                    if tx.strip() == '#' and hsh is None:
                        hsh = no  # header start
                elif tx.startswith('$CMP '):
                    stx = no if hsh is None else hsh
                    if tx[5:].strip() != device:
                        return 'Unexpected device in', path
                    txt[no] = tx.replace(device, eec, 1)
                else:
                    hsh = None
            elif etx is None:
                if tx.startswith('$CMP '):
                    return 'Multiple devices in', path
                elif tx.startswith('$ENDCMP'):
                    etx = no + 1
                elif tx.startswith('D'):
                    t = tx[2:].strip()
                    dsc = Pretext(t)('Device description')
                    if dsc:
                        txt[no] = 'D ' + dsc
                elif tx.startswith('F'):
                    t = tx[2:].strip()
                    url = Pretext(t)('Datasheet URL')
                    if url:
                        txt[no] = 'F ' + url
        if etx is None:
            return device, 'not found in', path
        dcm = '\n'.join(txt[stx:etx]) + '\n'

        rd_dcm = LIB / (PRJ[prj] + '.dcm')
        wr_dcm = LIB / (PRJ[prj] + '.dcm~')
        update = False
        with rd_dcm.open('rt') as rf:
            with wr_dcm.open('wt') as wf:
                for tx in rf:
                    if tx.startswith('$CMP '):
                        t = tx[5:].strip()
                        if t.startswith(eec):
                            yes = Pretext('No')(
                                eec + ' in library, replace it ? ')
                            update = yes and 'yes'.startswith(yes.lower())
                            if not update:
                                return 'OK:', eec, 'already in', rd_dcm
                            Update = True
                            wf.write(dcm)
                    elif re.match('# *end ', tx, re.IGNORECASE):
                        if not Update:
                            wf.write(dcm)
                        wf.write(tx)
                        break
                    elif update:
                        if tx.startswith('$ENDCMP'):
                            update = False
                    else:
                        wf.write(tx)

        txt = symb.read_text().splitlines()

        stx = None
        etx = None
        hsh = None
        for no, tx in enumerate(txt):
            if stx is None:
                if tx.startswith('#'):
                    if tx.strip() == '#' and hsh is None:
                        hsh = no  # header start
                elif tx.startswith('DEF '):
                    stx = no if hsh is None else hsh
                    txt[no] = tx.replace(device, eec, 1)
                else:
                    hsh = None
            elif etx is None:
                if tx.startswith('ENDDEF'):
                    etx = no + 1
                elif tx.startswith('F1 '):
                    txt[no] = tx.replace(device, eec, 1)
            elif tx.startswith('DEF '):
                return 'Multiple devices in', symb
        if etx is None:
            return device, 'not found in', symb
        lib = '\n'.join(txt[stx:etx]) + '\n'

        rd_lib = LIB / (PRJ[prj] + '.lib')
        wr_lib = LIB / (PRJ[prj] + '.lib~')
        update = False
        with rd_lib.open('rt') as rf:
            with wr_lib.open('wt') as wf:
                for tx in rf:
                    if Update and tx.startswith('DEF '):
                        t = tx[4:].lstrip()
                        if t.startswith(eec):
                            update = True
                            wf.write(lib)
                    elif re.match('# *end ', tx, re.IGNORECASE):
                        if not Update:
                            wf.write(lib)
                        wf.write(tx)
                        break
                    elif update:
                        if tx.startswith('ENDDEF'):
                            update = False
                    else:
                        wf.write(tx)

        pretty = 0
        for rd in food.iterdir():
            if rd.name.endswith('.kicad_mod') or rd.name.endswith('.mod'):
                pretty += 1
                name = (rd.name if rd.name.startswith(eec)
                        else eec + '_' + rd.name)
                txt = rd.read_text()
                with (LIB / (PRJ[prj] + '.pretty') / name).open('wt') as wr:
                    wr.write(txt)
        print('footprints:', pretty)

        wr_dcm.replace(rd_dcm)
        wr_lib.replace(rd_lib)

    return 'OK:',


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        epilog='Note, empty input: invites clipboard content, if available.')
    parser.add_argument('--init', action='store_true',
                        help='initialize library')
    parser.add_argument('--zap', action='store_true',
                        help='delete source zipfile after assembly')
    arg = parser.parse_args()

    signal.signal(signal.SIGINT, Signal)

    readline.set_completer_delims('\t')
    readline.parse_and_bind('tab: complete')
    readline.set_auto_history(False)

    try:
        if arg.init:
            libras = list(PRJ.values())
            while libras:
                libra = Select(libras)('Erase/Initialize which library? ')
                if libra == '':
                    break
                assert libra in libras, 'Unknown library'

                dcm = LIB / (libra + '.dcm')
                with dcm.open('wt') as dcmf:
                    dcmf.writelines(['EESchema-DOCLIB  Version 2.0\n',
                                     '#End Doc Library\n'])
                dcm.chmod(0o660)

                lib = LIB / (libra + '.lib')
                with lib.open('wt') as libf:
                    libf.writelines(['EESchema-LIBRARY Version 2.4\n',
                                     '#encoding utf-8\n',
                                     '#End Library\n'])
                lib.chmod(0o660)

                pcb = LIB / (libra + '.pretty')
                shutil.rmtree(pcb, ignore_errors=True)
                pcb.mkdir(mode=0o770, parents=False, exist_ok=False)

                libras.remove(libra)

        while True:
            zips = [zip.name for zip in SRC.glob('*.zip')]
            zip = SRC / Select(zips)('Library zip file: ')
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
