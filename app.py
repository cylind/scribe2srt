import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow
from core.config import STYLESHEET

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())