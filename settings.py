"""
Хранение пользовательских настроек:
  • SSID + флаг «запомнить» → QSettings (реестр Windows)
  • Пароль                  → keyring (Windows Credential Manager, зашифрован)
  • Автозапуск              → HKCU\\...\\Run через winreg
"""
import os
import sys

import keyring
from PyQt5.QtCore import QSettings

ORG_NAME = "WiFiMonitor"
APP_NAME = "WiFiMonitor"
KEYRING_SERVICE = "WiFiMonitor"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "WiFiMonitor"


# ── Учётные данные ────────────────────────────
def _qs() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def load_credentials() -> tuple[str, str, bool]:
    """Возвращает (ssid, password, remember). Пустые строки если не сохранены."""
    qs = _qs()
    remember = qs.value("remember", False, type=bool)
    ssid = qs.value("ssid", "", type=str) if remember else ""
    password = ""
    if remember and ssid:
        try:
            password = keyring.get_password(KEYRING_SERVICE, ssid) or ""
        except keyring.errors.KeyringError:
            password = ""
    return ssid, password, remember


def save_credentials(ssid: str, password: str) -> None:
    qs = _qs()
    qs.setValue("remember", True)
    qs.setValue("ssid", ssid)
    try:
        keyring.set_password(KEYRING_SERVICE, ssid, password)
    except keyring.errors.KeyringError:
        pass


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
        # Собранный PyInstaller-ом exe
        return f'"{sys.executable}"'
    # Режим разработки: python.exe main.py
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
