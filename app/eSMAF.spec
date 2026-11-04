# PyInstaller build recipe for the eSMAF desktop application.
#
#   pyinstaller eSMAF.spec
#
# Produces a single directory under dist/eSMAF containing eSMAF.exe (Windows)
# or the equivalent bundle on macOS and Linux. The scientific data files are
# collected explicitly so that a packaged build reads exactly the same crop
# database and calculation models as a source checkout.

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH)
SRC = ROOT / "src"

datas = [
    (str(SRC / "esmaf_core" / "data" / "crops.csv"), "esmaf_core/data"),
    (str(SRC / "esmaf_core" / "data" / "municipalities.csv"), "esmaf_core/data"),
    (str(SRC / "esmaf_core" / "data" / "models"), "esmaf_core/data/models"),
]
datas += [(str(SRC / "esmaf_app" / "assets"), "esmaf_app/assets")]
datas += collect_data_files("reportlab")

# The window icon is read at run time from inside the package; the same file
# is stamped into the executable below.
ICON = SRC / "esmaf_app" / "assets" / "esmaf.ico"

a = Analysis(
    [str(ROOT / "run_esmaf.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=["esmaf_core", "esmaf_app"],
    hookspath=[],
    runtime_hooks=[],
    # Qt ships far more than a data application needs; dropping these keeps the
    # installer to a sensible size without touching anything eSMAF uses.
    excludes=[
        # Never imported by eSMAF. Listed explicitly because PyInstaller's
        # pandas and matplotlib hooks pull these in optimistically if they
        # happen to be installed, which made the bundle 80 MB larger on one
        # machine and left it out on another -- the build has to be the same
        # size whatever else is in the environment.
        "scipy", "lxml", "IPython", "notebook", "jupyter", "sqlalchemy",
        "pytest", "_pytest", "setuptools", "pip", "tkinter",
        "PyQt5", "PyQt6", "PySide2", "matplotlib.tests", "numpy.tests",
        "pandas.tests", "PIL.ImageQt",
        # Qt modules a data application has no use for.
        "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml",
        "PySide6.Qt3DCore", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth", "PySide6.QtNetworkAuth", "PySide6.QtNfc",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtDesigner",
        "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtPositioning",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio",
        "PySide6.QtTest", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel",
        "PySide6.QtWebSockets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="eSMAF",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no console window behind the interface
    icon=str(ICON) if ICON.exists() else None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="eSMAF",
)
