from __future__ import annotations

from typing import Any

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
            [InlineKeyboardButton(text="Нейтралы", callback_data="faction:Нейтралы")],
            [InlineKeyboardButton(text="Бандиты", callback_data="faction:Бандиты")],
        ]
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎒 Инвентарь")],
            [KeyboardButton(text="🛒 Торговец"), KeyboardButton(text="📋 Задания")],
            [KeyboardButton(text="⚔️ Война"), KeyboardButton(text="🗺 Переход")],
            [KeyboardButton(text="🪖 Рейды"), KeyboardButton(text="🛰 События")],
            [KeyboardButton(text="👥 Группировка"), KeyboardButton(text="🏦 Экономика")],
            [KeyboardButton(text="📟 КПК"), KeyboardButton(text="ℹ️ Информация")],
            [KeyboardButton(text="⭐ Пополнить")],
        ],
        resize_keyboard=True,
    )


def pda_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧾 Профиль"), KeyboardButton(text="💬 Чаты")],
            [KeyboardButton(text="🏆 Рейтинг"), KeyboardButton(text="🗺 Карта")],
            [KeyboardButton(text="🎖 Достижения"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👥 Игроки"), KeyboardButton(text="📣 Сбор")],
            [KeyboardButton(text="🔗 Реферальная система")],
            [KeyboardButton(text="⬅️ В меню")],
        ],
        resize_keyboard=True,
    )


def quests_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Легко", callback_data="quest:easy")],
            [InlineKeyboardButton(text="🟡 Сложно", callback_data="quest:hard")],
            [InlineKeyboardButton(text="🟠 Тяжело", callback_data="quest:heavy")],
            [InlineKeyboardButton(text="🔴 Невозможно", callback_data="quest:impossible")],
            [InlineKeyboardButton(text="🚚 Контрабанда", callback_data="eco:smuggle:run")],
        ]
    )


def trader_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Покупка", callback_data="trade:menu:buy")],
            [InlineKeyboardButton(text="🔴 Продажа", callback_data="trade:menu:sell")],
        ]
    )


TRADER_PAGE_SIZE = 5


def _trader_page_keyboard(
    items: list[tuple[str, str]],
    *,
    page: int,
    page_prefix: str,
    back_callback: str,
    back_text: str,
) -> InlineKeyboardMarkup:
    total = len(items)
    total_pages = max(1, (total + TRADER_PAGE_SIZE - 1) // TRADER_PAGE_SIZE)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * TRADER_PAGE_SIZE
    chunk = items[start : start + TRADER_PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=title, callback_data=callback)] for title, callback in chunk
    ]
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if safe_page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=f"{page_prefix}:{safe_page - 1}",
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{safe_page + 1}/{total_pages}",
                callback_data=f"{page_prefix}:{safe_page}",
            )
        )
        if safe_page + 1 < total_pages:
            nav.append(
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=f"{page_prefix}:{safe_page + 1}",
                )
            )
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=back_text, callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trader_buy_categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Расходники", callback_data="trade:buy:consumables:0")],
            [InlineKeyboardButton(text="🛡 Снаряжение", callback_data="trade:buy:gear:0")],
            [InlineKeyboardButton(text="🦺 Броня", callback_data="trade:buy:armor:0")],
            [InlineKeyboardButton(text="🔫 Оружие", callback_data="trade:buy:weapons:0")],
            [InlineKeyboardButton(text="🔧 Ремонт", callback_data="trade:buy:repair")],
            [InlineKeyboardButton(text="⬅️ Назад в Торговец", callback_data="trade:menu:root")],
        ]
    )


