import pcbnew
import os.path
import wx
from time import sleep
from threading import Thread

if __name__ == "__main__":
    from impart_gui import impartGUI
    from KiCadImport import import_lib
    from impart_helper_func import filehandler, config_handler
else:
    # relative import is required in kicad
    from .impart_gui import impartGUI
    from .KiCadImport import import_lib
    from .impart_helper_func import filehandler, config_handler


EVT_UPDATE_ID = wx.NewId()


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
        while (not self.stopThread):
            if lenStr != len(backend_h.print_buffer):
                self.report(backend_h.print_buffer)
                lenStr = len(backend_h.print_buffer)
            sleep(0.5)

    def report(self, status):
        wx.PostEvent(self.wxObject, ResultEvent(status))


class impart_backend():
    importer = import_lib()

    def __init__(self):
        path2config = os.path.join(os.path.dirname(__file__), 'config.ini')
        self.config = config_handler(path2config)
        self.runThread = False
        self.autoImport = False
        self.overwriteImport = False
        self.folderhandler = filehandler('.')
        self.print_buffer = ""
        self.importer.print = self.print2buffer

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
                    res, = self.importer.import_all(
                        lib, overwrite_if_exists=self.overwriteImport)
                    self.print2buffer(res)
                except Exception as e:
                    self.print2buffer(e)
                self.print2buffer("")

            if not self.runThread:
                break
            if not pcbnew.GetBoard():
                # print("pcbnew close")
                break
            sleep(1)


backend_h = impart_backend()


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

        if backend_h.runThread:
            self.m_button.Label = "automatic import / press to stop"
        else:
            self.m_button.Label = "Start"

        EVT_UPDATE(self, self.updateDisplay)
        self.Thread = PluginThread(self)  # only for text output

    def updateDisplay(self, status):
        self.m_text.SetValue(status.data)

    # def print(self, text):
    #     self.m_text.AppendText(str(text)+"\n")

    def on_close(self, event):
        if backend_h.runThread:
            dlg = wx.MessageDialog(
                None,
                "The automatic import process continues in the background. " +
                "If this is not desired, it must be stopped.\n" +
                "As soon as the PCB Editor window is closed, the import process also ends.",
                "WARNING: impart background process",
                wx.KILL_OK | wx.ICON_WARNING)
            if dlg.ShowModal() != wx.ID_OK:
                return

        backend_h.autoImport = self.m_autoImport.IsChecked()
        backend_h.overwriteImport = self.m_overwrite.IsChecked()
        # backend_h.runThread = False
        self.Thread.stopThread = True  # only for text output
        event.Skip()

    def BottonClick(self, event):
        backend_h.importer.set_DEST_PATH(backend_h.config.get_DEST_PATH())

        backend_h.autoImport = self.m_autoImport.IsChecked()
        backend_h.overwriteImport = self.m_overwrite.IsChecked()

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
        event.Skip()

    def DirChange(self, event):
        backend_h.config.set_SRC_PATH(self.m_dirPicker_sourcepath.GetPath())
        backend_h.config.set_DEST_PATH(self.m_dirPicker_librarypath.GetPath())
        event.Skip()


class ActionImpartPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.set_LOGO()

    def set_LOGO(self, is_red=False):
        self.name = "impartGUI"
        self.category = "Import library files"
        self.description = "Import library files from Octopart, Samacsys, Ultralibrarian and Snapeda"
        self.show_toolbar_button = True

        if not is_red:
            self.icon_file_name = os.path.join(
                os.path.dirname(__file__), 'icon_small.png')
        else:
            self.icon_file_name = os.path.join(
                os.path.dirname(__file__), 'icon_small_red.png')
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
