from .impart_action import *

if __name__ == "__main__":
    app = wx.App()
    frame = wx.Frame(None, title="KiCad Plugin")
    Impart_t = impart_frontend()
    Impart_t.ShowModal()
    Impart_t.Destroy()
