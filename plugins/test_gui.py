
# sudo apt-get install python-wxtools
from impartGUI import *

app = wx.App()
frame = impartGUI(None)
frame.Show()
app.MainLoop()
