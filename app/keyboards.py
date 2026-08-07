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
            [KeyboardButton(text="📟 КПК")],
            [KeyboardButton(text="🎒 Инвентарь"), KeyboardButton(text="📋 Задания")],
            [KeyboardButton(text="🛒 Торговец"), KeyboardButton(text="🏕 Вылазка")],
            [KeyboardButton(text="🛰 События"), KeyboardButton(text="👥 Группировка")],
            [KeyboardButton(text="🏦 Экономика"), KeyboardButton(text="ℹ️ Информация")],
            [KeyboardButton(text="⭐ Пополнить")],
        ],
        resize_keyboard=True,
    )


def pda_keyboard(*, is_leader: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="🧾 Профиль"), KeyboardButton(text="💬 Чаты")],
        [KeyboardButton(text="🏆 Рейтинг"), KeyboardButton(text="🗺 Карта")],
        [KeyboardButton(text="🎖 Достижения"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="👥 Игроки"), KeyboardButton(text="☠️ Смерти")],
    ]
    if is_leader:
        rows[-1].append(KeyboardButton(text="📣 Сбор"))
    rows.append([KeyboardButton(text="🔗 Реферальная система")])
    rows.append([KeyboardButton(text="⬅️ В меню")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def sortie_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚔️ Война"), KeyboardButton(text="🗺 Переход")],
            [KeyboardButton(text="🪖 Рейды"), KeyboardButton(text="👥 Кооп-вылазка")],
            [KeyboardButton(text="⬅️ В меню")],
        ],
        resize_keyboard=True,
    )


def quests_keyboard(
    *,
    contract_buttons: list[tuple[str, str]] | None = None,
    show_work: bool = False,
    show_turnin: bool = False,
    show_cancel: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if show_work:
        rows.append([InlineKeyboardButton(text="⚙️ Выполнить работу", callback_data="contract:work")])
    if show_turnin:
        rows.append([InlineKeyboardButton(text="📦 Сдать отчёт на базе", callback_data="contract:turnin")])
    for label, callback_data in contract_buttons or []:
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
    if show_cancel:
        rows.append([InlineKeyboardButton(text="❌ Отменить контракт", callback_data="contract:cancel")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="contract:refresh")])
    rows.append([InlineKeyboardButton(text="🚚 Контрабанда", callback_data="eco:smuggle:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def travel_keyboard(
    locations: list[dict[str, str | int | None]],
    *,
    traveling: bool = False,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if traveling:
        rows.append([InlineKeyboardButton(text="⏱ Статус перехода", callback_data="travel:status")])
    else:
        for location in locations:
            name = str(location["name"])
            ptype = str(location["point_type"])
            owner = location["controlled_by"] or "нейтрал"
            label = f"{name} [{ptype}, {owner}]"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"travel:to:{name}")])
    if back_callback:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def travel_transport_keyboard(
    destination: str,
    modes: list[tuple[str, str]],
    *,
    back_callback: str = "travel:back",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=f"travel:go:{mode}:{destination}")]
        for mode, label in modes
    ]
    rows.append([InlineKeyboardButton(text="⬅️ К локациям", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def smuggle_transport_keyboard(
    destination: str,
    modes: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=f"eco:smuggle:go:{mode}:{destination}")]
        for mode, label in modes
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="eco:smuggle:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [InlineKeyboardButton(text="🛠 Прочее", callback_data="trade:buy:gear:0")],
            [InlineKeyboardButton(text="🦺 Броня", callback_data="trade:buy:armor:0")],
            [InlineKeyboardButton(text="🔫 Оружие", callback_data="trade:buy:weapons:0")],
            [InlineKeyboardButton(text="🔧 Ремонт", callback_data="trade:buy:repair")],
            [InlineKeyboardButton(text="⬅️ Назад в Торговец", callback_data="trade:menu:root")],
        ]
    )


BUY_CONSUMABLE_AMOUNTS: tuple[int, ...] = (1, 5, 10, 25)


