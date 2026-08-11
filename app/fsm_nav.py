"""Сброс FSM при нажатии кнопок навигации во время ввода числа/текста."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


def normalize_nav_button_text(value: str | None) -> str:
    """Убрать variation selector (🗺 vs 🗺️) и лишние пробелы у текста reply-кнопки."""
    return (value or "").replace("\ufe0f", "").strip()

REPLY_NAV_BUTTONS: frozenset[str] = frozenset(
    {
        "📟 КПК",
        "🎒 Инвентарь",
        "📋 Задания",
        "🛒 Торговец",
        "🏕 Вылазка",
        "🛰 События",
        "👥 Группировка",
        "🏦 Экономика",
        "ℹ️ Информация",
        "⭐ Пополнить",
        "🧾 Профиль",
        "💬 Чаты",
        "🏆 Рейтинг",
        "🗺 Карта",
        "👥 Игроки",
        "☠️ Смерти",
        "📅 Ежедневка",
        "🔔 Уведомления",
        "📘 Обучение",
        "🏛 Клановые задачи",
        "📣 Сбор",
        "🔗 Реферальная система",
        "⬅️ В меню",
        "⚔️ Война",
        "⚔️ Арена",
        "🗺 Переход",
        "🪖 Рейды",
        "👥 Совместная вылазка",
        "⚡ Выпить энергетик",
    }
)

_NAV_BUTTONS_NORMALIZED = frozenset(normalize_nav_button_text(button) for button in REPLY_NAV_BUTTONS)


def is_reply_menu_button(text: str | None) -> bool:
    return normalize_nav_button_text(text) in _NAV_BUTTONS_NORMALIZED


def nav_button(*labels: str):
    """Фильтр сообщений по тексту reply-кнопки с учётом emoji variation selector."""
    expected = frozenset(normalize_nav_button_text(label) for label in labels)
    return F.func(lambda message: normalize_nav_button_text(message.text) in expected)


async def abort_fsm_if_nav(message: Message, state: FSMContext) -> bool:
    """Отменить ввод, если игрок нажал кнопку меню. Возвращает True, если ввод отменён."""
    text = normalize_nav_button_text(message.text)
    if text not in _NAV_BUTTONS_NORMALIZED:
        return False
    current = await state.get_state()
    if current is None:
        return False
    await state.clear()
    await message.answer("Ввод отменён. Нажми нужную кнопку меню ещё раз (или /cancel).")
    return True
