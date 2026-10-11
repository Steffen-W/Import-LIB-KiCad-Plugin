import sys
import types
from pathlib import Path

PLUGINS = Path(__file__).resolve().parents[1] / "plugins"

# Register "plugins" without running its __init__.py, the KiCad entry point requiring pcbnew/wx.
_package = types.ModuleType("plugins")
_package.__path__ = [str(PLUGINS)]
sys.modules["plugins"] = _package
sys.path.insert(0, str(PLUGINS / "kiutils" / "src"))