def trader_buy_consumables_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Энергетик (от 250)", "buyqty:energy_drink"),
        ("Аптечка (от 260)", "buyqty:medkit"),
        ("Армейская аптечка (от 450)", "buyqty:medkit_army"),
        ("Научная аптечка (от 600)", "buyqty:medkit_science"),
        ("Патроны (от 120)", "buyqty:ammo_pack"),
        ("Водка (от 150)", "buyqty:vodka"),
        ("Антирад (от 400)", "buyqty:antirad"),
        ("Хлеб (от 50)", "buyqty:bread"),
        ("Колбаса (от 100)", "buyqty:sausage"),
        ("Тушёнка (от 250)", "buyqty:stew"),
        ("Вода (от 50)", "buyqty:water_bottle"),
        ("Минералка (от 100)", "buyqty:mineral_water"),
        ("Чай Бороды (от 250)", "buyqty:beard_tea"),
        ("Дизель +5 (от 450)", "buyqty:diesel_can"),
        ("Бензин +5 (от 225)", "buyqty:gasoline_can"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:buy:consumables",
        back_callback="trade:menu:buy",
        back_text="⬅️ Назад к категориям покупки",
    )


def trader_buy_consumable_qty_keyboard(item_key: str, *, unit_price: int, title: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for amount in BUY_CONSUMABLE_AMOUNTS:
        total = unit_price * amount
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"×{amount} — {total} RU",
                    callback_data=f"buy:{item_key}:{amount}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад к расходникам", callback_data="trade:buy:consumables:0")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trader_buy_gear_keyboard(*, page: int = 0) -> InlineKeyboardMarkup:
    items = [
        ("Купить детектор «Отклик» (1000)", "buy:detector_otklik"),
        ("Купить детектор «Медведь» (4000)", "buy:detector_medved"),
        ("Купить детектор «Велес» (10000)", "buy:detector_veles"),
        ("Купить детектор «Сварог» (30000)", "buy:detector_svarog"),
        ("Купить Ниву (10000)", "buy:niva"),
        ("Купить велосипед (3500)", "buy:bicycle"),
        ("Купить грузовик (50000)", "buy:truck"),
        ("Купить спальник (20000)", "buy:sleeping_bag"),
        ("Купить тайник (2000)", "buy:stash_case"),
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
            [InlineKeyboardButton(text="Купить улучшение брони (+1 защита, 5000 RU)", callback_data="upgrade:armor")],
            [InlineKeyboardButton(text="Ремонт грузовика", callback_data="repair:truck")],
            [InlineKeyboardButton(text="Ремонт Нивы", callback_data="repair:niva")],
            [InlineKeyboardButton(text="⬅️ Назад к категориям покупки", callback_data="trade:menu:buy")],
        ]
    )


def inventory_equipment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧰 Расходники", callback_data="inventory:consumables")],
            [InlineKeyboardButton(text="🗄 Схрон", callback_data="stash:menu")],
            [InlineKeyboardButton(text="📦 Открыть тайник", callback_data="use:stash_case")],
            [InlineKeyboardButton(text="📡 Поиск артефактов", callback_data="artifact:search")],
            [InlineKeyboardButton(text="⚙️ Экипировка", callback_data="equip:root")],
        ]
    )


def artifact_hunt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬆️", callback_data="hunt:up"),
            ],
            [
                InlineKeyboardButton(text="⬅️", callback_data="hunt:left"),
                InlineKeyboardButton(text="⬇️", callback_data="hunt:down"),
                InlineKeyboardButton(text="➡️", callback_data="hunt:right"),
            ],
            [
                InlineKeyboardButton(text="🏃 Свалить", callback_data="hunt:leave"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="hunt:refresh"),
            ],
        ]
    )


def quest_mission_keyboard(*, medkits: int = 0) -> InlineKeyboardMarkup:
    med_label = f"💊 Аптечка ({medkits})" if medkits > 0 else "💊 Аптечка"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬆️ Вперёд", callback_data="qmission:up")],
            [
                InlineKeyboardButton(text="⬅️ Лево", callback_data="qmission:left"),
                InlineKeyboardButton(text="⬇️ Назад", callback_data="qmission:down"),
                InlineKeyboardButton(text="➡️ Право", callback_data="qmission:right"),
            ],
            [
                InlineKeyboardButton(text=med_label, callback_data="qmission:medkit"),
                InlineKeyboardButton(text="🔄", callback_data="qmission:refresh"),
            ],
            [InlineKeyboardButton(text="🏃 Свалить", callback_data="qmission:leave")],
        ]
    )


