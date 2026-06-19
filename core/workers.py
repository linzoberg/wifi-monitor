"""
Фоновые потоки приложения:
  • _StoppableThread — общая база с прерываемым sleep
  • PingThread       — периодический пинг 8.8.8.8
  • MonitorThread    — мониторинг Wi-Fi подключения
"""
import re
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal

from core.wifi import WiFiMonitor, run_hidden

# Прекомпилированные regex для разбора вывода ping
_RE_PING_TIME = re.compile(r"(?:[Вв]ремя|[Tt]ime)\s*[=<]\s*(\d+)")
_RE_PING_LT1 = re.compile(r"(?:[Вв]ремя|[Tt]ime)\s*<\s*1")


# ─────────────────────────────────────────────
#  Общая база для потоков с прерываемым sleep
# ─────────────────────────────────────────────
class _StoppableThread(QThread):
    """QThread с флагом остановки и прерываемой паузой."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def stop(self):
        self._running = False
        self.wait()

    def interruptible_sleep(self, ms: int) -> bool:
        """Спит ms миллисекунд, но просыпается при stop(). Возвращает False если остановлен."""
        steps = max(1, ms // 100)
        for _ in range(steps):
            if not self._running:
                return False
            self.msleep(100)
        return self._running


# ─────────────────────────────────────────────
#  Поток пинга
# ─────────────────────────────────────────────
class PingThread(_StoppableThread):
    """Каждые PING_INTERVAL секунд пингует PING_HOST и отдаёт результат."""

    ping_result = pyqtSignal(str)

    PING_HOST = "8.8.8.8"
    INITIAL_DELAY_MS = 3000

    def __init__(self, ping_interval: int, parent=None):
        super().__init__(parent)
        self.ping_interval = max(1, int(ping_interval))

    def run(self):
        if not self.interruptible_sleep(self.INITIAL_DELAY_MS):
            return

        cmd = ["ping", "-n", "1", "-w", "2000", self.PING_HOST]

        while self._running:
            ms = self._ping(cmd)
            if ms is None:
                self.ping_result.emit("Ping 8.8.8.8: недоступен")
            elif ms <= 1:
                # время < 1 мс — признак VPN
                self.ping_result.emit("Ping 8.8.8.8: VPN is ON")
            else:
                self.ping_result.emit(f"Ping 8.8.8.8: {ms} мс")

            if not self.interruptible_sleep(self.ping_interval * 1000):
                return

    @staticmethod
    def _ping(cmd) -> int | None:
        try:
            result = run_hidden(cmd, timeout=5)
        except (subprocess.SubprocessError, OSError):
            return None

        output = result.stdout or ""
        match = _RE_PING_TIME.search(output)
        if match:
            return int(match.group(1))

        if result.returncode == 0 and _RE_PING_LT1.search(output):
            return 1
        return None


# ─────────────────────────────────────────────
#  Поток мониторинга Wi-Fi
# ─────────────────────────────────────────────
class MonitorThread(_StoppableThread):
    """Фоновый мониторинг Wi-Fi."""

    status_signal = pyqtSignal(str, bool)
    connection_changed = pyqtSignal(bool)

    def __init__(self, monitor: WiFiMonitor, check_interval: int, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self.check_interval = max(1, int(check_interval))
        self._last_status = ""

    def run(self):
        while self._running:
            try:
                status = self._tick()
            except Exception as e:  # noqa: BLE001 — не хотим уронить весь поток
                self.status_signal.emit(f"Ошибка мониторинга: {e}", True)
                if not self.interruptible_sleep(5000):
                    return
                continue

            if status is None:
                # Tick уже всё засигналил сам — просто ждём дальше
                pass
            else:
                status_changed = status != self._last_status
                self.status_signal.emit(status, status_changed)
                self._last_status = status

            if not self.interruptible_sleep(self.check_interval * 1000):
                return

    def _tick(self) -> str | None:
        if not self.monitor.check_wifi_available():
            self.connection_changed.emit(False)
            return f"Сеть {self.monitor.ssid} не обнаружена"

        if self.monitor.get_current_connection():
            self.connection_changed.emit(True)
            if self.monitor.check_internet():
                return f"Подключено к {self.monitor.ssid}, интернет доступен"
            return f"Подключено к {self.monitor.ssid}, но нет интернета"

        # Сеть видна, но не подключены — пробуем подключиться.
        # Это может занять до RECONNECT_ATTEMPTS * RECONNECT_DELAY секунд,
        # поэтому показываем промежуточный статус и НЕ переписываем его финальной строкой.
        self.status_signal.emit(
            f"Обнаружена сеть {self.monitor.ssid}, подключаюсь...", True
        )
        success, message = self.monitor.connect_to_wifi()
        self.connection_changed.emit(bool(success))
        self.status_signal.emit(message, True)
        self._last_status = message
        return None
