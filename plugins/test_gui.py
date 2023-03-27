# rm *.zip; zip -r Import-LIB-KiCad-Plugin.zip plugins resources metadata.json

# sudo apt-get install python-wxtools
from impartGUI import *

app = wx.App()
frame = impartGUI(None)
frame.Show()
app.MainLoop()
