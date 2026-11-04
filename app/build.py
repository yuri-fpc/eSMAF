#!/usr/bin/env python3
"""Build the eSMAF desktop application.

Run it directly, or through build_windows.bat / build.sh, which are thin
wrappers that only locate Python and keep the window open afterwards.

    python build.py               build
    python build.py --notest      skip the scientific tests
    python build.py --clean       delete the build environment first
    python build.py --check       report the environment and stop
    python build.py --manifest    stamp the source into MANIFEST.sha256

Only the standard library is used here, because this script runs before
anything has been installed.

Why the build environment is not created next to this file: this folder is
typically inside OneDrive. A Python environment is tens of thousands of small
files, the sync client locks them while it uploads, and pip loses that race
partway through. The synced path is also long enough that some package files
cross the 260-character limit Windows still enforces. Both problems disappear
by building somewhere local.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_PYTHON = (3, 10)

#: import name -> name on PyPI
PACKAGES = [
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("matplotlib", "matplotlib"),
    ("openpyxl", "openpyxl"),
    ("xlsxwriter", "XlsxWriter"),
    ("reportlab", "reportlab"),
    ("PySide6", "PySide6"),
    ("pytest", "pytest"),
    ("PyInstaller", "pyinstaller"),
]

WINDOWS = os.name == "nt"

#: Every file the application needs, relative to this folder. Checked before
#: anything else runs, because a folder copied from a synced drive can arrive
#: with a file missing, and the symptom is otherwise an ImportError deep in the
#: test run that says nothing about the real cause.
REQUIRED = [
    "run_esmaf.py", "eSMAF.spec", "requirements.txt",
    "src/esmaf_core/__init__.py", "src/esmaf_core/charts.py",
    "src/esmaf_core/crops.py", "src/esmaf_core/engine.py",
    "src/esmaf_core/equations.py", "src/esmaf_core/export_excel.py",
    "src/esmaf_core/factors.py", "src/esmaf_core/importer.py",
    "src/esmaf_core/indicators.py", "src/esmaf_core/models.py",
    "src/esmaf_core/parameters.py", "src/esmaf_core/project.py",
    "src/esmaf_core/report_pdf.py", "src/esmaf_core/selftest.py",
    "src/esmaf_core/sites.py", "src/esmaf_core/units.py",
    "src/esmaf_core/validation.py", "src/esmaf_core/version.py",
    "src/esmaf_core/weights.py",
    "src/esmaf_core/data/crops.csv", "src/esmaf_core/data/municipalities.csv",
    "src/esmaf_core/data/models/esmaf-2.0.json",
    "src/esmaf_core/data/models/esmaf-1.0-legacy.json",
    "src/esmaf_app/__init__.py", "src/esmaf_app/main.py",
    "src/esmaf_app/state.py", "src/esmaf_app/theme.py",
    "src/esmaf_app/widgets.py",
    "src/esmaf_app/pages/__init__.py", "src/esmaf_app/pages/analysis.py",
    "src/esmaf_app/pages/data.py", "src/esmaf_app/pages/home.py",
    "src/esmaf_app/pages/report.py", "src/esmaf_app/pages/results.py",
    "src/esmaf_app/pages/setup.py",
    "src/esmaf_app/assets/esmaf.ico", "src/esmaf_app/assets/esmaf.png",
    "tests/test_crops.py", "tests/test_engine.py",
    "tests/test_reference_curves.py", "tests/test_report_layout.py",
    "tests/test_sites.py", "tests/test_units.py",
    "tests/test_weight_figure.py",
    "tests/test_unit_aware_checks.py",
    "tests/reference/smaf_qs_2022_curves.json",
    "tests/reference/demo_dataset.xlsx",
    "tests/reference/demo_multisite.xlsx",
    "tests/reference/demo_laudo_br.xlsx",
]


MANIFEST = "MANIFEST.sha256"


def digest(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def write_manifest(log: Log) -> int:
    """Stamp the current source, so a later copy can be checked against it."""
    missing = [name for name in REQUIRED if not (HERE / name).exists()]
    if missing:
        log("Cannot stamp an incomplete folder. Missing:")
        for name in missing:
            log(f"  {name}")
        return 1
    lines = [f"{digest(HERE / name)}  {name}" for name in REQUIRED]
    (HERE / MANIFEST).write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Wrote {MANIFEST} with {len(lines)} entries.")
    return 0


def read_manifest() -> dict[str, str]:
    path = HERE / MANIFEST
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        checksum, _, name = line.partition("  ")
        if checksum and name:
            out[name.strip()] = checksum
    return out


def check_source_is_complete(log: Log) -> bool:
    """Name what is missing or out of date, rather than letting an import fail.

    A missing file stops the build: the application cannot run without it. A
    file whose contents differ from the manifest only produces a warning,
    because you may have edited it on purpose -- but if you did not, it means
    an old copy of that file is sitting in this folder, and the failures it
    causes further down will not point here.
    """
    missing = [name for name in REQUIRED if not (HERE / name).exists()]
    empty = [name for name in REQUIRED
             if name not in missing and (HERE / name).stat().st_size == 0
             and not name.endswith("__init__.py")]

    expected = read_manifest()
    changed = [name for name in REQUIRED
               if name in expected and name not in missing
               and digest(HERE / name) != expected[name]]

    if missing or empty:
        log("")
        log("      This copy of the application is incomplete.")
        for name in missing:
            log(f"        missing   {name}")
        for name in empty:
            log(f"        empty     {name}")
        log("")
        log("      Nothing is wrong with your computer or with Python. A file")
        log("      did not arrive when this folder was copied or synchronised.")
        log("      Copy the folder again, or ask for the files listed above,")
        log("      and run this script once more.")
        return False

    if not expected:
        log(f"      all {len(REQUIRED)} source files are present")
        log(f"      ({MANIFEST} is absent, so contents were not checked)")
        return True

    if changed:
        log("")
        log(f"      All {len(REQUIRED)} files are present, but {len(changed)} "
            f"differ from {MANIFEST}:")
        for name in changed:
            log(f"        changed   {name}")
        log("")
        log("      If you edited these yourself, this is expected; re-stamp")
        log("      the folder with  build_windows.bat manifest  to silence it.")
        log("      If you did not, an out-of-date copy of these files is in")
        log("      this folder, and any test failure below starts here.")
        log("")
        return True

    log(f"      all {len(REQUIRED)} source files are present and match "
        f"{MANIFEST}")
    return True


class Log:
    """Everything goes to the console and to build_log.txt at the same time."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.handle = path.open("w", encoding="utf-8")
        except OSError:
            self.handle = None
            print(f"(could not open {path} for writing; console only)")

    def __call__(self, line: str = "") -> None:
        print(line, flush=True)
        self.write(line)

    def write(self, line: str) -> None:
        if self.handle:
            try:
                self.handle.write(line.rstrip("\n") + "\n")
                self.handle.flush()
            except OSError:
                pass

    def close(self) -> None:
        if self.handle:
            self.handle.close()


