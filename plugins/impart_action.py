import pcbnew
import os.path
import wx
from time import sleep
from threading import Thread
import sys
import traceback

if __name__ == "__main__":
    from impart_gui import impartGUI
    from KiCadImport import import_lib
    from impart_helper_func import filehandler, config_handler, KiCad_Settings
    from impart_migration import find_old_lib_files, convert_lib_list
else:
    # relative import is required in kicad
    from .impart_gui import impartGUI
    from .KiCadImport import import_lib
    from .impart_helper_func import filehandler, config_handler, KiCad_Settings
    from .impart_migration import find_old_lib_files, convert_lib_list


EVT_UPDATE_ID = wx.NewIdRef()


def EVT_UPDATE(win, func):
    win.Connect(-1, -1, EVT_UPDATE_ID, func)


class ResultEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_UPDATE_ID)
        self.data = data


class PluginThread(Thread):
    def __init__(self, wxObject):
        Thread.__init__(self)
        self.wxObject = wxObject
        self.stopThread = False
        self.start()

    def run(self):
        lenStr = 0
        global backend_h
        while not self.stopThread:
            if lenStr != len(backend_h.print_buffer):
                self.report(backend_h.print_buffer)
                lenStr = len(backend_h.print_buffer)
            sleep(0.5)

    def report(self, status):
        wx.PostEvent(self.wxObject, ResultEvent(status))


additional_information = (
    "Important information: "
    + "\nIf you have already used the previous version of the plugin, you should "
    + "note that the current version only supports the current library file format. "
    + "If this plugin is being used for the first time, settings in KiCad are required. "
    + "The settings are checked at the end of the import process. For easy setup, "
    + "auto setting can be activated."
)


class impart_backend:
    importer = import_lib()

    def __init__(self):
        path2config = os.path.join(os.path.dirname(__file__), "config.ini")
        self.config = config_handler(path2config)
        path_seting = pcbnew.SETTINGS_MANAGER().GetUserSettingsPath()
        self.KiCad_Settings = KiCad_Settings(path_seting)
        self.runThread = False
        self.autoImport = False
        self.overwriteImport = False
        self.import_old_format = False
        self.autoLib = False
        self.folderhandler = filehandler(".")
        self.print_buffer = ""
        self.importer.print = self.print2buffer

        if not self.config.config_is_set:
            self.print2buffer(
                "Warning: The path where the libraries should be saved has not been adjusted yet."
                + " Maybe you use the plugin in this version for the first time.\n\n"
            )
            self.print2buffer(additional_information)
            self.print2buffer("\n##############################\n")

    def print2buffer(self, text):
        self.print_buffer = self.print_buffer + str(text) + "\n"

    def __find_new_file__(self):
        path = self.config.get_SRC_PATH()

        if not os.path.isdir(path):
            return 0

        while True:
            newfilelist = self.folderhandler.GetNewFiles(path)
            for lib in newfilelist:
                try:
                    (res,) = self.importer.import_all(
                        lib,
                        overwrite_if_exists=self.overwriteImport,
                        import_old_format=self.import_old_format,
                    )
                    self.print2buffer(res)
                except Exception as e:
                    self.print2buffer(e)
                    backend_h.print2buffer(f"Error: {e}")
                    backend_h.print2buffer("Python version " + sys.version)
                    print(traceback.format_exc())
                self.print2buffer("")

            if not self.runThread:
                break
            if not pcbnew.GetBoard():
                # print("pcbnew close")
                break
            sleep(1)


backend_h = impart_backend()