def trader_buy_consumables_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Купить энергетик (250)", "buy:energy_drink"),
        ("Купить аптечку (260)", "buy:medkit"),
        ("Купить патроны (120)", "buy:ammo_pack"),
        ("Купить водку (150)", "buy:vodka"),
        ("Купить антирад (400)", "buy:antirad"),
        ("Купить хлеб (50)", "buy:bread"),
        ("Купить колбасу (100)", "buy:sausage"),
        ("Купить тушёнку (250)", "buy:stew"),
        ("Купить воду (50)", "buy:water_bottle"),
        ("Купить минералку (100)", "buy:mineral_water"),
        ("Купить чай Бороды (250)", "buy:beard_tea"),
        ("Купить топливо +5 (450)", "buy:fuel_can"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:buy:consumables",
        back_callback="trade:menu:buy",
        back_text="⬅️ Назад к категориям покупки",
    )


def trader_buy_gear_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Купить детектор «Отклик» (1000)", "buy:detector_otklik"),
        ("Купить детектор «Медведь» (4000)", "buy:detector_medved"),
        ("Купить детектор «Велес» (10000)", "buy:detector_veles"),
        ("Купить детектор «Сварог» (30000)", "buy:detector_svarog"),
        ("Купить грузовик (50000)", "buy:truck"),
        ("Купить спальник (30000)", "buy:sleeping_bag"),
        ("Купить тайник (1000)", "buy:stash_case"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:buy:gear",
        back_callback="trade:menu:buy",
        back_text="⬅️ Назад к категориям покупки",
    )


def trader_buy_repair_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ремонт оружия", callback_data="repair:weapon")],
            [InlineKeyboardButton(text="Ремонт брони", callback_data="repair:armor")],
            [InlineKeyboardButton(text="Ремонт грузовика", callback_data="repair:truck")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def inventory_equipment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Расходники", callback_data="inventory:consumables")],
            [InlineKeyboardButton(text="⚡ Выпить энергетик", callback_data="use:energy_drink")],
            [InlineKeyboardButton(text="📦 Открыть тайник", callback_data="use:stash_case")],
            [InlineKeyboardButton(text="📡 Поиск артефактов", callback_data="artifact:search")],
            [InlineKeyboardButton(text="⚙️ Экипировка", callback_data="equip:root")],
            [InlineKeyboardButton(text="☠️ Респавн (если HP=0)", callback_data="player:respawn")],
        ]
    )


def inventory_consumables_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Выпить энергетик", callback_data="use:energy_drink")],
            [InlineKeyboardButton(text="🩹 Использовать аптечку", callback_data="use:medkit")],
            [InlineKeyboardButton(text="🍸 Выпить водку (-20 рад.)", callback_data="use:vodka")],
            [InlineKeyboardButton(text="💉 Использовать антирад (-50 рад.)", callback_data="use:antirad")],
            [InlineKeyboardButton(text="🍞 Поесть хлеб (+10 сытости)", callback_data="use:bread")],
            [InlineKeyboardButton(text="🥓 Поесть колбасу (+20 сытости)", callback_data="use:sausage")],
            [InlineKeyboardButton(text="🥫 Поесть тушёнку (+50 сытости)", callback_data="use:stew")],
            [InlineKeyboardButton(text="💧 Выпить воду (+10 жажды)", callback_data="use:water_bottle")],
            [InlineKeyboardButton(text="🧴 Выпить минералку (+20 жажды)", callback_data="use:mineral_water")],
            [InlineKeyboardButton(text="🍵 Выпить чай Бороды (+50 жажды)", callback_data="use:beard_tea")],
            [InlineKeyboardButton(text="⬅️ Назад в инвентарь", callback_data="inventory:open")],
        ]
    )


def inventory_actions_keyboard() -> InlineKeyboardMarkup:
    return inventory_equipment_keyboard()


def dead_character_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="♻️ Респавн на базе (500 RU)", callback_data="respawn:base")],
        ]
    )


