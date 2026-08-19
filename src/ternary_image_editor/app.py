"""Qt application entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib import resources

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from . import __version__


def _load_application_icon() -> QIcon:
    icon_resource = resources.files("ternary_image_editor").joinpath("assets", "app_icon.png")
    try:
        icon_data = icon_resource.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Application icon could not be read: {icon_resource}") from exc

    pixmap = QPixmap()
    if not pixmap.loadFromData(icon_data, "PNG"):
        raise RuntimeError(f"Application icon is not a valid PNG: {icon_resource}")
    return QIcon(pixmap)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create the sole QApplication and attach stable settings identifiers."""

    existing = QApplication.instance()
    if existing is None:
        application = QApplication(list(argv) if argv is not None else sys.argv)
    elif isinstance(existing, QApplication):
        application = existing
    else:
        raise RuntimeError("A non-GUI QCoreApplication already exists")
    QCoreApplication.setOrganizationName("TernaryImageEditor")
    QCoreApplication.setApplicationName("TernaryImageEditor")
    QCoreApplication.setApplicationVersion(__version__)
    application.setApplicationDisplayName("三値画像修正")
    application.setWindowIcon(_load_application_icon())
    return application


def main() -> int:
    application = create_application()
    from .main_window import MainWindow

    window = MainWindow()
    window.show()
    return application.exec()
