# main.py

import sys

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


# output emojis and UTF-8 configuration
def _harden_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _harden_stdio()

    app = QApplication(sys.argv)

    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()