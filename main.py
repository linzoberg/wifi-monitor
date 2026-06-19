import re
import subprocess
import sys
import time
from datetime import datetime
from platform import system as platform_system

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config
from wifi_monitor import WiFiMonitor


# ─────────────────────────────────────────────
#  Константы стилей (дизайн не меняем)
# ─────────────────────────────────────────────
BORDER_NONE = "border: none;"

STYLE_PING_FRAME = """
    QWidget {
        background-color: #ecf0f1;
        border: 1px solid #bdc3c7;
        border-radius: 5px;
    }
"""

STYLE_TEXT_EDIT = """
    QTextEdit {
        background-color: #ecf0f1;
        border: 1px solid #bdc3c7;
        border-radius: 5px;
        padding: 10px;
    }
"""


def button_style(bg: str, bg_hover: str) -> str:
    """Стиль для кнопок — без визуальных отличий от старого."""
    return f"""
        QPushButton {{
            background-color: {bg};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {bg_hover}; }}
    """


# Прекомпилированные regex
_RE_TIME_RU = re.compile(r"[Вв]ремя\s*[=<]\s*(\d+)")
_RE_TIME_EN = re.compile(r"[Tt]ime[=<](\d+)")
_RE_TIME_LT1 = re.compile(r"[Вв]ремя\s*<\s*1")
_RE_PING_MS = re.compile(r"(\d+)\s*мс")


