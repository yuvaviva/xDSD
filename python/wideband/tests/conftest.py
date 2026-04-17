"""Pytest configuration: isolate dsd.wideband from the Python-2-era dsd/__init__.py.

The existing `python/__init__.py` in this repo predates Python 3 and has
tab/space inconsistencies that make it unimportable on Python 3. For the
wideband subpackage tests we replace the parent module with a bare stub that
still points at the right filesystem location.
"""

from __future__ import annotations

import os
import sys
import types


def _install_dsd_stub() -> None:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # `here` == /.../python
    if "dsd" in sys.modules and hasattr(sys.modules["dsd"], "__path__"):
        return
    pkg = types.ModuleType("dsd")
    pkg.__path__ = [here]
    sys.modules["dsd"] = pkg


_install_dsd_stub()
