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
            [InlineKeyboardButton(text="Нейтралы", callback_data="faction:Нейтралы")],
            [InlineKeyboardButton(text="Бандиты", callback_data="faction:Бандиты")],
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
            [KeyboardButton(text="ℹ️ Информация")],
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
            [InlineKeyboardButton(text="🦺 Броня", callback_data="trade:buy:armor")],
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
            [InlineKeyboardButton(text="Купить водку (150)", callback_data="buy:vodka")],
            [InlineKeyboardButton(text="Купить антирад (400)", callback_data="buy:antirad")],
            [InlineKeyboardButton(text="Купить хлеб (50)", callback_data="buy:bread")],
            [InlineKeyboardButton(text="Купить колбасу (100)", callback_data="buy:sausage")],
            [InlineKeyboardButton(text="Купить тушёнку (250)", callback_data="buy:stew")],
            [InlineKeyboardButton(text="Купить воду (50)", callback_data="buy:water_bottle")],
            [InlineKeyboardButton(text="Купить минералку (100)", callback_data="buy:mineral_water")],
            [InlineKeyboardButton(text="Купить чай Бороды (250)", callback_data="buy:beard_tea")],
            [InlineKeyboardButton(text="Купить топливо +5 (450)", callback_data="buy:fuel_can")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def trader_buy_gear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ремонт оружия", callback_data="repair:weapon")],
            [InlineKeyboardButton(text="Ремонт брони", callback_data="repair:armor")],
            [InlineKeyboardButton(text="Купить детектор «Отклик» (1000)", callback_data="buy:detector_otklik")],
            [InlineKeyboardButton(text="Купить детектор «Медведь» (4000)", callback_data="buy:detector_medved")],
            [InlineKeyboardButton(text="Купить детектор «Велес» (10000)", callback_data="buy:detector_veles")],
            [InlineKeyboardButton(text="Купить детектор «Сварог» (30000)", callback_data="buy:detector_svarog")],
            [InlineKeyboardButton(text="Купить грузовик (7000)", callback_data="buy:truck")],
            [InlineKeyboardButton(text="Купить спальник (30000)", callback_data="buy:sleeping_bag")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def inventory_equipment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🩹 Использовать аптечку", callback_data="use:medkit")],
            [InlineKeyboardButton(text="📡 Поиск артефактов", callback_data="artifact:search")],
            [InlineKeyboardButton(text="🍸 Выпить водку (-20 рад.)", callback_data="use:vodka")],
            [InlineKeyboardButton(text="💉 Использовать антирад (-50 рад.)", callback_data="use:antirad")],
            [InlineKeyboardButton(text="🍞 Поесть хлеб (+10 сытости)", callback_data="use:bread")],
            [InlineKeyboardButton(text="🥓 Поесть колбасу (+20 сытости)", callback_data="use:sausage")],
            [InlineKeyboardButton(text="🥫 Поесть тушёнку (+50 сытости)", callback_data="use:stew")],
            [InlineKeyboardButton(text="💧 Выпить воду (+10 жажды)", callback_data="use:water_bottle")],
            [InlineKeyboardButton(text="🧴 Выпить минералку (+20 жажды)", callback_data="use:mineral_water")],
            [InlineKeyboardButton(text="🍵 Выпить чай Бороды (+50 жажды)", callback_data="use:beard_tea")],
            [InlineKeyboardButton(text="Экипировать оружие", callback_data="equip:menu:weapon")],
            [InlineKeyboardButton(text="Экипировать броню", callback_data="equip:menu:armor")],
            [InlineKeyboardButton(text="Экипировать артефакт", callback_data="equip:artifact")],
            [InlineKeyboardButton(text="☠️ Респавн (если HP=0)", callback_data="player:respawn")],
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


def equip_weapon_keyboard(available_weapons: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for weapon_key, title, amount in available_weapons:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Надеть: {title} (x{amount})",
                    callback_data=f"equip:weapon:{weapon_key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад в инвентарь", callback_data="inventory:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equip_armor_keyboard(available_armor: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for armor_key, title, amount in available_armor:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Надеть: {title} (x{amount})",
                    callback_data=f"equip:armor:{armor_key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад в инвентарь", callback_data="inventory:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trader_buy_armor_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить Кожаную куртку (900)", callback_data="buy:armor_leather")],
            [InlineKeyboardButton(text="Купить Сталкерский бронежилет (1800)", callback_data="buy:armor_stalker_vest")],
            [InlineKeyboardButton(text="Купить Комбинезон «Заря» (2000)", callback_data="buy:armor_sunrise")],
            [InlineKeyboardButton(text="Купить Берилл-5М (5300)", callback_data="buy:armor_berill5m")],
            [InlineKeyboardButton(text="Купить Костюм СЕВА (5400)", callback_data="buy:armor_seva")],
            [InlineKeyboardButton(text="Купить Экзоскелет (18000)", callback_data="buy:armor_exoskeleton")],
            [InlineKeyboardButton(text="Купить Носорог (24000)", callback_data="buy:armor_nosorog")],
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
            [InlineKeyboardButton(text="Купить АН-94 (5200)", callback_data="buy:weapon_an94")],
            [InlineKeyboardButton(text="Купить ГП37 (7900)", callback_data="buy:weapon_gp37")],
            [InlineKeyboardButton(text="Купить Винтарь ВС (8700)", callback_data="buy:weapon_vintar")],
            [InlineKeyboardButton(text="Купить СВДм-2 (8800)", callback_data="buy:weapon_svd")],
            [InlineKeyboardButton(text="Купить РП-74 (9500)", callback_data="buy:weapon_rp74")],
            [InlineKeyboardButton(text="Купить Гаусс-пушку (25000)", callback_data="buy:weapon_gauss")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def trader_sell_categories_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Расходники", callback_data="trade:sell:consumables")],
            [InlineKeyboardButton(text="🛡 Снаряжение", callback_data="trade:sell:gear")],
            [InlineKeyboardButton(text="🦺 Броня", callback_data="trade:sell:armor")],
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
            [InlineKeyboardButton(text="Продать артефакт (900)", callback_data="sell:artifact")],
            [InlineKeyboardButton(text="Продать топливо +5 (200)", callback_data="sell:fuel_can")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям продажи", callback_data="trade:menu:sell")],
        ]
    )


def trader_sell_gear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продать грузовик (3500)", callback_data="sell:truck")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям продажи", callback_data="trade:menu:sell")],
        ]
    )


