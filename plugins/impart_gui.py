# -*- coding: utf-8 -*-

###########################################################################
## Python code generated with wxFormBuilder (version 3.10.0.6-0-g90453e5d)
## http://www.wxformbuilder.org/
##
## PLEASE DO *NOT* EDIT THIS FILE!
###########################################################################

import wx
import wx.xrc
import wx.adv

###########################################################################
## Class impartGUI
###########################################################################

class impartGUI ( wx.Dialog ):

    def __init__( self, parent ):
        wx.Dialog.__init__ ( self, parent, id = wx.ID_ANY, title = u"impartGUI", pos = wx.DefaultPosition, size = wx.Size( 600,600 ), style = wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER|wx.BORDER_DEFAULT )

        self.SetSizeHints( wx.DefaultSize, wx.DefaultSize )
        self.SetBackgroundColour( wx.SystemSettings.GetColour( wx.SYS_COLOUR_WINDOW ) )

        bSizer1 = wx.BoxSizer( wx.VERTICAL )

        self.m_button = wx.Button( self, wx.ID_ANY, u"Start", wx.DefaultPosition, wx.DefaultSize, 0 )
        bSizer1.Add( self.m_button, 0, wx.ALL|wx.ALIGN_CENTER_HORIZONTAL|wx.EXPAND, 5 )

        self.m_text = wx.TextCtrl( self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize, wx.TE_BESTWRAP|wx.TE_MULTILINE )
        bSizer1.Add( self.m_text, 1, wx.ALL|wx.EXPAND, 5 )

        fgSizer1 = wx.FlexGridSizer( 0, 3, 0, 0 )
        fgSizer1.SetFlexibleDirection( wx.BOTH )
        fgSizer1.SetNonFlexibleGrowMode( wx.FLEX_GROWMODE_SPECIFIED )

        fgSizer1.SetMinSize( wx.Size( -1,0 ) )
        self.m_autoImport = wx.CheckBox( self, wx.ID_ANY, u"automatic import", wx.DefaultPosition, wx.DefaultSize, 0 )
        fgSizer1.Add( self.m_autoImport, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

        self.m_overwrite = wx.CheckBox( self, wx.ID_ANY, u"overwrite if existing", wx.DefaultPosition, wx.DefaultSize, 0 )
        fgSizer1.Add( self.m_overwrite, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

        self.m_check_import_all = wx.CheckBox( self, wx.ID_ANY, u"import also old format", wx.DefaultPosition, wx.DefaultSize, 0 )
        fgSizer1.Add( self.m_check_import_all, 0, wx.ALL, 5 )


        bSizer1.Add( fgSizer1, 0, wx.EXPAND, 5 )

        self.m_staticText_sourcepath = wx.StaticText( self, wx.ID_ANY, u"Folder of the library to import:", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.m_staticText_sourcepath.Wrap( -1 )

        bSizer1.Add( self.m_staticText_sourcepath, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5 )

        self.m_dirPicker_sourcepath = wx.DirPickerCtrl( self, wx.ID_ANY, u".", u"Select a folder", wx.DefaultPosition, wx.DefaultSize, wx.DIRP_DEFAULT_STYLE )
        bSizer1.Add( self.m_dirPicker_sourcepath, 0, wx.ALL|wx.EXPAND, 5 )

        self.m_staticText_librarypath = wx.StaticText( self, wx.ID_ANY, u"Library save location:", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.m_staticText_librarypath.Wrap( -1 )

        bSizer1.Add( self.m_staticText_librarypath, 0, wx.ALL, 5 )

        self.m_dirPicker_librarypath = wx.DirPickerCtrl( self, wx.ID_ANY, u".", u"Select a folder", wx.DefaultPosition, wx.DefaultSize, wx.DIRP_DEFAULT_STYLE )
        bSizer1.Add( self.m_dirPicker_librarypath, 0, wx.ALL|wx.EXPAND, 5 )

        self.m_staticline1 = wx.StaticLine( self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL )
        self.m_staticline1.SetForegroundColour( wx.SystemSettings.GetColour( wx.SYS_COLOUR_WINDOW ) )
        self.m_staticline1.SetBackgroundColour( wx.SystemSettings.GetColour( wx.SYS_COLOUR_GRAYTEXT ) )

        bSizer1.Add( self.m_staticline1, 0, wx.EXPAND |wx.ALL, 5 )

        self.m_staticText5 = wx.StaticText( self, wx.ID_ANY, u"There is no guarantee for faultless function. Use only at your own risk. Should there be any errors please write an issue.\nNecessary settings for the integration of the libraries can be found in the README:", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.m_staticText5.Wrap( -1 )

        self.m_staticText5.SetMinSize( wx.Size( -1,50 ) )

        bSizer1.Add( self.m_staticText5, 0, wx.EXPAND|wx.TOP|wx.RIGHT|wx.LEFT, 5 )

        self.m_hyperlink = wx.adv.HyperlinkCtrl( self, wx.ID_ANY, u"github.com/Steffen-W/Import-LIB-KiCad-Plugin", u"https://github.com/Steffen-W/Import-LIB-KiCad-Plugin", wx.DefaultPosition, wx.DefaultSize, wx.adv.HL_DEFAULT_STYLE )
        bSizer1.Add( self.m_hyperlink, 0, wx.BOTTOM|wx.RIGHT|wx.LEFT, 5 )


        self.SetSizer( bSizer1 )
        self.Layout()

        self.Centre( wx.BOTH )

        # Connect Events
        self.Bind( wx.EVT_CLOSE, self.on_close )
        self.m_button.Bind( wx.EVT_BUTTON, self.BottonClick )
        self.m_dirPicker_sourcepath.Bind( wx.EVT_DIRPICKER_CHANGED, self.DirChange )
        self.m_dirPicker_librarypath.Bind( wx.EVT_DIRPICKER_CHANGED, self.DirChange )

    def __del__( self ):
        pass


    # Virtual event handlers, override them in your derived class
    def on_close( self, event ):
        event.Skip()

    def BottonClick( self, event ):
        event.Skip()

    def DirChange( self, event ):
        event.Skip()