def run(command: list[str], log: Log, live: bool = False,
        cwd: Path | None = None) -> int:
    """Run a command, capturing everything into the log."""
    log.write(f"$ {' '.join(str(c) for c in command)}")
    if live:
        process = subprocess.Popen(
            command, cwd=str(cwd or HERE), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line.rstrip(), flush=True)
            log.write(line.rstrip())
        return process.wait()

    result = subprocess.run(
        command, cwd=str(cwd or HERE), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    log.write(result.stdout or "")
    return result.returncode


def build_root() -> Path:
    if WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "eSMAF-build"


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if WINDOWS else "bin/python")


def looks_synced(path: Path) -> str | None:
    markers = ("onedrive", "dropbox", "google drive", "icloud", "nextcloud", "box sync")
    lowered = str(path).lower()
    for marker in markers:
        if marker in lowered:
            return marker
    return None


def describe_environment(log: Log) -> None:
    log("Environment")
    log(f"  python            {platform.python_version()}  ({sys.executable})")
    log(f"  platform          {platform.platform()}")
    log(f"  source folder     {HERE}")
    log(f"  path length       {len(str(HERE))} characters")
    log(f"  build folder      {build_root()}")
    synced = looks_synced(HERE)
    if synced:
        log(f"  note              this folder is inside {synced}; the build")
        log( "                    environment is kept outside it on purpose")
    try:
        free = shutil.disk_usage(build_root().anchor).free / 1e9
        log(f"  free disk         {free:.1f} GB")
    except OSError:
        pass
    log("")