def personal_stash_menu_keyboard(*, at_home: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if at_home:
        rows.append([InlineKeyboardButton(text="📥 Положить в схрон", callback_data="stash:putlist:0")])
        rows.append([InlineKeyboardButton(text="📤 Забрать из схрона", callback_data="stash:takelist:0")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в инвентарь", callback_data="inventory:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def personal_stash_items_keyboard(
    buttons: list[tuple[str, str]],
    *,
    page: int,
    total_pages: int,
    page_prefix: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=label, callback_data=cb)] for label, cb in buttons
    ]
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"{page_prefix}:{page - 1}")
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=f"{page_prefix}:{page}",
            )
        )
        if page + 1 < total_pages:
            nav.append(
                InlineKeyboardButton(text="➡️", callback_data=f"{page_prefix}:{page + 1}")
            )
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К схрону", callback_data="stash:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def personal_stash_amount_keyboard(action: str, item_key: str, max_amount: int) -> InlineKeyboardMarkup:
    """action: put | take"""
    rows: list[list[InlineKeyboardButton]] = []
    choices = [1]
    if max_amount >= 5:
        choices.append(5)
    if max_amount >= 10:
        choices.append(10)
    if max_amount not in choices:
        choices.append(max_amount)
    for qty in choices:
        if qty > max_amount:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'📥' if action == 'put' else '📤'} {qty} шт.",
                    callback_data=f"stash:{action}qty:{item_key}:{qty}",
                )
            ]
        )
    back = "stash:putlist:0" if action == "put" else "stash:takelist:0"
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def inventory_consumables_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Выпить энергетик", callback_data="use:energy_drink")],
            [InlineKeyboardButton(text="🩹 Использовать аптечку (+25 HP)", callback_data="use:medkit")],
            [InlineKeyboardButton(text="🪖 Армейская аптечка (+50 HP)", callback_data="use:medkit_army")],
            [InlineKeyboardButton(text="🔬 Научная аптечка (+75 HP, −15 рад.)", callback_data="use:medkit_science")],
            [InlineKeyboardButton(text="🍸 Выпить водку (−20 рад.)", callback_data="use:vodka")],
            [InlineKeyboardButton(text="💉 Использовать антирад (−50 рад.)", callback_data="use:antirad")],
            [InlineKeyboardButton(text="🍞 Поесть хлеб (голод −10)", callback_data="use:bread")],
            [InlineKeyboardButton(text="🥓 Поесть колбасу (голод −20)", callback_data="use:sausage")],
            [InlineKeyboardButton(text="🥫 Поесть тушёнку (голод −50)", callback_data="use:stew")],
            [InlineKeyboardButton(text="💧 Выпить воду (жажда −10)", callback_data="use:water_bottle")],
            [InlineKeyboardButton(text="🧴 Выпить минералку (жажда −20)", callback_data="use:mineral_water")],
            [InlineKeyboardButton(text="🍵 Выпить чай Бороды (жажда −50)", callback_data="use:beard_tea")],
            [InlineKeyboardButton(text="⬅️ Назад в инвентарь", callback_data="inventory:open")],
        ]
    )


def inventory_actions_keyboard() -> InlineKeyboardMarkup:
    return inventory_equipment_keyboard()


def dead_character_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="♻️ Спасение на базе (500 RU)", callback_data="respawn:base")],
            [InlineKeyboardButton(text="☠️ Журнал смертей", callback_data="death:log")],
        ]
    )


