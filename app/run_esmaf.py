#!/usr/bin/env python3
"""Launch the eSMAF desktop application.

    python run_esmaf.py              open the application
    python run_esmaf.py --selftest   check that this build computes correctly
    python run_esmaf.py --version    print the version and exit
    python run_esmaf.py study.esmaf  open a project file
"""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def main() -> int:
    args = sys.argv[1:]

    if "--selftest" in args:
        from esmaf_core.selftest import run
        return run()

    if "--version" in args or "-V" in args:
        from esmaf_core.version import SOFTWARE_VERSION, DEFAULT_MODEL_ID
        print(f"eSMAF {SOFTWARE_VERSION} (calculation model {DEFAULT_MODEL_ID})")
        return 0

    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    from esmaf_app.main import main as launch
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
