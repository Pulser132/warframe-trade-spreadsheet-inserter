"""Resource-path resolution for running from source vs. as a frozen PyInstaller build.

Two path classes:
  resource_path() resolves bundled, read-only files (assets/, scripts/). When frozen,
    PyInstaller extracts these under sys._MEIPASS; when run from source, they live
    beside this file.
  user_data_path() resolves writable files (configs/, data/) that must persist across
    rebuilds and upgrades. When frozen, that's the directory containing the exe
    (sys.executable); when run from source, it's the same project directory.

The frozen/source branch is a runtime check (getattr(sys, "frozen", False)), never a
fork in behavior — both paths exist in every build.
"""

import os
import sys


def _frozen():
    return getattr(sys, "frozen", False)


def resource_path(*parts):
    """Return a path under the bundled read-only resource directory."""
    if _frozen():
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def user_data_path(*parts):
    """Return a path under the writable user-data directory."""
    if _frozen():
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)
