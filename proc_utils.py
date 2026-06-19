"""
Утилиты для запуска внешних команд (netsh, ping) на Windows
со скрытием окна консоли в windowed-сборке.
"""
import os
import subprocess

# ── Скрытие окон CMD (PyInstaller --windowed) ─
if os.name == "nt":
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUPINFO.wShowWindow = subprocess.SW_HIDE
    CREATE_NO_WINDOW = 0x08000000
else:  # pragma: no cover — приложение Windows-only
    _STARTUPINFO = None
    CREATE_NO_WINDOW = 0


def run_hidden(
    cmd,
    timeout: float = 5,
    text: bool = True,
    encoding: str = "cp866",
) -> subprocess.CompletedProcess:
    """Запуск процесса со скрытым окном и единым кодированием вывода."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=text,
        encoding=encoding if text else None,
        timeout=timeout,
        startupinfo=_STARTUPINFO,
        creationflags=CREATE_NO_WINDOW,
    )
