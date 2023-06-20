import pcbnew
import os
import os.path
import wx
import time
import threading

if __name__ == "__main__":
    from impart_gui import impartGUI
    from KiCadImport import import_lib
    from impart_helper_func import filehandler, config_handler
else:
    # relative import is required in kicad
    from .impart_gui import impartGUI
    from .KiCadImport import import_lib
    from .impart_helper_func import filehandler, config_handler


class ImpartPlugin(impartGUI):

    importer = import_lib()

    def __init__(self, board, action):
        super(ImpartPlugin, self).__init__(None)
        self.board = board
        self.action = action

        path2config = os.path.join(os.path.dirname(__file__), 'config.ini')
        self.config = config_handler(path2config)
        self.m_dirPicker_sourcepath.SetPath(self.config.get_SRC_PATH())
        self.m_dirPicker_librarypath.SetPath(self.config.get_DEST_PATH())

        self.m_button.Label = "Start"
        self.runThread = False
        self.folderhandler = filehandler('.')

    def __find_new_file__(self, path='.'):
        if not os.path.isdir(path):
            return 0

        self.importer.print = self.print2buffer

        while True:
            self.print_buffer = ""
            newfilelist = self.folderhandler.GetNewFiles(path)
            for lib in newfilelist:
                try:
                    res, = self.importer.import_all(
                        lib, overwrite_if_exists=self.m_overwrite.IsChecked())
                    self.print2buffer(res)
                except Exception as e:
                    self.print2buffer(e)

                if not self.runThread and self.print_buffer != "":
                    self.print(self.print_buffer)
                    self.print_buffer = ""

            if not self.runThread:
                break
            if self.print_buffer != "":
                self.print(self.print_buffer)
            time.sleep(1)

    def print2buffer(self, text):
        self.print_buffer = self.print_buffer + str(text) + "\n"

    def print(self, text):
        self.m_text.AppendText(str(text)+"\n")

    def on_close(self, event):
        self.runThread = False
        event.Skip()

    def BottonClick(self, event):
        self.importer.set_DEST_PATH(self.config.get_DEST_PATH())
        self.importer.print = self.print

        if self.runThread:
            self.runThread = False
            self.m_button.Label = "Start"
            return

        self.runThread = False
        self.__find_new_file__(self.config.get_SRC_PATH())
        self.m_button.Label = "Start"

        if self.m_autoImport.IsChecked():
            self.runThread = True
            self.m_button.Label = "automatic import / press to stop"
            x = threading.Thread(target=self.__find_new_file__, args=(
                self.config.get_SRC_PATH(),))
            x.start()

        event.Skip()
        event.Skip()

    def DirChange(self, event):
        self.config.set_SRC_PATH(self.m_dirPicker_sourcepath.GetPath())
        self.config.set_DEST_PATH(self.m_dirPicker_librarypath.GetPath())
        event.Skip()


class ActionImpartPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "impartGUI"  # + __version__
        self.category = "Import library files"
        self.description = "Import library files from Octopart, Samacsys, Ultralibrarian and Snapeda"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(
            os.path.dirname(__file__), 'icon_small.png')
        self.dark_icon_file_name = os.path.join(
            os.path.dirname(__file__), 'icon_small.png')

    def Run(self):
        board = pcbnew.GetBoard()
        Impart_h = ImpartPlugin(board, self)
        Impart_h.ShowModal()
        Impart_h.Destroy()
        pcbnew.Refresh()


if __name__ == "__main__":
    app = wx.App()
    frame = wx.Frame(None, title="KiCad Plugin")
    Impart_t = ImpartPlugin(None, None)
    Impart_t.ShowModal()
    Impart_t.Destroy()
