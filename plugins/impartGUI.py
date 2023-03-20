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


class impartGUI (wx.Frame):

    def __init__(self, parent):
        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title=u"impartGUI", pos=wx.DefaultPosition, size=wx.Size(
            600, 600), style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)

        self.SetSizeHints(wx.Size(150, 150), wx.Size(600, 600))
        self.SetFont(wx.Font(wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT,
                     wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, wx.EmptyString))
        self.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        self.SetBackgroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))

        bSizer1 = wx.BoxSizer(wx.VERTICAL)

        self.m_button1 = wx.Button(
            self, wx.ID_ANY, u"Button1", wx.DefaultPosition, wx.DefaultSize, 0)
        bSizer1.Add(self.m_button1, 0, wx.ALL |
                    wx.ALIGN_CENTER_HORIZONTAL | wx.EXPAND, 5)

        self.m_staticText6 = wx.StaticText(
            self, wx.ID_ANY, u"MyLabel", wx.DefaultPosition, wx.DefaultSize, 0)
        self.m_staticText6.Wrap(-1)

        self.m_staticText6.SetBackgroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_INFOTEXT))

        bSizer1.Add(self.m_staticText6, 1, wx.ALL | wx.EXPAND, 5)

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
        self.m_button1.Bind(wx.EVT_BUTTON, self.Botton1Click)

    def __del__(self):
        print('by')
        pass

    # Virtual event handlers, override them in your derived class
    def Botton1Click(self, event):
        event.Skip()