def trader_sell_armor_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продать Кожаную куртку (420)", callback_data="sell:armor_leather")],
            [InlineKeyboardButton(text="Продать Сталкерский бронежилет (850)", callback_data="sell:armor_stalker_vest")],
            [InlineKeyboardButton(text="Продать «Заря» (1000)", callback_data="sell:armor_sunrise")],
            [InlineKeyboardButton(text="Продать Берилл-5М (2650)", callback_data="sell:armor_berill5m")],
            [InlineKeyboardButton(text="Продать СЕВА (2700)", callback_data="sell:armor_seva")],
            [InlineKeyboardButton(text="Продать Экзоскелет (9000)", callback_data="sell:armor_exoskeleton")],
            [InlineKeyboardButton(text="Продать Носорог (12000)", callback_data="sell:armor_nosorog")],
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
            [InlineKeyboardButton(text="Продать АН-94 (2500)", callback_data="sell:weapon_an94")],
            [InlineKeyboardButton(text="Продать ГП37 (3900)", callback_data="sell:weapon_gp37")],
            [InlineKeyboardButton(text="Продать Винтарь ВС (4300)", callback_data="sell:weapon_vintar")],
            [InlineKeyboardButton(text="Продать СВДм-2 (4400)", callback_data="sell:weapon_svd")],
            [InlineKeyboardButton(text="Продать РП-74 (4750)", callback_data="sell:weapon_rp74")],
            [InlineKeyboardButton(text="Продать Гаусс-пушку (12500)", callback_data="sell:weapon_gauss")],
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
            [InlineKeyboardButton(text="⭐ 1 звезда (150 RU)", callback_data="topup:1")],
            [InlineKeyboardButton(text="⭐ 5 звезд (750 RU)", callback_data="topup:5")],
            [InlineKeyboardButton(text="⭐ 10 звезд (1500 RU)", callback_data="topup:10")],
            [InlineKeyboardButton(text="⭐ 25 звезд (3750 RU)", callback_data="topup:25")],
            [InlineKeyboardButton(text="⭐ Другое количество", callback_data="topup:custom")],
        ]
    )


def raid_keyboard(locations: list[dict[str, str | int | None]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Присоединиться к открытому рейду", callback_data="raid:join")],
        [InlineKeyboardButton(text="🤝 Союзник: присоединиться к рейду", callback_data="raid:ally:join")],
        [InlineKeyboardButton(text="🚀 Запустить мой открытый рейд", callback_data="raid:launch")],
    ]
    for location in locations:
        name = str(location["name"])
        rows.append([InlineKeyboardButton(text=f"Создать рейд на логово: {name}", callback_data=f"raid:create:{name}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def war_lobby_keyboard(locations: list[dict[str, str | int | None]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Вступить в военное лобби", callback_data="war_lobby:join")],
        [InlineKeyboardButton(text="🚀 Запустить военное лобби", callback_data="war_lobby:launch")],
    ]
    for location in locations:
        name = str(location["name"])
        rows.append([InlineKeyboardButton(text=f"Создать штурм-лобби: {name}", callback_data=f"war_lobby:create:{name}")])
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
            [InlineKeyboardButton(text="🪖 Военные лобби", callback_data="war:section:lobby")],
            [InlineKeyboardButton(text="🎯 Точка для штурма", callback_data="war:section:assault")],
        ]
    )


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
            [InlineKeyboardButton(text="🛒 Рынок: выставить экипировку", callback_data="eco:market:create:choose")],
            [InlineKeyboardButton(text="🛒 Рынок: список лотов экипировки", callback_data="eco:market:list")],
            [InlineKeyboardButton(text="🛑 Рынок: отменить мой лот", callback_data="eco:market:cancel:mine")],
            [InlineKeyboardButton(text="⚖️ Биржа: купить первый лот", callback_data="eco:auction:buy:first")],
            [InlineKeyboardButton(text="🛑 Биржа: отменить мой первый лот", callback_data="eco:auction:cancel:mine")],
            [InlineKeyboardButton(text="🚚 Контрабанда", callback_data="eco:smuggle:run")],
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ratings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
