"""Главное окно приложения и системный трей."""
import re
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import settings
from core.wifi import WiFiMonitor
from core.workers import MonitorThread, PingThread
from ui.dialogs import ask_prefs
from ui.icons import make_tray_icon
from ui.styles import (
    APP_HEIGHT,
    APP_TITLE,
    APP_WIDTH,
    BORDER_NONE,
    STYLE_BOTTOM_BASE,
    STYLE_PING_FRAME,
    STYLE_TEXT_EDIT,
    button_style,
)

# Regex для парсинга миллисекунд из строки пинга, приходящей из PingThread
_RE_PING_MS = re.compile(r"(\d+)\s*мс")


# ─────────────────────────────────────────────
#  Главное окно
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    MAX_LOG_LINES = 500

    def __init__(self, monitor: WiFiMonitor):
        super().__init__()
        self.monitor = monitor
        self.prefs = settings.load_prefs()
        # Сразу применяем IP роутера из пользовательских настроек
        self.monitor.router_ip = self.prefs.router_ip

        self.monitor_thread: MonitorThread | None = None
        self.ping_thread: PingThread | None = None
        self._log_count = 0
        self._last_log_message = ""  # для дедупликации повторяющихся строк

        self._init_ui()
        self._init_tray()
        self._init_ping()
        self.start_monitoring()

    # ── UI ────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(APP_WIDTH, APP_HEIGHT)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        title = QLabel(APP_TITLE)
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
        self._set_bottom_status_style("#7f8c8d", "normal")
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

        self.settings_button = QPushButton("Настройки")
        self.settings_button.clicked.connect(self._open_settings)
        self.settings_button.setStyleSheet(button_style("#95a5a6", "#7f8c8d"))

        row = QHBoxLayout()
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.clear_button)
        row.addWidget(self.settings_button)
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
            self.ping_thread = None
        self.tray.hide()
        QApplication.quit()

    def _on_autostart_toggled(self, checked: bool):
        if settings.set_autostart(checked):
            return
        QMessageBox.warning(
            self,
            "Автозапуск",
            "Не удалось обновить настройку автозапуска.",
        )
        self.autostart_checkbox.blockSignals(True)
        self.autostart_checkbox.setChecked(not checked)
        self.autostart_checkbox.blockSignals(False)

    # ── Пинг ──────────────────────────────────
    def _init_ping(self):
        self.ping_thread = PingThread(self.prefs.ping_interval, self)
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
        if ms < 80:
            color = "#27ae60"
        elif ms < 200:
            color = "#f39c12"
        else:
            color = "#e74c3c"
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

        self.monitor_thread = MonitorThread(self.monitor, self.prefs.check_interval, self)
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

    # ── Настройки ─────────────────────────────
    def _open_settings(self):
        new_prefs = ask_prefs(self, self.prefs)
        if new_prefs is None:
            return

        old = self.prefs
        self.prefs = new_prefs
        settings.save_prefs(new_prefs)

        # IP роутера применяем немедленно
        self.monitor.router_ip = new_prefs.router_ip

        # Перезапускаем только те потоки, у которых сменился интервал
        if new_prefs.check_interval != old.check_interval and self.monitor_thread:
            self.stop_monitoring()
            self.start_monitoring()

        if new_prefs.ping_interval != old.ping_interval and self.ping_thread:
            self.ping_thread.stop()
            self._init_ping()

        self.add_status(
            f"Настройки обновлены: проверка {new_prefs.check_interval} с, "
            f"пинг {new_prefs.ping_interval} с",
            True,
        )

    # ── Лог ──────────────────────────────────
    def add_status(self, message: str, is_new_line: bool = False):
        """
        Добавляет строку в лог. Если is_new_line=False, заменяет последнюю строку
        новой (без полной перерисовки виджета).

        Дедупликация: если новое сообщение идентично последнему — просто
        обновляем время в существующей строке, новую не добавляем.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"

        # Дедупликация: повтор последнего — только обновляем timestamp
        if message == self._last_log_message and self._log_count > 0:
            cursor = self.status_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.select(QTextCursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.insertText(formatted)
            return

        if is_new_line or self._log_count == 0:
            self.status_display.append(formatted)
            self._log_count += 1
            self._last_log_message = message
            self._trim_log_if_needed()
            return

        cursor = self.status_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.LineUnderCursor)
        cursor.removeSelectedText()
        cursor.insertText(formatted)
        self._last_log_message = message

    def _trim_log_if_needed(self):
        if self._log_count <= self.MAX_LOG_LINES:
            return

        excess = self._log_count - self.MAX_LOG_LINES
        cursor = self.status_display.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, excess)
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

        self._set_bottom_status_style(color, weight)
        self.bottom_status.setText(message)

    def _set_bottom_status_style(self, color: str, weight: str):
        self.bottom_status.setStyleSheet(
            f"color: {color}; font-weight: {weight}; {STYLE_BOTTOM_BASE}"
        )

    def update_connection_status(self, connected: bool):
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
