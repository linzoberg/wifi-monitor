"""Фабрики иконок для системного трея."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap


def make_tray_icon(color: str) -> QIcon:
    """Рисует круглую иконку нужного цвета."""
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