def checkImport(add_if_possible=True):
    libnames = ["Octopart", "Samacsys", "UltraLibrarian", "Snapeda", "EasyEDA"]
    setting = backend_h.KiCad_Settings
    DEST_PATH = backend_h.config.get_DEST_PATH()

    msg = ""
    msg += setting.check_GlobalVar(DEST_PATH, add_if_possible)

    for name in libnames:
        # The lines work but old libraries should not be added automatically
        # libname = os.path.join(DEST_PATH, name + ".lib")
        # if os.path.isfile(libname):
        #     msg += setting.check_symbollib(name + ".lib", add_if_possible)

        libdir = os.path.join(DEST_PATH, name + ".kicad_sym")
        libdir_old = os.path.join(DEST_PATH, name + "_kicad_sym.kicad_sym")
        if os.path.isfile(libdir):
            libname = name + ".kicad_sym"
            msg += setting.check_symbollib(libname, add_if_possible)
        elif os.path.isfile(libdir_old):
            libname = name + "_kicad_sym.kicad_sym"
            msg += setting.check_symbollib(libname, add_if_possible)

        libdir = os.path.join(DEST_PATH, name + ".pretty")
        if os.path.isdir(libdir):
            msg += setting.check_footprintlib(name, add_if_possible)
    return msg