def equip_root_keyboard(items: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for slot_key, title, count in items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{title} ({count})",
                    callback_data=f"equip:slot:{slot_key}:0",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад в инвентарь", callback_data="inventory:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equip_slot_page_keyboard(
    slot: str,
    *,
    page: int,
    total_pages: int,
    options: list[tuple[str, str, int]],
    can_unequip_artifact: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item_key, title, amount in options:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Надеть: {title} (x{amount})",
                    callback_data=f"equip:put:{slot}:{item_key}",
                )
            ]
        )
    if not options:
        rows.append([InlineKeyboardButton(text="Пусто", callback_data=f"equip:slot:{slot}:{page}")])
    if slot == "artifact" and can_unequip_artifact:
        rows.append(
            [InlineKeyboardButton(text="Снять артефакт", callback_data="equip:unequip:artifact")]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"equip:slot:{slot}:{page - 1}",
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data=f"equip:slot:{slot}:{page}",
        )
    )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"equip:slot:{slot}:{page + 1}",
            )
        )
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К категориям", callback_data="equip:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equip_weapon_keyboard(available_weapons: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """Совместимость: старое прямое меню оружия → страница экипировки."""
    return equip_slot_page_keyboard("weapon", page=0, total_pages=1, options=available_weapons)


def equip_armor_keyboard(available_armor: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """Совместимость: старое прямое меню брони → страница экипировки."""
    return equip_slot_page_keyboard("armor", page=0, total_pages=1, options=available_armor)


def trader_buy_armor_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Купить Кожаную куртку (900)", "buy:armor_leather"),
        ("Купить Сталкерский бронежилет (1800)", "buy:armor_stalker_vest"),
        ("Купить Комбинезон «Заря» (2000)", "buy:armor_sunrise"),
        ("Купить Берилл-5М (5300)", "buy:armor_berill5m"),
        ("Купить Костюм СЕВА (5400)", "buy:armor_seva"),
        ("Купить Экзоскелет (18000)", "buy:armor_exoskeleton"),
        ("Купить Носорог (24000)", "buy:armor_nosorog"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:buy:armor",
        back_callback="trade:menu:buy",
        back_text="⬅️ Назад к категориям покупки",
    )


def trader_buy_weapons_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Купить ПМ (900)", "buy:weapon_pm"),
        ("Купить Фора-12 (1300)", "buy:weapon_fora12"),
        ("Купить Обрез (1200)", "buy:weapon_sawedoff"),
        ("Купить Гадюка-5 (2200)", "buy:weapon_mp5"),
        ("Купить Chaser-13 (2500)", "buy:weapon_chaser13"),
        ("Купить АКС-74У (2600)", "buy:weapon_aks74u"),
        ("Купить АК-74 (3400)", "buy:weapon_ak74"),
        ("Купить СПАС-12 (3900)", "buy:weapon_spas12"),
        ("Купить TRs 301 (5000)", "buy:weapon_lr300"),
        ("Купить ИЛ86 (5200)", "buy:weapon_il86"),
        ("Купить АН-94 (5200)", "buy:weapon_an94"),
        ("Купить ГП37 (7900)", "buy:weapon_gp37"),
        ("Купить Винтарь ВС (8700)", "buy:weapon_vintar"),
        ("Купить СВДм-2 (8800)", "buy:weapon_svd"),
        ("Купить РП-74 (9500)", "buy:weapon_rp74"),
        ("Купить Гаусс-пушку (25000)", "buy:weapon_gauss"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:buy:weapons",
        back_callback="trade:menu:buy",
        back_text="⬅️ Назад к категориям покупки",
    )


def trader_sell_categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Расходники", callback_data="trade:sell:consumables:0")],
            [InlineKeyboardButton(text="🛡 Снаряжение", callback_data="trade:sell:gear:0")],
            [InlineKeyboardButton(text="🦺 Броня", callback_data="trade:sell:armor:0")],
            [InlineKeyboardButton(text="🔫 Оружие", callback_data="trade:sell:weapons:0")],
            [InlineKeyboardButton(text="⬅️ Назад в Торговец", callback_data="trade:menu:root")],
        ]
    )


