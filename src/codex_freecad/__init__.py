"""FreeCAD modeling tools; the native engine has no third-party Python dependencies."""

import json
from pathlib import Path

_release = json.loads(Path(__file__).with_name("release.json").read_text(encoding="utf-8"))
__version__ = _release["display_version"]
__package_version__ = _release["package_version"]
