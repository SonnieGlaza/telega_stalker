"""Сброс FSM при нажатии кнопок навигации во время ввода числа/текста."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

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


def is_reply_menu_button(text: str | None) -> bool:
    return (text or "").strip() in REPLY_NAV_BUTTONS


async def abort_fsm_if_nav(message: Message, state: FSMContext) -> bool:
    """Отменить ввод, если игрок нажал кнопку меню. Возвращает True, если ввод отменён."""
    text = (message.text or "").strip()
    if text not in REPLY_NAV_BUTTONS:
        return False
    current = await state.get_state()
    if current is None:
        return False
    await state.clear()
    await message.answer("Ввод отменён. Нажми нужную кнопку меню ещё раз (или /cancel).")
    return True
