"""The eSMAF desktop application: window, navigation rail and status strip.

The rail is the workflow, read downwards like a soil profile: each step fills
in as it is completed, so the question "where am I and what is left?" is
answered by looking at it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from esmaf_core.models import load_model
from esmaf_core.project import SUFFIX
from esmaf_core.version import SOFTWARE_VERSION

from . import theme
from .pages.analysis import AnalysisPage
from .pages.data import DataPage
from .pages.home import HomePage, remember
from .pages.report import ReportPage
from .pages.results import ResultsPage
from .pages.setup import SetupPage
from .state import AppState

STEPS = (
    ("home", "Home"),
    ("data", "Data"),
    ("setup", "Setup"),
    ("analysis", "Analysis check"),
    ("results", "Results"),
    ("report", "Report and export"),
)

ASSETS = Path(__file__).resolve().parent / "assets"


def application_icon() -> QIcon:
    """The eSMAF mark, for the window, the task bar and the executable.

    Resolution is relative to this file, so a packaged build finds the assets
    inside _internal exactly as a source checkout finds them in the package,
    which is the same rule the crop database and the calculation models follow.
    The PNG carries an alpha channel on every platform; the ICO is the same
    image at the sizes Windows asks for, and is what PyInstaller stamps into
    eSMAF.exe.
    """
    icon = QIcon()
    for name in ("esmaf.png", "esmaf.ico"):
        path = ASSETS / name
        if path.exists():
            icon.addFile(str(path))
    return icon


def _register_windows_identity() -> None:
    """Windows groups task-bar buttons by an explicit application id.

    Without one, a packaged PySide6 application is filed under the Python
    interpreter's identity and the task bar shows the interpreter's icon
    rather than this one. Ignored on every other platform.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "esmaf.desktop")
    except Exception:
        pass