def trader_sell_consumables_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Продать энергетик (170)", "sell:energy_drink"),
        ("Продать аптечку (120)", "sell:medkit"),
        ("Продать патроны (55)", "sell:ammo_pack"),
        ("Продать артефакт Зоны (900)", "sell:artifact"),
        ("Продать Арт «Сила» (1100)", "sell:artifact_power"),
        ("Продать Арт «Живучесть» (1100)", "sell:artifact_vitality"),
        ("Продать топливо +5 (200)", "sell:fuel_can"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:sell:consumables",
        back_callback="trade:menu:sell",
        back_text="⬅️ Назад к категориям продажи",
    )


def trader_sell_gear_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Продать грузовик (3500)", "sell:truck"),
        ("Продать тайник (200)", "sell:stash_case"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:sell:gear",
        back_callback="trade:menu:sell",
        back_text="⬅️ Назад к категориям продажи",
    )


def trader_sell_armor_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Продать Кожаную куртку (420)", "sell:armor_leather"),
        ("Продать Сталкерский бронежилет (850)", "sell:armor_stalker_vest"),
        ("Продать «Заря» (1000)", "sell:armor_sunrise"),
        ("Продать Берилл-5М (2650)", "sell:armor_berill5m"),
        ("Продать СЕВА (2700)", "sell:armor_seva"),
        ("Продать Экзоскелет (9000)", "sell:armor_exoskeleton"),
        ("Продать Носорог (12000)", "sell:armor_nosorog"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:sell:armor",
        back_callback="trade:menu:sell",
        back_text="⬅️ Назад к категориям продажи",
    )


def trader_sell_weapons_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Продать ПМ (420)", "sell:weapon_pm"),
        ("Продать Фора-12 (620)", "sell:weapon_fora12"),
        ("Продать Обрез (560)", "sell:weapon_sawedoff"),
        ("Продать Гадюка-5 (1050)", "sell:weapon_mp5"),
        ("Продать Chaser-13 (1200)", "sell:weapon_chaser13"),
        ("Продать АКС-74У (1200)", "sell:weapon_aks74u"),
        ("Продать АК-74 (1600)", "sell:weapon_ak74"),
        ("Продать СПАС-12 (1900)", "sell:weapon_spas12"),
        ("Продать TRs 301 (2400)", "sell:weapon_lr300"),
        ("Продать ИЛ86 (2500)", "sell:weapon_il86"),
        ("Продать АН-94 (2500)", "sell:weapon_an94"),
        ("Продать ГП37 (3900)", "sell:weapon_gp37"),
        ("Продать Винтарь ВС (4300)", "sell:weapon_vintar"),
        ("Продать СВДм-2 (4400)", "sell:weapon_svd"),
        ("Продать РП-74 (4750)", "sell:weapon_rp74"),
        ("Продать Гаусс-пушку (12500)", "sell:weapon_gauss"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:sell:weapons",
        back_callback="trade:menu:sell",
        back_text="⬅️ Назад к категориям продажи",
    )


def locations_keyboard(
    locations: list[dict[str, str | int | None]],
    mode: str,
    *,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    for location in locations:
        name = str(location["name"])
        ptype = str(location["point_type"])
        owner = location["controlled_by"] or "нейтрал"
        text = f"{name} [{ptype}, {owner}]"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"{mode}:{name}")])
    if back_callback:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 1 звезда (150 RU)", callback_data="topup:1")],
            [InlineKeyboardButton(text="⭐ 5 звезд (750 RU)", callback_data="topup:5")],
            [InlineKeyboardButton(text="⭐ 10 звезд (1500 RU)", callback_data="topup:10")],
            [InlineKeyboardButton(text="⭐ 25 звезд (3750 RU)", callback_data="topup:25")],
            [InlineKeyboardButton(text="⭐ Другое количество", callback_data="topup:custom")],
        ]
    )


