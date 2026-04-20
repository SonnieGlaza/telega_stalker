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
            [KeyboardButton(text="🗺 Карта"), KeyboardButton(text="🪖 Рейды")],
            [KeyboardButton(text="🛰 События"), KeyboardButton(text="🏦 Экономика")],
            [KeyboardButton(text="🎖 Достижения"), KeyboardButton(text="🏆 Рейтинг")],
            [KeyboardButton(text="⚡ Выпить энергетик"), KeyboardButton(text="⭐ Пополнить")],
        ],
        resize_keyboard=True,
    )


def quests_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Легко", callback_data="quest:easy")],
            [InlineKeyboardButton(text="Сложно", callback_data="quest:hard")],
            [InlineKeyboardButton(text="Тяжело", callback_data="quest:heavy")],
            [InlineKeyboardButton(text="Невозможно", callback_data="quest:impossible")],
        ]
    )


def trader_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Покупка", callback_data="trade:menu:buy")],
            [InlineKeyboardButton(text="🔴 Продажа", callback_data="trade:menu:sell")],
        ]
    )


def trader_buy_categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Расходники", callback_data="trade:buy:consumables")],
            [InlineKeyboardButton(text="🛡 Снаряжение", callback_data="trade:buy:gear")],
            [InlineKeyboardButton(text="🔫 Оружие", callback_data="trade:buy:weapons")],
            [InlineKeyboardButton(text="⬅️ Назад в Торговец", callback_data="trade:menu:root")],
        ]
    )


def trader_buy_consumables_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить энергетик (250)", callback_data="buy:energy_drink")],
            [InlineKeyboardButton(text="Купить аптечку (260)", callback_data="buy:medkit")],
            [InlineKeyboardButton(text="Купить патроны (120)", callback_data="buy:ammo_pack")],
            [InlineKeyboardButton(text="Купить топливо +5 (450)", callback_data="buy:fuel_can")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def trader_buy_gear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Улучшить снарягу (1200)", callback_data="buy:gear_upgrade")],
            [InlineKeyboardButton(text="Купить Комбинезон «Заря» (2200)", callback_data="buy:armor_zarya")],
            [InlineKeyboardButton(text="Купить ПСЗ-9д «Булат» (3600)", callback_data="buy:armor_bulat")],
            [InlineKeyboardButton(text="Купить СЕВА (5200)", callback_data="buy:armor_seva")],
            [InlineKeyboardButton(text="Купить Экзоскелет (9000)", callback_data="buy:armor_exo")],
            [InlineKeyboardButton(text="Купить Научный костюм (7800)", callback_data="buy:armor_scientific")],
            [InlineKeyboardButton(text="Ремонт оружия", callback_data="repair:weapon")],
            [InlineKeyboardButton(text="Ремонт брони", callback_data="repair:armor")],
            [InlineKeyboardButton(text="Купить грузовик (7000)", callback_data="buy:truck")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def trader_buy_weapons_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить ПМ (900)", callback_data="buy:weapon_pm")],
            [InlineKeyboardButton(text="Купить Фора-12 (1300)", callback_data="buy:weapon_fora12")],
            [InlineKeyboardButton(text="Купить Обрез (1200)", callback_data="buy:weapon_sawedoff")],
            [InlineKeyboardButton(text="Купить Гадюка-5 (2200)", callback_data="buy:weapon_mp5")],
            [InlineKeyboardButton(text="Купить Chaser-13 (2500)", callback_data="buy:weapon_chaser13")],
            [InlineKeyboardButton(text="Купить АКС-74У (2600)", callback_data="buy:weapon_aks74u")],
            [InlineKeyboardButton(text="Купить АК-74 (3400)", callback_data="buy:weapon_ak74")],
            [InlineKeyboardButton(text="Купить СПАС-12 (3900)", callback_data="buy:weapon_spas12")],
            [InlineKeyboardButton(text="Купить TRs 301 (5000)", callback_data="buy:weapon_lr300")],
            [InlineKeyboardButton(text="Купить ИЛ86 (5200)", callback_data="buy:weapon_il86")],
            [InlineKeyboardButton(text="Купить АН-94 (6200)", callback_data="buy:weapon_an94")],
            [InlineKeyboardButton(text="Купить ГП37 (7900)", callback_data="buy:weapon_gp37")],
            [InlineKeyboardButton(text="Купить Винтарь ВС (8700)", callback_data="buy:weapon_vintar")],
            [InlineKeyboardButton(text="Купить СВДм-2 (9800)", callback_data="buy:weapon_svd")],
            [InlineKeyboardButton(text="Купить РП-74 (10500)", callback_data="buy:weapon_rp74")],
            [InlineKeyboardButton(text="Купить Гаусс-пушку (22000)", callback_data="buy:weapon_gauss")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def trader_sell_categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Расходники", callback_data="trade:sell:consumables")],
            [InlineKeyboardButton(text="🛡 Снаряжение", callback_data="trade:sell:gear")],
            [InlineKeyboardButton(text="🔫 Оружие", callback_data="trade:sell:weapons")],
            [InlineKeyboardButton(text="⬅️ Назад в Торговец", callback_data="trade:menu:root")],
        ]
    )


def trader_sell_consumables_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продать энергетик (170)", callback_data="sell:energy_drink")],
            [InlineKeyboardButton(text="Продать аптечку (120)", callback_data="sell:medkit")],
            [InlineKeyboardButton(text="Продать патроны (55)", callback_data="sell:ammo_pack")],
            [InlineKeyboardButton(text="Продать артефакт (650)", callback_data="sell:artifact")],
            [InlineKeyboardButton(text="Продать топливо +5 (200)", callback_data="sell:fuel_can")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям продажи", callback_data="trade:menu:sell")],
        ]
    )


