Assembles local KiCad component libraries from downloaded octopart,
samacsys, ultralibrarian and snapeda zipfiles. Currently assembles just the
symbols and the footptints only. Supports component updates. Can copy
multi-lines from the clipboard to update component description.


# Configure

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

