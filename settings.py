"""
Хранение пользовательских настроек:
  • SSID + флаг «запомнить» → QSettings (реестр Windows)
  • Пароль                  → keyring (Windows Credential Manager, зашифрован)
  • Автозапуск              → HKCU\\...\\Run через winreg
"""
import os
import sys

import keyring
import keyring.errors
from PyQt5.QtCore import QSettings

import config

ORG_NAME = "WiFiMonitor"
APP_NAME = "WiFiMonitor"
KEYRING_SERVICE = "WiFiMonitor"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "WiFiMonitor"

# Допустимые диапазоны значений настроек (защита от мусора)
CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX = 1, 3600
PING_INTERVAL_MIN, PING_INTERVAL_MAX = 1, 3600


# ── Учётные данные ────────────────────────────
def _qs() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def load_credentials() -> tuple[str, str, bool]:
    """Возвращает (ssid, password, remember). Пустые строки если не сохранены."""
    qs = _qs()
    remember = qs.value("remember", False, type=bool)
    if not remember:
        return "", "", False

    ssid = qs.value("ssid", "", type=str)
    password = ""
    if ssid:
        try:
            password = keyring.get_password(KEYRING_SERVICE, ssid) or ""
        except keyring.errors.KeyringError:
            password = ""
    return ssid, password, True


def save_credentials(ssid: str, password: str) -> None:
    qs = _qs()
    qs.setValue("remember", True)
    qs.setValue("ssid", ssid)
    try:
        keyring.set_password(KEYRING_SERVICE, ssid, password)
    except keyring.errors.KeyringError:
        pass


# ── Пользовательские настройки ────────────────
class Prefs:
    """Контейнер пользовательских настроек."""

    __slots__ = ("check_interval", "ping_interval", "router_ip")

    def __init__(self, check_interval: int, ping_interval: int, router_ip: str):
        self.check_interval = check_interval
        self.ping_interval = ping_interval
        self.router_ip = router_ip


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def load_prefs() -> Prefs:
    """Загружает настройки, подставляя дефолты из config.py."""
    qs = _qs()
    check_interval = qs.value("check_interval", config.CHECK_INTERVAL, type=int)
    ping_interval = qs.value("ping_interval", 5, type=int)
    router_ip = qs.value("router_ip", config.ROUTER_IP, type=str) or config.ROUTER_IP

    return Prefs(
        check_interval=_clamp(check_interval, CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX),
        ping_interval=_clamp(ping_interval, PING_INTERVAL_MIN, PING_INTERVAL_MAX),
        router_ip=router_ip.strip(),
    )


def save_prefs(prefs: Prefs) -> None:
    qs = _qs()
    qs.setValue("check_interval", int(prefs.check_interval))
    qs.setValue("ping_interval", int(prefs.ping_interval))
    qs.setValue("router_ip", prefs.router_ip.strip())


def forget_credentials() -> None:
    qs = _qs()
    old_ssid = qs.value("ssid", "", type=str)
    qs.setValue("remember", False)
    qs.remove("ssid")
    if old_ssid:
        try:
            keyring.delete_password(KEYRING_SERVICE, old_ssid)
        except keyring.errors.KeyringError:
            pass


# ── Автозапуск ────────────────────────────────
def _exe_command() -> str:
    """Команда для автозапуска: путь к exe (или python + main.py при отладке)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return f'"{sys.executable}" "{script}"'


def is_autostart_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_NAME)
            return bool(value)
    except (FileNotFoundError, OSError):
        return False


def set_autostart(enabled: bool) -> bool:
    """Включает/выключает автозапуск. Возвращает True при успехе."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, AUTOSTART_NAME, 0, winreg.REG_SZ, _exe_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
