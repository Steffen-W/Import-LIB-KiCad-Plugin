# -*- coding: utf-8 -*-

###########################################################################
# Python code generated with wxFormBuilder (version 3.10.0.6-0-g90453e5d)
# http://www.wxformbuilder.org/
##
# PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc

###########################################################################
# Class impartGUI
###########################################################################

import configparser
import os
from pathlib import Path
import KiCadImport


class GUI_functions():

    def init(self):
        print("start")
        self.config = configparser.ConfigParser()
        self.config_path = os.path.join(
            os.path.dirname(__file__), 'config.ini')
        try:
            self.config.read(self.config_path)
            self.config['config']['SRC_PATH']  # only for check
            self.config['config']['DEST_PATH']  # only for check
        except:
            print("An exception occurred during import " + self.config_path)
            self.config = configparser.ConfigParser()
            self.config.add_section("config")
            self.config.set("config", "SRC_PATH", "")
            self.config.set("config", "DEST_PATH", "")

        if self.config['config']['SRC_PATH'] == "":
            self.config['config']['SRC_PATH'] = str(Path.home() / 'Downloads')
        if self.config['config']['DEST_PATH'] == "":
            self.config['config']['DEST_PATH'] = str(Path.home() / 'KiCad')
        self.m_dirPicker_sourcepath.SetPath(self.config['config']['SRC_PATH'])
        self.m_dirPicker_librarypath.SetPath(
            self.config['config']['DEST_PATH'])

    def print(self, text):
        self.m_text.AppendText(str(text)+"\n")

    def BottonClick(self, event):
        KiCadImport.SRC_PATH = Path(self.config['config']['SRC_PATH'])
        KiCadImport.DEST_PATH = Path(self.config['config']['DEST_PATH'])

        for lib in os.listdir(self.config['config']['SRC_PATH']):
            if lib.startswith('LIB') and lib.endswith('.zip'):
                lib = os.path.join(self.config['config']['SRC_PATH'], lib)
                res, = KiCadImport.import_all(lib, 'YES')
                print(res)
        event.Skip()

    def DirChange(self, event):
        self.config['config']['SRC_PATH'] = self.m_dirPicker_librarypath.GetPath()
        self.config['config']['DEST_PATH'] = self.m_dirPicker_sourcepath.GetPath()
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)
        event.Skip()


class impartGUI (wx.Frame, GUI_functions):

    def __init__(self, parent):
        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title=u"impartGUI", pos=wx.DefaultPosition, size=wx.Size(
            600, 600), style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)

        self.SetSizeHints(wx.Size(150, 150), wx.Size(600, 1000))
        self.SetFont(wx.Font(wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT,
                     wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString))
        self.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        self.SetBackgroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))

        bSizer1 = wx.BoxSizer(wx.VERTICAL)

        self.m_button = wx.Button(
            self, wx.ID_ANY, u"Start", wx.DefaultPosition, wx.DefaultSize, 0)
        bSizer1.Add(self.m_button, 0, wx.ALL |
                    wx.ALIGN_CENTER_HORIZONTAL | wx.EXPAND, 5)

        self.m_text = wx.TextCtrl(self, wx.ID_ANY, u"output:\n", wx.DefaultPosition,
                                  wx.DefaultSize, wx.HSCROLL | wx.TE_LEFT | wx.TE_MULTILINE | wx.TE_READONLY)
        bSizer1.Add(self.m_text, 1, wx.ALL | wx.EXPAND, 5)

        fgSizer1 = wx.FlexGridSizer(0, 2, 0, 0)
        fgSizer1.SetFlexibleDirection(wx.BOTH)
        fgSizer1.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_SPECIFIED)

        fgSizer1.SetMinSize(wx.Size(-1, 0))
        self.m_staticText_sourcepath = wx.StaticText(
            self, wx.ID_ANY, u"Library source path:", wx.DefaultPosition, wx.DefaultSize, 0)
        self.m_staticText_sourcepath.Wrap(-1)

        fgSizer1.Add(self.m_staticText_sourcepath, 0, wx.ALL |
                     wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 5)

        self.m_checkBox_autoImport = wx.CheckBox(
            self, wx.ID_ANY, u"Import library automatically", wx.DefaultPosition, wx.DefaultSize, 0)
        fgSizer1.Add(self.m_checkBox_autoImport, 0,
                     wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        bSizer1.Add(fgSizer1, 0, 0, 5)

        self.m_dirPicker_sourcepath = wx.DirPickerCtrl(
            self, wx.ID_ANY, u".", u"Select a folder", wx.DefaultPosition, wx.DefaultSize, wx.DIRP_DEFAULT_STYLE)
        bSizer1.Add(self.m_dirPicker_sourcepath, 0, wx.ALL | wx.EXPAND, 5)

        self.m_staticText_librarypath = wx.StaticText(
            self, wx.ID_ANY, u"Save to library path:", wx.DefaultPosition, wx.DefaultSize, 0)
        self.m_staticText_librarypath.Wrap(-1)

        bSizer1.Add(self.m_staticText_librarypath, 0, wx.ALL, 5)

        self.m_dirPicker_librarypath = wx.DirPickerCtrl(
            self, wx.ID_ANY, u".", u"Select a folder", wx.DefaultPosition, wx.DefaultSize, wx.DIRP_DEFAULT_STYLE)
        bSizer1.Add(self.m_dirPicker_librarypath, 0, wx.ALL | wx.EXPAND, 5)

        self.m_staticline1 = wx.StaticLine(
            self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.m_staticline1.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        self.m_staticline1.SetBackgroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))

        bSizer1.Add(self.m_staticline1, 0, wx.EXPAND | wx.ALL, 5)

        self.m_staticText5 = wx.StaticText(
            self, wx.ID_ANY, u"There is no guarantee for faultless function. Use only at your own risk.\n\nAuthor:\nSteffen-W and mweizel\n\nMany thanks to:\nwexi with impart @ github.com\ntopherbuckley @ github.com", wx.DefaultPosition, wx.DefaultSize, 0)
        self.m_staticText5.Wrap(-1)

        bSizer1.Add(self.m_staticText5, 0, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(bSizer1)
        self.Layout()

        self.Centre(wx.BOTH)

        # Connect Events
        self.m_button.Bind(wx.EVT_BUTTON, self.BottonClick)
        self.m_dirPicker_sourcepath.Bind(
            wx.EVT_DIRPICKER_CHANGED, self.DirChange)
        self.m_dirPicker_librarypath.Bind(
            wx.EVT_DIRPICKER_CHANGED, self.DirChange)
        self.init()

    def __del__(self):
        pass
