import os
import re
import socket
import subprocess
import tempfile
import time

import config

# ─────────────────────────────────────────────
#  Скрытие окон CMD (PyInstaller --windowed)
# ─────────────────────────────────────────────
if os.name == "nt":
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    STARTUPINFO.wShowWindow = subprocess.SW_HIDE
    CREATE_NO_WINDOW = 0x08000000
else:
    STARTUPINFO = None
    CREATE_NO_WINDOW = 0


# Прекомпилированные regex
_RE_SSID = re.compile(r"SSID\s*:\s*(.+)")


def _run(cmd, timeout=5, text=True, encoding="cp866"):
    """Универсальный запуск netsh-команды со скрытым окном."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=text,
        encoding=encoding if text else None,
        timeout=timeout,
        startupinfo=STARTUPINFO,
        creationflags=CREATE_NO_WINDOW,
    )


class WiFiMonitor:
    """Класс для мониторинга и управления Wi-Fi подключениями."""

    def __init__(self, ssid: str, password: str):
        self.ssid = ssid
        self.password = password
        self.connected = False
        self.ssid_available = False

    # ── Сканирование сетей ────────────────────
    def check_wifi_available(self) -> bool:
        """Проверяет, доступна ли указанная Wi-Fi сеть."""
        try:
            result = _run(["netsh", "wlan", "show", "networks"], timeout=5)
            if result.returncode == 0:
                self.ssid_available = self.ssid in result.stdout
                return self.ssid_available
        except (subprocess.SubprocessError, OSError) as e:
            print(f"Ошибка при сканировании сетей: {e}")
        return False

    # ── Текущее подключение ───────────────────
    def get_current_connection(self) -> bool:
        """Проверяет, подключены ли мы к нужной сети."""
        try:
            result = _run(["netsh", "wlan", "show", "interfaces"], timeout=3)
            if result.returncode != 0:
                self.connected = False
                return False

            output = result.stdout
            ssid_match = _RE_SSID.search(output)
            current_ssid = ssid_match.group(1).strip() if ssid_match else None
            is_connected = "подключено" in output.lower()

            self.connected = bool(current_ssid == self.ssid and is_connected)
            return self.connected

        except (subprocess.SubprocessError, OSError) as e:
            print(f"Ошибка при получении информации о подключении: {e}")
            self.connected = False
            return False

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

    def connect_to_wifi(self):
        """Подключается к указанной Wi-Fi сети с повторными попытками."""
        max_attempts = config.RECONNECT_ATTEMPTS
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            temp_path = None
            try:
                # Удаляем старый профиль
                _run(
                    ["netsh", "wlan", "delete", "profile", f"name={self.ssid}"],
                    timeout=5,
                )

                # Создаём временный XML-файл с профилем
                fd, temp_path = tempfile.mkstemp(prefix="wifi_", suffix=".xml")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(self._build_profile_xml())

                # Добавляем профиль
                _run(
                    ["netsh", "wlan", "add", "profile", f"filename={temp_path}"],
                    timeout=5,
                )

                # Подключаемся
                connect_result = _run(
                    ["netsh", "wlan", "connect", f"name={self.ssid}"],
                    timeout=5,
                )

                if connect_result.returncode == 0:
                    if self._wait_for_connection(timeout=5.0, poll=0.5):
                        return True, f"Успешно подключено к {self.ssid}"
                    last_error = (
                        f"Попытка {attempt}/{max_attempts}: "
                        f"не удалось установить соединение"
                    )
                else:
                    last_error = (
                        f"Попытка {attempt}/{max_attempts}: "
                        f"ошибка команды подключения"
                    )

            except (subprocess.SubprocessError, OSError) as e:
                last_error = f"Попытка {attempt}/{max_attempts}: ошибка: {e}"

            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

            # Пауза перед следующей попыткой
            if attempt < max_attempts:
                time.sleep(config.RECONNECT_DELAY)

        return False, f"Не удалось подключиться после {max_attempts} попыток ({last_error})"

    def _wait_for_connection(self, timeout: float = 5.0, poll: float = 0.5) -> bool:
        """Активно ждёт появления подключения вместо фиксированной паузы."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.get_current_connection():
                return True
            time.sleep(poll)
        return False

    # ── Интернет ──────────────────────────────
    def check_internet(self) -> bool:
        """Проверяет доступность интернета (роутер → DNS Google)."""
        for host, port in ((config.ROUTER_IP, 80), ("8.8.8.8", 53)):
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                continue
        return False
