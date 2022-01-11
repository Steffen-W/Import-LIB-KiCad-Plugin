Assembles KiCad "legacy" format component libraries from downloaded
[Octopart](https://octopart.com/), [Samacsys](https://componentsearchengine.com/), [Ultralibrarian](https://app.ultralibrarian.com/search) and [Snapeda](https://www.snapeda.com/home/) zipfiles. Currently
assembles only symbols and footprints. Supports component updates. Can
safely copy multi-lines from the clipboard to update the component
description and URL. Can be used with KiCad 5 and 6.


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

