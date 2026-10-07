"""Desktop entry point. --smoke-test exercises the packaged application offline."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from toolkit.ui import MainWindow, STYLE


def main():
    app = QApplication(sys.argv)
    # Offscreen Qt builds do not discover Windows fonts automatically.
    # Explicit registration also keeps packaged screenshots representative.
    from PySide6.QtGui import QFontDatabase, QFont
    font_path = Path("C:/Windows/Fonts/segoeui.ttf")
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("Local Image Toolkit")
    app.setOrganizationName("LocalImageToolkit")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    if "--smoke-test" in sys.argv:
        from toolkit.smoke import run
        return run(app, Path(sys.argv[sys.argv.index("--smoke-test") + 1]))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
