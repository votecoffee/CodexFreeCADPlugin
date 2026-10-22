"""FreeCAD's experimental host; domain operations remain in the separate SDK 2 backend."""

import json
from pathlib import Path

APPLICATION_ID = "freecad-mcp-server"
FRAMEWORK_VERSION = "0.20.0"
_release = json.loads(Path(__file__).with_name("release.json").read_text(encoding="utf-8"))
__version__ = _release["display_version"]
__package_version__ = _release["package_version"]
