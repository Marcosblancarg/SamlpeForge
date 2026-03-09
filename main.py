#!/usr/bin/env python3
"""
SampleForge — AI-Powered Audio Sample Manager
Entry point: sets up logging, creates QApplication, shows MainWindow.
"""
import logging
import sys
import os

# Ensure the app directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from config import APP_NAME, IS_MACOS


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy libraries
    for lib in ("urllib3", "httpx", "transformers.tokenization_utils_base"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def main():
    setup_logging()
    log = logging.getLogger(__name__)
    log.info("Starting %s …", APP_NAME)

    # High-DPI support
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("SampleForge")
    app.setStyle("Fusion")  # Consistent cross-platform base

    # macOS: hide dock icon if desired (comment out to keep)
    # if IS_MACOS:
    #     app.setProperty("NSApplicationActivationPolicy", 2)

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    log.info("UI ready.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