def trader_sell_gear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продать «Заря» (1000)", callback_data="sell:armor_zarya")],
            [InlineKeyboardButton(text="Продать «Булат» (1700)", callback_data="sell:armor_bulat")],
            [InlineKeyboardButton(text="Продать СЕВА (2500)", callback_data="sell:armor_seva")],
            [InlineKeyboardButton(text="Продать Экзоскелет (4500)", callback_data="sell:armor_exo")],
            [InlineKeyboardButton(text="Продать Научный костюм (3800)", callback_data="sell:armor_scientific")],
            [InlineKeyboardButton(text="Продать грузовик (3500)", callback_data="sell:truck")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям продажи", callback_data="trade:menu:sell")],
        ]
    )


def trader_sell_weapons_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продать ПМ (420)", callback_data="sell:weapon_pm")],
            [InlineKeyboardButton(text="Продать Фора-12 (620)", callback_data="sell:weapon_fora12")],
            [InlineKeyboardButton(text="Продать Обрез (560)", callback_data="sell:weapon_sawedoff")],
            [InlineKeyboardButton(text="Продать Гадюка-5 (1050)", callback_data="sell:weapon_mp5")],
            [InlineKeyboardButton(text="Продать Chaser-13 (1200)", callback_data="sell:weapon_chaser13")],
            [InlineKeyboardButton(text="Продать АКС-74У (1200)", callback_data="sell:weapon_aks74u")],
            [InlineKeyboardButton(text="Продать АК-74 (1600)", callback_data="sell:weapon_ak74")],
            [InlineKeyboardButton(text="Продать СПАС-12 (1900)", callback_data="sell:weapon_spas12")],
            [InlineKeyboardButton(text="Продать TRs 301 (2400)", callback_data="sell:weapon_lr300")],
            [InlineKeyboardButton(text="Продать ИЛ86 (2500)", callback_data="sell:weapon_il86")],
            [InlineKeyboardButton(text="Продать АН-94 (3000)", callback_data="sell:weapon_an94")],
            [InlineKeyboardButton(text="Продать ГП37 (3900)", callback_data="sell:weapon_gp37")],
            [InlineKeyboardButton(text="Продать Винтарь ВС (4300)", callback_data="sell:weapon_vintar")],
            [InlineKeyboardButton(text="Продать СВДм-2 (4800)", callback_data="sell:weapon_svd")],
            [InlineKeyboardButton(text="Продать РП-74 (5200)", callback_data="sell:weapon_rp74")],
            [InlineKeyboardButton(text="Продать Гаусс-пушку (11000)", callback_data="sell:weapon_gauss")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям продажи", callback_data="trade:menu:sell")],
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


def raid_keyboard(locations: list[dict[str, str | int | None]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Присоединиться к открытому рейду", callback_data="raid:join")],
        [InlineKeyboardButton(text="🚀 Запустить мой открытый рейд", callback_data="raid:launch")],
    ]
    for location in locations:
        name = str(location["name"])
        rows.append([InlineKeyboardButton(text=f"Создать рейд: {name}", callback_data=f"raid:create:{name}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def economy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Склад группировки", callback_data="eco:warehouse:view")],
            [InlineKeyboardButton(text="📥 Сдать 1 патроны на склад", callback_data="eco:warehouse:deposit:ammo_pack")],
            [InlineKeyboardButton(text="📤 Забрать 1 патроны со склада", callback_data="eco:warehouse:withdraw:ammo_pack")],
            [InlineKeyboardButton(text="📥 Сдать 1 аптечку на склад", callback_data="eco:warehouse:deposit:medkit")],
            [InlineKeyboardButton(text="📤 Забрать 1 аптечку со склада", callback_data="eco:warehouse:withdraw:medkit")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот артефакт", callback_data="eco:auction:create:artifact")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот патроны", callback_data="eco:auction:create:ammo_pack")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот аптечки", callback_data="eco:auction:create:medkit")],
            [InlineKeyboardButton(text="⚖️ Биржа: купить первый лот", callback_data="eco:auction:buy:first")],
            [InlineKeyboardButton(text="🛑 Биржа: отменить мой первый лот", callback_data="eco:auction:cancel:mine")],
            [InlineKeyboardButton(text="🚚 Контрабанда", callback_data="eco:smuggle:run")],
        ]
    )


def ratings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎖 Мои достижения", callback_data="ratings:achievements")],
            [InlineKeyboardButton(text="🏆 Топ сталкеров", callback_data="ratings:leaderboard")],
        ]
    )