def equip_root_keyboard(
    items: list[tuple[str, str, int]],
    *,
    can_install_upgrade: bool = False,
    can_remove_upgrade: bool = False,
) -> InlineKeyboardMarkup:
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
    if can_install_upgrade:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛡 Установить улучшение брони",
                    callback_data="equip:upgrade:install",
                )
            ]
        )
    if can_remove_upgrade:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛡 Снять улучшение брони",
                    callback_data="equip:upgrade:remove",
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
        ("Купить Кожаную куртку (1470)", "buy:armor_leather"),
        ("Купить Сталкерский бронежилет (2950)", "buy:armor_stalker_vest"),
        ("Купить Комбинезон «Заря» (3270)", "buy:armor_sunrise"),
        ("Купить ПСЗ-7 «Долг» (4750)", "buy:armor_psz7d"),
        ("Купить Берилл-5М (8670)", "buy:armor_berill5m"),
        ("Купить Костюм СЕВА (8840)", "buy:armor_seva"),
        ("Купить Научный костюм (16040)", "buy:armor_scientific"),
        ("Купить Экзоскелет (29450)", "buy:armor_exoskeleton"),
        ("Купить Носорог (90000)", "buy:armor_nosorog"),
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
        ("Купить ПМ (1470)", "buy:weapon_pm"),
        ("Купить Фора-12 (2130)", "buy:weapon_fora12"),
        ("Купить Обрез (1960)", "buy:weapon_sawedoff"),
        ("Купить Гадюка-5 (3600)", "buy:weapon_mp5"),
        ("Купить Chaser-13 (4090)", "buy:weapon_chaser13"),
        ("Купить АКС-74У (4250)", "buy:weapon_aks74u"),
        ("Купить АК-74 (5560)", "buy:weapon_ak74"),
        ("Купить СПАС-12 (6380)", "buy:weapon_spas12"),
        ("Купить TRs 301 (8180)", "buy:weapon_lr300"),
        ("Купить ИЛ86 (8510)", "buy:weapon_il86"),
        ("Купить АН-94 (8510)", "buy:weapon_an94"),
        ("Купить ГП37 (12930)", "buy:weapon_gp37"),
        ("Купить Винтарь ВС (14240)", "buy:weapon_vintar"),
        ("Купить СВДм-2 (14400)", "buy:weapon_svd"),
        ("Купить РП-74 (15550)", "buy:weapon_rp74"),
        ("Купить Гаусс-пушку (90000)", "buy:weapon_gauss"),
    ]
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix="trade:buy:weapons",
        back_callback="trade:menu:buy",
        back_text="⬅️ Назад к категориям покупки",
    )


def trader_sell_categories_keyboard(
    items: list[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    if items is None:
        items = [
            ("🧰 Расходники", "trade:sell:consumables:0"),
            ("💎 Трофеи", "trade:sell:trophies:0"),
            ("🛠 Прочее", "trade:sell:gear:0"),
            ("🦺 Броня", "trade:sell:armor:0"),
            ("🔫 Оружие", "trade:sell:weapons:0"),
        ]
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=title, callback_data=callback)] for title, callback in items
    ]
    if not rows:
        rows.append(
            [InlineKeyboardButton(text="Нечего продавать", callback_data="trade:menu:root")]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад в Торговец", callback_data="trade:menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _trader_sell_items_keyboard(
    items: list[tuple[str, str]],
    *,
    page: int,
    page_prefix: str,
) -> InlineKeyboardMarkup:
    if not items:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="В этой категории нечего продавать", callback_data="trade:menu:sell")],
                [InlineKeyboardButton(text="⬅️ Назад к категориям продажи", callback_data="trade:menu:sell")],
            ]
        )
    return _trader_page_keyboard(
        items,
        page=page,
        page_prefix=page_prefix,
        back_callback="trade:menu:sell",
        back_text="⬅️ Назад к категориям продажи",
    )


