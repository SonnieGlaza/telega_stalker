from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Мужской", callback_data="gender:male"),
                InlineKeyboardButton(text="Женский", callback_data="gender:female"),
            ]
        ]
    )


def faction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Долг", callback_data="faction:Долг")],
            [InlineKeyboardButton(text="Свобода", callback_data="faction:Свобода")],
        ]
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎒 Инвентарь"), KeyboardButton(text="🧾 Профиль")],
            [KeyboardButton(text="🛒 Торговец"), KeyboardButton(text="📋 Задания")],
            [KeyboardButton(text="⚔️ Война"), KeyboardButton(text="🗺 Переход")],
            [KeyboardButton(text="⚡ Выпить энергетик"), KeyboardButton(text="⭐ Пополнить")],
        ],
        resize_keyboard=True,
    )


def quests_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Легко (до 90%)", callback_data="quest:easy")],
            [InlineKeyboardButton(text="Сложно (до 80%)", callback_data="quest:hard")],
            [InlineKeyboardButton(text="Тяжело (до 70%)", callback_data="quest:heavy")],
            [InlineKeyboardButton(text="Невозможно (до 60%)", callback_data="quest:impossible")],
        ]
    )


def trader_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить энергетик (350)", callback_data="buy:energy_drink")],
            [InlineKeyboardButton(text="Купить аптечку (260)", callback_data="buy:medkit")],
            [InlineKeyboardButton(text="Купить патроны (120)", callback_data="buy:ammo_pack")],
            [InlineKeyboardButton(text="Улучшить снарягу (1200)", callback_data="buy:gear_upgrade")],
            [InlineKeyboardButton(text="Купить грузовик (7000)", callback_data="buy:truck")],
            [InlineKeyboardButton(text="Купить топливо +5 (450)", callback_data="buy:fuel_can")],
            [InlineKeyboardButton(text="Продать энергетик (170)", callback_data="sell:energy_drink")],
            [InlineKeyboardButton(text="Продать аптечку (120)", callback_data="sell:medkit")],
            [InlineKeyboardButton(text="Продать патроны (55)", callback_data="sell:ammo_pack")],
            [InlineKeyboardButton(text="Продать топливо +5 (200)", callback_data="sell:fuel_can")],
        ]
    )


def locations_keyboard(locations: list[dict[str, str | int | None]], mode: str) -> InlineKeyboardMarkup:
    rows = []
    for location in locations:
        name = str(location["name"])
        ptype = str(location["point_type"])
        owner = location["controlled_by"] or "нейтрал"
        text = f"{name} [{ptype}, {owner}]"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"{mode}:{name}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 1 звезда (10 RU)", callback_data="topup:1")],
            [InlineKeyboardButton(text="⭐ 5 звезд (50 RU)", callback_data="topup:5")],
            [InlineKeyboardButton(text="⭐ 10 звезд (100 RU)", callback_data="topup:10")],
            [InlineKeyboardButton(text="⭐ 25 звезд (250 RU)", callback_data="topup:25")],
            [InlineKeyboardButton(text="⭐ Другое количество", callback_data="topup:custom")],
        ]
    )
