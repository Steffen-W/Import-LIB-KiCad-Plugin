import os
import sys

# add current dir to sys
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from .impart_action import ActionImpartPlugin

ActionImpartPlugin().register()