def trader_sell_consumables_keyboard(
    items: list[tuple[str, str]] | None = None,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    if items is None:
        items = [
            ("Продать энергетик (170)", "sell:energy_drink"),
            ("Продать аптечку (120)", "sell:medkit"),
            ("Продать армейскую аптечку (180)", "sell:medkit_army"),
            ("Продать научную аптечку (240)", "sell:medkit_science"),
            ("Продать патроны (55)", "sell:ammo_pack"),
            ("Продать водку (50)", "sell:vodka"),
            ("Продать антирад (130)", "sell:antirad"),
            ("Продать хлеб (16)", "sell:bread"),
            ("Продать колбасу (33)", "sell:sausage"),
            ("Продать тушёнку (83)", "sell:stew"),
            ("Продать воду (16)", "sell:water_bottle"),
            ("Продать минералку (33)", "sell:mineral_water"),
            ("Продать чай Бороды (83)", "sell:beard_tea"),
            ("Продать дизель +5 (200)", "sell:diesel_can"),
            ("Продать бензин +5 (100)", "sell:gasoline_can"),
        ]
    return _trader_sell_items_keyboard(items, page=page, page_prefix="trade:sell:consumables")


def trader_sell_trophies_keyboard(
    items: list[tuple[str, str]] | None = None,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    if items is None:
        items = [
            ("Продать артефакт Зоны (5000)", "sell:artifact"),
            ("Продать Арт «Сила» (1100)", "sell:artifact_power"),
            ("Продать Арт «Живучесть» (1100)", "sell:artifact_vitality"),
            ("Продать Арт «Антирад» (5000)", "sell:artifact_antirad"),
            ("Продать Слизь (350)", "sell:artifact_junk_slime"),
            ("Продать Ржавый болт (300)", "sell:artifact_junk_bolt"),
            ("Продать Дохлую батарейку (450)", "sell:artifact_junk_battery"),
            ("Продать Вспышку (500)", "sell:artifact_junk_flash"),
            ("Продать Аномальный камень (400)", "sell:artifact_junk_stone"),
            ("Продать Сгусток тумана (550)", "sell:artifact_junk_fog"),
            ("Продать Осколок (600)", "sell:artifact_junk_splinter"),
        ]
    return _trader_sell_items_keyboard(items, page=page, page_prefix="trade:sell:trophies")


def trader_sell_gear_keyboard(
    items: list[tuple[str, str]] | None = None,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    if items is None:
        items = [
            ("Продать детектор «Отклик» (330)", "sell:detector_otklik"),
            ("Продать детектор «Медведь» (1330)", "sell:detector_medved"),
            ("Продать детектор «Велес» (3330)", "sell:detector_veles"),
            ("Продать детектор «Сварог» (10000)", "sell:detector_svarog"),
            ("Продать спальник (10000)", "sell:sleeping_bag"),
            ("Продать велосипед (1500)", "sell:bicycle"),
            ("Продать Ниву (4500)", "sell:niva"),
            ("Продать грузовик (17500)", "sell:truck"),
            ("Продать тайник (500)", "sell:stash_case"),
        ]
    return _trader_sell_items_keyboard(items, page=page, page_prefix="trade:sell:gear")


def trader_sell_armor_keyboard(
    items: list[tuple[str, str]] | None = None,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    if items is None:
        items = [
            ("Продать Кожаную куртку (690)", "sell:armor_leather"),
            ("Продать Сталкерский бронежилет (1390)", "sell:armor_stalker_vest"),
            ("Продать Комбинезон «Заря» (1550)", "sell:armor_sunrise"),
            ("Продать Берилл-5М (4170)", "sell:armor_berill5m"),
            ("Продать Костюм СЕВА (4250)", "sell:armor_seva"),
            ("Продать Экзоскелет (14240)", "sell:armor_exoskeleton"),
            ("Продать Носорог (45000)", "sell:armor_nosorog"),
        ]
    return _trader_sell_items_keyboard(items, page=page, page_prefix="trade:sell:armor")


def trader_sell_weapons_keyboard(
    items: list[tuple[str, str]] | None = None,
    *,
    page: int = 0,
) -> InlineKeyboardMarkup:
    if items is None:
        items = [
            ("Продать ПМ (690)", "sell:weapon_pm"),
            ("Продать Фора-12 (1010)", "sell:weapon_fora12"),
            ("Продать Обрез (920)", "sell:weapon_sawedoff"),
            ("Продать Гадюка-5 (1720)", "sell:weapon_mp5"),
            ("Продать Chaser-13 (1960)", "sell:weapon_chaser13"),
            ("Продать АКС-74У (1960)", "sell:weapon_aks74u"),
            ("Продать АК-74 (2620)", "sell:weapon_ak74"),
            ("Продать СПАС-12 (3110)", "sell:weapon_spas12"),
            ("Продать TRs 301 (3930)", "sell:weapon_lr300"),
            ("Продать ИЛ86 (4090)", "sell:weapon_il86"),
            ("Продать АН-94 (4090)", "sell:weapon_an94"),
            ("Продать ГП37 (6380)", "sell:weapon_gp37"),
            ("Продать Винтарь ВС (7040)", "sell:weapon_vintar"),
            ("Продать СВДм-2 (7040)", "sell:weapon_svd"),
            ("Продать РП-74 (7530)", "sell:weapon_rp74"),
            ("Продать Гаусс-пушку (45000)", "sell:weapon_gauss"),
        ]
    return _trader_sell_items_keyboard(items, page=page, page_prefix="trade:sell:weapons")


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
    # Курс должен совпадать с TOPUP_RATE_RU_PER_STAR в app/bot.py (75 RU/звезда).
    rate = 75
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ 1 звезда ({rate} RU)", callback_data="topup:1")],
            [InlineKeyboardButton(text=f"⭐ 5 звезд ({5 * rate} RU)", callback_data="topup:5")],
            [InlineKeyboardButton(text=f"⭐ 10 звезд ({10 * rate} RU)", callback_data="topup:10")],
            [InlineKeyboardButton(text=f"⭐ 25 звезд ({25 * rate} RU)", callback_data="topup:25")],
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
        if str(location.get("point_type") or "") == "база":
            continue
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


def faction_group_keyboard(
    *,
    is_leader: bool = False,
    can_withdraw_warehouse: bool = False,
    can_withdraw_treasury: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="📦 Склад группировки", callback_data="faction:warehouse:view")],
        [InlineKeyboardButton(text="📥 Сдать 1 патроны на склад", callback_data="eco:warehouse:deposit:ammo_pack")],
        [InlineKeyboardButton(text="📥 Сдать 1 аптечку на склад", callback_data="eco:warehouse:deposit:medkit")],
        [InlineKeyboardButton(text="📥 Сдать 1 энергетик на склад", callback_data="eco:warehouse:deposit:energy_drink")],
        [InlineKeyboardButton(text="📥 Сдать 1 артефакт на склад", callback_data="eco:warehouse:deposit:artifact")],
        [InlineKeyboardButton(text="💰 Внести 500 RU в казну", callback_data="eco:treasury:deposit:500")],
        [InlineKeyboardButton(text="💰 Внести 1000 RU в казну", callback_data="eco:treasury:deposit:1000")],
        [InlineKeyboardButton(text="💰 Внести своё количество", callback_data="eco:treasury:deposit:custom")],
        [InlineKeyboardButton(text="🏚 Гараж: сдать канистру бензина", callback_data="faction:garage:deposit:gasoline")],
        [InlineKeyboardButton(text="🏚 Гараж: сдать канистру дизеля", callback_data="faction:garage:deposit:diesel")],
        [InlineKeyboardButton(text="🏚 Сдать Ниву в гараж", callback_data="faction:garage:deposit:niva")],
        [InlineKeyboardButton(text="🏚 Сдать грузовик в гараж", callback_data="faction:garage:deposit:truck")],
    ]
    if can_withdraw_warehouse:
        rows.extend(
            [
                [InlineKeyboardButton(text="📤 Забрать 1 патроны со склада", callback_data="eco:warehouse:withdraw:ammo_pack")],
                [InlineKeyboardButton(text="📤 Забрать 1 аптечку со склада", callback_data="eco:warehouse:withdraw:medkit")],
                [InlineKeyboardButton(text="📤 Забрать 1 энергетик со склада", callback_data="eco:warehouse:withdraw:energy_drink")],
                [InlineKeyboardButton(text="📤 Забрать 1 артефакт со склада", callback_data="eco:warehouse:withdraw:artifact")],
                [InlineKeyboardButton(text="🏚 Гараж: забрать канистру бензина", callback_data="faction:garage:withdraw:gasoline")],
                [InlineKeyboardButton(text="🏚 Гараж: забрать канистру дизеля", callback_data="faction:garage:withdraw:diesel")],
                [InlineKeyboardButton(text="🏚 Забрать Ниву из гаража", callback_data="faction:garage:withdraw:niva")],
                [InlineKeyboardButton(text="🏚 Забрать грузовик из гаража", callback_data="faction:garage:withdraw:truck")],
            ]
        )
    if can_withdraw_treasury:
        rows.extend(
            [
                [InlineKeyboardButton(text="🏦 Вывести 500 RU из казны", callback_data="eco:treasury:withdraw:500")],
                [InlineKeyboardButton(text="🏦 Вывести 1000 RU из казны", callback_data="eco:treasury:withdraw:1000")],
                [InlineKeyboardButton(text="🏦 Снять своё количество", callback_data="eco:treasury:withdraw:custom")],
            ]
        )
    if is_leader:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛡 Укрепить базу (10000 RU из казны)",
                    callback_data="faction:base:fortify",
                )
            ]
        )
        rows.append([InlineKeyboardButton(text="🎖 Назначить звание", callback_data="rank:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def economy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот артефакт", callback_data="eco:auction:create:artifact")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот арт «Сила»", callback_data="eco:auction:create:artifact_power")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот арт «Живучесть»", callback_data="eco:auction:create:artifact_vitality")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот арт «Антирад»", callback_data="eco:auction:create:artifact_antirad")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот патроны", callback_data="eco:auction:create:ammo_pack")],
            [InlineKeyboardButton(text="⚖️ Биржа: создать лот аптечки", callback_data="eco:auction:create:medkit")],
            [InlineKeyboardButton(text="🛒 Рынок: выставить экипировку", callback_data="eco:market:create:choose")],
            [InlineKeyboardButton(text="🛒 Рынок: список лотов экипировки", callback_data="eco:market:list")],
            [InlineKeyboardButton(text="🛑 Рынок: отменить мой лот", callback_data="eco:market:cancel:mine")],
            [InlineKeyboardButton(text="⚖️ Биржа: купить старейший лот", callback_data="eco:auction:buy:first")],
            [InlineKeyboardButton(text="🛑 Биржа: отменить мой старейший лот", callback_data="eco:auction:cancel:mine")],
            [InlineKeyboardButton(text="⚖️ Биржа: список лотов", callback_data="eco:auction:list")],
            [InlineKeyboardButton(text="🚚 Контрабанда: перевозка", callback_data="eco:smuggle:menu")],
        ]
    )


