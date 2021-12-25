Assembles local KiCad component libraries from downloaded [Octopart](https://octopart.com/),
[Samacsys](https://componentsearchengine.com/), [Ultralibrarian](https://app.ultralibrarian.com/search) and [Snapeda](https://www.snapeda.com/home/) zipfiles. Currently assembles just
symbols and footptints. Supports component updates. Can safely copy
multi-lines from the clipboard to update component description. Tested with
KiCad 5.1.12 for Ubuntu.


# Configure mydirs.py

    SRC = Path.home() / 'Desktop'
    TGT = Path.home() / 'private/edn/kicad-libs'


# Usage

    $ impart -h
    usage: impart [-h] [--init] [--zap]
    
    optional arguments:
      -h, --help  show this help message and exit
      --init      initialize library
      --zap       delete source zipfile after assembly
    
    Copy to clipboard as usual, just hit Enter to paste...