def raid_keyboard(
    locations: list[dict[str, str | int | None]],
    *,
    led_raids: list[dict[str, Any]] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Присоединиться к открытому рейду", callback_data="raid:join")],
        [InlineKeyboardButton(text="🤝 Союзник: присоединиться к рейду", callback_data="raid:ally:join")],
        [InlineKeyboardButton(text="🚀 Запустить мой открытый рейд", callback_data="raid:launch")],
    ]
    led = led_raids or []
    if led:
        for raid in led:
            raid_id = int(raid["id"])
            location = str(raid.get("location") or "?")
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"❌ Отменить рейд #{raid_id}: {location}",
                        callback_data=f"raid:cancel:{raid_id}",
                    )
                ]
            )
        rows.append(
            [InlineKeyboardButton(text="🗑 Отменить все мои рейды", callback_data="raid:cancel:all")]
        )
    for location in locations:
        name = str(location["name"])
        rows.append([InlineKeyboardButton(text=f"Создать рейд на логово: {name}", callback_data=f"raid:create:{name}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def war_lobby_keyboard(
    locations: list[dict[str, str | int | None]],
    *,
    can_dissolve: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Вступить в военное лобби", callback_data="war_lobby:join")],
        [InlineKeyboardButton(text="🚀 Запустить военное лобби", callback_data="war_lobby:launch")],
    ]
    if can_dissolve:
        rows.append(
            [InlineKeyboardButton(text="🛑 Распустить лобби", callback_data="war_lobby:dissolve")]
        )
    for location in locations:
        name = str(location["name"])
        rows.append([InlineKeyboardButton(text=f"Создать штурм-лобби: {name}", callback_data=f"war_lobby:create:{name}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="war:section:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def war_transfer_keyboard(allies: list[str], location_name: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ally in allies:
        rows.append(
            [InlineKeyboardButton(text=f"🎁 Отдать {location_name} -> {ally}", callback_data=f"war:transfer:{ally}")]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Нет союзников для передачи", callback_data="alliance:none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def war_sections_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📘 Сценарий войны", callback_data="war:section:scenario")],
            [InlineKeyboardButton(text="🪖 Военные лобби (штурм от 5)", callback_data="war:section:lobby")],
        ]
    )


def faction_group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Склад группировки", callback_data="faction:warehouse:view")],
            [InlineKeyboardButton(text="📥 Сдать 1 патроны на склад", callback_data="eco:warehouse:deposit:ammo_pack")],
            [InlineKeyboardButton(text="📤 Забрать 1 патроны со склада", callback_data="eco:warehouse:withdraw:ammo_pack")],
            [InlineKeyboardButton(text="📥 Сдать 1 аптечку на склад", callback_data="eco:warehouse:deposit:medkit")],
            [InlineKeyboardButton(text="📤 Забрать 1 аптечку со склада", callback_data="eco:warehouse:withdraw:medkit")],
            [InlineKeyboardButton(text="🏦 Лидер: вывести 500 RU из казны", callback_data="eco:treasury:withdraw:500")],
            [InlineKeyboardButton(text="🏦 Лидер: вывести 1000 RU из казны", callback_data="eco:treasury:withdraw:1000")],
            [InlineKeyboardButton(text="🎖 Лидер: назначить звание", callback_data="rank:menu")],
        ]
    )


def economy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот артефакт", callback_data="eco:auction:create:artifact")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот патроны", callback_data="eco:auction:create:ammo_pack")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот аптечки", callback_data="eco:auction:create:medkit")],
            [InlineKeyboardButton(text="🛒 Рынок: выставить экипировку", callback_data="eco:market:create:choose")],
            [InlineKeyboardButton(text="🛒 Рынок: список лотов экипировки", callback_data="eco:market:list")],
            [InlineKeyboardButton(text="🛑 Рынок: отменить мой лот", callback_data="eco:market:cancel:mine")],
            [InlineKeyboardButton(text="⚖️ Биржа: купить первый лот", callback_data="eco:auction:buy:first")],
            [InlineKeyboardButton(text="🛑 Биржа: отменить мой первый лот", callback_data="eco:auction:cancel:mine")],
        ]
    )


