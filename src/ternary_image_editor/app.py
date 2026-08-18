"""Qt application entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from . import __version__


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create the sole QApplication and attach stable settings identifiers."""

    existing = QApplication.instance()
    if existing is not None:
        return existing
    application = QApplication(list(argv) if argv is not None else sys.argv)
    QCoreApplication.setOrganizationName("TernaryImageEditor")
    QCoreApplication.setApplicationName("TernaryImageEditor")
    QCoreApplication.setApplicationVersion(__version__)
    application.setApplicationDisplayName("三値画像修正")
    return application


def main() -> int:
    application = create_application()
    from .main_window import MainWindow

    window = MainWindow()
    window.show()
    return application.exec()