class impart_frontend(impartGUI):
    global backend_h

    def __init__(self, board, action):
        super(impart_frontend, self).__init__(None)
        self.board = board
        self.action = action

        self.m_dirPicker_sourcepath.SetPath(backend_h.config.get_SRC_PATH())
        self.m_dirPicker_librarypath.SetPath(backend_h.config.get_DEST_PATH())

        self.m_autoImport.SetValue(backend_h.autoImport)
        self.m_overwrite.SetValue(backend_h.overwriteImport)
        self.m_check_autoLib.SetValue(backend_h.autoLib)
        self.m_check_import_all.SetValue(backend_h.import_old_format)

        if backend_h.runThread:
            self.m_button.Label = "automatic import / press to stop"
        else:
            self.m_button.Label = "Start"

        EVT_UPDATE(self, self.updateDisplay)
        self.Thread = PluginThread(self)  # only for text output

        self.test_migrate_possible()

    def updateDisplay(self, status):
        self.m_text.SetValue(status.data)
        self.m_text.SetInsertionPointEnd()

    # def print(self, text):
    #     self.m_text.AppendText(str(text)+"\n")

    def on_close(self, event):
        if backend_h.runThread:
            dlg = wx.MessageDialog(
                None,
                "The automatic import process continues in the background. "
                + "If this is not desired, it must be stopped.\n"
                + "As soon as the PCB Editor window is closed, the import process also ends.",
                "WARNING: impart background process",
                wx.KILL_OK | wx.ICON_WARNING,
            )
            if dlg.ShowModal() != wx.ID_OK:
                return

        backend_h.autoImport = self.m_autoImport.IsChecked()
        backend_h.overwriteImport = self.m_overwrite.IsChecked()
        backend_h.autoLib = self.m_check_autoLib.IsChecked()
        backend_h.import_old_format = self.m_check_import_all.IsChecked()
        # backend_h.runThread = False
        self.Thread.stopThread = True  # only for text output
        event.Skip()

    def BottonClick(self, event):
        backend_h.importer.set_DEST_PATH(backend_h.config.get_DEST_PATH())

        backend_h.autoImport = self.m_autoImport.IsChecked()
        backend_h.overwriteImport = self.m_overwrite.IsChecked()
        backend_h.autoLib = self.m_check_autoLib.IsChecked()
        backend_h.import_old_format = self.m_check_import_all.IsChecked()

        if backend_h.runThread:
            backend_h.runThread = False
            self.m_button.Label = "Start"
            return

        backend_h.runThread = False
        backend_h.__find_new_file__()
        self.m_button.Label = "Start"

        if backend_h.autoImport:
            backend_h.runThread = True
            self.m_button.Label = "automatic import / press to stop"
            x = Thread(target=backend_h.__find_new_file__, args=[])
            x.start()

        add_if_possible  = self.m_check_autoLib.IsChecked()
        msg = checkImport(add_if_possible)
        if msg:
            msg += "\n\nMore information can be found in the README for the integration into KiCad.\n"
            msg += "github.com/Steffen-W/Import-LIB-KiCad-Plugin"
            msg += "\nSome configurations require a KiCad restart to be detected correctly."

            dlg = wx.MessageDialog(None, msg, "WARNING", wx.KILL_OK | wx.ICON_WARNING)

            if dlg.ShowModal() != wx.ID_OK:
                return

            backend_h.print2buffer("\n##############################\n")
            # backend_h.print2buffer(additional_information)
            backend_h.print2buffer(msg)
            backend_h.print2buffer("\n##############################\n")
        event.Skip()

    def DirChange(self, event):
        backend_h.config.set_SRC_PATH(self.m_dirPicker_sourcepath.GetPath())
        backend_h.config.set_DEST_PATH(self.m_dirPicker_librarypath.GetPath())
        backend_h.folderhandler.filelist = []
        self.test_migrate_possible()
        event.Skip()

    def ButtomManualImport(self, event):
        try:
            from impart_easyeda import easyeda2kicad_wrapper

            component_id = self.m_textCtrl2.GetValue().strip()  # example: "C2040"
            overwrite = self.m_overwrite.IsChecked()
            backend_h.print2buffer("")
            backend_h.print2buffer(
                "Try to import EeasyEDA /  LCSC Part# : " + component_id
            )
            base_folder = (
                backend_h.config.get_DEST_PATH()
            )  # "~/Documents/Kicad/easyeda"
            easyeda_import = easyeda2kicad_wrapper()
            easyeda_import.print = backend_h.print2buffer
            easyeda_import.full_import(component_id, base_folder, overwrite)
            event.Skip()
        except Exception as e:
            backend_h.print2buffer(f"Error: {e}")
            backend_h.print2buffer("Python version " + sys.version)
            print(traceback.format_exc())

    def get_old_libfiles(self):
        libpath = self.m_dirPicker_librarypath.GetPath()
        libs = ["Octopart", "Samacsys", "UltraLibrarian", "Snapeda", "EasyEDA"]
        return find_old_lib_files(folder_path=libpath, libs=libs)

    def test_migrate_possible(self):
        libs2migrate = self.get_old_libfiles()
        conv = convert_lib_list(libs2migrate, drymode=True)

        if len(conv):
            self.m_button_migrate.Show()
        else:
            self.m_button_migrate.Hide()

    def migrate_libs(self, event):
        libs2migrate = self.get_old_libfiles()

        conv = convert_lib_list(libs2migrate, drymode=True)

        msg = "Current dry mode without changes:\n"
        for line in conv:
            msg += line + "\n"
        msg = "\nShould the changes be applied? Backup files are also created automatically."

        if conv:
            dlg = wx.MessageDialog(
                None, msg, "WARNING", wx.KILL_OK | wx.ICON_WARNING | wx.CANCEL
            )
            if dlg.ShowModal() == wx.ID_OK:
                backend_h.print2buffer("convert_lib_list")
                conv = convert_lib_list(libs2migrate, drymode=False)
                for line in conv:
                    backend_h.print2buffer(line)
                backend_h.print2buffer("TODO: need to update KiCad Settings")  # TODO
                backend_h.print2buffer("##############################")

        self.test_migrate_possible()

        event.Skip()


class ActionImpartPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.set_LOGO()

        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.append(current_dir)

    def set_LOGO(self, is_red=False):
        self.name = "impartGUI"
        self.category = "Import library files"
        self.description = "Import library files from Octopart, Samacsys, Ultralibrarian, Snapeda and EasyEDA"
        self.show_toolbar_button = True

        if not is_red:
            self.icon_file_name = os.path.join(
                os.path.dirname(__file__), "icon_small.png"
            )
        else:
            self.icon_file_name = os.path.join(
                os.path.dirname(__file__), "icon_small_red.png"
            )
        self.dark_icon_file_name = self.icon_file_name

    def Run(self):
        global backend_h
        board = pcbnew.GetBoard()
        Impart_h = impart_frontend(board, self)
        Impart_h.ShowModal()
        Impart_h.Destroy()
        self.set_LOGO(is_red=backend_h.runThread)  # not yet working


if __name__ == "__main__":
    app = wx.App()
    frame = wx.Frame(None, title="KiCad Plugin")
    Impart_t = impart_frontend(None, None)
    Impart_t.ShowModal()
    Impart_t.Destroy()
