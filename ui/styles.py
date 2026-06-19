"""Стили интерфейса и константы окна. Дизайн не менять."""

# ── Настройки окна ───────────────────────────
APP_TITLE = "Wi-Fi Монитор"
APP_WIDTH = 600
APP_HEIGHT = 400

# ── Стили ────────────────────────────────────
BORDER_NONE = "border: none;"

STYLE_PING_FRAME = """
    QWidget {
        background-color: #ecf0f1;
        border: 1px solid #bdc3c7;
        border-radius: 5px;
    }
"""

STYLE_TEXT_EDIT = """
    QTextEdit {
        background-color: #ecf0f1;
        border: 1px solid #bdc3c7;
        border-radius: 5px;
        padding: 10px;
    }
"""

STYLE_BOTTOM_BASE = "padding-top: 10px; border-top: 1px solid #ecf0f1;"


def button_style(bg: str, bg_hover: str) -> str:
    return f"""
        QPushButton {{
            background-color: {bg};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {bg_hover}; }}
    """
