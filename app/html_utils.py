from __future__ import annotations

from html import escape


def html_safe(text: str | None) -> str:
    """Экранировать пользовательский текст для Telegram HTML."""
    if text is None:
        return ""
    return escape(str(text), quote=False)
