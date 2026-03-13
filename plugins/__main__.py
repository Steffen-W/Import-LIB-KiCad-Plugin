import wx

from .impart_action import ImpartFrontend

if __name__ == "__main__":
    app = wx.App()
    frame = wx.Frame(None, title="KiCad Plugin")
    frontend = ImpartFrontend()
    frontend.ShowModal()
    frontend.Destroy()