def smuggling_keyboard(
    destinations: list[str],
    *,
    has_active: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_active:
        rows.append([InlineKeyboardButton(text="📦 Сбросить груз", callback_data="eco:smuggle:abandon")])
        rows.append([InlineKeyboardButton(text="⏱ Статус рейса", callback_data="eco:smuggle:status")])
    else:
        for name in destinations:
            rows.append(
                [InlineKeyboardButton(text=f"→ {name}", callback_data=f"eco:smuggle:to:{name}")]
            )
        if not rows:
            rows.append([InlineKeyboardButton(text="Нет доступных точек", callback_data="alliance:none")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в экономику", callback_data="eco:menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
                    text=f"#{lot_id} {title} x{amount} • {price} RU • продавец {seller_id}",
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


def exchange_lots_keyboard(lots: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for lot in lots[:20]:
        lot_id = int(lot["id"])
        title = str(lot["title"])
        price = int(lot["price"])
        amount = int(lot["amount"])
        seller_id = int(lot["seller_id"])
        if lot.get("is_own"):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🛑 #{lot_id} {title} x{amount} • {price} RU (твой, отменить)",
                        callback_data=f"eco:auction:cancel:{lot_id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"#{lot_id} {title} x{amount} • {price} RU • продавец {seller_id}",
                        callback_data=f"eco:auction:buy:{lot_id}",
                    )
                ]
            )
    if not rows:
        rows.append([InlineKeyboardButton(text="Открытых лотов нет", callback_data="alliance:none")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в экономику", callback_data="eco:menu:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [InlineKeyboardButton(text="🏆 Топ сталкеров", callback_data="rating:page:0")],
        ]
    )


def rating_page_keyboard(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"rating:page:{page - 1}",
            )
        )
    nav.append(
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data=f"rating:page:{page}",
        )
    )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"rating:page:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
        rows.append([InlineKeyboardButton(text="Нет доступных группировок", callback_data="alliance:none")])
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


