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
TGT = Path.home() / 'private/edn/kicad-libs'
PRJ = {0: 'octopart', 1: 'samacsys', 2: 'ultralibrarian', 3: 'snapeda'}


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
        reply = input(prompt)
        if reply == '':
            text = clipboard.paste()
            if text:
                self._pretext = text.replace('\n', ' ')
                clipboard.copy('')
                reply = input(prompt)

        readline.set_pre_input_hook(None)
        return reply

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
            response = self._pre[state]
        except IndexError:
            response = None
        return response


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
    eec = Pretext(device)('Generic device name ? ')
    if eec == '':
        eec = device
    print('Adding', eec, 'to', PRJ[prj])

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
            txt = ['$CMP ' + device, 'D ' + device, 'F ', '$ENDCMP']

        stx = None
        etx = None
        for no, tx in enumerate(txt):
            if stx is None:
                if tx.startswith('$CMP '):
                    stx = no
                    t = tx[5:].strip()
                    if t != device:
                        return 'Unexpected device in', path
                    txt[no] = '$CMP ' + eec
            elif etx is None:
                if tx.startswith('$CMP '):
                    return 'Multiple devices in', path
                elif tx.startswith('$ENDCMP'):
                    etx = no + 1
                elif tx.startswith('D '):
                    dsc = Pretext('')(
                        'Device description [=' + tx[2:] + '] ? ')
                    if dsc:
                        txt[no] = 'D ' + dsc
                elif tx.startswith('F '):
                    url = Pretext('')(
                        'URL ' + (('[=' + tx[2:] + '] ') if tx[2:]
                                  else '') + '? ')
                    if url:
                        txt[no] = 'F ' + url
        if etx is None:
            return device, 'not found in', path
        dcm = '\n'.join(txt[stx:etx]) + '\n#\n'  # documentation

        rd_dcm = TGT / (PRJ[prj] + '.dcm')
        wr_dcm = TGT / (PRJ[prj] + '.dcm~')
        with rd_dcm.open('rt') as rf:
            with wr_dcm.open('wt') as wf:
                for tx in rf:
                    if tx.startswith('$CMP ') and tx[5:].startswith(eec):
                        return 'OK:', eec, 'already in', rd_dcm
                    elif re.match('# *end ', tx, re.IGNORECASE):
                        wf.write(dcm)
                        wf.write(tx)
                        break
                    wf.write(tx)

        stx = None
        etx = None
        txt = symb.read_text().splitlines()
        for no, tx in enumerate(txt):
            if stx is None:
                if tx.startswith('DEF ' + device):
                    stx = no
                    txt[no] = tx.replace(device, eec, 1)
            elif etx is None:
                if tx.startswith('ENDDEF'):
                    etx = no + 1
                elif tx.startswith('F1 '):
                    txt[no] = tx.replace(device, eec, 1)
            elif tx.startswith('DEF '):
                return 'Multiple devices in', symb
        if etx is None:
            return device, 'not found in', symb
        lib = '\n'.join(txt[stx:etx]) + '\n#\n'

        rd_lib = TGT / (PRJ[prj] + '.lib')
        wr_lib = TGT / (PRJ[prj] + '.lib~')
        with rd_lib.open('rt') as rf:
            with wr_lib.open('wt') as wf:
                for tx in rf:
                    if re.match('# *end ', tx, re.IGNORECASE):
                        wf.write(lib)
                        wf.write(tx)
                        break
                    wf.write(tx)

        pretty = 0
        for rd in food.iterdir():
            if rd.name.endswith('.kicad_mod') or rd.name.endswith('.mod'):
                pretty += 1
                name = (rd.name if rd.name.startswith(eec)
                        else eec + '_' + rd.name)
                txt = rd.read_text()
                with (TGT / (PRJ[prj] + '.pretty') / name).open('wt') as wr:
                    wr.write(txt)
        print('footprints:', pretty)

        wr_dcm.replace(rd_dcm)
        wr_lib.replace(rd_lib)

    return 'OK:',


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        epilog='Copy to clipboard as usual, just hit Enter to paste...')
    parser.add_argument('--init', action='store_true',
                        help='initialize library')
    parser.add_argument('--zap', action='store_true',
                        help='delete source zipfile after assembly')
    arg = parser.parse_args()

    signal.signal(signal.SIGINT, Signal)

    readline.set_completer_delims('\t')
    readline.parse_and_bind('tab: complete')

    try:
        if arg.init:
            libras = list(PRJ.values())
            while libras:
                libra = Select(libras)('Erase/Initialize which library? ')
                if libra == '':
                    break
                assert libra in libras, 'Unknown library'

                dcm = TGT / (libra + '.dcm')
                with dcm.open('wt') as dcmf:
                    dcmf.writelines(['EESchema-DOCLIB  Version 2.0\n',
                                     '#\n',
                                     '#End Doc Library\n'])
                dcm.chmod(0o660)

                lib = TGT / (libra + '.lib')
                with lib.open('wt') as libf:
                    libf.writelines(['EESchema-LIBRARY Version 2.4\n',
                                     '#encoding utf-8\n',
                                     '#\n',
                                     '#End Library\n'])
                lib.chmod(0o660)

                pcb = TGT / (libra + '.pretty')
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