class HorizonRail(QFrame):
    """The workflow, as a sequence of horizons that fill in as work proceeds."""

    def __init__(self, on_select, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("rail")
        self.setFixedWidth(228)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel("eSMAF")
        brand.setObjectName("railBrand")
        tagline = QLabel("Soil Management\nAssessment Framework")
        tagline.setObjectName("railTagline")
        layout.addWidget(brand)
        layout.addWidget(tagline)

        self.buttons: dict[str, QPushButton] = {}
        self.bands: dict[str, QFrame] = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        for index, (key, label) in enumerate(STEPS):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)

            band = QFrame()
            band.setFixedWidth(4)
            band.setStyleSheet("background: transparent;")
            self.bands[key] = band

            button = QPushButton(f"{index + 1}   {label}")
            button.setObjectName("railStep")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _, k=key: on_select(k))
            self.group.addButton(button)
            self.buttons[key] = button

            row_layout.addWidget(band)
            row_layout.addWidget(button, 1)
            layout.addWidget(row)

        layout.addStretch(1)
        self.footer = QLabel()
        self.footer.setObjectName("railFooter")
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)

    def set_current(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def set_progress(self, done: dict[str, bool]) -> None:
        for index, (key, _) in enumerate(STEPS):
            colour = theme.HORIZONS[index % len(theme.HORIZONS)]
            self.bands[key].setStyleSheet(
                f"background: {colour};" if done.get(key)
                else "background: transparent;")

    def set_footer(self, text: str) -> None:
        self.footer.setText(text)


class StatusStrip(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statusStrip")
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(18)
        self.message = QLabel("")
        self.message.setObjectName("statusText")
        self.model = QLabel("")
        self.model.setObjectName("statusText")
        layout.addWidget(self.message, 1)
        layout.addWidget(self.model)

    def show_message(self, severity: str, text: str) -> None:
        colour = {"error": theme.ERROR, "warning": theme.WARNING,
                  "ok": theme.ACCENT}.get(severity, theme.INK_SOFT)
        self.message.setText(text)
        self.message.setStyleSheet(f"font-size:11px;color:{colour};")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = AppState()
        self.settings = QSettings("eSMAF", "eSMAF")
        self.setWindowIcon(application_icon())

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.rail = HorizonRail(self.go_to)
        self.stack = QStackedWidget()
        body_layout.addWidget(self.rail)
        body_layout.addWidget(self.stack, 1)

        self.status = StatusStrip()
        outer.addWidget(body, 1)
        outer.addWidget(self.status)

        self.pages = {
            "home": HomePage(self.state, self.go_to),
            "data": DataPage(self.state, self.go_to),
            "setup": SetupPage(self.state, self.go_to),
            "analysis": AnalysisPage(self.state, self.go_to),
            "results": ResultsPage(self.state, self.go_to),
            "report": ReportPage(self.state, self.go_to),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        self._build_menu()

        self.state.message.connect(self.status.show_message)
        for signal in (self.state.project_changed, self.state.data_changed,
                       self.state.setup_changed, self.state.result_changed):
            signal.connect(self._sync)

        self.resize(1280, 830)
        self.setMinimumSize(1020, 680)
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.go_to("home")
        self._sync()

    # --------------------------------------------------------------- menu

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self._action(file_menu, "&New project", QKeySequence.StandardKey.New,
                     lambda: (self.state.new_project(), self.go_to("data")))
        self._action(file_menu, "&Open project…", QKeySequence.StandardKey.Open,
                     self._open)
        self._action(file_menu, "&Save project", QKeySequence.StandardKey.Save,
                     self._save)
        self._action(file_menu, "Save project &as…",
                     QKeySequence.StandardKey.SaveAs, lambda: self._save(True))
        file_menu.addSeparator()
        self._action(file_menu, "&Import data…", QKeySequence("Ctrl+I"),
                     lambda: (self.go_to("data"), self.pages["data"]._browse()))
        file_menu.addSeparator()
        self._action(file_menu, "E&xit", QKeySequence.StandardKey.Quit, self.close)

        go_menu = bar.addMenu("&Go")
        for index, (key, label) in enumerate(STEPS):
            self._action(go_menu, label, QKeySequence(f"Ctrl+{index + 1}"),
                         lambda k=key: self.go_to(k))

        analysis_menu = bar.addMenu("&Analysis")
        self._action(analysis_menu, "&Calculate", QKeySequence("F5"),
                     self.pages["analysis"].run)
        self._action(analysis_menu, "Write &PDF report…", QKeySequence("Ctrl+R"),
                     lambda: (self.go_to("report"), self.pages["report"]._write_pdf()))
        self._action(analysis_menu, "Write &Excel workbook…", QKeySequence("Ctrl+E"),
                     lambda: (self.go_to("report"), self.pages["report"]._write_excel()))

        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "&About eSMAF", None, self._about)

    def _action(self, menu, label: str, shortcut, handler) -> None:
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(lambda: handler())
        menu.addAction(action)

    # ------------------------------------------------------------ commands

    def go_to(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.rail.set_current(key)
        if hasattr(page, "refresh"):
            page.refresh()

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open eSMAF project", "", f"eSMAF project (*{SUFFIX})")
        if not path:
            return
        try:
            self.state.open_project(path)
            remember(Path(path))
            self.go_to("data")
        except Exception as error:
            QMessageBox.warning(self, "Could not open the project", str(error))

    def _save(self, ask: bool = False) -> None:
        project = self.state.project
        path = project.path
        if ask or path is None:
            chosen, _ = QFileDialog.getSaveFileName(
                self, "Save project",
                str(path or f"{project.name or 'eSMAF project'}{SUFFIX}"),
                f"eSMAF project (*{SUFFIX})")
            if not chosen:
                return
            path = Path(chosen)
        try:
            saved = self.state.save_project(path)
            remember(saved)
        except Exception as error:
            QMessageBox.warning(self, "Could not save the project", str(error))

    def _about(self) -> None:
        model = load_model(self.state.project.model_id)
        QMessageBox.about(
            self, "About eSMAF",
            f"<h3>eSMAF {SOFTWARE_VERSION}</h3>"
            "<p>Electronic Soil Management Assessment Framework — a desktop "
            "implementation of SMAF (Andrews et al., 2004; Wienhold et al., "
            "2009; Stott et al., 2010).</p>"
            f"<p><b>Calculation model</b><br>{model.label}<br>"
            f"<span style='color:#5A6663'>{model.summary}</span></p>"
            "<p>Everything is computed on this computer. No measurement leaves it.</p>")

    # --------------------------------------------------------------- state

    def _sync(self) -> None:
        self.setWindowTitle(self.state.window_title)
        project = self.state.project
        steps = project.progress()
        done = {
            "home": bool(project.name),
            "data": steps[0][1],
            "setup": steps[2][1] and steps[3][1],
            "analysis": steps[4][1],
            "results": self.state.result is not None,
            "report": bool(project.history),
        }
        self.rail.set_progress(done)
        self.rail.set_footer(
            f"eSMAF {SOFTWARE_VERSION}\nModel {project.model_id}\nWorking offline")
        self.status.model.setText(
            f"model {project.model_id}   ·   "
            f"{'unsaved changes' if self.state.dirty else 'saved'}")

    def closeEvent(self, event) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        if self.state.dirty:
            answer = QMessageBox.question(
                self, "Save before closing?",
                "This project has changes that have not been saved.",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Save:
                self._save()
        event.accept()


def main() -> int:
    _register_windows_identity()
    application = QApplication(sys.argv)
    application.setApplicationName("eSMAF")
    application.setWindowIcon(application_icon())
    application.setApplicationVersion(SOFTWARE_VERSION)
    application.setOrganizationName("eSMAF")
    application.setStyleSheet(theme.stylesheet())

    window = MainWindow()
    window.show()

    if len(sys.argv) > 1 and sys.argv[1].endswith(SUFFIX):
        try:
            window.state.open_project(sys.argv[1])
            window.go_to("data")
        except Exception as error:
            QMessageBox.warning(window, "Could not open the project", str(error))

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
