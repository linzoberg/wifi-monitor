import sys
import time
import subprocess
import platform
import re
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QTextEdit, QPushButton, QLabel, QHBoxLayout,
                             QDialog, QLineEdit, QFormLayout, QDialogButtonBox,
                             QMessageBox, QSystemTrayIcon, QMenu, QAction)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QBrush

import config
from wifi_monitor import WiFiMonitor


# ─────────────────────────────────────────────
#  Генерация иконок трея
# ─────────────────────────────────────────────
def make_tray_icon(color: str) -> QIcon:
    """Рисует круглую иконку нужного цвета прямо в памяти."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.end()

    return QIcon(pixmap)


# ─────────────────────────────────────────────
#  Поток пинга
# ─────────────────────────────────────────────
class PingThread(QThread):
    """Каждые PING_INTERVAL секунд пингует 8.8.8.8 и отдаёт результат."""

    ping_result = pyqtSignal(str)

    PING_HOST     = "8.8.8.8"
    PING_INTERVAL = 5   # секунд

    def run(self):
        time.sleep(3)
        while True:
            ms = self._ping()
            if ms is None:
                self.ping_result.emit("Ping 8.8.8.8: недоступен")
            elif ms <= 1:
                # время < 1мс — признак VPN
                self.ping_result.emit("Ping 8.8.8.8: VPN is ON")
            else:
                self.ping_result.emit(f"Ping 8.8.8.8: {ms} мс")
            self.msleep(self.PING_INTERVAL * 1000)

    def _ping(self):
        system = platform.system().lower()
        cmd = (["ping", "-n", "1", "-w", "2000", self.PING_HOST]
               if system == "windows"
               else ["ping", "-c", "1", "-W", "2", self.PING_HOST])
        try:
            # Флаг CREATE_NO_WINDOW — скрывает окно консоли ping.exe
            creation_flags = 0x08000000 if system == "windows" else 0

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
                creationflags=creation_flags  # ← это скрывает окно
            )
            output = result.stdout.decode("cp866", errors="ignore")

            match = re.search(r"[Вв]ремя\s*[=<]\s*(\d+)", output)
            if not match:
                match = re.search(r"[Tt]ime[=<](\d+)", output)
            if match:
                return int(match.group(1))

            if result.returncode == 0 and re.search(r"[Вв]ремя\s*<\s*1", output):
                return 1

        except Exception:
            pass
        return None


# ─────────────────────────────────────────────
#  Поток мониторинга WiFi
# ─────────────────────────────────────────────
class MonitorThread(QThread):
    """Поток для мониторинга Wi-Fi в фоновом режиме"""

    status_signal      = pyqtSignal(str, bool)
    connection_changed = pyqtSignal(bool)

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.running = True
        self.last_status = ""
        self.last_router_check = 0
        self.router_check_interval = 300

    def run(self):
        while self.running:
            try:
                ssid_available = self.monitor.check_wifi_available()

                if ssid_available:
                    is_connected = self.monitor.get_current_connection()

                    if is_connected:
                        has_internet = self.monitor.check_internet()

                        if has_internet:
                            status = f"Подключено к {self.monitor.ssid}, интернет доступен"

                            current_time = time.time()
                            if current_time - self.last_router_check > self.router_check_interval:
                                self.last_router_check = current_time
                                self.status_signal.emit("Проверка роутера...", True)
                        else:
                            status = f"Подключено к {self.monitor.ssid}, но нет интернета"

                        self.connection_changed.emit(True)

                    else:
                        status = f"Обнаружена сеть {self.monitor.ssid}, подключаюсь..."
                        success, message = self.monitor.connect_to_wifi()

                        if success:
                            status = f"{message}"
                            self.connection_changed.emit(True)
                        else:
                            status = f"{message}"
                            self.connection_changed.emit(False)

                else:
                    status = f"Сеть {self.monitor.ssid} не обнаружена"
                    self.connection_changed.emit(False)

                status_changed = (status != self.last_status)
                self.status_signal.emit(status, status_changed)
                self.last_status = status

                self.msleep(config.CHECK_INTERVAL * 1000)

            except Exception as e:
                error_status = f"Ошибка мониторинга: {str(e)}"
                self.status_signal.emit(error_status, True)
                self.msleep(5000)

    def stop(self):
        self.running = False
        self.wait()


# ─────────────────────────────────────────────
#  Главное окно
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    """Главное окно приложения"""

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.monitor_thread = None
        self.status_history = []
        self.init_ui()
        self._init_tray()
        self._init_ping()
        self.start_monitoring()

    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(config.APP_WIDTH, config.APP_HEIGHT)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        title_label = QLabel(config.APP_TITLE)
        title_font = QFont("Arial", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Информация о сети
        info_label = QLabel(f"Мониторинг сети: {self.monitor.ssid}")
        info_label.setFont(QFont("Arial", 10))
        info_label.setStyleSheet("color: #7f8c8d; margin-bottom: 5px;")
        layout.addWidget(info_label)

        # ── Поле пинга ────────────────────────
        ping_frame = QWidget()
        ping_frame.setStyleSheet("""
            QWidget {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
            }
        """)
        ping_layout = QHBoxLayout(ping_frame)
        ping_layout.setContentsMargins(10, 6, 10, 6)

        ping_title = QLabel("Ping:")
        ping_title.setFont(QFont("Arial", 9))
        ping_title.setStyleSheet("color: #7f8c8d; border: none;")

        self.ping_label = QLabel("Ожидание...")
        self.ping_label.setFont(QFont("Arial", 9, QFont.Bold))
        self.ping_label.setStyleSheet("color: #7f8c8d; border: none;")

        ping_layout.addWidget(ping_title)
        ping_layout.addWidget(self.ping_label)
        ping_layout.addStretch()

        layout.addWidget(ping_frame)
        # ──────────────────────────────────────

        # Разделитель
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #bdc3c7;")
        layout.addWidget(line)

        # Текстовое поле лога
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setFont(QFont("Consolas", 9))
        self.status_display.setStyleSheet("""
            QTextEdit {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.status_display)

        # Кнопки
        button_layout = QHBoxLayout()

        self.start_button = QPushButton("Запуск мониторинга")
        self.start_button.clicked.connect(self.start_monitoring)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #27ae60; }
        """)

        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)

        self.clear_button = QPushButton("Очистить лог")
        self.clear_button.clicked.connect(self.clear_log)
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Статусная строка внизу
        self.bottom_status = QLabel("Готов к работе...")
        self.bottom_status.setFont(QFont("Arial", 9))
        self.bottom_status.setStyleSheet(
            "color: #7f8c8d; padding-top: 10px; border-top: 1px solid #ecf0f1;")
        layout.addWidget(self.bottom_status)

    # ── Трей ──────────────────────────────────
    def _init_tray(self):
        """Создаёт иконку в системном трее."""
        self.icon_green = make_tray_icon("#2ecc71")
        self.icon_red   = make_tray_icon("#e74c3c")

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.icon_red)
        self.tray.setToolTip("WiFi Monitor")

        tray_menu = QMenu()

        action_open = QAction("Открыть", self)
        action_open.triggered.connect(self._show_window)

        action_quit = QAction("Выход", self)
        action_quit.triggered.connect(self._quit_app)

        tray_menu.addAction(action_open)
        tray_menu.addSeparator()
        tray_menu.addAction(action_quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self):
        self.stop_monitoring()
        self.tray.hide()
        QApplication.quit()

    # ── Пинг ──────────────────────────────────
    def _init_ping(self):
        """Запускает поток пинга."""
        self.ping_thread = PingThread()
        self.ping_thread.ping_result.connect(self._on_ping_result)
        self.ping_thread.start()

    def _on_ping_result(self, message: str):
        """Обновляет только лейбл пинга, в лог не пишет."""
        if "VPN is ON" in message:
            self.ping_label.setText("VPN is ON")
            self.ping_label.setStyleSheet(
                "color: #f39c12; font-weight: bold; border: none;")
        elif "недоступен" in message:
            self.ping_label.setText("Недоступен")
            self.ping_label.setStyleSheet(
                "color: #e74c3c; font-weight: bold; border: none;")
        else:
            match = re.search(r"(\d+)\s*мс", message)
            if match:
                ms = int(match.group(1))
                color = (
                    "#27ae60" if ms < 80 else
                    "#f39c12" if ms < 200 else
                    "#e74c3c"
                )
                self.ping_label.setText(f"{ms} мс")
                self.ping_label.setStyleSheet(
                    f"color: {color}; font-weight: bold; border: none;")

    # ── Мониторинг ────────────────────────────
    def start_monitoring(self):
        if self.monitor_thread is None or not self.monitor_thread.isRunning():
            self.monitor_thread = MonitorThread(self.monitor)
            self.monitor_thread.status_signal.connect(self.update_status)
            self.monitor_thread.connection_changed.connect(self.update_connection_status)
            self.monitor_thread.start()

            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.add_status("Мониторинг запущен", True)

    def stop_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.monitor_thread = None

            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.add_status("Мониторинг остановлен", True)

    def clear_log(self):
        self.status_display.clear()
        self.status_history = []
        self.add_status("Лог очищен", True)

    def add_status(self, message, is_new_line=False):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"

        if is_new_line or not self.status_history:
            self.status_display.append(formatted_message)
            self.status_history.append(formatted_message)
        else:
            if self.status_history:
                self.status_history[-1] = formatted_message
                self.status_display.clear()
                for status in self.status_history:
                    self.status_display.append(status)

    def update_status(self, message, status_changed):
        self.add_status(message, status_changed)

        if "Подключено" in message and "интернет доступен" in message:
            self.bottom_status.setStyleSheet(
                "color: #27ae60; font-weight: bold; padding-top: 10px; border-top: 1px solid #ecf0f1;")
        elif "нет интернета" in message or "не обнаружена" in message:
            self.bottom_status.setStyleSheet(
                "color: #e74c3c; font-weight: bold; padding-top: 10px; border-top: 1px solid #ecf0f1;")
        else:
            self.bottom_status.setStyleSheet(
                "color: #7f8c8d; padding-top: 10px; border-top: 1px solid #ecf0f1;")

        self.bottom_status.setText(message)

    def update_connection_status(self, connected: bool):
        """Обновляет иконку трея при смене статуса подключения."""
        if connected:
            self.tray.setIcon(self.icon_green)
            self.tray.setToolTip(f"{self.monitor.ssid} — Подключено")
        else:
            self.tray.setIcon(self.icon_red)
            self.tray.setToolTip(f"{self.monitor.ssid} — Нет соединения")

    def closeEvent(self, event):
        """Закрытие окна → сворачиваем в трей."""
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "WiFi Monitor",
            "Приложение свёрнуто в трей. Для выхода используйте меню трея.",
            QSystemTrayIcon.Information,
            2000
        )


# ─────────────────────────────────────────────
#  Точка входа
# ─────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    dialog = QDialog()
    dialog.setWindowTitle("Настройка Wi-Fi сети")
    dialog.setFixedSize(350, 180)
    layout = QFormLayout()

    ssid_input = QLineEdit()
    password_input = QLineEdit()
    password_input.setEchoMode(QLineEdit.Password)

    layout.addRow("SSID сети:", ssid_input)
    layout.addRow("Пароль:", password_input)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)

    dialog.setLayout(layout)

    if dialog.exec_() == QDialog.Accepted:
        ssid = ssid_input.text().strip()
        password = password_input.text().strip()

        if not ssid or not password:
            QMessageBox.critical(None, "Ошибка", "SSID и пароль не могут быть пустыми!")
            sys.exit(1)

        monitor = WiFiMonitor(ssid, password)
    else:
        sys.exit(0)

    window = MainWindow(monitor)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()