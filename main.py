import sys
import time
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QTextEdit, QPushButton, QLabel, QHBoxLayout,
                             QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont

import config
from wifi_monitor import WiFiMonitor  # Теперь безопасно — нет обратного импорта


class MonitorThread(QThread):
    """Поток для мониторинга Wi-Fi в фоновом режиме"""

    status_signal = pyqtSignal(str, bool)  # текст статуса, изменился ли статус
    connection_changed = pyqtSignal(bool)  # состояние подключения

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.running = True
        self.last_status = ""
        self.last_router_check = 0
        self.router_check_interval = 300  # 5 минут

    def run(self):
        """Основной цикл потока мониторинга"""
        while self.running:
            try:
                # 1. Проверяем, доступна ли наша сеть
                ssid_available = self.monitor.check_wifi_available()

                if ssid_available:
                    # 2. Проверяем, подключены ли мы к ней
                    is_connected = self.monitor.get_current_connection()

                    if is_connected:
                        # Проверяем интернет
                        has_internet = self.monitor.check_internet()

                        if has_internet:
                            status = f"Подключено к {self.monitor.ssid}, интернет доступен"

                            # Проверяем роутер (раз в заданный интервал)
                            current_time = time.time()
                            if current_time - self.last_router_check > self.router_check_interval:
                                self.last_router_check = current_time
                                self.status_signal.emit("Проверка роутера...", True)
                                # Здесь можно добавить логику проверки/настройки роутера
                        else:
                            status = f"Подключено к {self.monitor.ssid}, но нет интернета"

                        self.connection_changed.emit(True)

                    else:
                        # Сеть доступна, но не подключены - пытаемся подключиться
                        status = f"Обнаружена сеть {self.monitor.ssid}, подключаюсь..."
                        success, message = self.monitor.connect_to_wifi()

                        if success:
                            status = f"{message}"
                            self.connection_changed.emit(True)
                        else:
                            status = f"{message}"
                            self.connection_changed.emit(False)

                else:
                    # Наша сеть недоступна
                    status = f"Сеть {self.monitor.ssid} не обнаружена"
                    self.connection_changed.emit(False)

                # Отправляем статус в GUI
                status_changed = (status != self.last_status)
                self.status_signal.emit(status, status_changed)
                self.last_status = status

                # Задержка перед следующей проверкой
                self.msleep(config.CHECK_INTERVAL * 1000)

            except Exception as e:
                error_status = f"Ошибка мониторинга: {str(e)}"
                self.status_signal.emit(error_status, True)
                self.msleep(5000)  # Ждем 5 секунд при ошибке

    def stop(self):
        """Останавливает поток"""
        self.running = False
        self.wait()


class MainWindow(QMainWindow):
    """Главное окно приложения"""

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.monitor_thread = None
        self.status_history = []
        self.init_ui()
        self.start_monitoring()

    def init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle(config.APP_TITLE)
        self.setFixedSize(config.APP_WIDTH, config.APP_HEIGHT)

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Основной layout
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
        info_label.setStyleSheet("color: #7f8c8d; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Разделитель
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #bdc3c7;")
        layout.addWidget(line)

        # Текстовое поле для статусов
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

        # Панель кнопок
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
            QPushButton:hover {
                background-color: #27ae60;
            }
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
            QPushButton:hover {
                background-color: #c0392b;
            }
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
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Статусная строка внизу
        self.bottom_status = QLabel("Готов к работе...")
        self.bottom_status.setFont(QFont("Arial", 9))
        self.bottom_status.setStyleSheet("color: #7f8c8d; padding-top: 10px; border-top: 1px solid #ecf0f1;")
        layout.addWidget(self.bottom_status)

    def start_monitoring(self):
        """Запускает поток мониторинга"""
        if self.monitor_thread is None or not self.monitor_thread.isRunning():
            self.monitor_thread = MonitorThread(self.monitor)
            self.monitor_thread.status_signal.connect(self.update_status)
            self.monitor_thread.connection_changed.connect(self.update_connection_status)
            self.monitor_thread.start()

            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.add_status("Мониторинг запущен", True)

    def stop_monitoring(self):
        """Останавливает поток мониторинга"""
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.monitor_thread = None

            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.add_status("Мониторинг остановлен", True)

    def clear_log(self):
        """Очищает лог сообщений"""
        self.status_display.clear()
        self.status_history = []
        self.add_status("Лог очищен", True)

    def add_status(self, message, is_new_line=False):
        """Добавляет сообщение в лог"""
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
        """Обновляет статус из потока мониторинга"""
        self.add_status(message, status_changed)

        if "Подключено" in message and "интернет доступен" in message:
            self.bottom_status.setStyleSheet(
                "color: #27ae60; font-weight: bold; padding-top: 10px; border-top: 1px solid #ecf0f1;")
        elif "нет интернета" in message or "не обнаружена" in message:
            self.bottom_status.setStyleSheet(
                "color: #e74c3c; font-weight: bold; padding-top: 10px; border-top: 1px solid #ecf0f1;")
        else:
            self.bottom_status.setStyleSheet("color: #7f8c8d; padding-top: 10px; border-top: 1px solid #ecf0f1;")

        self.bottom_status.setText(message)

    def update_connection_status(self, connected):
        """Обновляет статус подключения"""
        pass

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.stop_monitoring()
        event.accept()


def main():
    """Точка входа в приложение"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Всплывающее окно для ввода Wi-Fi данных
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

        # Создаём монитор с введёнными данными
        monitor = WiFiMonitor(ssid, password)
    else:
        sys.exit(0)  # Выход при отмене

    # Создаём и показываем главное окно
    window = MainWindow(monitor)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()