def market_lots_keyboard(lots: list[dict[str, str | int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for lot in lots[:20]:
        lot_id = int(lot["id"])
        title = str(lot["title"])
        price = int(lot["price"])
        amount = int(lot["amount"])
        seller_id = int(lot["seller_id"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{lot_id} {title} x{amount} • {price} RU • seller {seller_id}",
                    callback_data=f"eco:market:buy:{lot_id}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Открытых лотов нет", callback_data="alliance:none")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в экономику", callback_data="eco:menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def market_lot_keyboard(lots: list[dict[str, str | int]]) -> InlineKeyboardMarkup:
    return market_lots_keyboard(lots)


def market_create_select_keyboard(items: list[dict[str, str | int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[:20]:
        item_key = str(item["item_key"])
        title = str(item["title"])
        amount = int(item["amount"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{title} (x{amount})",
                    callback_data=f"eco:market:create:{item_key}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Нет подходящих вещей", callback_data="alliance:none")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в экономику", callback_data="eco:menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ratings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="ratings:stats")],
            [InlineKeyboardButton(text="🎖 Мои достижения", callback_data="ratings:achievements")],
            [InlineKeyboardButton(text="🏆 Топ сталкеров", callback_data="ratings:leaderboard")],
        ]
    )


def alliance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕊️ Запросить мир", callback_data="alliance:menu:propose")],
            [InlineKeyboardButton(text="✅ Подтвердить входящий договор", callback_data="alliance:menu:confirm")],
            [InlineKeyboardButton(text="⚔️ Объявить войну", callback_data="alliance:menu:declare_war")],
            [InlineKeyboardButton(text="💔 Разорвать союз", callback_data="alliance:menu:break")],
            [InlineKeyboardButton(text="⬅️ К разделам войны", callback_data="war:section:root")],
        ]
    )


def alliance_target_keyboard(
    factions: list[dict[str, int | str]],
    current_faction: str,
    mode: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for faction in factions:
        name = str(faction.get("name", ""))
        if not name or name == current_faction:
            continue
        if mode == "propose":
            rows.append(
                [InlineKeyboardButton(text=f"🕊️ Запросить мир с {name}", callback_data=f"alliance:propose:{name}")]
            )
        elif mode == "declare_war":
            rows.append([InlineKeyboardButton(text=f"⚔️ Объявить войну: {name}", callback_data=f"alliance:war:{name}")])
        else:
            rows.append([InlineKeyboardButton(text=f"💔 Разорвать с {name}", callback_data=f"alliance:break:{name}")])
    if not rows:
        rows.append([InlineKeyboardButton(text="Нет доступных фракций", callback_data="alliance:none")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="alliance:menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def alliance_pending_keyboard(pending_from: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for faction_name in pending_from:
        rows.append(
            [InlineKeyboardButton(text=f"✅ Подтвердить союз с {faction_name}", callback_data=f"alliance:confirm:{faction_name}")]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Входящих договоров нет", callback_data="alliance:none")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="alliance:menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def players_factions_keyboard(items: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for faction_key, title, count in items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{title} ({count})",
                    callback_data=f"players:f:{faction_key}:0",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Игроков нет", callback_data="players:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def players_faction_page_keyboard(faction_key: str, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"players:f:{faction_key}:{page - 1}",
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data=f"players:f:{faction_key}:{page}",
        )
    )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"players:f:{faction_key}:{page + 1}",
            )
        )
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К группировкам", callback_data="players:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faction_ranks_members_keyboard(
    members: list[dict[str, str | int]],
    *,
    leader_id: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for member in members[:30]:
        telegram_id = int(member["telegram_id"])
        nickname = str(member.get("nickname") or telegram_id)
        if telegram_id == leader_id:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"⭐ {nickname} (лидер)",
                        callback_data="rank:menu",
                    )
                ]
            )
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=nickname,
                    callback_data=f"rank:member:{telegram_id}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Бойцов нет", callback_data="faction:menu:root")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в группировку", callback_data="faction:menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faction_rank_pick_keyboard(target_id: int, ranks: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, title in ranks:
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"rank:set:{target_id}:{key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ К списку бойцов", callback_data="rank:menu")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в группировку", callback_data="faction:menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