# ─────────────────────────────────────────────
#  Генерация иконок трея
# ─────────────────────────────────────────────
def make_tray_icon(color: str) -> QIcon:
    """Рисует круглую иконку нужного цвета прямо в памяти."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(color)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 56, 56)
    finally:
        painter.end()

    return QIcon(pixmap)


# ─────────────────────────────────────────────
#  Поток пинга
# ─────────────────────────────────────────────
class PingThread(QThread):
    """Каждые PING_INTERVAL секунд пингует 8.8.8.8 и отдаёт результат."""

    ping_result = pyqtSignal(str)

    PING_HOST = "8.8.8.8"
    PING_INTERVAL = 5  # секунд

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._is_windows = platform_system().lower() == "windows"
        self._cmd = (
            ["ping", "-n", "1", "-w", "2000", self.PING_HOST]
            if self._is_windows
            else ["ping", "-c", "1", "-W", "2", self.PING_HOST]
        )
        self._creation_flags = 0x08000000 if self._is_windows else 0

    def stop(self):
        self._running = False
        self.wait()

    def run(self):
        # Небольшая пауза перед первым пингом
        for _ in range(30):
            if not self._running:
                return
            self.msleep(100)

        while self._running:
            ms = self._ping()
            if ms is None:
                self.ping_result.emit("Ping 8.8.8.8: недоступен")
            elif ms <= 1:
                # время < 1мс — признак VPN
                self.ping_result.emit("Ping 8.8.8.8: VPN is ON")
            else:
                self.ping_result.emit(f"Ping 8.8.8.8: {ms} мс")

            # Прерываемый sleep
            for _ in range(self.PING_INTERVAL * 10):
                if not self._running:
                    return
                self.msleep(100)

    def _ping(self):
        try:
            result = subprocess.run(
                self._cmd,
                capture_output=True,
                timeout=5,
                creationflags=self._creation_flags,
            )
            output = result.stdout.decode("cp866", errors="ignore")

            match = _RE_TIME_RU.search(output) or _RE_TIME_EN.search(output)
            if match:
                return int(match.group(1))

            if result.returncode == 0 and _RE_TIME_LT1.search(output):
                return 1
        except Exception:
            pass
        return None


# ─────────────────────────────────────────────
#  Поток мониторинга WiFi
# ─────────────────────────────────────────────
class MonitorThread(QThread):
    """Поток для мониторинга Wi-Fi в фоновом режиме."""

    status_signal = pyqtSignal(str, bool)
    connection_changed = pyqtSignal(bool)

    ROUTER_CHECK_INTERVAL = 300  # сек

    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self._running = True
        self._last_status = ""
        self._last_router_check = 0.0

    def stop(self):
        self._running = False
        self.wait()

    def run(self):
        while self._running:
            try:
                status = self._tick()
            except Exception as e:
                self.status_signal.emit(f"Ошибка мониторинга: {e}", True)
                self._interruptible_sleep(5000)
                continue

            status_changed = status != self._last_status
            self.status_signal.emit(status, status_changed)
            self._last_status = status

            self._interruptible_sleep(config.CHECK_INTERVAL * 1000)

    def _tick(self) -> str:
        if not self.monitor.check_wifi_available():
            self.connection_changed.emit(False)
            return f"Сеть {self.monitor.ssid} не обнаружена"

        if self.monitor.get_current_connection():
            self.connection_changed.emit(True)
            if self.monitor.check_internet():
                now = time.time()
                if now - self._last_router_check > self.ROUTER_CHECK_INTERVAL:
                    self._last_router_check = now
                    self.status_signal.emit("Проверка роутера...", True)
                return f"Подключено к {self.monitor.ssid}, интернет доступен"
            return f"Подключено к {self.monitor.ssid}, но нет интернета"

        # Сеть видна, но мы не подключены — пробуем подключиться
        self.status_signal.emit(
            f"Обнаружена сеть {self.monitor.ssid}, подключаюсь...", True
        )
        success, message = self.monitor.connect_to_wifi()
        self.connection_changed.emit(bool(success))
        return message

    def _interruptible_sleep(self, ms: int):
        """Sleep, который можно прервать через stop()."""
        steps = max(1, ms // 100)
        for _ in range(steps):
            if not self._running:
                return
            self.msleep(100)


# ─────────────────────────────────────────────
#  Главное окно
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    """Главное окно приложения."""

    MAX_LOG_LINES = 500

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.monitor_thread: MonitorThread | None = None
        self.ping_thread: PingThread | None = None
        self._log_count = 0

        self._init_ui()
        self._init_tray()
        self._init_ping()
        self.start_monitoring()

    # ── UI ────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(config.APP_WIDTH, config.APP_HEIGHT)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        title = QLabel(config.APP_TITLE)
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)

        # Информация о сети
        info = QLabel(f"Мониторинг сети: {self.monitor.ssid}")
        info.setFont(QFont("Arial", 10))
        info.setStyleSheet("color: #7f8c8d; margin-bottom: 5px;")
        layout.addWidget(info)

        # Поле пинга
        layout.addWidget(self._build_ping_frame())

        # Разделитель
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #bdc3c7;")
        layout.addWidget(line)

        # Лог
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setFont(QFont("Consolas", 9))
        self.status_display.setStyleSheet(STYLE_TEXT_EDIT)
        layout.addWidget(self.status_display)

        # Кнопки
        layout.addLayout(self._build_buttons())

        # Статусная строка
        self.bottom_status = QLabel("Готов к работе...")
        self.bottom_status.setFont(QFont("Arial", 9))
        self.bottom_status.setStyleSheet(
            "color: #7f8c8d; padding-top: 10px; border-top: 1px solid #ecf0f1;"
        )
        layout.addWidget(self.bottom_status)

    def _build_ping_frame(self) -> QWidget:
        frame = QWidget()
        frame.setStyleSheet(STYLE_PING_FRAME)

        ping_layout = QHBoxLayout(frame)
        ping_layout.setContentsMargins(10, 6, 10, 6)

        ping_title = QLabel("Ping:")
        ping_title.setFont(QFont("Arial", 9))
        ping_title.setStyleSheet(f"color: #7f8c8d; {BORDER_NONE}")

        self.ping_label = QLabel("Ожидание...")
        self.ping_label.setFont(QFont("Arial", 9, QFont.Bold))
        self.ping_label.setStyleSheet(f"color: #7f8c8d; {BORDER_NONE}")

        ping_layout.addWidget(ping_title)
        ping_layout.addWidget(self.ping_label)
        ping_layout.addStretch()
        return frame

    def _build_buttons(self) -> QHBoxLayout:
        self.start_button = QPushButton("Запуск мониторинга")
        self.start_button.clicked.connect(self.start_monitoring)
        self.start_button.setStyleSheet(button_style("#2ecc71", "#27ae60"))

        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.stop_button.setStyleSheet(button_style("#e74c3c", "#c0392b"))

        self.clear_button = QPushButton("Очистить лог")
        self.clear_button.clicked.connect(self.clear_log)
        self.clear_button.setStyleSheet(button_style("#3498db", "#2980b9"))

        row = QHBoxLayout()
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.clear_button)
        row.addStretch()
        return row

    # ── Трей ──────────────────────────────────
    def _init_tray(self):
        self.icon_green = make_tray_icon("#2ecc71")
        self.icon_red = make_tray_icon("#e74c3c")

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.icon_red)
        self.tray.setToolTip("WiFi Monitor")

        menu = QMenu()

        action_open = QAction("Открыть", self)
        action_open.triggered.connect(self._show_window)

        action_quit = QAction("Выход", self)
        action_quit.triggered.connect(self._quit_app)

        menu.addAction(action_open)
        menu.addSeparator()
        menu.addAction(action_quit)

        self.tray.setContextMenu(menu)
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
        if self.ping_thread:
            self.ping_thread.stop()
        self.tray.hide()
        QApplication.quit()

    # ── Пинг ──────────────────────────────────
    def _init_ping(self):
        self.ping_thread = PingThread(self)
        self.ping_thread.ping_result.connect(self._on_ping_result)
        self.ping_thread.start()

    def _on_ping_result(self, message: str):
        """Обновляет только лейбл пинга, в лог не пишет."""
        if "VPN is ON" in message:
            self._set_ping_label("VPN is ON", "#f39c12")
            return
        if "недоступен" in message:
            self._set_ping_label("Недоступен", "#e74c3c")
            return

        match = _RE_PING_MS.search(message)
        if not match:
            return

        ms = int(match.group(1))
        color = "#27ae60" if ms < 80 else "#f39c12" if ms < 200 else "#e74c3c"
        self._set_ping_label(f"{ms} мс", color)

    def _set_ping_label(self, text: str, color: str):
        self.ping_label.setText(text)
        self.ping_label.setStyleSheet(
            f"color: {color}; font-weight: bold; {BORDER_NONE}"
        )

    # ── Мониторинг ────────────────────────────
    def start_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            return

        self.monitor_thread = MonitorThread(self.monitor, self)
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
        self._log_count = 0
        self.add_status("Лог очищен", True)

    # ── Лог ──────────────────────────────────
    def add_status(self, message: str, is_new_line: bool = False):
        """
        Дописывает строку в лог. Если is_new_line=False — заменяет последнюю
        строку на новую (без полной перерисовки виджета).
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"

        if is_new_line or self._log_count == 0:
            self.status_display.append(formatted)
            self._log_count += 1
            self._trim_log_if_needed()
            return

        # Заменить последнюю строку — без полной перерисовки
        cursor = self.status_display.textCursor()
        cursor.movePosition(cursor.End)
        cursor.select(cursor.LineUnderCursor)
        cursor.removeSelectedText()
        cursor.insertText(formatted)

    def _trim_log_if_needed(self):
        """Подрезаем лог, чтобы не разрастался бесконечно."""
        if self._log_count <= self.MAX_LOG_LINES:
            return

        excess = self._log_count - self.MAX_LOG_LINES
        cursor = self.status_display.textCursor()
        cursor.movePosition(cursor.Start)
        cursor.movePosition(cursor.Down, cursor.KeepAnchor, excess)
        cursor.removeSelectedText()
        self._log_count = self.MAX_LOG_LINES

    def update_status(self, message: str, status_changed: bool):
        self.add_status(message, status_changed)

        if "Подключено" in message and "интернет доступен" in message:
            color, weight = "#27ae60", "bold"
        elif "нет интернета" in message or "не обнаружена" in message:
            color, weight = "#e74c3c", "bold"
        else:
            color, weight = "#7f8c8d", "normal"

        self.bottom_status.setStyleSheet(
            f"color: {color}; font-weight: {weight}; "
            f"padding-top: 10px; border-top: 1px solid #ecf0f1;"
        )
        self.bottom_status.setText(message)

    def update_connection_status(self, connected: bool):
        """Обновляет иконку трея при смене статуса подключения."""
        if connected:
            self.tray.setIcon(self.icon_green)
            self.tray.setToolTip(f"{self.monitor.ssid} — Подключено")
        else:
            self.tray.setIcon(self.icon_red)
            self.tray.setToolTip(f"{self.monitor.ssid} — Нет соединения")

    # ── Закрытие ──────────────────────────────
    def closeEvent(self, event):
        """Закрытие окна → сворачиваем в трей."""
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "WiFi Monitor",
            "Приложение свёрнуто в трей. Для выхода используйте меню трея.",
            QSystemTrayIcon.Information,
            2000,
        )


# ─────────────────────────────────────────────
#  Диалог настройки сети
# ─────────────────────────────────────────────
def ask_credentials() -> tuple[str, str] | None:
    """Показывает диалог ввода SSID/пароля. Возвращает (ssid, password) или None."""
    dialog = QDialog()
    dialog.setWindowTitle("Настройка Wi-Fi сети")
    dialog.setFixedSize(350, 180)

    layout = QFormLayout(dialog)

    ssid_input = QLineEdit()
    password_input = QLineEdit()
    password_input.setEchoMode(QLineEdit.Password)

    layout.addRow("SSID сети:", ssid_input)
    layout.addRow("Пароль:", password_input)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)

    if dialog.exec_() != QDialog.Accepted:
        return None

    ssid = ssid_input.text().strip()
    password = password_input.text().strip()

    if not ssid or not password:
        QMessageBox.critical(None, "Ошибка", "SSID и пароль не могут быть пустыми!")
        return None

    return ssid, password


# ─────────────────────────────────────────────
#  Точка входа
# ─────────────────────────────────────────────
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
