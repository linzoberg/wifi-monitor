"""
Wi-Fi Монитор — точка входа.

Следит за подключением к выбранной сети, переподключается при разрыве,
пингует 8.8.8.8 и живёт в системном трее.
"""
import sys

from PyQt5.QtWidgets import QApplication

from core.wifi import WiFiMonitor
from ui.dialogs import ask_credentials
from ui.window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    creds = ask_credentials()
    if not creds:
        sys.exit(0)

    monitor = WiFiMonitor(*creds)
    window = MainWindow(monitor)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
