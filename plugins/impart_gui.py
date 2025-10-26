# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version 4.2.1-0-g80c4cb6)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc

###########################################################################
## Class impartGUI
###########################################################################


class impartGUI(wx.Dialog):

    def __init__(self, parent):
        wx.Dialog.__init__(
            self,
            parent,
            id=wx.ID_ANY,
            title="Footprint Importer",
            pos=wx.DefaultPosition,
            size=wx.Size(650, 650),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.BORDER_DEFAULT,
        )

        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))

        bSizer = wx.BoxSizer(wx.VERTICAL)

        self.m_button_migrate = wx.Button(
            self,
            wx.ID_ANY,
            "Migrate existing libraries (recommended)",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        self.m_button_migrate.SetFont(
            wx.Font(
                15,
                wx.FONTFAMILY_DEFAULT,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
                False,
                wx.EmptyString,
            )
        )
        self.m_button_migrate.Hide()
        self.m_button_migrate.SetMaxSize(wx.Size(-1, 150))

        bSizer.Add(self.m_button_migrate, 0, wx.ALL | wx.EXPAND, 5)

        conversionBox = wx.StaticBoxSizer(
            wx.StaticBox(self, wx.ID_ANY, "Import Actions"), wx.VERTICAL
        )

        manualRow = wx.BoxSizer(wx.HORIZONTAL)

        self.m_buttonImportManual = wx.Button(
            self,
            wx.ID_ANY,
            "Import from LCSC",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        manualRow.Add(
            self.m_buttonImportManual, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5
        )

        self.m_textCtrl2 = wx.TextCtrl(
            self,
            wx.ID_ANY,
            wx.EmptyString,
            wx.DefaultPosition,
            wx.DefaultSize,
            wx.TE_PROCESS_ENTER,
        )
        self.m_textCtrl2.SetMinSize(wx.Size(220, -1))
        self.m_textCtrl2.SetHint("Enter LCSC part number")
        self.m_textCtrl2.SetToolTip("Type an LCSC part number (eg C2040)")

        manualRow.Add(self.m_textCtrl2, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        conversionBox.Add(manualRow, 0, wx.EXPAND, 0)

        convertRow = wx.BoxSizer(wx.HORIZONTAL)

        self.m_button = wx.Button(
            self,
            wx.ID_ANY,
            "Import from Folder",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        convertRow.Add(self.m_button, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.m_overwrite = wx.CheckBox(
            self,
            wx.ID_ANY,
            "Overwrite existing libraries",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        convertRow.Add(self.m_overwrite, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.m_autoImport = wx.CheckBox(
            self,
            wx.ID_ANY,
            "Auto background import",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        convertRow.Add(self.m_autoImport, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.m_check_import_all = wx.CheckBox(
            self, wx.ID_ANY, "import old format", wx.DefaultPosition, wx.DefaultSize, 0
        )
        self.m_check_import_all.Enable(False)
        self.m_check_import_all.Hide()
        convertRow.Add(self.m_check_import_all, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        convertRow.AddStretchSpacer()

        conversionBox.Add(convertRow, 0, wx.EXPAND, 0)

        bSizer.Add(conversionBox, 0, wx.ALL | wx.EXPAND, 5)

        logBox = wx.StaticBoxSizer(
            wx.StaticBox(self, wx.ID_ANY, "Activity Log"), wx.VERTICAL
        )

        self.m_text = wx.TextCtrl(
            self,
            wx.ID_ANY,
            wx.EmptyString,
            wx.DefaultPosition,
            wx.DefaultSize,
            wx.TE_BESTWRAP | wx.TE_MULTILINE | wx.TE_READONLY,
        )
        logBox.Add(self.m_text, 1, wx.ALL | wx.EXPAND, 5)

        bSizer.Add(logBox, 1, wx.ALL | wx.EXPAND, 5)

        pathsBox = wx.StaticBoxSizer(
            wx.StaticBox(self, wx.ID_ANY, "Library Locations"), wx.VERTICAL
        )

        sourceLabel = wx.StaticText(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            "Import library location:",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        sourceLabel.Wrap(-1)
        pathsBox.Add(sourceLabel, 0, wx.TOP | wx.LEFT | wx.RIGHT, 5)

        self.m_dirPicker_sourcepath = wx.DirPickerCtrl(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            ".",
            "Choose the folder containing ZIP files",
            wx.DefaultPosition,
            wx.DefaultSize,
            wx.DIRP_DEFAULT_STYLE,
        )
        pathsBox.Add(self.m_dirPicker_sourcepath, 0, wx.ALL | wx.EXPAND, 5)

        customLibRow = wx.BoxSizer(wx.HORIZONTAL)

        self.m_checkBoxCustomLib = wx.CheckBox(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            "Use one library name for everything",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        customLibRow.Add(self.m_checkBoxCustomLib, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.m_textCtrlCustomLib = wx.TextCtrl(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            wx.EmptyString,
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        self.m_textCtrlCustomLib.Enable(False)
        customLibRow.Add(self.m_textCtrlCustomLib, 1, wx.TOP | wx.BOTTOM | wx.RIGHT, 5)

        pathsBox.Add(customLibRow, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        localRow = wx.BoxSizer(wx.HORIZONTAL)

        self.m_checkBoxLocalLib = wx.CheckBox(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            "Save inside this KiCad project",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        localRow.Add(self.m_checkBoxLocalLib, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.m_textCtrlLocalSubfolder = wx.TextCtrl(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            wx.EmptyString,
            wx.DefaultPosition,
            wx.Size(200, -1),
            0,
        )
        self.m_textCtrlLocalSubfolder.Enable(False)
        localRow.Add(
            self.m_textCtrlLocalSubfolder,
            1,
            wx.TOP | wx.BOTTOM | wx.RIGHT,
            5,
        )

        pathsBox.Add(localRow, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        self.m_staticText_librarypath = wx.StaticText(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            "Global library folder:",
            wx.DefaultPosition,
            wx.DefaultSize,
            0,
        )
        self.m_staticText_librarypath.Wrap(-1)

        pathsBox.Add(self.m_staticText_librarypath, 0, wx.TOP | wx.LEFT | wx.RIGHT, 5)

        self.m_dirPicker_librarypath = wx.DirPickerCtrl(
            pathsBox.GetStaticBox(),
            wx.ID_ANY,
            ".",
            "Choose a global library folder",
            wx.DefaultPosition,
            wx.DefaultSize,
            wx.DIRP_DEFAULT_STYLE,
        )
        pathsBox.Add(self.m_dirPicker_librarypath, 0, wx.ALL | wx.EXPAND, 5)

        bSizer.Add(pathsBox, 0, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(bSizer)
        self.Layout()

        self.Centre(wx.BOTH)

        # Connect Events
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.m_button_migrate.Bind(wx.EVT_BUTTON, self.migrate_libs)
        self.m_button.Bind(wx.EVT_BUTTON, self.BottonClick)
        self.m_buttonImportManual.Bind(wx.EVT_BUTTON, self.ButtomManualImport)
        self.m_textCtrl2.Bind(wx.EVT_TEXT_ENTER, self.ButtomManualImport)
        self.m_dirPicker_sourcepath.Bind(wx.EVT_DIRPICKER_CHANGED, self.DirChange)
        self.m_checkBoxLocalLib.Bind(wx.EVT_CHECKBOX, self.m_checkBoxLocalLibOnCheckBox)
        self.m_dirPicker_librarypath.Bind(wx.EVT_DIRPICKER_CHANGED, self.DirChange)
        self.m_checkBoxCustomLib.Bind(
            wx.EVT_CHECKBOX, self.m_checkBoxCustomLibOnCheckBox
        )
        self.m_textCtrlCustomLib.Bind(wx.EVT_TEXT, self.m_textCtrlCustomLibOnText)
        self.m_textCtrlLocalSubfolder.Bind(
            wx.EVT_TEXT, self.m_textCtrlLocalSubfolderOnText
        )

    def __del__(self):
        pass

    # Virtual event handlers, override them in your derived class
    def on_close(self, event):
        event.Skip()

    def migrate_libs(self, event):
        event.Skip()

    def BottonClick(self, event):
        event.Skip()

    def ButtomManualImport(self, event):
        event.Skip()

    def DirChange(self, event):
        event.Skip()

    def m_checkBoxLocalLibOnCheckBox(self, event):
        event.Skip()

    def m_checkBoxCustomLibOnCheckBox(self, event):
        event.Skip()

    def m_textCtrlCustomLibOnText(self, event):
        event.Skip()

    def m_textCtrlLocalSubfolderOnText(self, event):
        event.Skip()
