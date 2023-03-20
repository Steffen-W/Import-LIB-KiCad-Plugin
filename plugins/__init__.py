#!/usr/bin/env python
import pcbnew
import os.path
from .impartGUI import impartGUI
import wx
import wx.xrc

__version__ = "0.1"


class impartGUI_Plugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "impartGUI " + __version__
        self.category = "Import library files"
        self.description = "Import library files from Octopart, Samacsys, Ultralibrarian and Snapeda"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(
            os.path.dirname(__file__), 'icon_small.png')

    def Run(self):
        app = wx.App()
        frame = impartGUI(None)
        frame.Show()
        app.MainLoop()
        pcbnew.Refresh()


impartGUI_Plugin().register()
