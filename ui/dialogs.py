"""Диалоговые окна: ввод учётных данных и редактирование настроек."""
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
)

from core import settings


# ─────────────────────────────────────────────
#  Диалог настройки сети
# ─────────────────────────────────────────────
def ask_credentials() -> tuple[str, str] | None:
    """Показывает диалог ввода SSID/пароля. Возвращает (ssid, password) или None."""
    saved_ssid, saved_password, saved_remember = settings.load_credentials()

    dialog = QDialog()
    dialog.setWindowTitle("Настройка Wi-Fi сети")
    dialog.setFixedSize(350, 210)

    layout = QFormLayout(dialog)

    ssid_input = QLineEdit(saved_ssid)
    password_input = QLineEdit(saved_password)
    password_input.setEchoMode(QLineEdit.Password)

    remember_checkbox = QCheckBox("Запомнить меня")
    remember_checkbox.setChecked(saved_remember)

    layout.addRow("SSID сети:", ssid_input)
    layout.addRow("Пароль:", password_input)
    layout.addRow("", remember_checkbox)

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

    if remember_checkbox.isChecked():
        settings.save_credentials(ssid, password)
    else:
        settings.forget_credentials()

    return ssid, password


# ─────────────────────────────────────────────
#  Диалог настроек
# ─────────────────────────────────────────────
def ask_prefs(parent, current: settings.Prefs) -> settings.Prefs | None:
    """Диалог редактирования настроек. Возвращает новые Prefs или None при отмене."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("Настройки")
    dialog.setFixedSize(380, 180)

    layout = QFormLayout(dialog)

    check_spin = QSpinBox()
    check_spin.setRange(settings.CHECK_INTERVAL_MIN, settings.CHECK_INTERVAL_MAX)
    check_spin.setSuffix(" сек")
    check_spin.setValue(current.check_interval)
    check_spin.setToolTip("Как часто проверять состояние Wi-Fi сети")

    ping_spin = QSpinBox()
    ping_spin.setRange(settings.PING_INTERVAL_MIN, settings.PING_INTERVAL_MAX)
    ping_spin.setSuffix(" сек")
    ping_spin.setValue(current.ping_interval)
    ping_spin.setToolTip("Как часто пинговать 8.8.8.8 для отображения задержки")

    router_input = QLineEdit(current.router_ip)
    router_input.setPlaceholderText("например, 192.168.0.1")
    router_input.setToolTip("IP вашего роутера для проверки локального доступа")
    router_input.hide()  # поле скрыто — функция временно не используется в UI

    layout.addRow("Интервал проверки сети:", check_spin)
    layout.addRow("Интервал пинга:", ping_spin)

    hint = QLabel(
        "Изменения применяются сразу: потоки мониторинга и пинга перезапускаются."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #7f8c8d; font-size: 11px;")
    layout.addRow(hint)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)

    if dialog.exec_() != QDialog.Accepted:
        return None

    router_ip = router_input.text().strip()
    if not router_ip:
        QMessageBox.warning(parent, "Настройки", "IP роутера не может быть пустым.")
        return None

    return settings.Prefs(
        check_interval=check_spin.value(),
        ping_interval=ping_spin.value(),
        router_ip=router_ip,
    )