def ensure_python_version(log: Log) -> bool:
    if sys.version_info[:2] >= MIN_PYTHON:
        return True
    log(f"This is Python {platform.python_version()}; eSMAF needs "
        f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer.")
    log("")
    log("Install a newer Python from https://www.python.org/downloads/ and")
    log('during setup tick "Add python.exe to PATH", then run this again.')
    return False


def create_environment(venv: Path, log: Log) -> Path | None:
    python = venv_python(venv)
    if python.exists():
        log(f"      reusing the environment in {venv}")
        return python

    log("      creating it, this takes a few seconds")
    venv.parent.mkdir(parents=True, exist_ok=True)
    code = run([sys.executable, "-m", "venv", str(venv)], log)
    python = venv_python(venv)
    if code != 0 or not python.exists():
        log("      the environment could not be created; see the log")
        return None

    run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools",
         "wheel", "--disable-pip-version-check", "-q"], log)
    return python


def installed(python: Path, module: str) -> bool:
    return subprocess.run(
        [str(python), "-c", f"import {module}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def install_packages(python: Path, log: Log) -> bool:
    for module, package in PACKAGES:
        if installed(python, module):
            log(f"      {module} is already there")
            continue
        log(f"      installing {package}")
        code = run([str(python), "-m", "pip", "install", package,
                    "--disable-pip-version-check", "--no-warn-script-location"],
                   log, live=True)
        if code != 0 or not installed(python, module):
            log("")
            log(f"      COULD NOT INSTALL {package}")
            log("      capturing the full output in the log")
            run([str(python), "-m", "pip", "install", package,
                 "--disable-pip-version-check", "-v"], log)
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument("--notest", action="store_true",
                        help="skip the scientific tests")
    parser.add_argument("--clean", action="store_true",
                        help="delete the build environment first")
    parser.add_argument("--check", action="store_true",
                        help="report the environment and stop")
    parser.add_argument("--manifest", action="store_true",
                        help="stamp the current source into MANIFEST.sha256")
    # Tolerate the bare words too, so `build_windows.bat notest` works.
    known, extra = parser.parse_known_args()
    for word in extra:
        if word.lower().lstrip("-") == "notest":
            known.notest = True
        elif word.lower().lstrip("-") == "clean":
            known.clean = True
        elif word.lower().lstrip("-") == "check":
            known.check = True
        elif word.lower().lstrip("-") == "manifest":
            known.manifest = True

    log = Log(HERE / "build_log.txt")
    started = time.time()
    log(f"eSMAF build log  -  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 66)
    log("")
    if known.manifest:
        code = write_manifest(log)
        log.close()
        return code

    describe_environment(log)

    log("[0/5] Checking that the source folder is complete")
    complete = check_source_is_complete(log)
    log("")

    if known.check:
        log.close()
        return 0 if complete else 1

    if not ensure_python_version(log):
        log.close()
        return 1

    if not complete:
        return finish(log, started, ok=False)

    work = build_root()
    venv = work / "venv"

    if known.clean and work.exists():
        log(f"Removing {work}")
        shutil.rmtree(work, ignore_errors=True)

    log("[1/5] Preparing the build environment")
    python = create_environment(venv, log)
    if python is None:
        return finish(log, started, ok=False)

    log("")
    log("[2/5] Installing packages, several minutes the first time")
    if not install_packages(python, log):
        return finish(log, started, ok=False)
    log("      checking that everything imports")
    modules = ",".join(m for m, _ in PACKAGES if m != "pytest")
    if run([str(python), "-c", f"import {modules}"], log) != 0:
        log("      a package is installed but does not import; see the log")
        return finish(log, started, ok=False)
    run([str(python), "-m", "pip", "list"], log)
    log("      all packages import")

    log("")
    if known.notest:
        log("[3/5] Tests skipped at your request")
    else:
        log("[3/5] Running the scientific tests")
        if run([str(python), "-m", "pytest", "tests", "-q"], log, live=True) != 0:
            log("")
            log("      The calculation tests did not pass, so the build stopped.")
            log("      A build that does not reproduce the reference scores")
            log("      should not be distributed. To build anyway:")
            log("          build_windows.bat notest")
            return finish(log, started, ok=False)
        log("      tests passed")

        # The article states that all three verification sets run before a
        # release is packaged. Two of them live in tests/; the third is the
        # reprocessing of the published assessment, which needs the data
        # transcribed beside it and so lives one level up.
        verification = HERE.parent / "verification"
        if (verification / "check_numbers.py").exists():
            log("      reproducing the published assessment")
            for script in ("run_verification.py", "decompose.py",
                           "check_numbers.py"):
                if run([str(python), str(verification / script)], log) != 0:
                    log("")
                    log(f"      {script} did not pass, so the build stopped.")
                    log("      The published assessment is no longer")
                    log("      reproduced, which a release must not ship.")
                    return finish(log, started, ok=False)
            log("      the published assessment is reproduced")

    log("")
    log("[4/5] Packaging, a few minutes")
    code = run([str(python), "-m", "PyInstaller", "eSMAF.spec", "--noconfirm",
                "--distpath", str(work / "dist"),
                "--workpath", str(work / "temp")], log)
    application = work / "dist" / "eSMAF" / ("eSMAF.exe" if WINDOWS else "eSMAF")
    if code != 0 or not application.exists():
        log("      packaging did not produce the application; see the log")
        return finish(log, started, ok=False)
    log("      packaged")

    log("")
    log("[5/5] Checking that the packaged application computes correctly")
    if run([str(application), "--selftest"], log, live=True,
           cwd=application.parent) != 0:
        log("")
        log("      The packaged application did not reproduce the reference")
        log("      scores, so it should not be used. This usually means a data")
        log("      file did not make it into the package.")
        return finish(log, started, ok=False)

    if WINDOWS:
        make_shortcut(application, log)

    log("")
    log("=" * 66)
    log("Done.")
    log("")
    log("The application is here:")
    log(f"  {application}")
    if WINDOWS:
        log("")
        log("A shortcut named eSMAF was placed on your Desktop.")
        log("To move the application to another computer, copy the whole")
        log("eSMAF folder, not just the .exe.")
    open_folder(application.parent)
    return finish(log, started, ok=True)


def make_shortcut(application: Path, log: Log) -> None:
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    if not desktop.exists():
        return
    script = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$s = $w.CreateShortcut('{desktop / 'eSMAF.lnk'}'); "
        f"$s.TargetPath = '{application}'; "
        f"$s.WorkingDirectory = '{application.parent}'; "
        "$s.Description = 'Electronic Soil Management Assessment Framework'; "
        "$s.Save()"
    )
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", script], log)


def open_folder(folder: Path) -> None:
    try:
        if WINDOWS:
            os.startfile(str(folder))  # noqa: S606 - opening a folder we made
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
    except Exception:
        pass


def finish(log: Log, started: float, ok: bool) -> int:
    elapsed = time.time() - started
    log("")
    if ok:
        log(f"Finished in {elapsed / 60:.1f} minutes.")
    else:
        log("The build did not finish.")
        log("")
        log("Everything that happened is in:")
        log(f"  {log.path}")
        log("")
        log("Send that file over and the cause can be read directly from it.")
    log.close()
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(1)
