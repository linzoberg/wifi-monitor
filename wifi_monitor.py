"""
Управление и мониторинг Wi-Fi подключения через netsh (Windows).
"""
import os
import re
import socket
import subprocess
import tempfile
import time

import config
from proc_utils import run_hidden

# Совпадает строка вида:  SSID                   : MyNetwork
_RE_SSID = re.compile(r"^\s*SSID\s*:\s*(.+)$", re.MULTILINE)

# Признаки активного подключения в выводе netsh wlan show interfaces.
# В разных локалях Windows строка отличается, поэтому держим набор маркеров.
_CONNECTED_MARKERS = ("подключено", "connected")


class WiFiMonitor:
    """Мониторинг и управление подключением к Wi-Fi."""

    def __init__(self, ssid: str, password: str, router_ip: str | None = None):
        self.ssid = ssid
        self.password = password
        self.router_ip = router_ip or config.ROUTER_IP
        self.connected = False
        self.ssid_available = False

    # ── Сканирование сетей ────────────────────
    def check_wifi_available(self) -> bool:
        """Проверяет, видна ли указанная сеть в эфире."""
        try:
            result = run_hidden(["netsh", "wlan", "show", "networks"], timeout=5)
        except (subprocess.SubprocessError, OSError):
            return False

        if result.returncode != 0 or not result.stdout:
            return False

        self.ssid_available = self.ssid in result.stdout
        return self.ssid_available

    # ── Текущее подключение ───────────────────
    def get_current_connection(self) -> bool:
        """Проверяет, что мы реально подключены к нужной сети."""
        try:
            result = run_hidden(["netsh", "wlan", "show", "interfaces"], timeout=3)
        except (subprocess.SubprocessError, OSError):
            self.connected = False
            return False

        if result.returncode != 0 or not result.stdout:
            self.connected = False
            return False

        output = result.stdout
        ssid_match = _RE_SSID.search(output)
        current_ssid = ssid_match.group(1).strip() if ssid_match else None

        output_lower = output.lower()
        is_connected = any(marker in output_lower for marker in _CONNECTED_MARKERS)

        self.connected = current_ssid == self.ssid and is_connected
        return self.connected

    # ── Подключение к Wi-Fi ───────────────────
    def _build_profile_xml(self) -> str:
        return (
            '<?xml version="1.0"?>\n'
            '<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">\n'
            f'    <name>{self.ssid}</name>\n'
            '    <SSIDConfig>\n'
            '        <SSID>\n'
            f'            <name>{self.ssid}</name>\n'
            '        </SSID>\n'
            '    </SSIDConfig>\n'
            '    <connectionType>ESS</connectionType>\n'
            '    <connectionMode>auto</connectionMode>\n'
            '    <MSM>\n'
            '        <security>\n'
            '            <authEncryption>\n'
            '                <authentication>WPA2PSK</authentication>\n'
            '                <encryption>AES</encryption>\n'
            '                <useOneX>false</useOneX>\n'
            '            </authEncryption>\n'
            '            <sharedKey>\n'
            '                <keyType>passPhrase</keyType>\n'
            '                <protected>false</protected>\n'
            f'                <keyMaterial>{self.password}</keyMaterial>\n'
            '            </sharedKey>\n'
            '        </security>\n'
            '    </MSM>\n'
            '</WLANProfile>\n'
        )

    def _try_connect_once(self) -> tuple[bool, str]:
        """Одна попытка установить соединение. Возвращает (успех, описание ошибки)."""
        temp_path = None
        try:
            # Удаляем старый профиль (ошибки игнорируем — его могло и не быть)
            run_hidden(
                ["netsh", "wlan", "delete", "profile", f"name={self.ssid}"],
                timeout=5,
            )

            # Создаём временный XML-файл с профилем
            fd, temp_path = tempfile.mkstemp(prefix="wifi_", suffix=".xml")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self._build_profile_xml())

            # Добавляем профиль
            run_hidden(
                ["netsh", "wlan", "add", "profile", f"filename={temp_path}"],
                timeout=5,
            )

            # Подключаемся
            connect_result = run_hidden(
                ["netsh", "wlan", "connect", f"name={self.ssid}"],
                timeout=5,
            )

            if connect_result.returncode != 0:
                return False, "ошибка команды подключения"

            if self._wait_for_connection(timeout=5.0, poll=0.5):
                return True, ""
            return False, "не удалось установить соединение"

        except (subprocess.SubprocessError, OSError) as e:
            return False, f"ошибка: {e}"

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def connect_to_wifi(self) -> tuple[bool, str]:
        """Пытается подключиться, с повторами по конфигу."""
        max_attempts = config.RECONNECT_ATTEMPTS
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            ok, err = self._try_connect_once()
            if ok:
                return True, f"Успешно подключено к {self.ssid}"

            last_error = f"Попытка {attempt}/{max_attempts}: {err}"

            if attempt < max_attempts:
                time.sleep(config.RECONNECT_DELAY)

        return False, f"Не удалось подключиться после {max_attempts} попыток ({last_error})"

    def _wait_for_connection(self, timeout: float = 5.0, poll: float = 0.5) -> bool:
        """Активно ждёт подключения вместо фиксированной паузы."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.get_current_connection():
                return True
            time.sleep(poll)
        return False

    # ── Интернет ──────────────────────────────
    def check_internet(self) -> bool:
        """Доступен ли интернет: пробуем роутер, затем DNS Google."""
        for host, port in ((self.router_ip, 80), ("8.8.8.8", 53)):
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                continue
        return False