def duel_challenge_keyboard(challenger_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять дуэль",
                    callback_data=f"duel:accept:{challenger_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"duel:decline:{challenger_id}",
                )
            ],
        ]
    )


def duel_grid_keyboard(*, is_active_turn: bool, medkit_available: bool) -> InlineKeyboardMarkup:
    refresh_row = [
        InlineKeyboardButton(text="🔄 Обновить", callback_data="dgrid:refresh"),
        InlineKeyboardButton(text="🏳 Сдаться", callback_data="dgrid:forfeit"),
    ]
    if not is_active_turn:
        return InlineKeyboardMarkup(inline_keyboard=[refresh_row])
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🚶 ⬆️", callback_data="dgrid:move:up")],
        [
            InlineKeyboardButton(text="🚶 ⬅️", callback_data="dgrid:move:left"),
            InlineKeyboardButton(text="🚶 ⬇️", callback_data="dgrid:move:down"),
            InlineKeyboardButton(text="🚶 ➡️", callback_data="dgrid:move:right"),
        ],
        [InlineKeyboardButton(text="🔫 ⬆️", callback_data="dgrid:shoot:up")],
        [
            InlineKeyboardButton(text="🔫 ⬅️", callback_data="dgrid:shoot:left"),
            InlineKeyboardButton(text="🔫 ⬇️", callback_data="dgrid:shoot:down"),
            InlineKeyboardButton(text="🔫 ➡️", callback_data="dgrid:shoot:right"),
        ],
    ]
    if medkit_available:
        rows.append([InlineKeyboardButton(text="💊 Аптечка (1×)", callback_data="dgrid:medkit")])
    rows.append(refresh_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coop_menu_keyboard(*, in_lobby: bool, is_host: bool, lobby_id: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if in_lobby and lobby_id:
        if is_host:
            rows.append([InlineKeyboardButton(text="▶️ Начать вылазку", callback_data=f"coop:start:{lobby_id}")])
        rows.append([InlineKeyboardButton(text="🚪 Выйти из группы", callback_data="coop:leave")])
    else:
        rows.append([InlineKeyboardButton(text="➕ Создать группу", callback_data="coop:create")])
        rows.append([InlineKeyboardButton(text="🔍 Найти группу", callback_data="coop:list")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="coop:refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coop_lobby_list_keyboard(lobbies: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """(lobby_id, host_nickname, member_count)"""
    rows: list[list[InlineKeyboardButton]] = []
    for lobby_id, host_name, count in lobbies[:8]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"👥 {host_name} ({count}/3)",
                    callback_data=f"coop:join:{lobby_id}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Групп нет", callback_data="coop:refresh")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="coop:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coop_mission_keyboard(
    *, is_active_turn: bool, medkit_available: bool, evac_available: bool = False
) -> InlineKeyboardMarkup:
    refresh_row = [
        InlineKeyboardButton(text="🔄", callback_data="coop:refresh"),
        InlineKeyboardButton(text="🏃 Свалить", callback_data="coop:forfeit"),
    ]
    if not is_active_turn:
        return InlineKeyboardMarkup(inline_keyboard=[refresh_row])
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="⬆️", callback_data="coop:move:up")],
        [
            InlineKeyboardButton(text="⬅️", callback_data="coop:move:left"),
            InlineKeyboardButton(text="⬇️", callback_data="coop:move:down"),
            InlineKeyboardButton(text="➡️", callback_data="coop:move:right"),
        ],
    ]
    if medkit_available:
        rows.append([InlineKeyboardButton(text="💊 Аптечка", callback_data="coop:medkit")])
    if evac_available:
        rows.append([InlineKeyboardButton(text="🦺 Эвак", callback_data="coop:evac")])
    rows.append(refresh_row)
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


def players_faction_page_keyboard(
    faction_key: str,
    *,
    page: int,
    total_pages: int,
    players: list[dict[str, Any]] | None = None,
    self_id: int | None = None,
) -> InlineKeyboardMarkup:
    _ = (players, self_id)  # список ников/ID в тексте сообщения
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
