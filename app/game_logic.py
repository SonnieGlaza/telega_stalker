from __future__ import annotations

import random
from math import dist
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.faction_ranks import (
    leader_title,
    rank_by_key,
    ranks_for_faction,
    resolve_rank_title,
)
from app.skins import next_skin_progress, resolve_skin
from app.storage import Character, Storage


@dataclass(frozen=True)
class QuestType:
    key: str
    title: str
    max_success: int
    energy_cost: int
    reward_min: int
    reward_max: int
    ammo_required: int
    medkit_required: int


QUESTS: dict[str, QuestType] = {
    "easy": QuestType("easy", "Легко", 80, 10, 270, 410, 0, 0),
    "hard": QuestType("hard", "Средне", 70, 16, 400, 650, 0, 0),
    "heavy": QuestType("heavy", "Опасно", 60, 22, 550, 1000, 2, 1),
    "impossible": QuestType("impossible", "Невозможно", 50, 28, 700, 1500, 3, 1),
}


SHOP_ITEMS: dict[str, dict[str, int | str]] = {
    "energy_drink": {"name": "Энергетик", "buy_price": 250, "sell_price": 170},
    "medkit": {"name": "Аптечка", "buy_price": 260, "sell_price": 120},
    "ammo_pack": {"name": "Патроны", "buy_price": 120, "sell_price": 55},
    "artifact": {"name": "Артефакт Зоны", "buy_price": 0, "sell_price": 900},
    "artifact_power": {"name": "Арт «Сила»", "buy_price": 0, "sell_price": 1100},
    "artifact_vitality": {"name": "Арт «Живучесть»", "buy_price": 0, "sell_price": 1100},
    "vodka": {"name": "Водка", "buy_price": 150, "sell_price": 50},
    "antirad": {"name": "Антирад", "buy_price": 400, "sell_price": 130},
    "bread": {"name": "Хлеб", "buy_price": 50, "sell_price": 16},
    "sausage": {"name": "Колбаса", "buy_price": 100, "sell_price": 33},
    "stew": {"name": "Тушенка", "buy_price": 250, "sell_price": 83},
    "water_bottle": {"name": "Бутылка воды", "buy_price": 50, "sell_price": 16},
    "mineral_water": {"name": "Минералка", "buy_price": 100, "sell_price": 33},
    "beard_tea": {"name": "Чай Бороды", "buy_price": 250, "sell_price": 83},
    "detector_otklik": {"name": "Детектор «Отклик»", "buy_price": 1000, "sell_price": 330},
    "detector_medved": {"name": "Детектор «Медведь»", "buy_price": 4000, "sell_price": 1330},
    "detector_veles": {"name": "Детектор «Велес»", "buy_price": 10000, "sell_price": 3330},
    "detector_svarog": {"name": "Детектор «Сварог»", "buy_price": 30000, "sell_price": 10000},
    "gear_upgrade": {"name": "Улучшение снаряги", "buy_price": 1200, "sell_price": 0},
    "truck": {"name": "Грузовик", "buy_price": 50000, "sell_price": 0},
    "sleeping_bag": {"name": "Спальник", "buy_price": 30000, "sell_price": 10000},
    "fuel_can": {"name": "Канистра топлива (+5)", "buy_price": 450, "sell_price": 200},
    "stash_case": {"name": "Тайник", "buy_price": 1000, "sell_price": 200},
}

ARMOR_CATALOG: dict[str, dict[str, int | str]] = {
    "armor_leather": {"name": "Кожаная куртка", "buy_price": 900, "sell_price": 420},
    "armor_stalker_vest": {"name": "Сталкерский бронежилет", "buy_price": 1800, "sell_price": 850},
    "armor_psz7d": {"name": "ПСЗ-7 «Долг»", "buy_price": 2900, "sell_price": 1400},
    "armor_zarya": {"name": "Комбинезон «Заря»", "buy_price": 2000, "sell_price": 950},
    "armor_bulat": {"name": "Берилл-5М «Булат»", "buy_price": 5300, "sell_price": 2550},
    "armor_seva": {"name": "Костюм СЕВА", "buy_price": 5400, "sell_price": 2600},
    "armor_scientific": {"name": "Научный костюм", "buy_price": 9800, "sell_price": 4800},
    "armor_exo": {"name": "Экзоскелет", "buy_price": 18000, "sell_price": 8700},
    "armor_nosorog": {"name": "Носорог", "buy_price": 24000, "sell_price": 11600},
}

WEAPON_CATALOG: dict[str, dict[str, int | str]] = {
    "weapon_pm": {"name": "ПМ", "buy_price": 900, "sell_price": 420},
    "weapon_fort12": {"name": "Фора-12", "buy_price": 1300, "sell_price": 620},
    "weapon_sawedoff": {"name": "Обрез", "buy_price": 1200, "sell_price": 560},
    "weapon_chaser13": {"name": "Chaser-13", "buy_price": 2500, "sell_price": 1200},
    "weapon_spas12": {"name": "СПАС-12", "buy_price": 3900, "sell_price": 1900},
    "weapon_mp5": {"name": "Гадюка-5", "buy_price": 2200, "sell_price": 1050},
    "weapon_aks74u": {"name": "АКС-74У", "buy_price": 2600, "sell_price": 1200},
    "weapon_ak74": {"name": "АК-74", "buy_price": 3400, "sell_price": 1600},
    "weapon_lr300": {"name": "TRs 301", "buy_price": 5000, "sell_price": 2400},
    "weapon_il86": {"name": "ИЛ86", "buy_price": 5200, "sell_price": 2500},
    "weapon_gp37": {"name": "ГП37", "buy_price": 7900, "sell_price": 3900},
    "weapon_an94": {"name": "АН-94", "buy_price": 5200, "sell_price": 2500},
    "weapon_vintar": {"name": "Винтарь ВС", "buy_price": 8700, "sell_price": 4300},
    "weapon_svd": {"name": "СВДм-2", "buy_price": 8800, "sell_price": 4300},
    "weapon_rp74": {"name": "РП-74", "buy_price": 9500, "sell_price": 4600},
    "weapon_gauss": {"name": "Гаусс-пушка", "buy_price": 25000, "sell_price": 12500},
}

# Legacy callback alias used in keyboards.
WEAPON_CATALOG["weapon_fora12"] = WEAPON_CATALOG["weapon_fort12"]
ARMOR_CATALOG["armor_sunrise"] = ARMOR_CATALOG["armor_zarya"]
ARMOR_CATALOG["armor_berill5m"] = ARMOR_CATALOG["armor_bulat"]
ARMOR_CATALOG["armor_exoskeleton"] = ARMOR_CATALOG["armor_exo"]

SHOP_ITEMS.update(ARMOR_CATALOG)
SHOP_ITEMS.update(WEAPON_CATALOG)

# Координаты должны совпадать с app/zone_map.py, чтобы время перехода
# соответствовало визуальной дистанции на карте.
MAP_TRAVEL_POINTS: dict[str, tuple[int, int]] = {
    "Кордон": (110, 530),
    "Свалка": (250, 470),
    "Росток": (395, 410),
    "Армейские склады": (195, 250),
    "НИИ Агропром": (340, 320),
    "Янтарь": (735, 180),
    "Болото": (115, 365),
    "Темная долина": (510, 520),
    "Рыжий лес": (730, 235),
    "Радар": (740, 125),
}

WEAPON_RATING_BY_NAME: dict[str, int] = {
    "Нож": 1,
    "ПМ": 1,
    "Фора-12": 1,
    "Обрез": 1,
    "Гадюка-5": 2,
    "Chaser-13": 2,
    "АКС-74У": 2,
    "АК-74": 3,
    "СПАС-12": 3,
    "TRs 301": 4,
    "ИЛ86": 4,
    "АН-94": 4,
    "ГП37": 5,
    "Винтарь ВС": 5,
    "СВДм-2": 5,
    "РП-74": 5,
    "Гаусс-пушка": 6,
}

ARMOR_RATING_BY_NAME: dict[str, int] = {
    "Куртка новичка": 1,
    "Кожаная куртка": 1,
    "Сталкерский бронежилет": 2,
    "Комбинезон «Заря»": 2,
    "ПСЗ-7 «Долг»": 2,  # legacy item in old inventories
    "Берилл-5М «Булат»": 3,
    "Костюм СЕВА": 3,
    "Научный костюм": 3,
    "Экзоскелет": 4,
    "Носорог": 5,
}
# Совместимость с историческими названиями экипировки из старых сохранений.
ARMOR_RATING_BY_NAME.setdefault("Бронежилет сталкера", ARMOR_RATING_BY_NAME["Сталкерский бронежилет"])
ARMOR_RATING_BY_NAME.setdefault("Усиленный бронекостюм", ARMOR_RATING_BY_NAME["ПСЗ-7 «Долг»"])
ARMOR_RATING_BY_NAME.setdefault("Штурмовой экзоскелет", ARMOR_RATING_BY_NAME["Экзоскелет"])


ITEM_LABELS = {
    "energy_drink": "Энергетик",
    "medkit": "Аптечка",
    "ammo_pack": "Патроны",
    "artifact": "Артефакт Зоны",
    "artifact_power": "Арт «Сила»",
    "artifact_vitality": "Арт «Живучесть»",
    "vodka": "Водка",
    "antirad": "Антирад",
    "bread": "Хлеб",
    "sausage": "Колбаса",
    "stew": "Тушенка",
    "water_bottle": "Бутылка воды",
    "mineral_water": "Минералка",
    "beard_tea": "Чай Бороды",
    "detector_otklik": "Детектор «Отклик»",
    "detector_medved": "Детектор «Медведь»",
    "detector_veles": "Детектор «Велес»",
    "detector_svarog": "Детектор «Сварог»",
    "sleeping_bag": "Спальник",
    "stash_case": "Тайник",
    "armor_leather": "Кожаная куртка",
    "armor_stalker_vest": "Сталкерский бронежилет",
    "armor_psz7d": "ПСЗ-7 «Долг»",
    "armor_zarya": "Комбинезон «Заря»",
    "armor_bulat": "Берилл-5М «Булат»",
    "armor_seva": "Костюм СЕВА",
    "armor_scientific": "Научный костюм",
    "armor_exo": "Экзоскелет",
    "armor_nosorog": "Носорог",
    "armor_sunrise": "Комбинезон «Заря»",
    "armor_berill5m": "Берилл-5М «Булат»",
    "armor_exoskeleton": "Экзоскелет",
    "weapon_pm": "ПМ",
    "weapon_fort12": "Фора-12",
    "weapon_fora12": "Фора-12",
    "weapon_sawedoff": "Обрез",
    "weapon_chaser13": "Chaser-13",
    "weapon_spas12": "СПАС-12",
    "weapon_mp5": "Гадюка-5",
    "weapon_aks74u": "АКС-74У",
    "weapon_ak74": "АК-74",
    "weapon_lr300": "TRs 301",
    "weapon_il86": "ИЛ86",
    "weapon_gp37": "ГП37",
    "weapon_an94": "АН-94",
    "weapon_vintar": "Винтарь ВС",
    "weapon_svd": "СВДм-2",
    "weapon_rp74": "РП-74",
    "weapon_gauss": "Гаусс-пушка",
}

ARTIFACT_DETECTORS: tuple[tuple[str, str, int], ...] = (
    ("detector_otklik", "Отклик", 10),
    ("detector_medved", "Медведь", 20),
    ("detector_veles", "Велес", 35),
    ("detector_svarog", "Сварог", 50),
)

# Экипированные арты: бонус к силе и/или к запасу HP.
ARTIFACT_EQUIP_BONUSES: dict[str, dict[str, int]] = {
    "Артефакт Зоны": {"power": 2, "hp": 0},
    "Артефакт": {"power": 2, "hp": 0},  # старые сейвы
    "Арт «Сила»": {"power": 1, "hp": 0},
    "Арт «Живучесть»": {"power": 0, "hp": 10},
}
ARTIFACT_ENERGY_REGEN_NAMES = frozenset({"Артефакт Зоны", "Артефакт"})
ARTIFACT_INVENTORY_TO_NAME: dict[str, str] = {
    "artifact": "Артефакт Зоны",
    "artifact_power": "Арт «Сила»",
    "artifact_vitality": "Арт «Живучесть»",
}
ARTIFACT_NAME_TO_INVENTORY: dict[str, str] = {
    **{name: key for key, name in ARTIFACT_INVENTORY_TO_NAME.items()},
    "Артефакт": "artifact",  # старые сейвы
}
ARTIFACT_DROP_KEYS = ("artifact", "artifact_power", "artifact_vitality")
# Абсолютные шансы дропа (взаимоисключающие), %:
ARTIFACT_DROP_RATES_PERCENT: tuple[tuple[str, float], ...] = (
    ("artifact", 0.1),  # Артефакт Зоны
    ("artifact_power", 5.0),  # Арт «Сила»
    ("artifact_vitality", 5.0),  # Арт «Живучесть»
)


def roll_artifact_drop() -> str | None:
    """Ролл дропа арта по абсолютным шансам. None — ничего не выпало."""
    roll = random.uniform(0.0, 100.0)
    cumulative = 0.0
    for key, chance in ARTIFACT_DROP_RATES_PERCENT:
        cumulative += float(chance)
        if roll < cumulative:
            return key
    return None


def pick_weighted_artifact_key() -> str:
    """Выбор типа арта по весам (когда награда уже гарантирована)."""
    keys = [key for key, _ in ARTIFACT_DROP_RATES_PERCENT]
    weights = [float(chance) for _, chance in ARTIFACT_DROP_RATES_PERCENT]
    return random.choices(keys, weights=weights, k=1)[0]


EQUIP_PAGE_SIZE = 8
EQUIP_SLOT_LABELS = {
    "weapon": "Оружие",
    "armor": "Броня",
    "artifact": "Артефакты",
}

WAREHOUSE_ITEM_KEYS = ("ammo_pack", "medkit", "energy_drink", "artifact")
TREASURY_WITHDRAW_MIN_RANK = 5

# Дроп контрабанды (независимые роллы при успехе).
SMUGGLING_CONSUMABLE_CHANCE = 20  # аптечка / еда / вода — каждый тип отдельно
SMUGGLING_ARMOR_T2_CHANCE = 3
SMUGGLING_WEAPON_T1_CHANCE = 3
SMUGGLING_OTKLIK_CHANCE = 7

SMUGGLING_FOOD_DROP_KEYS = ("bread", "sausage", "stew")
SMUGGLING_WATER_DROP_KEYS = ("water_bottle", "mineral_water")
SMUGGLING_ARMOR_T2_KEYS = ("armor_stalker_vest", "armor_zarya")
SMUGGLING_WEAPON_T1_KEYS = ("weapon_pm", "weapon_sawedoff", "weapon_fort12")

# Тайники (кейсы): дроп с активностей + покупка у торговца.
STASH_ITEM_KEY = "stash_case"
STASH_ACTIVITY_DROP_CHANCE = 5  # %
STASH_CONSUMABLE_KEYS = (
    "medkit",
    "energy_drink",
    "ammo_pack",
    "vodka",
    "antirad",
    "bread",
    "sausage",
    "stew",
    "water_bottle",
    "mineral_water",
    "beard_tea",
)
# Шансы тира снаряги при открытии (броня ИЛИ оружие, не вместе), %:
# 1-2: 4%, 3: 2%, 4: 0.5%, 5: 0.01%
STASH_GEAR_TIER_CHANCES: tuple[tuple[int | tuple[int, int], float], ...] = (
    ((1, 2), 4.0),
    (3, 2.0),
    (4, 0.5),
    (5, 0.01),
)
STASH_ARMOR_BY_TIER: dict[int, tuple[str, ...]] = {
    1: ("armor_leather",),
    2: ("armor_stalker_vest", "armor_zarya"),
    3: ("armor_bulat", "armor_seva", "armor_scientific"),
    4: ("armor_exo",),
    5: ("armor_nosorog",),
}
STASH_WEAPON_BY_TIER: dict[int, tuple[str, ...]] = {
    1: ("weapon_pm", "weapon_fort12", "weapon_sawedoff"),
    2: ("weapon_mp5", "weapon_chaser13", "weapon_aks74u"),
    3: ("weapon_ak74", "weapon_spas12"),
    4: ("weapon_lr300", "weapon_il86", "weapon_an94"),
    5: ("weapon_gp37", "weapon_vintar", "weapon_svd", "weapon_rp74"),
}
STASH_CONSUMABLE_DROP_CHANCE = 40  # % на каждый тип расходника при открытии

AUCTION_DEFAULT_LOTS: dict[str, tuple[str, int, int]] = {
    "artifact": ("artifact", 1, 900),
    "artifact_power": ("artifact_power", 1, 1100),
    "artifact_vitality": ("artifact_vitality", 1, 1100),
    "ammo_pack": ("ammo_pack", 5, 520),
    "medkit": ("medkit", 2, 420),
}

MARKET_SELL_FEE_PERCENT = 30
EXCHANGE_SELL_FEE_PERCENT = 30
TRADER_EQUIPMENT_SELL_RATE = 1 / 3
RESOURCE_POINT_INCOME_PER_HOUR = 100
BASE_POINT_INCOME_PER_HOUR = 50
POINTS_INCOME_META_KEY = "points_income_last_at"
POINTS_INCOME_MAX_HOURS = 24
EMISSION_INTERVAL_HOURS = 6
EMISSION_WARN_60_MINUTES = 60
EMISSION_WARN_30_MINUTES = 30
EMISSION_META_AT = "emission_at"
EMISSION_META_WARN60 = "emission_warn60_sent"
EMISSION_META_WARN30 = "emission_warn30_sent"
ZONE_EVENT_META_NEXT_AT = "zone_event_next_at"
ZONE_EVENT_INTERVAL_MIN_MINUTES = 30
ZONE_EVENT_INTERVAL_MAX_MINUTES = 90

FACTION_HOME_BASE: dict[str, str] = {
    "Долг": "Росток",
    "Свобода": "Армейские склады",
    "Нейтралы": "Кордон",
    "Бандиты": "Свалка",
}

ZONE_EVENT_POOL: tuple[tuple[str, int, str], ...] = (
    ("mutant_swarm", 10, "Миграция мутантов: сопротивление на локации выросло."),
    ("bandit_ambush", 7, "Бандитские засады усилили гарнизон противника."),
    ("anomaly_flux", -6, "Аномальный шторм спутал вражеские патрули."),
    ("merc_support", 5, "Наемники временно усилили местных NPC."),
    ("silent_night", -4, "Тихая ночь: активность NPC снижена."),
)


GEAR_PROGRESS: tuple[tuple[int, str, str], ...] = (
    (0, "Куртка новичка", "Нож"),
    (4, "Бронежилет сталкера", "ПМ"),
    (8, "Усиленный бронекостюм", "АКС-74У"),
    (13, "Штурмовой экзоскелет", "АН-94"),
)

MAX_DURABILITY = 100
MIN_EFFECTIVE_DURABILITY = 15
RATING_REWARD = {
    "quest_success": 12,
    "quest_fail": 2,
    "war_success": 22,
    "war_fail": 6,
    "raid_success": 26,
    "raid_fail": 8,
    "smuggle_success": 10,
    "smuggle_fail": 3,
    "trade_action": 4,
}

QUEST_FAIL_PENALTY_RANGE: dict[str, tuple[int, int]] = {
    "easy": (30, 80),
    "hard": (60, 130),
    "heavy": (90, 170),
    "impossible": (120, 220),
}

RAID_ARTIFACT_REWARD_CAP = 2
RAID_ARTIFACT_MIN_ENEMY_POWER = 25
WAR_MIN_FACTION_MEMBERS = 5
MAX_FACTION_ALLIANCES = 2

SURVIVAL_ACTIVE_RADIATION_MIN = 1
SURVIVAL_ACTIVE_RADIATION_MAX = 3
SURVIVAL_ACTIVE_HUNGER_INC = 1
SURVIVAL_ACTIVE_THIRST_INC = 1
SURVIVAL_ACTIVE_HP_DRAIN_MIN = 1
SURVIVAL_ACTIVE_HP_DRAIN_MAX = 3

HUNGER_PASSIVE_PER_HOUR = 1
THIRST_PASSIVE_PER_HOUR = 1
SURVIVAL_TICK_MINUTES = 30
SURVIVAL_OVERLIMIT_HP_DRAIN = 10
TRANSFER_FEE_PERCENT = 30
TRUCK_WEAR_MIN = 5
TRUCK_WEAR_MAX = 15

SURVIVAL_CRAVING_THRESHOLD = 40
SURVIVAL_URGENT_THRESHOLD = 75
SURVIVAL_CRITICAL_THRESHOLD = 100

HUNGER_CRAVING_PHRASES: tuple[str, ...] = (
    "Как же есть хочется...",
    "Живот уже урчит.",
    "Был бы сейчас хлеб с колбасой...",
    "Зона кормит радиациями, а не обедом.",
    "Пора бы перекусить, брат.",
)
HUNGER_URGENT_PHRASES: tuple[str, ...] = (
    "Голод давит сильнее, чем отклик детектора.",
    "Есть хочется так, что готов сухарик у бандитов купить.",
    "Без еды далеко не уйду.",
    "Сил мало — нужно поесть.",
)
HUNGER_CRITICAL_PHRASES: tuple[str, ...] = (
    "Голод уже бьёт по здоровью — срочно ешь!",
    "Сил почти нет. Ищи еду в инвентаре!",
    "Так голоден, что Зона кажется пирожком.",
)
THIRST_CRAVING_PHRASES: tuple[str, ...] = (
    "Как же пить хочется...",
    "Горло пересохло.",
    "Вода бы сейчас — хоть глоток.",
    "Жажда напоминает о себе.",
    "Минералку бы... или хотя бы водички.",
)
THIRST_URGENT_PHRASES: tuple[str, ...] = (
    "Жажда мешает сосредоточиться.",
    "Язык прилип к небу.",
    "Без воды далеко не уйду.",
    "Пить хочется сильнее, чем артефакты искать.",
)
THIRST_CRITICAL_PHRASES: tuple[str, ...] = (
    "Жажда уже опасная — пей, пока не поздно!",
    "Горло сохнет. Срочно нужна вода!",
    "Обезвоживание бьёт по силам.",
)


@dataclass(frozen=True)
class AchievementRule:
    key: str
    title: str
    description: str
    reward_ru: int
    reward_rating: int
    check: Callable[[dict[str, int], Character], bool]


def _faction_controls_all_contestable_points(storage: Storage, faction: str | None) -> bool:
    """True, если группировка держит все точки, кроме баз ГП."""
    if not faction:
        return False
    contestable = [
        loc
        for loc in storage.get_locations()
        if str(loc.get("point_type") or "") != "база"
    ]
    if not contestable:
        return False
    return all(str(loc.get("controlled_by") or "") == faction for loc in contestable)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    text: str


REFERRAL_INVITER_BONUS_RU = 2000
REFERRAL_STARTER_PACK: tuple[tuple[str, int], ...] = (
    ("stew", 2),
    ("antirad", 1),
    ("water_bottle", 1),
    ("medkit", 1),
    ("weapon_pm", 1),
)


def parse_referral_payload(raw: str | None) -> int | None:
    """Извлекает telegram_id пригласившего из /start payload (ref_123 / ref123)."""
    token = (raw or "").strip()
    if not token:
        return None
    lowered = token.casefold()
    if lowered.startswith("ref_"):
        digits = token[4:]
    elif lowered.startswith("ref"):
        digits = token[3:]
    else:
        return None
    if not digits.isdigit():
        return None
    value = int(digits)
    return value if value > 0 else None


def build_referral_link(bot_username: str, telegram_id: int) -> str:
    username = (bot_username or "").lstrip("@").strip()
    return f"https://t.me/{username}?start=ref_{int(telegram_id)}"


def apply_referral_rewards(
    storage: Storage,
    invitee_id: int,
    referrer_id: int | None,
) -> ActionResult:
    """Награда за реферал: пригласивший +2000 RU, новичок — стартовый набор."""
    if referrer_id is None:
        return ActionResult(False, "Реферал не указан.")
    if int(referrer_id) == int(invitee_id):
        return ActionResult(False, "Нельзя пригласить самого себя.")
    if not storage.character_exists(int(referrer_id)):
        return ActionResult(False, "Пригласивший ещё не зарегистрирован в Зоне.")
    if storage.has_referral_claim(int(invitee_id)):
        return ActionResult(False, "Стартовый набор по рефералу уже получен.")
    if not storage.record_referral(invitee_id=int(invitee_id), referrer_id=int(referrer_id)):
        return ActionResult(False, "Не удалось зафиксировать реферал.")

    for item_key, amount in REFERRAL_STARTER_PACK:
        storage.add_item(int(invitee_id), item_key, amount)
    storage.change_money(int(referrer_id), REFERRAL_INVITER_BONUS_RU)

    pack_text = ", ".join(
        f"{ITEM_LABELS.get(key, key)} x{amount}" for key, amount in REFERRAL_STARTER_PACK
    )
    return ActionResult(
        True,
        f"Реферал засчитан.\n"
        f"Тебе стартовый набор: {pack_text}.\n"
        f"Пригласивший получил {REFERRAL_INVITER_BONUS_RU} RU.",
    )


@dataclass(frozen=True)
class RaidLaunchResult:
    ok: bool
    text: str
    notify_member_ids: tuple[int, ...]


@dataclass(frozen=True)
class QuestChanceBreakdown:
    chance: int
    base_chance: int
    gear_bonus: int
    ammo_bonus: int
    medkit_bonus: int


def resolve_equipment_by_power(gear_power: int) -> tuple[str, str]:
    armor = GEAR_PROGRESS[0][1]
    weapon = GEAR_PROGRESS[0][2]
    for threshold, armor_name, weapon_name in GEAR_PROGRESS:
        if gear_power >= threshold:
            armor = armor_name
            weapon = weapon_name
    return armor, weapon


def _durability_percent(character: Character, slot: str) -> int:
    key = f"{slot}_durability"
    raw = character.equipment.get(key, MAX_DURABILITY)
    if isinstance(raw, (int, float)):
        value = int(raw)
    else:
        try:
            value = int(str(raw))
        except ValueError:
            value = MAX_DURABILITY
    return max(0, min(MAX_DURABILITY, value))


def _durability_penalty(percent: int, max_penalty: int) -> int:
    if percent >= MIN_EFFECTIVE_DURABILITY:
        return 0
    missing = MIN_EFFECTIVE_DURABILITY - percent
    return int(round((missing / MIN_EFFECTIVE_DURABILITY) * max_penalty))


def equipment_power(character: Character) -> int:
    weapon_name = str(character.equipment.get("weapon", "Нож"))
    armor_name = str(character.equipment.get("armor", "Куртка новичка"))
    artifact_name = str(character.equipment.get("artifact", "Нет"))
    weapon_durability = _durability_percent(character, "weapon")
    armor_durability = _durability_percent(character, "armor")

    weapon_level = _weapon_rating(weapon_name)
    armor_level = _armor_rating(armor_name)
    if artifact_name in ARTIFACT_EQUIP_BONUSES:
        artifact_bonus = int(ARTIFACT_EQUIP_BONUSES[artifact_name].get("power", 0))
    elif artifact_name and artifact_name != "Нет":
        # Старые сейвы с неизвестным артом — как базовый.
        artifact_bonus = 2
    else:
        artifact_bonus = 0
    durability_penalty = _durability_penalty(weapon_durability, 6) + _durability_penalty(armor_durability, 6)
    return max(1, weapon_level + armor_level + artifact_bonus - durability_penalty)


def _artifact_hp_bonus(character: Character) -> int:
    artifact_name = str(character.equipment.get("artifact", "Нет"))
    return int(ARTIFACT_EQUIP_BONUSES.get(artifact_name, {}).get("hp", 0))


def effective_max_health(character: Character) -> int:
    return 100 + max(0, _artifact_hp_bonus(character))


def compute_total_gear_power(character: Character) -> int:
    return equipment_power(character)


def _apply_durability_decay(storage: Storage, telegram_id: int, weapon_loss: int, armor_loss: int) -> str:
    character = storage.get_character(telegram_id, refresh_energy=False)
    if character is None:
        return ""
    weapon_old = _durability_percent(character, "weapon")
    armor_old = _durability_percent(character, "armor")
    weapon_new = max(0, weapon_old - max(0, weapon_loss))
    armor_new = max(0, armor_old - max(0, armor_loss))
    if weapon_new == weapon_old and armor_new == armor_old:
        return ""
    storage.update_equipment_fields(
        telegram_id,
        {"weapon_durability": weapon_new, "armor_durability": armor_new},
    )
    warning = ""
    if weapon_new <= 10 or armor_new <= 10:
        warning = "\n⚠️ Снаряжение на грани поломки: загляни в ремонт у торговца."
    return (
        f"\nИзнос: оружие {weapon_old}%→{weapon_new}%, броня {armor_old}%→{armor_new}%."
        f"{warning}"
    )


RESPAWN_HEALTH = 60
RESPAWN_ENERGY = 60
RESPAWN_COST_RU = 500


def faction_home_base(faction: str | None) -> str:
    if not faction:
        return FACTION_HOME_BASE["Долг"]
    return FACTION_HOME_BASE.get(faction, FACTION_HOME_BASE["Долг"])


def _is_dead(character: Character) -> bool:
    return character.health <= 0


def _pick_survival_phrase(phrases: tuple[str, ...]) -> str:
    return random.choice(phrases)


def build_survival_craving_notice(character: Character) -> str:
    if _is_dead(character):
        return ""
    lines: list[str] = []
    if character.hunger >= SURVIVAL_CRITICAL_THRESHOLD:
        lines.append(_pick_survival_phrase(HUNGER_CRITICAL_PHRASES))
    elif character.hunger >= SURVIVAL_URGENT_THRESHOLD:
        lines.append(_pick_survival_phrase(HUNGER_URGENT_PHRASES))
    elif character.hunger >= SURVIVAL_CRAVING_THRESHOLD:
        lines.append(_pick_survival_phrase(HUNGER_CRAVING_PHRASES))
    if character.thirst >= SURVIVAL_CRITICAL_THRESHOLD:
        lines.append(_pick_survival_phrase(THIRST_CRITICAL_PHRASES))
    elif character.thirst >= SURVIVAL_URGENT_THRESHOLD:
        lines.append(_pick_survival_phrase(THIRST_URGENT_PHRASES))
    elif character.thirst >= SURVIVAL_CRAVING_THRESHOLD:
        lines.append(_pick_survival_phrase(THIRST_CRAVING_PHRASES))
    if not lines:
        return ""
    return "💬 " + "\n💬 ".join(lines) + "\n\n"


def append_survival_craving_notice(storage: Storage, telegram_id: int, text: str) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return text
    notice = build_survival_craving_notice(player)
    if not notice:
        return text
    return notice + text


def _dead_block_text() -> str:
    return "Персонаж мертв (HP=0). Используй респавн из инвентаря."


def build_dead_character_text(character: Character) -> str:
    max_hp = effective_max_health(character)
    return (
        f"☠️ {character.nickname}, ты погиб в Зоне.\n"
        f"HP: {character.health}/{max_hp}\n"
        f"Локация: {character.location}\n"
        f"Для продолжения нужен респавн.\n"
        f"Стоимость: {RESPAWN_COST_RU} RU."
    )


def respawn_character(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if not _is_dead(player):
        return ActionResult(False, "Респавн доступен только при HP=0.")
    if not storage.change_money(telegram_id, -RESPAWN_COST_RU):
        return ActionResult(False, f"Недостаточно денег для респавна ({RESPAWN_COST_RU} RU).")
    current_health = player.health
    current_energy = player.energy
    storage.change_health(telegram_id, RESPAWN_HEALTH - current_health)
    storage.restore_energy(telegram_id, RESPAWN_ENERGY - current_energy)
    home = faction_home_base(player.faction)
    storage.set_location(telegram_id, home)
    return ActionResult(
        True,
        f"Ты был эвакуирован в «{home}».\n"
        f"HP восстановлено до {RESPAWN_HEALTH}, энергия до {RESPAWN_ENERGY}.\n"
        f"Списано за респавн: {RESPAWN_COST_RU} RU.",
    )


def _add_rating(storage: Storage, telegram_id: int, amount: int) -> None:
    if amount == 0:
        return
    storage.add_player_stat(telegram_id, "rating_points", amount)


def _achievement_rules() -> tuple[AchievementRule, ...]:
    return (
        AchievementRule(
            key="quest_5",
            title="Полевой сталкер",
            description="Выполни 5 заданий",
            reward_ru=300,
            reward_rating=20,
            check=lambda stats, _: stats["quests_completed"] >= 5,
        ),
        AchievementRule(
            key="quest_25",
            title="Легенда поручений",
            description="Выполни 25 заданий",
            reward_ru=900,
            reward_rating=65,
            check=lambda stats, _: stats["quests_completed"] >= 25,
        ),
        AchievementRule(
            key="quest_50",
            title="Сталкер без выходных",
            description="Выполни 50 заданий",
            reward_ru=1500,
            reward_rating=90,
            check=lambda stats, _: stats["quests_completed"] >= 50,
        ),
        AchievementRule(
            key="quest_100",
            title="Старый болот",
            description="Выполни 100 заданий",
            reward_ru=2500,
            reward_rating=120,
            check=lambda stats, _: stats["quests_completed"] >= 100,
        ),
        AchievementRule(
            key="raid_5",
            title="Рейд-лидер",
            description="Заверши 5 успешных рейдов",
            reward_ru=700,
            reward_rating=55,
            check=lambda stats, _: stats["raids_completed"] >= 5,
        ),
        AchievementRule(
            key="raid_15",
            title="Мастер налётов",
            description="Заверши 15 успешных рейдов",
            reward_ru=1200,
            reward_rating=75,
            check=lambda stats, _: stats["raids_completed"] >= 15,
        ),
        AchievementRule(
            key="raid_30",
            title="Король логова",
            description="Заверши 30 успешных рейдов",
            reward_ru=2000,
            reward_rating=100,
            check=lambda stats, _: stats["raids_completed"] >= 30,
        ),
        AchievementRule(
            key="war_3",
            title="Захватчик",
            description="Выиграй 3 штурма точек",
            reward_ru=600,
            reward_rating=45,
            check=lambda stats, _: stats["wars_won"] >= 3,
        ),
        AchievementRule(
            key="war_10",
            title="Полководец Зоны",
            description="Выиграй 10 штурмов точек",
            reward_ru=1500,
            reward_rating=85,
            check=lambda stats, _: stats["wars_won"] >= 10,
        ),
        AchievementRule(
            key="enemy_base_1",
            title="Штурм вражеской базы",
            description="Захвати вражескую базу группировки",
            reward_ru=1200,
            reward_rating=80,
            check=lambda stats, _: stats["enemy_bases_captured"] >= 1,
        ),
        AchievementRule(
            key="zone_overlord",
            title="Повелитель Зоны",
            description="Захвати все точки Зоны (кроме баз группировок)",
            reward_ru=3000,
            reward_rating=150,
            # Проверка идёт через карту в _progress_and_unlock_achievements.
            check=lambda _stats, _char: False,
        ),
        AchievementRule(
            key="smuggle_10",
            title="Контрабандист",
            description="Успешно проведи 10 контрабанд",
            reward_ru=500,
            reward_rating=35,
            check=lambda stats, _: stats["smuggling_success"] >= 10,
        ),
        AchievementRule(
            key="smuggle_25",
            title="Теневой барон",
            description="Успешно проведи 25 контрабанд",
            reward_ru=900,
            reward_rating=60,
            check=lambda stats, _: stats["smuggling_success"] >= 25,
        ),
        AchievementRule(
            key="trade_30",
            title="Барыга Зоны",
            description="Соверши 30 сделок у торговца",
            reward_ru=550,
            reward_rating=40,
            check=lambda stats, _: stats["trades_done"] >= 30,
        ),
        AchievementRule(
            key="trade_100",
            title="Оптовик",
            description="Соверши 100 сделок у торговца",
            reward_ru=800,
            reward_rating=55,
            check=lambda stats, _: stats["trades_done"] >= 100,
        ),
        AchievementRule(
            key="money_5000",
            title="Первый капитал",
            description="Заработай суммарно 5 000 RU",
            reward_ru=400,
            reward_rating=25,
            check=lambda stats, _: stats["money_earned"] >= 5_000,
        ),
        AchievementRule(
            key="money_20000",
            title="Толстый кошелек",
            description="Заработай суммарно 20 000 RU",
            reward_ru=1200,
            reward_rating=80,
            check=lambda stats, _: stats["money_earned"] >= 20_000,
        ),
        AchievementRule(
            key="money_50000",
            title="Банкир Зоны",
            description="Заработай суммарно 50 000 RU",
            reward_ru=2500,
            reward_rating=120,
            check=lambda stats, _: stats["money_earned"] >= 50_000,
        ),
        AchievementRule(
            key="artifact_5",
            title="Собиратель",
            description="Найди 5 артефактов",
            reward_ru=400,
            reward_rating=30,
            check=lambda stats, _: stats["artifacts_found"] >= 5,
        ),
        AchievementRule(
            key="artifact_20",
            title="Артефактщик",
            description="Найди 20 артефактов",
            reward_ru=1000,
            reward_rating=65,
            check=lambda stats, _: stats["artifacts_found"] >= 20,
        ),
        AchievementRule(
            key="artifact_50",
            title="Магнит аномалий",
            description="Найди 50 артефактов",
            reward_ru=1800,
            reward_rating=90,
            check=lambda stats, _: stats["artifacts_found"] >= 50,
        ),
        AchievementRule(
            key="death_3",
            title="Бессмертный?",
            description="Погибни 3 раза",
            reward_ru=200,
            reward_rating=15,
            check=lambda stats, _: stats["deaths"] >= 3,
        ),
        AchievementRule(
            key="death_10",
            title="Частый гость Ростка",
            description="Погибни 10 раз",
            reward_ru=500,
            reward_rating=25,
            check=lambda stats, _: stats["deaths"] >= 10,
        ),
        AchievementRule(
            key="rating_500",
            title="Уважаемый сталкер",
            description="Достигни 500 рейтинга",
            reward_ru=400,
            reward_rating=30,
            check=lambda stats, _: stats["rating_points"] >= 500,
        ),
        AchievementRule(
            key="rating_1000",
            title="Имя в Зоне",
            description="Достигни 1000 рейтинга",
            reward_ru=800,
            reward_rating=50,
            check=lambda stats, _: stats["rating_points"] >= 1000,
        ),
        AchievementRule(
            key="rating_2500",
            title="Живая легенда",
            description="Достигни 2500 рейтинга",
            reward_ru=1200,
            reward_rating=75,
            check=lambda stats, _: stats["rating_points"] >= 2500,
        ),
        AchievementRule(
            key="rating_5000",
            title="Легенда",
            description="Достигни 5000 рейтинга",
            reward_ru=1500,
            reward_rating=100,
            check=lambda stats, _: stats["rating_points"] >= 5000,
        ),
        AchievementRule(
            key="gear_15",
            title="Бронированный",
            description="Доведи силу снаряжения до 15",
            reward_ru=500,
            reward_rating=35,
            check=lambda stats, char: int(char.gear_power) >= 15,
        ),
        AchievementRule(
            key="gear_20",
            title="Ходячий танк",
            description="Доведи силу снаряжения до 20",
            reward_ru=900,
            reward_rating=55,
            check=lambda stats, char: int(char.gear_power) >= 20,
        ),
        AchievementRule(
            key="truck_owned",
            title="Водитель",
            description="Купи грузовик",
            reward_ru=700,
            reward_rating=45,
            check=lambda _, char: bool(char.truck_owned),
        ),
        AchievementRule(
            key="sleeping_bag",
            title="Сон на земле",
            description="Купи спальник",
            reward_ru=350,
            reward_rating=25,
            check=lambda _, char: bool(char.sleeping_bag_owned),
        ),
        AchievementRule(
            key="achievements_10",
            title="Коллекционер медалей",
            description="Открой 10 достижений",
            reward_ru=600,
            reward_rating=40,
            check=lambda stats, _: stats["achievements_unlocked"] >= 10,
        ),
    )


ACHIEVEMENT_RULES = _achievement_rules()
ACHIEVEMENT_BY_KEY = {rule.key: rule for rule in ACHIEVEMENT_RULES}


def _progress_and_unlock_achievements(storage: Storage, telegram_id: int) -> str:
    character = storage.get_character(telegram_id, refresh_energy=False)
    if character is None:
        return ""
    stats = storage.get_player_stats(telegram_id)
    already = storage.get_player_achievement_keys(telegram_id)
    unlocked: list[AchievementRule] = []
    for rule in ACHIEVEMENT_RULES:
        if rule.key in already:
            continue
        if rule.key == "zone_overlord":
            ok = _faction_controls_all_contestable_points(storage, character.faction)
        else:
            ok = rule.check(stats, character)
        if not ok:
            continue
        if not storage.unlock_player_achievement(telegram_id, rule.key):
            continue
        storage.add_player_stat(telegram_id, "achievements_unlocked", 1)
        storage.change_money(telegram_id, rule.reward_ru)
        _add_rating(storage, telegram_id, rule.reward_rating)
        storage.add_player_stat(telegram_id, "money_earned", rule.reward_ru)
        unlocked.append(rule)
    if not unlocked:
        return ""
    lines = ["", "🏅 Новые достижения:"]
    for rule in unlocked:
        lines.append(
            f"• {rule.title} — {rule.description}. Награда: +{rule.reward_ru} RU, +{rule.reward_rating} рейтинга."
        )
    return "\n".join(lines)


def build_achievements_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return "Сначала создай персонажа через /start."
    stats = storage.get_player_stats(telegram_id)
    unlocked_rows = storage.list_player_achievements(telegram_id)
    unlocked_keys = {str(row["achievement_key"]) for row in unlocked_rows}
    total = len(ACHIEVEMENT_RULES)
    unlocked_count = len(unlocked_rows)
    recent_rows = unlocked_rows[-5:]
    recent_lines: list[str] = []
    for row in recent_rows:
        key = str(row["achievement_key"])
        rule = ACHIEVEMENT_BY_KEY.get(key)
        title = rule.title if rule else key
        recent_lines.append(f"• {title}")
    progress_lines = []
    for rule in ACHIEVEMENT_RULES:
        marker = "✅" if rule.key in unlocked_keys else "🔒"
        progress_lines.append(f"{marker} {rule.title} — {rule.description}")
    if not recent_lines:
        recent_lines = ["• Пока нет открытых достижений"]
    return (
        "🎖 Система достижений\n"
        "Выполняй задания, соревнуйся и забирай награды!\n\n"
        f"Открыто: {unlocked_count}/{total}\n"
        f"Рейтинг: {stats['rating_points']}\n"
        f"Получено RU за карьеру: {stats['money_earned']}\n\n"
        "Последние достижения:\n"
        f"{chr(10).join(recent_lines)}\n\n"
        "Прогресс:\n"
        f"{chr(10).join(progress_lines)}"
    )


def build_character_stats_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return "Сначала создай персонажа через /start."
    stats = storage.get_player_stats(telegram_id)
    return (
        f"📊 Статистика персонажа — {player.nickname}\n\n"
        f"📋 Заданий выполнено: {stats['quests_completed']}\n"
        f"🪖 Успешных рейдов: {stats['raids_completed']}\n"
        f"⚔️ Захватов точек: {stats['wars_won']}\n"
        f"🏛 Вражеских баз захвачено: {stats['enemy_bases_captured']}\n"
        f"💰 Денег накоплено: {stats['money_earned']} RU\n"
        f"🔮 Артефактов найдено: {stats['artifacts_found']}\n"
        f"☠️ Смертей: {stats['deaths']}\n\n"
        f"⭐ Рейтинг: {stats['rating_points']}\n"
        f"🏅 Достижений: {stats['achievements_unlocked']}"
    )


def build_rating_overview(storage: Storage, requester_id: int, limit: int = 10) -> str:
    top = storage.get_rating_leaderboard(limit=limit)
    if not top:
        return "🏆 Рейтинг пока пуст. Стань первым сталкером!"
    requester_rank = None
    lines = ["🏆 Рейтинг сталкеров (по очкам)"]
    for idx, row in enumerate(top, start=1):
        faction = row.get("faction") or "нейтрал"
        nickname = str(row.get("nickname") or f"Игрок {row.get('telegram_id')}")
        rating = int(row.get("rating_points") or 0)
        achievements = int(row.get("achievements_unlocked") or 0)
        marker = "👑 " if idx == 1 else ""
        lines.append(f"{idx}. {marker}{nickname} [{faction}] — {rating} очк., достижений {achievements}")
        if int(row.get("telegram_id") or 0) == requester_id:
            requester_rank = idx
    if requester_rank is None:
        all_top = storage.get_rating_leaderboard(limit=25)
        for idx, row in enumerate(all_top, start=1):
            if int(row.get("telegram_id") or 0) == requester_id:
                requester_rank = idx
                break
    if requester_rank is not None:
        lines.append(f"\nТвоя позиция: #{requester_rank}")
    return "\n".join(lines)


def calculate_equipment_bonus(character: Character) -> int:
    armor_name = character.equipment.get("armor", "")
    weapon_name = character.equipment.get("weapon", "")
    artifact_name = str(character.equipment.get("artifact", "Нет"))
    weapon_durability = _durability_percent(character, "weapon")
    armor_durability = _durability_percent(character, "armor")

    # Каждый уровень оружия/брони дает +1 к силе снаряжения (начиная с 1-го уровня).
    armor_bonus = _armor_rating(armor_name)
    weapon_bonus = _weapon_rating(weapon_name)
    if artifact_name in ARTIFACT_EQUIP_BONUSES:
        artifact_bonus = int(ARTIFACT_EQUIP_BONUSES[artifact_name].get("power", 0))
    elif artifact_name and artifact_name != "Нет":
        artifact_bonus = 2
    else:
        artifact_bonus = 0
    armor_penalty = _durability_penalty(armor_durability, max_penalty=6)
    weapon_penalty = _durability_penalty(weapon_durability, max_penalty=6)
    return max(0, armor_bonus + weapon_bonus + artifact_bonus - armor_penalty - weapon_penalty)


def calculate_quest_success(
    gear_power: int,
    max_success: int,
    ammo_stock: int,
    medkit_stock: int,
    ammo_required: int,
    medkit_required: int,
) -> QuestChanceBreakdown:
    """Шанс = база 18% + вклад снаряги/пушек + бонусы запасов, потолок по сложности."""
    gear_contrib = max(0, gear_power) * 4
    base_chance = 18
    extra_ammo = max(0, ammo_stock - ammo_required)
    extra_medkits = max(0, medkit_stock - medkit_required)
    ammo_bonus = min(18, extra_ammo * 2)
    medkit_bonus = min(12, extra_medkits * 4)
    chance = max(10, min(max_success, base_chance + gear_contrib + ammo_bonus + medkit_bonus))
    return QuestChanceBreakdown(
        chance=chance,
        base_chance=base_chance,
        gear_bonus=gear_contrib,
        ammo_bonus=ammo_bonus,
        medkit_bonus=medkit_bonus,
    )


def calculate_quest_success_for_quest(
    character: Character,
    quest: QuestType,
) -> QuestChanceBreakdown:
    """Шанс успеха по заданию: снаряга и оружие влияют, потолок — max_success сложности."""
    ammo_stock = int(character.inventory.get("ammo_pack", 0))
    medkit_stock = int(character.inventory.get("medkit", 0))
    return calculate_quest_success(
        gear_power=compute_total_gear_power(character),
        max_success=quest.max_success,
        ammo_stock=ammo_stock,
        medkit_stock=medkit_stock,
        ammo_required=quest.ammo_required,
        medkit_required=quest.medkit_required,
    )


def build_quest_overview(character: Character) -> str:
    ammo_stock = int(character.inventory.get("ammo_pack", 0))
    medkit_stock = int(character.inventory.get("medkit", 0))
    lines = [
        "Текущие запасы:",
        f"• Патроны: {ammo_stock}",
        f"• Аптечки: {medkit_stock}",
        f"• Энергия: {character.energy}/{character.max_energy}",
        "",
        "Сложности заданий (шанс растёт со снарягой, потолок по сложности):",
    ]
    for quest in QUESTS.values():
        chance = calculate_quest_success_for_quest(character, quest).chance
        if quest.ammo_required <= 0 and quest.medkit_required <= 0:
            lines.append(
                f"• {quest.title}: шанс ~{chance}%, энергия {quest.energy_cost}, без обязательного расхода"
            )
            continue
        lines.append(
            f"• {quest.title}: шанс ~{chance}%, энергия {quest.energy_cost}, "
            f"патроны {quest.ammo_required}, аптечки {quest.medkit_required}"
        )
    lines.extend(
        [
            "",
            "🚚 Контрабанда — отдельная активность (не сложность задания).",
        ]
    )
    return "\n".join(lines)


def quest_ammo_requirements(quest_key: str) -> dict[str, int]:
    quest = QUESTS.get(quest_key)
    if quest is None:
        return {"ammo_pack": 0, "medkit": 0}
    return {"ammo_pack": quest.ammo_required, "medkit": quest.medkit_required}


def calculate_quest_success_by_key(character: Character, quest_key: str) -> int:
    quest = QUESTS.get(quest_key)
    if quest is None:
        return 0
    return calculate_quest_success_for_quest(character, quest).chance


def run_quest(storage: Storage, telegram_id: int, quest_key: str) -> ActionResult:
    character = storage.get_character(telegram_id)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(character):
        return ActionResult(False, _dead_block_text())
    if character.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")

    quest = QUESTS.get(quest_key)
    if quest is None:
        return ActionResult(False, "Неизвестный тип задания.")

    ammo_stock = int(character.inventory.get("ammo_pack", 0))
    medkit_stock = int(character.inventory.get("medkit", 0))
    if ammo_stock < quest.ammo_required:
        return ActionResult(
            False,
            f"Недостаточно патронов. Для задания нужно {quest.ammo_required}, у тебя {ammo_stock}.",
        )
    if medkit_stock < quest.medkit_required:
        return ActionResult(
            False,
            f"Недостаточно аптечек. Для задания нужно {quest.medkit_required}, у тебя {medkit_stock}.",
        )

    if not storage.spend_energy(telegram_id, quest.energy_cost):
        return ActionResult(
            False,
            f"Не хватает энергии. Нужно {quest.energy_cost} ед., восстанови её или купи энергетик.",
        )
    if not storage.remove_item(telegram_id, "ammo_pack", quest.ammo_required):
        storage.restore_energy(telegram_id, quest.energy_cost)
        return ActionResult(False, "Ошибка расхода патронов, задание отменено.")
    if quest.medkit_required > 0 and not storage.remove_item(telegram_id, "medkit", quest.medkit_required):
        storage.add_item(telegram_id, "ammo_pack", quest.ammo_required)
        storage.restore_energy(telegram_id, quest.energy_cost)
        return ActionResult(False, "Ошибка расхода аптечек, задание отменено.")

    updated = storage.get_character(telegram_id, refresh_energy=False)
    if updated is None:
        return ActionResult(False, "Персонаж не найден.")

    breakdown = calculate_quest_success_for_quest(updated, quest)
    roll = random.randint(1, 100)
    success = roll <= breakdown.chance

    durability_text = _apply_durability_decay(storage, telegram_id, weapon_loss=3, armor_loss=2)
    if success:
        reward = random.randint(quest.reward_min, quest.reward_max)
        storage.change_money(telegram_id, reward)
        _add_rating(storage, telegram_id, RATING_REWARD["quest_success"])
        storage.add_player_stat(telegram_id, "quests_completed", 1)
        storage.add_player_stat(telegram_id, "money_earned", reward)

        art_key = roll_artifact_drop()
        if art_key is not None:
            storage.add_item(telegram_id, art_key, 1)
            storage.add_player_stat(telegram_id, "artifacts_found", 1)
            extra = f"\nТы нашел редкий артефакт: {ITEM_LABELS.get(art_key, art_key)}!"
        else:
            extra = ""
        stash_text = _maybe_drop_stash(storage, telegram_id)
        achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
        formula_line = (
            f"База {breakdown.base_chance}% (+снар {breakdown.gear_bonus}%) "
            f"+патр {breakdown.ammo_bonus}% +апт {breakdown.medkit_bonus}% "
            f"(потолок {quest.max_success}%)."
        )
        return ActionResult(
            True,
            f"«{quest.title}» выполнено! Шанс {breakdown.chance}% (бросок {roll}).\n"
            f"{formula_line}\n"
            f"Расход: патр {quest.ammo_required}, апт {quest.medkit_required}. "
            f"Награда: {reward} RU.{extra}{stash_text}{durability_text}{achievements_text}",
        )

    min_penalty, max_penalty = QUEST_FAIL_PENALTY_RANGE.get(quest.key, (50, 120))
    penalty = random.randint(min_penalty, max_penalty)
    storage.change_money(telegram_id, -penalty)
    _add_rating(storage, telegram_id, -RATING_REWARD["quest_fail"])
    storage.add_player_stat(telegram_id, "quests_failed", 1)
    return ActionResult(
        False,
        f"Провал задания «{quest.title}».\n"
        f"Расход: патроны {quest.ammo_required}, аптечки {quest.medkit_required}.\n"
        f"Потери на расходники: {penalty} RU.{durability_text}",
    )


def use_energy_drink(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if not storage.remove_item(telegram_id, "energy_drink", 1):
        return ActionResult(False, "У тебя нет энергетика в инвентаре.")
    storage.restore_energy(telegram_id, 35)
    return ActionResult(True, "Ты выпил энергетик и восстановил 35 энергии.")


def use_medkit(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    max_hp = effective_max_health(player)
    if player.health >= max_hp:
        return ActionResult(False, "Здоровье уже полное, аптечка не требуется.")
    if not storage.remove_item(telegram_id, "medkit", 1):
        return ActionResult(False, "У тебя нет аптечки в инвентаре.")
    heal_amount = min(25, max_hp - player.health)
    storage.change_health(telegram_id, heal_amount, max_health=max_hp)
    return ActionResult(True, f"Ты использовал аптечку и восстановил {heal_amount} HP.")


def _apply_active_survival(storage: Storage, telegram_id: int) -> str:
    radiation_gain = random.randint(SURVIVAL_ACTIVE_RADIATION_MIN, SURVIVAL_ACTIVE_RADIATION_MAX)
    hp_loss = random.randint(SURVIVAL_ACTIVE_HP_DRAIN_MIN, SURVIVAL_ACTIVE_HP_DRAIN_MAX)
    storage.adjust_survival(
        telegram_id,
        radiation_delta=radiation_gain,
        hunger_delta=SURVIVAL_ACTIVE_HUNGER_INC,
        thirst_delta=SURVIVAL_ACTIVE_THIRST_INC,
        health_delta=-hp_loss,
    )
    return f"\nВыживание: +{radiation_gain} рад., +1 голод, +1 жажда, -{hp_loss} HP."


def _consume_survival_item(
    storage: Storage,
    telegram_id: int,
    item_key: str,
    *,
    radiation_delta: int = 0,
    hunger_delta: int = 0,
    thirst_delta: int = 0,
    text: str,
) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if not storage.remove_item(telegram_id, item_key, 1):
        return ActionResult(False, f"У тебя нет предмета: {ITEM_LABELS.get(item_key, item_key)}.")
    storage.adjust_survival(
        telegram_id,
        radiation_delta=radiation_delta,
        hunger_delta=hunger_delta,
        thirst_delta=thirst_delta,
    )
    return ActionResult(True, text)


def use_vodka(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "vodka",
        radiation_delta=-20,
        text="Ты выпил водку. Радиация снижена на 20.",
    )


def use_antirad(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "antirad",
        radiation_delta=-50,
        text="Ты использовал антирад. Радиация снижена на 50.",
    )


def use_bread(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "bread",
        hunger_delta=-10,
        text="Ты съел хлеб. Голод снижен на 10.",
    )


def use_sausage(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "sausage",
        hunger_delta=-20,
        text="Ты съел колбасу. Голод снижен на 20.",
    )


def use_stew(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "stew",
        hunger_delta=-50,
        text="Ты съел тушенку. Голод снижен на 50.",
    )


def use_water(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "water_bottle",
        thirst_delta=-10,
        text="Ты выпил воду. Жажда снижена на 10.",
    )


def use_mineralka(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "mineral_water",
        thirst_delta=-20,
        text="Ты выпил минералку. Жажда снижена на 20.",
    )


def use_beard_tea(storage: Storage, telegram_id: int) -> ActionResult:
    return _consume_survival_item(
        storage,
        telegram_id,
        "beard_tea",
        thirst_delta=-50,
        text="Ты выпил чай Бороды. Жажда снижена на 50.",
    )


def _maybe_drop_stash(storage: Storage, telegram_id: int) -> str:
    """5% шанс найти тайник после успешной активности."""
    if random.randint(1, 100) > STASH_ACTIVITY_DROP_CHANCE:
        return ""
    storage.add_item(telegram_id, STASH_ITEM_KEY, 1)
    return f"\nНаходка: {ITEM_LABELS[STASH_ITEM_KEY]}!"


def _roll_stash_gear_tier() -> int | None:
    """Взаимоисключающий ролл тира снаряги. Без дропа — None."""
    roll = random.random() * 100.0
    cumulative = 0.0
    # Редкость сверху вниз (T5 → T1-2), шансы из STASH_GEAR_TIER_CHANCES.
    for tier_spec, chance in reversed(STASH_GEAR_TIER_CHANCES):
        cumulative += float(chance)
        if roll < cumulative:
            if isinstance(tier_spec, tuple):
                return int(random.choice(list(tier_spec)))
            return int(tier_spec)
    return None


def _roll_stash_loot(storage: Storage, telegram_id: int) -> list[str]:
    """Лут из тайника: расходники + броня ИЛИ оружие (не вместе)."""
    drops: list[str] = []

    for item_key in STASH_CONSUMABLE_KEYS:
        if random.randint(1, 100) > STASH_CONSUMABLE_DROP_CHANCE:
            continue
        amount = random.randint(1, 2)
        storage.add_item(telegram_id, item_key, amount)
        drops.append(f"{ITEM_LABELS.get(item_key, item_key)} x{amount}")

    # Гарантия хотя бы одного расходника, если ничего не выпало.
    if not drops:
        item_key = random.choice(STASH_CONSUMABLE_KEYS)
        amount = random.randint(1, 2)
        storage.add_item(telegram_id, item_key, amount)
        drops.append(f"{ITEM_LABELS.get(item_key, item_key)} x{amount}")

    tier = _roll_stash_gear_tier()
    if tier is not None:
        # Броня или оружие — взаимоисключающе.
        pool_kind = random.choice(("armor", "weapon"))
        pool = STASH_ARMOR_BY_TIER if pool_kind == "armor" else STASH_WEAPON_BY_TIER
        candidates = pool.get(tier, ())
        if candidates:
            gear_key = random.choice(candidates)
            storage.add_item(telegram_id, gear_key, 1)
            kind_label = "броня" if pool_kind == "armor" else "оружие"
            drops.append(f"{ITEM_LABELS.get(gear_key, gear_key)} (тир {tier}, {kind_label})")

    return drops


def open_stash(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if not storage.remove_item(telegram_id, STASH_ITEM_KEY, 1):
        return ActionResult(False, "У тебя нет тайника в инвентаре.")

    loot_lines = _roll_stash_loot(storage, telegram_id)
    loot_text = "\n".join(f"• {line}" for line in loot_lines)
    return ActionResult(
        True,
        f"Ты открыл тайник и нашёл:\n{loot_text}",
    )


def search_artifacts(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    chosen: tuple[str, str, int] | None = None
    for detector in reversed(ARTIFACT_DETECTORS):
        key, _, _ = detector
        if int(player.inventory.get(key, 0)) > 0:
            chosen = detector
            break
    if chosen is None:
        return ActionResult(
            False,
            "У тебя нет детектора. Купи его у торговца в разделе снаряжения.",
        )
    detector_key, detector_name, base_chance = chosen
    energy_cost = 12
    if not storage.spend_energy(telegram_id, energy_cost):
        return ActionResult(False, f"Не хватает энергии для поиска артов (нужно {energy_cost}).")
    event_bonus = max(0, _active_location_event_modifier(storage, player.location) // 2)
    gear_bonus = min(15, equipment_power(player) * 2)
    chance = max(5, min(90, base_chance + gear_bonus + event_bonus))
    roll = random.randint(1, 100)
    survival_text = _apply_active_survival(storage, telegram_id)
    if roll <= chance:
        art_key = pick_weighted_artifact_key()
        storage.add_item(telegram_id, art_key, 1)
        storage.add_player_stat(telegram_id, "artifacts_found", 1)
        return ActionResult(
            True,
            f"Поиск артефакта ({detector_name}) успешен!\n"
            f"Шанс: {chance}% (бросок {roll}).\n"
            f"Найдено: {ITEM_LABELS.get(art_key, art_key)} x1."
            f"{survival_text}",
        )
    return ActionResult(
        False,
        f"Поиск артефакта ({detector_name}) не дал результата.\n"
        f"Шанс: {chance}% (бросок {roll})."
        f"{survival_text}",
    )


def transfer_money_with_fee(storage: Storage, sender_id: int, target_id: int, amount: int) -> ActionResult:
    if amount <= 0:
        return ActionResult(False, "Сумма перевода должна быть положительной.")
    if sender_id == target_id:
        return ActionResult(False, "Нельзя переводить деньги самому себе.")
    sender = storage.get_character(sender_id, refresh_energy=False)
    target = storage.get_character(target_id, refresh_energy=False)
    if sender is None or target is None:
        return ActionResult(False, "Один из игроков не найден.")
    if _is_dead(sender):
        return ActionResult(False, _dead_block_text())
    fee = int(round(amount * 0.30))
    total = amount + fee
    if not storage.change_money(sender_id, -total):
        return ActionResult(False, f"Недостаточно денег. Нужно {total} RU (включая комиссию {fee} RU).")
    storage.change_money(target_id, amount)
    return ActionResult(
        True,
        f"Перевод выполнен: {amount} RU игроку {target.nickname}.\nКомиссия: {fee} RU.\nСписано: {total} RU.",
    )


def buy_item(storage: Storage, telegram_id: int, item_key: str) -> ActionResult:
    item = SHOP_ITEMS.get(item_key)
    if item is None:
        return ActionResult(False, "Такого товара нет у торговца.")
    price = int(item["buy_price"])
    title = str(item["name"])

    character = storage.get_character(telegram_id)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(character):
        return ActionResult(False, _dead_block_text())

    if item_key == "truck" and character.truck_owned:
        return ActionResult(False, "У тебя уже есть грузовик.")
    if item_key == "sleeping_bag" and character.sleeping_bag_owned:
        return ActionResult(False, "У тебя уже есть спальник.")
    if item_key == "gear_upgrade":
        return ActionResult(False, "Улучшение снаряги отключено. Сила теперь зависит от оружия и брони.")
    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, f"Недостаточно денег для покупки: {title}.")

    if item_key == "truck":
        storage.set_truck_owned(telegram_id)
        return ActionResult(True, "Покупка оформлена: грузовик теперь в твоем распоряжении.")
    if item_key == "sleeping_bag":
        storage.set_sleeping_bag_owned(telegram_id)
        return ActionResult(True, "Спальник куплен. Энергия теперь восстанавливается в 2 раза быстрее.")
    if item_key == "fuel_can":
        storage.change_fuel(telegram_id, 5)
        return ActionResult(True, f"Куплена канистра топлива. Топливо +5 (стоимость {price} RU).")
    if item_key in WEAPON_CATALOG:
        storage.add_item(telegram_id, item_key, 1)
        return ActionResult(
            True,
            f"Куплено оружие: {title} (стоимость {price} RU).\n"
            "Предмет добавлен в инвентарь, экипируй его вручную в разделе Инвентарь.",
        )
    if item_key in ARMOR_CATALOG:
        storage.add_item(telegram_id, item_key, 1)
        return ActionResult(
            True,
            f"Куплена броня: {title}.\n"
            "Предмет добавлен в инвентарь, экипируй его вручную в разделе Инвентарь.",
        )

    storage.add_item(telegram_id, item_key, 1)
    return ActionResult(True, f"Куплено: {title}.")


def sell_item(storage: Storage, telegram_id: int, item_key: str) -> ActionResult:
    item = SHOP_ITEMS.get(item_key)
    if item is None:
        return ActionResult(False, "Такого предмета нет.")
    sell_price = int(item["sell_price"])
    title = str(item["name"])
    if sell_price <= 0:
        return ActionResult(False, f"{title} торговец не выкупает.")
    character = storage.get_character(telegram_id, refresh_energy=False)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(character):
        return ActionResult(False, _dead_block_text())
    if item_key == "truck":
        if not character.truck_owned:
            return ActionResult(False, "У тебя нет грузовика для продажи.")
        storage.clear_truck_owned(telegram_id)
        storage.change_money(telegram_id, sell_price)
        return ActionResult(True, f"Продано: {title} за {sell_price} RU.")
    if item_key == "sleeping_bag":
        if not character.sleeping_bag_owned:
            return ActionResult(False, "У тебя нет спальника для продажи.")
        storage.clear_sleeping_bag_owned(telegram_id)
        storage.change_money(telegram_id, sell_price)
        return ActionResult(True, f"Продано: {title} за {sell_price} RU.")
    if item_key in WEAPON_CATALOG:
        weapon_name = str(item["name"])
        equipped_weapon = str(character.equipment.get("weapon", "Нож"))
        final_sell_price = sell_price
        if equipped_weapon == weapon_name:
            if weapon_name == "Нож":
                return ActionResult(False, "Нож продать нельзя.")
            weapon_durability = _durability_percent(character, "weapon")
            final_sell_price = _price_with_durability(sell_price, weapon_durability)
            storage.set_equipment_item(telegram_id, "weapon", "Нож")
        elif not storage.remove_item(telegram_id, item_key, 1):
            return ActionResult(False, f"У тебя нет оружия: {weapon_name}.")
        storage.change_money(telegram_id, final_sell_price)
        if final_sell_price != sell_price:
            return ActionResult(
                True,
                f"Продано: {title} за {final_sell_price} RU.\n"
                f"(Базовая цена {sell_price} RU снижена из-за износа.)",
            )
        return ActionResult(True, f"Продано: {title} за {final_sell_price} RU.")
    if item_key in ARMOR_CATALOG:
        armor_name = str(item["name"])
        equipped_armor = str(character.equipment.get("armor", "Куртка новичка"))
        final_sell_price = sell_price
        if equipped_armor == armor_name:
            armor_durability = _durability_percent(character, "armor")
            final_sell_price = _price_with_durability(sell_price, armor_durability)
            storage.set_equipment_item(telegram_id, "armor", "Куртка новичка")
        elif not storage.remove_item(telegram_id, item_key, 1):
            return ActionResult(False, f"У тебя нет брони: {armor_name}.")
        storage.change_money(telegram_id, final_sell_price)
        if final_sell_price != sell_price:
            return ActionResult(
                True,
                f"Продано: {title} за {final_sell_price} RU.\n"
                f"(Базовая цена {sell_price} RU снижена из-за износа.)",
            )
        return ActionResult(True, f"Продано: {title} за {final_sell_price} RU.")
    if item_key in ARTIFACT_INVENTORY_TO_NAME:
        removed_from_inventory = storage.remove_item(telegram_id, item_key, 1)
        if not removed_from_inventory:
            equipped_artifact = str(character.equipment.get("artifact", "Нет"))
            expected_name = ARTIFACT_INVENTORY_TO_NAME[item_key]
            if equipped_artifact == expected_name:
                storage.set_equipment_item(telegram_id, "artifact", "Нет")
                # После снятия арта «Живучесть» HP не выше 100.
                if character.health > 100:
                    storage.change_health(telegram_id, 100 - character.health, max_health=100)
                storage.sync_gear_power(telegram_id)
            else:
                return ActionResult(False, f"У тебя нет артефакта: {title}.")
        else:
            storage.sync_gear_power(telegram_id)
        storage.change_money(telegram_id, sell_price)
        return ActionResult(True, f"Продано: {title} за {sell_price} RU.")
    if item_key == "fuel_can":
        if not storage.change_fuel(telegram_id, -5):
            return ActionResult(False, "Недостаточно топлива для продажи канистры.")
    else:
        if item_key not in WEAPON_CATALOG and not storage.remove_item(telegram_id, item_key, 1):
            return ActionResult(False, f"У тебя нет предмета: {title}.")
    storage.change_money(telegram_id, sell_price)
    return ActionResult(True, f"Продано: {title} за {sell_price} RU.")


def _primary_keys_by_name(catalog: dict[str, dict[str, int | str]]) -> dict[str, str]:
    by_name: dict[str, str] = {}
    for key, entry in catalog.items():
        name = str(entry["name"])
        by_name.setdefault(name, key)
    return by_name


def _price_with_durability(base_price: int, durability: int) -> int:
    # Даже сильно изношенный предмет имеет минимальную выкупную стоимость.
    effective = max(20, min(100, durability))
    return max(1, int(round(base_price * (effective / 100))))


def list_equippable_weapons(character: Character) -> list[tuple[str, str, int]]:
    options: list[tuple[str, str, int]] = []
    for key, amount in sorted(character.inventory.items()):
        if key in WEAPON_CATALOG and amount > 0:
            title = str(WEAPON_CATALOG[key]["name"])
            options.append((key, title, int(amount)))
    return options


def list_equippable_armor(character: Character) -> list[tuple[str, str, int]]:
    options: list[tuple[str, str, int]] = []
    for key, amount in sorted(character.inventory.items()):
        if key in ARMOR_CATALOG and amount > 0:
            title = str(ARMOR_CATALOG[key]["name"])
            options.append((key, title, int(amount)))
    return options


def list_equippable_artifacts(character: Character) -> list[tuple[str, str, int]]:
    options: list[tuple[str, str, int]] = []
    for key in ARTIFACT_DROP_KEYS:
        amount = int(character.inventory.get(key, 0))
        if amount > 0:
            title = ARTIFACT_INVENTORY_TO_NAME.get(key, ITEM_LABELS.get(key, key))
            options.append((key, title, amount))
    return options


def list_equippable_for_slot(character: Character, slot: str) -> list[tuple[str, str, int]]:
    if slot == "weapon":
        return list_equippable_weapons(character)
    if slot == "armor":
        return list_equippable_armor(character)
    if slot == "artifact":
        return list_equippable_artifacts(character)
    return []


def _artifact_bonus_short(artifact_name: str) -> str:
    if artifact_name in ARTIFACT_ENERGY_REGEN_NAMES:
        power = int(ARTIFACT_EQUIP_BONUSES.get(artifact_name, {}).get("power", 2))
        return f"+{power} сила, +5% энергия"
    bonus = ARTIFACT_EQUIP_BONUSES.get(artifact_name, {})
    power = int(bonus.get("power", 0))
    hp = int(bonus.get("hp", 0))
    parts: list[str] = []
    if power:
        parts.append(f"+{power} сила")
    if hp:
        parts.append(f"+{hp} HP")
    return ", ".join(parts) if parts else "без бонуса"


def build_equip_root_text(character: Character) -> tuple[str, list[tuple[str, str, int]]]:
    """Корневое меню экипировки: текущая снаряга + категории."""
    weapon = str(character.equipment.get("weapon", "Нож"))
    armor = str(character.equipment.get("armor", "Куртка новичка"))
    artifact = str(character.equipment.get("artifact", "Нет") or "Нет")
    w_count = len(list_equippable_weapons(character))
    a_count = len(list_equippable_armor(character))
    art_count = len(list_equippable_artifacts(character))
    menu_items = [
        ("weapon", EQUIP_SLOT_LABELS["weapon"], w_count),
        ("armor", EQUIP_SLOT_LABELS["armor"], a_count),
        ("artifact", EQUIP_SLOT_LABELS["artifact"], art_count),
    ]
    art_note = ""
    if artifact and artifact != "Нет":
        art_note = f" ({_artifact_bonus_short(artifact)})"
    text = (
        "⚙️ Экипировка\n"
        "Выбери категорию, затем предмет из инвентаря.\n"
        f"Сила снаряги: {equipment_power(character)}\n\n"
        f"🔫 Оружие: {weapon}\n"
        f"🦺 Броня: {armor}\n"
        f"💎 Артефакт: {artifact}{art_note}\n\n"
        f"В инвентаре: оружие {w_count}, броня {a_count}, арты {art_count}."
    )
    return text, menu_items


def build_equip_slot_page(
    character: Character,
    slot: str,
    page: int = 0,
) -> tuple[str, str, int, int, list[tuple[str, str, int]]]:
    """Возвращает (text, slot, page, total_pages, page_options)."""
    if slot not in EQUIP_SLOT_LABELS:
        return ("Неизвестная категория экипировки.", "weapon", 0, 1, [])

    options = list_equippable_for_slot(character, slot)
    label = EQUIP_SLOT_LABELS[slot]
    current = str(character.equipment.get(slot, "Нет") or "Нет")
    if slot == "weapon" and not current:
        current = "Нож"
    if slot == "armor" and not current:
        current = "Куртка новичка"

    if not options:
        empty = (
            f"⚙️ {label}\n"
            f"Сейчас надето: {current}\n\n"
            f"В инвентаре нет предметов этой категории."
        )
        return empty, slot, 0, 1, []

    total = len(options)
    total_pages = max(1, (total + EQUIP_PAGE_SIZE - 1) // EQUIP_PAGE_SIZE)
    safe_page = max(0, min(int(page), total_pages - 1))
    start = safe_page * EQUIP_PAGE_SIZE
    chunk = options[start : start + EQUIP_PAGE_SIZE]

    lines = [
        f"⚙️ {label}",
        f"Сейчас надето: {current}",
        f"Страница {safe_page + 1}/{total_pages} • доступно: {total}",
        "",
        "Выбери предмет:",
    ]
    for key, title, amount in chunk:
        mark = " ✅" if title == current else ""
        bonus = ""
        if slot == "artifact":
            bonus = f" [{_artifact_bonus_short(title)}]"
        lines.append(f"• {title} x{amount}{bonus}{mark}")
    return ("\n".join(lines), slot, safe_page, total_pages, chunk)


def _unequip_artifact_to_inventory(storage: Storage, telegram_id: int, equipped_name: str) -> None:
    """Вернуть экипированный арт в инвентарь и снять бонус HP при необходимости."""
    if not equipped_name or equipped_name == "Нет":
        return
    inv_key = ARTIFACT_NAME_TO_INVENTORY.get(equipped_name)
    if inv_key is not None:
        storage.add_item(telegram_id, inv_key, 1)
    storage.set_equipment_item(telegram_id, "artifact", "Нет")
    # После снятия «Живучести» HP не выше базовых 100.
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is not None and player.health > 100:
        storage.change_health(telegram_id, 100 - player.health, max_health=100)
    storage.sync_gear_power(telegram_id)


def unequip_artifact(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    equipped = str(player.equipment.get("artifact", "Нет") or "Нет")
    if not equipped or equipped == "Нет":
        return ActionResult(False, "Артефакт не экипирован.")
    _unequip_artifact_to_inventory(storage, telegram_id, equipped)
    return ActionResult(True, f"Снят артефакт: {equipped}. Он вернулся в инвентарь.")


def equip_weapon(storage: Storage, telegram_id: int, item_key: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if item_key not in WEAPON_CATALOG:
        return ActionResult(False, "Такое оружие нельзя экипировать.")
    if not storage.remove_item(telegram_id, item_key, 1):
        return ActionResult(False, "Этого оружия нет в инвентаре.")

    weapon_name = str(WEAPON_CATALOG[item_key]["name"])
    current_weapon = str(player.equipment.get("weapon", "Нож"))
    if current_weapon == weapon_name:
        storage.add_item(telegram_id, item_key, 1)
        return ActionResult(False, f"Оружие «{weapon_name}» уже экипировано.")

    old_key = _primary_keys_by_name(WEAPON_CATALOG).get(current_weapon)
    if old_key is not None and current_weapon != "Нож":
        storage.add_item(telegram_id, old_key, 1)
    storage.set_equipment_item(telegram_id, "weapon", weapon_name)
    return ActionResult(True, f"Экипировано оружие: {weapon_name}.")


def equip_armor(storage: Storage, telegram_id: int, item_key: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if item_key not in ARMOR_CATALOG:
        return ActionResult(False, "Такую броню нельзя экипировать.")
    if not storage.remove_item(telegram_id, item_key, 1):
        return ActionResult(False, "Этой брони нет в инвентаре.")

    armor_name = str(ARMOR_CATALOG[item_key]["name"])
    current_armor = str(player.equipment.get("armor", "Куртка новичка"))
    if current_armor == armor_name:
        storage.add_item(telegram_id, item_key, 1)
        return ActionResult(False, f"Броня «{armor_name}» уже экипирована.")

    old_key = _primary_keys_by_name(ARMOR_CATALOG).get(current_armor)
    if old_key is not None:
        storage.add_item(telegram_id, old_key, 1)
    storage.set_equipment_item(telegram_id, "armor", armor_name)
    return ActionResult(True, f"Экипирована броня: {armor_name}.")


def repair_gear(storage: Storage, telegram_id: int, target: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if target not in {"weapon", "armor"}:
        return ActionResult(False, "Неизвестный тип ремонта.")
    item_name = str(player.equipment.get(target, "—"))
    current = _durability_percent(player, target)
    if current >= MAX_DURABILITY:
        return ActionResult(False, f"{'Оружие' if target == 'weapon' else 'Броня'} уже в идеальном состоянии.")
    missing = MAX_DURABILITY - current
    price = max(80, missing * 7)
    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, f"Недостаточно денег на ремонт ({price} RU).")
    storage.update_equipment_fields(telegram_id, {f"{target}_durability": MAX_DURABILITY})
    storage.add_player_stat(telegram_id, "trades_done", 1)
    _add_rating(storage, telegram_id, RATING_REWARD["trade_action"])
    achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
    target_label = "Оружие" if target == "weapon" else "Броня"
    return ActionResult(
        True,
        f"{target_label} «{item_name}» полностью отремонтировано за {price} RU.{achievements_text}",
    )


def repair_truck(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if not player.truck_owned:
        return ActionResult(False, "У тебя нет грузовика для ремонта.")
    current = max(0, min(100, int(player.truck_durability)))
    if current >= 100:
        return ActionResult(False, "Грузовик уже в идеальном состоянии.")
    missing = 100 - current
    price = max(500, missing * 70)
    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, f"Недостаточно денег на ремонт грузовика ({price} RU).")
    storage.set_truck_durability(telegram_id, 100)
    storage.add_player_stat(telegram_id, "trades_done", 1)
    _add_rating(storage, telegram_id, RATING_REWARD["trade_action"])
    achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
    return ActionResult(True, f"Грузовик полностью отремонтирован за {price} RU.{achievements_text}")


def equip_artifact(storage: Storage, telegram_id: int, item_key: str | None = None) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())

    chosen_key = item_key
    if chosen_key is None or chosen_key not in ARTIFACT_INVENTORY_TO_NAME:
        return ActionResult(False, "Выбери артефакт в меню экипировки.")

    if int(player.inventory.get(chosen_key, 0)) <= 0:
        return ActionResult(False, "У тебя нет этого артефакта в инвентаре.")

    artifact_name = ARTIFACT_INVENTORY_TO_NAME[chosen_key]
    equipped_artifact = str(player.equipment.get("artifact", "Нет") or "Нет")
    if equipped_artifact == artifact_name:
        return ActionResult(False, f"{artifact_name} уже экипирован.")

    if not storage.remove_item(telegram_id, chosen_key, 1):
        return ActionResult(False, "У тебя нет этого артефакта в инвентаре.")

    # Смена арта: старый возвращается в инвентарь (как оружие/броня).
    if equipped_artifact and equipped_artifact != "Нет":
        old_key = ARTIFACT_NAME_TO_INVENTORY.get(equipped_artifact)
        if old_key is not None:
            storage.add_item(telegram_id, old_key, 1)

    storage.set_equipment_item(telegram_id, "artifact", artifact_name)
    storage.sync_gear_power(telegram_id)

    bonus = ARTIFACT_EQUIP_BONUSES.get(artifact_name, {"power": 0, "hp": 0})
    bonus_parts: list[str] = []
    if bonus.get("power"):
        bonus_parts.append(f"+{bonus['power']} к силе")
    hp_bonus = int(bonus.get("hp") or 0)
    max_hp = 100 + hp_bonus
    current = storage.get_character(telegram_id, refresh_energy=False)
    if current is not None:
        if current.health > max_hp:
            storage.change_health(telegram_id, max_hp - current.health, max_health=max_hp)
        elif hp_bonus > 0 and current.health < max_hp:
            heal = min(hp_bonus, max_hp - current.health)
            if heal > 0:
                storage.change_health(telegram_id, heal, max_health=max_hp)
    if hp_bonus:
        bonus_parts.append(f"+{hp_bonus} к запасу HP")
    if chosen_key == "artifact":
        bonus_parts.append("+5% реген энергии")
    if not bonus_parts:
        bonus_parts.append("без доп. бонуса")

    achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
    return ActionResult(
        True,
        f"Экипирован {artifact_name}. Бонус: {', '.join(bonus_parts)}.{achievements_text}",
    )


def format_inventory(
    character: Character,
    *,
    rating_points: int = 0,
    storage: Storage | None = None,
) -> str:
    rating = max(0, int(rating_points))
    skin = resolve_skin(rating)
    _, next_skin, rating_left = next_skin_progress(rating)
    skin_progress = (
        f"Рейтинг: {rating} | Скин: {skin.title}\n"
        f"До «{next_skin.title}»: ещё {rating_left} рейтинга.\n"
        if next_skin is not None
        else f"Рейтинг: {rating} | Скин: {skin.title} (максимум)\n"
    )
    if character.inventory:
        items = "\n".join(
            f"• {ITEM_LABELS.get(key, key)} x{amount}"
            for key, amount in sorted(character.inventory.items())
        )
    else:
        items = "• Пусто"

    vehicle = (
        f"Есть грузовик ({max(0, min(100, int(character.truck_durability)))}%)"
        if character.truck_owned
        else "Нет транспорта"
    )
    sleeping_bag = "Есть спальник (x2 реген энергии)" if character.sleeping_bag_owned else "Спальника нет"
    equipment_labels = {
        "weapon": "Оружие",
        "armor": "Броня",
        "artifact": "Артефакт",
    }
    weapon_durability = _durability_percent(character, "weapon")
    armor_durability = _durability_percent(character, "armor")
    equipment = "\n".join(
        f"• {equipment_labels.get(k, k)}: {v}"
        for k, v in character.equipment.items()
        if k in {"weapon", "armor", "artifact"}
    )
    durability_block = (
        f"• Прочность оружия: {weapon_durability}%\n"
        f"• Прочность брони: {armor_durability}%"
    )

    current_gear_power = equipment_power(character)
    survival_line = (
        f"☢ Радиация: {character.radiation} | "
        f"🍗 Голод: {character.hunger} | "
        f"💧 Жажда: {character.thirst}"
    )
    craving_notice = build_survival_craving_notice(character)
    is_leader = False
    if storage is not None and character.faction:
        is_leader = storage.get_faction_leader_id(character.faction) == character.telegram_id
    rank_title = resolve_rank_title(
        faction=character.faction,
        faction_rank=character.faction_rank,
        is_leader=is_leader,
    )
    faction_line = f"Фракция: {character.faction or 'не выбрана'}"
    if rank_title:
        faction_line = f"Фракция: {character.faction} | Звание: {rank_title}"
    return (
        f"{craving_notice}"
        f"👤 {character.nickname} ({character.gender})\n"
        f"ID-адрес: {character.player_uid}\n"
        f"Telegram ID: {character.telegram_id}\n"
        f"{faction_line}\n"
        f"Локация: {character.location}\n"
        f"Здоровье: {character.health}/{effective_max_health(character)}\n"
        f"Энергия: {character.energy}/{character.max_energy}\n"
        f"Сила снаряги: {current_gear_power}\n"
        f"{skin_progress}"
        f"Баланс: {character.money} RU\n"
        f"Транспорт: {vehicle}\n"
        f"Спальник: {sleeping_bag}\n"
        f"Топливо: {character.fuel}\n"
        f"{survival_line}\n\n"
        f"Снаряга:\n{equipment}\n{durability_block}\n\n"
        f"Вещи:\n{items}"
    )


def _compute_truck_wear(distance_px: float | None, travel_minutes: int) -> int:
    if distance_px is not None:
        factor = max(0.0, min(1.0, float(distance_px) / 420.0))
    else:
        factor = max(0.0, min(1.0, (travel_minutes - 5) / 20))
    min_wear = TRUCK_WEAR_MIN + int(round(4 * factor))
    max_wear = TRUCK_WEAR_MIN + int(round(10 * factor))
    min_wear = max(TRUCK_WEAR_MIN, min(TRUCK_WEAR_MAX, min_wear))
    max_wear = max(min_wear, min(TRUCK_WEAR_MAX, max_wear))
    return random.randint(min_wear, max_wear)


def travel_to(storage: Storage, telegram_id: int, destination: str) -> ActionResult:
    character = storage.get_character(telegram_id)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(character):
        return ActionResult(False, _dead_block_text())
    if character.location == destination:
        return ActionResult(False, f"Ты уже находишься в локации «{destination}».")

    locations = {loc["name"]: loc for loc in storage.get_locations()}
    if destination not in locations:
        return ActionResult(False, "Такой локации нет.")
    target = locations[destination]

    will_use_truck = character.truck_owned and character.truck_durability > 0 and character.fuel > 0
    energy_cost = 8 if will_use_truck else 16
    travel_minutes = 10 if will_use_truck else 30
    distance_px: float | None = None
    current_point = MAP_TRAVEL_POINTS.get(character.location)
    destination_point = MAP_TRAVEL_POINTS.get(destination)
    if current_point and destination_point:
        distance_px = dist(current_point, destination_point)
        if will_use_truck:
            travel_minutes = max(5, round(distance_px / 24))
        else:
            travel_minutes = max(10, round(distance_px / 8))

    if target["point_type"] == "точка интереса" and target["controlled_by"] == character.faction:
        travel_minutes = max(5, int(travel_minutes * 0.7))

    if not storage.spend_energy(telegram_id, energy_cost):
        return ActionResult(False, f"Не хватает энергии для перехода (нужно {energy_cost}).")
    if will_use_truck and not storage.change_fuel(telegram_id, -1):
        storage.restore_energy(telegram_id, energy_cost)
        return ActionResult(False, "Не удалось списать топливо, переход отменен.")

    truck_wear_text = ""
    if will_use_truck:
        wear = _compute_truck_wear(distance_px, travel_minutes)
        durability = storage.apply_truck_wear(telegram_id, wear)
        if durability is None:
            durability = max(0, int(character.truck_durability) - wear)
        if durability <= 0:
            truck_wear_text = f"\nГрузовик изношен на {wear}% и окончательно сломан."
        else:
            truck_wear_text = f"\nИзнос грузовика: -{wear}% (прочность: {durability}%)."

    storage.set_location(telegram_id, destination)
    return ActionResult(
        True,
        f"Переход в «{destination}» выполнен.\n"
        f"Затрачено энергии: {energy_cost}.\n"
        f"Оценка времени пути: ~{travel_minutes} мин."
        f"{truck_wear_text}",
    )


def build_alliance_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return "Союзы доступны только после выбора группировки."
    leader_id = storage.get_faction_leader_id(player.faction)
    role_text = (
        "Ты лидер группировки."
        if leader_id is not None and leader_id == telegram_id
        else "Ты не лидер группировки."
    )
    allies = storage.list_faction_alliances(player.faction)
    if not allies:
        return f"Союзы {player.faction}: нет активных союзов.\n{role_text}"
    return (
        f"Союзы {player.faction} ({len(allies)}/{MAX_FACTION_ALLIANCES}): "
        + ", ".join(sorted(allies))
        + f"\n{role_text}"
    )


def propose_alliance(storage: Storage, telegram_id: int, target_faction: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    if not target_faction or target_faction == player.faction:
        return ActionResult(False, "Нельзя заключить союз с собственной группировкой.")
    if storage.get_faction_leader_id(player.faction) != telegram_id:
        return ActionResult(False, "Заключать договор может только лидер твоей группировки.")
    target_leader_id = storage.get_faction_leader_id(target_faction)
    if target_leader_id is None:
        return ActionResult(False, f"У группировки {target_faction} не назначен лидер.")
    if storage.are_factions_allied(player.faction, target_faction):
        return ActionResult(False, f"Союз с {target_faction} уже активен.")
    if len(storage.list_faction_alliances(player.faction)) >= MAX_FACTION_ALLIANCES:
        return ActionResult(False, f"Можно иметь максимум {MAX_FACTION_ALLIANCES} союзов.")
    if not storage.create_alliance_request(player.faction, target_faction, telegram_id):
        return ActionResult(False, "Предложение уже отправлено или не удалось создать заявку.")
    return ActionResult(
        True,
        f"Предложение союза отправлено в {target_faction}.\n"
        f"Лидер {target_faction} должен подтвердить договор.",
    )


def accept_alliance(storage: Storage, telegram_id: int, from_faction: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    if storage.get_faction_leader_id(player.faction) != telegram_id:
        return ActionResult(False, "Подтверждать договор может только лидер твоей группировки.")
    if storage.get_faction_leader_id(from_faction) is None:
        return ActionResult(False, f"У группировки {from_faction} не назначен лидер.")
    if not from_faction or from_faction == player.faction:
        return ActionResult(False, "Некорректная группировка для подтверждения.")
    if storage.are_factions_allied(player.faction, from_faction):
        return ActionResult(False, f"Союз с {from_faction} уже активен.")
    if len(storage.list_faction_alliances(player.faction)) >= MAX_FACTION_ALLIANCES:
        return ActionResult(False, f"Можно иметь максимум {MAX_FACTION_ALLIANCES} союзов.")
    if len(storage.list_faction_alliances(from_faction)) >= MAX_FACTION_ALLIANCES:
        return ActionResult(False, f"У группировки {from_faction} уже максимум союзов.")
    incoming = storage.list_incoming_alliance_requests(player.faction)
    has_offer = any(str(row.get("requester_faction", "")) == from_faction for row in incoming)
    if not has_offer:
        return ActionResult(False, "Активного предложения на союз не найдено.")
    if not storage.set_faction_alliance(from_faction, player.faction, allied=True):
        return ActionResult(False, "Не удалось подтвердить союз.")
    storage.remove_alliance_request(from_faction, player.faction)
    return ActionResult(True, f"Договор о союзе между {from_faction} и {player.faction} заключен.")


def break_alliance(storage: Storage, telegram_id: int, target_faction: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    if not target_faction or target_faction == player.faction:
        return ActionResult(False, "Нельзя разорвать союз с собственной группировкой.")
    if storage.get_faction_leader_id(player.faction) != telegram_id:
        return ActionResult(False, "Разрывать союз может только лидер твоей группировки.")
    if not storage.are_factions_allied(player.faction, target_faction):
        return ActionResult(False, f"Союза с {target_faction} сейчас нет.")
    if not storage.set_faction_alliance(player.faction, target_faction, allied=False):
        return ActionResult(False, "Не удалось разорвать союз.")
    return ActionResult(True, f"Союз между {player.faction} и {target_faction} разорван.")


def declare_war(storage: Storage, telegram_id: int, target_faction: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    if not target_faction or target_faction == player.faction:
        return ActionResult(False, "Нельзя объявить войну собственной группировке.")
    if storage.get_faction_leader_id(player.faction) != telegram_id:
        return ActionResult(False, "Объявлять войну может только лидер твоей группировки.")
    if storage.get_faction_leader_id(target_faction) is None:
        return ActionResult(False, f"У группировки {target_faction} не назначен лидер.")
    had_alliance = storage.are_factions_allied(player.faction, target_faction)
    storage.remove_alliance_request(player.faction, target_faction)
    storage.remove_alliance_request(target_faction, player.faction)
    if had_alliance:
        if not storage.set_faction_alliance(player.faction, target_faction, allied=False):
            return ActionResult(False, "Не удалось объявить войну: ошибка смены дипломатии.")
        return ActionResult(
            True,
            f"{player.faction} объявила войну {target_faction}.\nСоюз разорван в одностороннем порядке.",
        )
    return ActionResult(
        True,
        f"{player.faction} объявила войну {target_faction}.\nПодтверждение второй стороны не требуется.",
    )


def attack_location(storage: Storage, telegram_id: int, location_name: str) -> ActionResult:
    """Сolo-штурм отключён: захват точек только через военное лобби (мин. 5 бойцов)."""
    _ = (storage, telegram_id, location_name)
    return ActionResult(
        False,
        f"Соло-штурм отключён. Собери военное лобби и запусти штурм минимум из "
        f"{WAR_MIN_FACTION_MEMBERS} живых бойцов (раздел «⚔️ Война» → «🪖 Военные лобби»).",
    )


def _weapon_rating(weapon_name: str) -> int:
    return WEAPON_RATING_BY_NAME.get(weapon_name, 1)


def _armor_rating(armor_name: str) -> int:
    return ARMOR_RATING_BY_NAME.get(armor_name, 1)


def _safe_fromiso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)


def _active_location_event_modifier(storage: Storage, location_name: str) -> int:
    now = datetime.now(timezone.utc)
    modifier = 0
    for event in storage.get_map_events():
        if str(event.get("location")) != location_name:
            continue
        expires_at = _safe_fromiso(str(event.get("expires_at", "")))
        if expires_at > now:
            modifier += int(event.get("modifier", 0))
    return modifier


def _simulate_raid_battle(
    members: list[Character],
    enemy_power: int,
) -> dict[str, Any]:
    squad_hp: dict[int, int] = {}
    squad_attack_bonus: dict[int, int] = {}
    squad_armor_bonus: dict[int, int] = {}
    member_gear_power: dict[int, int] = {}
    for member in members:
        weapon_bonus = _weapon_rating(member.equipment.get("weapon", ""))
        armor_bonus = _armor_rating(member.equipment.get("armor", ""))
        gear_power = equipment_power(member)
        member_gear_power[member.telegram_id] = gear_power
        squad_attack_bonus[member.telegram_id] = weapon_bonus
        squad_armor_bonus[member.telegram_id] = armor_bonus
        squad_hp[member.telegram_id] = 75 + gear_power * 4 + armor_bonus * 3

    enemy_hp = max(80, enemy_power * 7)
    enemy_damage_base = max(8, enemy_power // 2)
    total_crits = 0
    wounds: list[int] = []

    for _round in range(1, 8):
        active_ids = [mid for mid, hp in squad_hp.items() if hp > 0]
        if not active_ids or enemy_hp <= 0:
            break

        for member in members:
            member_hp = squad_hp.get(member.telegram_id, 0)
            if member_hp <= 0 or enemy_hp <= 0:
                continue
            gear_power = member_gear_power.get(member.telegram_id, 1)
            base_damage = 6 + gear_power * 2 + squad_attack_bonus[member.telegram_id]
            damage = base_damage + random.randint(0, 8)
            crit_chance = min(35, 8 + gear_power * 2)
            if random.randint(1, 100) <= crit_chance:
                damage = int(damage * 1.7)
                total_crits += 1
            enemy_hp -= damage

        if enemy_hp <= 0:
            break

        target_id = random.choice(active_ids)
        armor_block = squad_armor_bonus.get(target_id, 0) * 2
        incoming = max(3, enemy_damage_base + random.randint(0, 7) - armor_block)
        squad_hp[target_id] = max(0, squad_hp[target_id] - incoming)
        if squad_hp[target_id] == 0 and target_id not in wounds:
            wounds.append(target_id)

    survivors = [mid for mid, hp in squad_hp.items() if hp > 0]
    success = enemy_hp <= 0 and bool(survivors)
    member_damage_taken: dict[int, int] = {}
    for member in members:
        gear_power = member_gear_power.get(member.telegram_id, 1)
        max_hp = 75 + gear_power * 4 + squad_armor_bonus[member.telegram_id] * 3
        member_damage_taken[member.telegram_id] = max(0, max_hp - squad_hp[member.telegram_id])

    return {
        "success": success,
        "enemy_hp_left": max(0, enemy_hp),
        "total_crits": total_crits,
        "wounds": wounds,
        "member_damage_taken": member_damage_taken,
        "survivors": survivors,
    }


def _location_is_friendly_to_faction(
    storage: Storage,
    location: dict[str, Any],
    faction: str,
) -> bool:
    owner = str(location.get("controlled_by") or "")
    if not owner:
        return False
    if owner == faction:
        return True
    return storage.are_factions_allied(faction, owner)


def list_assaultable_locations(storage: Storage, faction: str) -> list[dict[str, Any]]:
    return [
        loc
        for loc in storage.get_locations()
        if not _location_is_friendly_to_faction(storage, loc, faction)
    ]


def _refund_spent_energy(storage: Storage, telegram_ids: list[int], amount: int) -> None:
    for telegram_id in telegram_ids:
        storage.restore_energy(telegram_id, amount)


def create_or_join_faction_raid(storage: Storage, telegram_id: int, location_name: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")

    location = storage.get_location(location_name)
    if location is None:
        return ActionResult(False, "Локация для рейда не найдена.")
    if str(location.get("point_type") or "") == "база":
        return ActionResult(
            False,
            "Базы штурмуются только через военное лобби (раздел «⚔️ Война»).",
        )
    if _location_is_friendly_to_faction(storage, location, player.faction):
        return ActionResult(False, "Нельзя рейдить свою или союзническую точку.")

    open_raid = storage.get_open_raid_for_faction(player.faction)
    if open_raid is None:
        for ally in storage.list_faction_alliances(player.faction):
            ally_open = storage.get_open_raid_for_faction(ally)
            if ally_open is not None and str(ally_open["location"]) == location_name:
                open_raid = ally_open
                break
    if open_raid is None:
        raid_id = storage.create_raid(player.faction, location_name, telegram_id)
        return ActionResult(
            True,
            f"Создан рейд #{raid_id} на логово «{location_name}».\n"
            "Позови товарищей по группировке и нажми «Запустить».",
        )

    if str(open_raid["location"]) != location_name:
        return ActionResult(
            False,
            f"У твоей группировки уже есть открытый рейд #{open_raid['id']} на логово «{open_raid['location']}».\n"
            "Сначала запусти или закрой его.",
        )

    raid_id = int(open_raid["id"])
    host_faction = str(open_raid["faction"])
    member_faction = player.faction
    if not storage.are_factions_allied(host_faction, member_faction) and host_faction != member_faction:
        return ActionResult(False, "К рейду можно присоединяться только своей группировкой или союзниками.")
    if not storage.add_raid_member(raid_id, telegram_id):
        return ActionResult(False, "Не удалось присоединиться к рейду.")
    member_ids = storage.get_raid_member_ids(raid_id)
    return ActionResult(
        True,
        f"Ты в составе рейда #{raid_id} на логово «{location_name}».\n"
        f"Состав рейда: {len(member_ids)} бойцов.",
    )


def launch_open_raid(storage: Storage, telegram_id: int) -> RaidLaunchResult:
    leader = storage.get_character(telegram_id, refresh_energy=False)
    if leader is None:
        return RaidLaunchResult(False, "Сначала создай персонажа.", ())
    if _is_dead(leader):
        return RaidLaunchResult(False, _dead_block_text(), ())
    if leader.faction is None:
        return RaidLaunchResult(False, "Сначала выбери группировку.", ())

    open_raid = storage.get_open_raid_for_faction(leader.faction)
    if open_raid is None:
        return RaidLaunchResult(False, "У твоей группировки нет открытого рейда.", ())
    if int(open_raid["leader_id"]) != telegram_id:
        return RaidLaunchResult(False, "Запускать рейд может только лидер, который его создал.", ())

    raid_id = int(open_raid["id"])
    member_ids = storage.get_raid_member_ids(raid_id)
    if len(member_ids) < 2:
        return RaidLaunchResult(False, "Для отрядного рейда нужно минимум 2 игрока.", ())

    members = storage.get_characters_by_ids(member_ids)
    allowed_factions = {leader.faction, *storage.list_faction_alliances(leader.faction)}
    members = [member for member in members if member.faction in allowed_factions and member.health > 0]
    if len(members) < 2:
        return RaidLaunchResult(False, "Недостаточно бойцов с нормальным здоровьем для запуска рейда.", ())

    raid_energy_cost = 18
    ready_members: list[Character] = []
    spent_ids: list[int] = []
    for member in members:
        if storage.spend_energy(member.telegram_id, raid_energy_cost):
            ready_members.append(member)
            spent_ids.append(member.telegram_id)
    if len(ready_members) < 2:
        _refund_spent_energy(storage, spent_ids, raid_energy_cost)
        return RaidLaunchResult(
            False,
            "У бойцов не хватает энергии для начала рейда. Нужно минимум 2 подготовленных сталкера.",
            (),
        )

    location_name = str(open_raid["location"])
    location = storage.get_location(location_name)
    if location is None:
        _refund_spent_energy(storage, spent_ids, raid_energy_cost)
        return RaidLaunchResult(False, "Локация рейда недоступна.", ())
    if str(location.get("point_type") or "") == "база":
        _refund_spent_energy(storage, spent_ids, raid_energy_cost)
        return RaidLaunchResult(
            False,
            "Базы штурмуются только через военное лобби.",
            (),
        )
    if _location_is_friendly_to_faction(storage, location, leader.faction):
        _refund_spent_energy(storage, spent_ids, raid_energy_cost)
        return RaidLaunchResult(False, "Нельзя рейдить свою или союзническую точку.", ())

    event_modifier = _active_location_event_modifier(storage, location_name)
    enemy_power = max(10, int(location["npc_power"]) + event_modifier)
    battle = _simulate_raid_battle(ready_members, enemy_power)

    if battle["success"]:
        captured_enemy_base = False
        storage.set_location_control(location_name, leader.faction)
        treasury_gain = 1400 + len(ready_members) * 180
        storage.change_faction_treasury(leader.faction, treasury_gain)
        artifacts_reward = 0
        if enemy_power >= RAID_ARTIFACT_MIN_ENEMY_POWER:
            artifacts_reward = min(
                RAID_ARTIFACT_REWARD_CAP,
                random.randint(1, RAID_ARTIFACT_REWARD_CAP),
            )
        notes: list[str] = []
        stash_finds = 0
        for member in ready_members:
            durability_text = _apply_durability_decay(
                storage,
                member.telegram_id,
                weapon_loss=6,
                armor_loss=5,
            )
            if artifacts_reward > 0:
                for _ in range(artifacts_reward):
                    art_key = pick_weighted_artifact_key()
                    storage.add_item(member.telegram_id, art_key, 1)
                storage.add_player_stat(member.telegram_id, "artifacts_found", artifacts_reward)
            if _maybe_drop_stash(storage, member.telegram_id):
                stash_finds += 1
            _add_rating(storage, member.telegram_id, RATING_REWARD["raid_success"])
            storage.add_player_stat(member.telegram_id, "raids_completed", 1)
            if captured_enemy_base:
                storage.add_player_stat(member.telegram_id, "enemy_bases_captured", 1)
            if member.telegram_id in battle["wounds"]:
                storage.change_health(member.telegram_id, -14)
            achievement_text = _progress_and_unlock_achievements(storage, member.telegram_id)
            if member.telegram_id == leader.telegram_id:
                notes.append(durability_text + achievement_text)
        new_npc_power = max(12, enemy_power - random.randint(4, 10))
        storage.set_location_npc_power(location_name, new_npc_power)
        storage.finish_raid(
            raid_id,
            status="success",
            result_text=f"Рейд успешен. Критов: {battle['total_crits']}.",
        )
        stash_line = (
            f"\nТайники найдены у {stash_finds} бойцов."
            if stash_finds > 0
            else ""
        )
        return RaidLaunchResult(
            True,
            f"Рейд #{raid_id} завершен успешно на логове «{location_name}».\n"
            f"Бойцов: {len(ready_members)}, критические попадания: {battle['total_crits']}.\n"
            f"Награда каждому: артефакты x{artifacts_reward} "
            f"(Зона / Сила / Живучесть, макс. {RAID_ARTIFACT_REWARD_CAP}).\n"
            f"Порог сложности для награды артефактами: от {RAID_ARTIFACT_MIN_ENEMY_POWER} силы.\n"
            f"В казну группировки: {treasury_gain} RU.\n"
            f"Раненых: {len(battle['wounds'])}."
            f"{stash_line}{''.join(notes)}",
            tuple(member_ids),
        )

    notes: list[str] = []
    for member in ready_members:
        durability_text = _apply_durability_decay(
            storage,
            member.telegram_id,
            weapon_loss=7,
            armor_loss=6,
        )
        storage.change_money(member.telegram_id, -110)
        _add_rating(storage, member.telegram_id, -RATING_REWARD["raid_fail"])
        storage.add_player_stat(member.telegram_id, "raids_failed", 1)
        damage_taken = int(battle["member_damage_taken"].get(member.telegram_id, 0))
        health_penalty = min(30, max(8, damage_taken // 4))
        storage.change_health(member.telegram_id, -health_penalty)
        achievement_text = _progress_and_unlock_achievements(storage, member.telegram_id)
        if member.telegram_id == leader.telegram_id:
            notes.append(durability_text + achievement_text)
    new_npc_power = min(80, enemy_power + random.randint(2, 7))
    storage.set_location_npc_power(location_name, new_npc_power)
    storage.finish_raid(
        raid_id,
        status="failed",
        result_text=f"Рейд провален. Остаток силы противника: {battle['enemy_hp_left']}.",
    )
    return RaidLaunchResult(
        False,
        f"Рейд #{raid_id} провален на логове «{location_name}».\n"
        f"Сила врага осталась: {battle['enemy_hp_left']}.\n"
        f"Каждый участник потерял 110 RU и получил ранения.{''.join(notes)}",
        tuple(member_ids),
    )


def build_raids_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return "Рейды доступны только после выбора группировки."

    open_raid = storage.get_open_raid_for_faction(player.faction)
    if open_raid is None:
        return (
            "Отрядные рейды:\n"
            "• Создай рейд на нужное логово.\n"
            "• Другие бойцы твоей группировки могут присоединиться.\n"
            "• Для запуска нужно минимум 2 участника.\n"
            f"• Награды: до {RAID_ARTIFACT_REWARD_CAP} артефактов за успешный рейд (от {RAID_ARTIFACT_MIN_ENEMY_POWER} силы NPC)."
        )

    raid_id = int(open_raid["id"])
    member_ids = storage.get_raid_member_ids(raid_id)
    members = storage.get_characters_by_ids(member_ids)
    members_text = "\n".join(f"• {member.nickname} (сила {equipment_power(member)}, HP {member.health})" for member in members)
    location_name = str(open_raid["location"])
    location = storage.get_location(location_name)
    npc_power = int(location["npc_power"]) if location else 0
    event_modifier = _active_location_event_modifier(storage, location_name)
    return (
        f"Открытый рейд #{raid_id}\n"
        f"Логово: {location_name}\n"
        f"Лидер: {open_raid['leader_id']}\n"
        f"Участников: {len(member_ids)}\n"
        f"Сила NPC: {npc_power} (модификатор событий {event_modifier:+d})\n\n"
        f"Состав:\n{members_text or '• Пока пусто'}\n\n"
        "Отменить рейд может только тот, кто его создал."
    )


def cancel_raid_by_leader(storage: Storage, telegram_id: int, raid_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")

    raid = storage.get_raid(raid_id)
    if raid is None or str(raid.get("status")) != "open":
        return ActionResult(False, f"Открытый рейд #{raid_id} не найден.")
    if int(raid["leader_id"]) != telegram_id:
        return ActionResult(False, "Отменить рейд может только тот, кто его создал.")

    cancelled = storage.cancel_raid(raid_id, telegram_id)
    if cancelled is None:
        return ActionResult(False, "Не удалось отменить рейд.")
    return ActionResult(
        True,
        f"Рейд #{raid_id} на «{cancelled.get('location')}» отменён создателем.",
    )


def cancel_all_raids_by_leader(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")

    open_raids = storage.list_open_raids_led_by(telegram_id)
    if not open_raids:
        return ActionResult(False, "У тебя нет открытых рейдов для отмены.")

    cancelled = storage.cancel_all_open_raids_led_by(telegram_id)
    if not cancelled:
        return ActionResult(False, "Не удалось отменить рейды.")
    lines = [f"• #{item['id']} — {item.get('location')}" for item in cancelled]
    return ActionResult(
        True,
        "Отменены твои открытые рейды:\n" + "\n".join(lines),
    )


def _normalize_item_key(item_key: str) -> str:
    return item_key if item_key in WAREHOUSE_ITEM_KEYS else "ammo_pack"


def character_rank_level(character: Character) -> int:
    rank = rank_by_key(character.faction, character.faction_rank)
    if rank is None:
        return 0
    return rank.level


def can_withdraw_faction_treasury(storage: Storage, character: Character) -> bool:
    """Вывод из казны и склада: лидер или звание от 5 уровня (по назначению лидера)."""
    if character.faction is None:
        return False
    if storage.get_faction_leader_id(character.faction) == character.telegram_id:
        return True
    return character_rank_level(character) >= TREASURY_WITHDRAW_MIN_RANK


def can_withdraw_faction_warehouse(storage: Storage, character: Character) -> bool:
    return can_withdraw_faction_treasury(storage, character)


def deposit_to_faction_warehouse(
    storage: Storage,
    telegram_id: int,
    item_key: str,
    amount: int,
) -> ActionResult:
    if amount <= 0:
        return ActionResult(False, "Некорректное количество для склада.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Склад доступен только бойцам группировки.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    key = _normalize_item_key(item_key)
    if not storage.remove_item(telegram_id, key, amount):
        return ActionResult(False, "В инвентаре недостаточно предметов для сдачи.")
    if not storage.change_faction_warehouse_item(player.faction, key, amount):
        storage.add_item(telegram_id, key, amount)
        return ActionResult(False, "Не удалось обновить склад группировки.")
    return ActionResult(True, f"На склад {player.faction} отправлено: {ITEM_LABELS.get(key, key)} x{amount}.")


def withdraw_from_faction_warehouse(
    storage: Storage,
    telegram_id: int,
    item_key: str,
    amount: int,
) -> ActionResult:
    if amount <= 0:
        return ActionResult(False, "Некорректное количество для выдачи.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Склад доступен только бойцам группировки.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if not can_withdraw_faction_warehouse(storage, player):
        return ActionResult(
            False,
            "Забирать со склада можно с 5 ранга (или лидеру группировки).",
        )
    key = _normalize_item_key(item_key)
    if not storage.change_faction_warehouse_item(player.faction, key, -amount):
        return ActionResult(False, "На складе недостаточно ресурсов.")
    storage.add_item(telegram_id, key, amount)
    return ActionResult(True, f"Со склада получено: {ITEM_LABELS.get(key, key)} x{amount}.")


def deposit_to_faction_treasury(storage: Storage, telegram_id: int, amount: int) -> ActionResult:
    if amount <= 0:
        return ActionResult(False, "Некорректная сумма для пополнения казны.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Казна доступна только бойцам группировки.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if not storage.change_money(telegram_id, -amount):
        return ActionResult(False, f"Недостаточно RU. Нужно {amount} RU.")
    storage.change_faction_treasury(player.faction, amount)
    return ActionResult(True, f"В казну {player.faction} внесено {amount} RU.")


def withdraw_from_faction_treasury(storage: Storage, telegram_id: int, amount: int) -> ActionResult:
    if amount <= 0:
        return ActionResult(False, "Некорректная сумма для вывода из казны.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Казна доступна только бойцам группировки.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if not can_withdraw_faction_treasury(storage, player):
        return ActionResult(
            False,
            "Снимать деньги из казны можно с 5 ранга (или лидеру группировки).",
        )
    if not storage.withdraw_faction_treasury(player.faction, amount):
        return ActionResult(False, "В казне недостаточно денег для вывода.")
    storage.change_money(telegram_id, amount)
    return ActionResult(True, f"Из казны {player.faction} выведено {amount} RU в твой баланс.")


def character_rank_title(storage: Storage, character: Character) -> str | None:
    if character.faction is None:
        return None
    is_leader = storage.get_faction_leader_id(character.faction) == character.telegram_id
    return resolve_rank_title(
        faction=character.faction,
        faction_rank=character.faction_rank,
        is_leader=is_leader,
    )


def assign_faction_rank(
    storage: Storage,
    leader_telegram_id: int,
    target_telegram_id: int,
    rank_key: str,
) -> ActionResult:
    leader = storage.get_character(leader_telegram_id, refresh_energy=False)
    if leader is None or leader.faction is None:
        return ActionResult(False, "Сначала вступи в группировку.")
    if storage.get_faction_leader_id(leader.faction) != leader_telegram_id:
        return ActionResult(False, "Назначать звания может только лидер группировки.")

    target = storage.get_character(target_telegram_id, refresh_energy=False)
    if target is None or target.faction != leader.faction:
        return ActionResult(False, "Игрок не состоит в твоей группировке.")
    if target.telegram_id == leader_telegram_id:
        title = leader_title(leader.faction) or "лидер"
        return ActionResult(False, f"Тебе уже закреплено звание лидера: {title}.")

    rank = rank_by_key(leader.faction, rank_key)
    if rank is None:
        return ActionResult(False, "Некорректное звание.")
    if not storage.set_faction_rank(target.telegram_id, rank.key):
        return ActionResult(False, "Не удалось сохранить звание.")
    return ActionResult(
        True,
        f"{target.nickname} теперь «{rank.title}» в группировке «{leader.faction}».",
    )


def build_faction_ranks_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return "Звания доступны после выбора группировки."
    if storage.get_faction_leader_id(player.faction) != telegram_id:
        own = character_rank_title(storage, player) or "без звания"
        return (
            f"Звания группировки «{player.faction}»\n"
            f"Твоё звание: {own}\n\n"
            "Назначать звания может только лидер."
        )

    ranks = ranks_for_faction(player.faction)
    leader_name = leader_title(player.faction) or "Лидер"
    lines = [
        f"🎖 Звания «{player.faction}»",
        f"Лидер: {leader_name} (ты)",
        "",
        "Выбери бойца, затем звание:",
    ]
    for rank in ranks:
        lines.append(f"{rank.level}) {rank.title}")
    return "\n".join(lines)


def build_faction_member_rank_pick_text(
    storage: Storage,
    leader_telegram_id: int,
    target_telegram_id: int,
) -> str:
    leader = storage.get_character(leader_telegram_id, refresh_energy=False)
    target = storage.get_character(target_telegram_id, refresh_energy=False)
    if leader is None or leader.faction is None:
        return "Сначала вступи в группировку."
    if target is None or target.faction != leader.faction:
        return "Игрок не в твоей группировке."
    current = character_rank_title(storage, target) or "без звания"
    return (
        f"Боец: {target.nickname}\n"
        f"Сейчас: {current}\n\n"
        "Выбери новое звание:"
    )


def create_faction_auction(storage: Storage, telegram_id: int, lot_key: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Аукцион доступен только бойцам группировки.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if lot_key == "gear":
        return create_market_lot(storage, telegram_id, "auto", 1)
    lot = AUCTION_DEFAULT_LOTS.get(lot_key)
    if lot is None:
        return ActionResult(False, "Неизвестный тип лота.")
    item_key, amount, price = lot
    if not storage.remove_item(telegram_id, item_key, amount):
        return ActionResult(False, f"Недостаточно предметов ({ITEM_LABELS.get(item_key, item_key)}) для лота.")
    auction_id = storage.create_auction(
        seller_id=telegram_id,
        faction=player.faction,
        item_key=item_key,
        amount=amount,
        price=price,
    )
    storage.add_player_stat(telegram_id, "trades_done", 1)
    _add_rating(storage, telegram_id, RATING_REWARD["trade_action"])
    achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
    return ActionResult(
        True,
        f"Лот #{auction_id} создан: {ITEM_LABELS.get(item_key, item_key)} x{amount} за {price} RU.\n"
        f"Комиссия при продаже: {EXCHANGE_SELL_FEE_PERCENT}%.{achievements_text}",
    )


def buy_first_faction_auction(storage: Storage, telegram_id: int) -> ActionResult:
    buyer = storage.get_character(telegram_id, refresh_energy=False)
    if buyer is None or buyer.faction is None:
        return ActionResult(False, "Покупка на аукционе доступна только бойцам группировки.")
    if _is_dead(buyer):
        return ActionResult(False, _dead_block_text())
    auctions = sorted(_list_open_exchange_lots(storage), key=lambda a: int(a["id"]))
    target = next((a for a in auctions if int(a["seller_id"]) != telegram_id), None)
    if target is None:
        return ActionResult(False, "Подходящих открытых лотов нет.")

    auction_id = int(target["id"])
    price = int(target["price"])
    item_key = str(target["item_key"])
    amount = int(target["amount"])
    seller_id = int(target["seller_id"])

    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, "Недостаточно денег для покупки лота.")
    if not storage.close_auction(auction_id, buyer_id=telegram_id, status="sold"):
        storage.change_money(telegram_id, price)
        return ActionResult(False, "Лот уже недоступен.")
    fee = max(1, int(round(price * (EXCHANGE_SELL_FEE_PERCENT / 100))))
    seller_income = max(0, price - fee)
    storage.change_money(seller_id, seller_income)
    storage.add_item(telegram_id, item_key, amount)
    storage.add_player_stat(telegram_id, "trades_done", 1)
    storage.add_player_stat(seller_id, "trades_done", 1)
    _add_rating(storage, telegram_id, RATING_REWARD["trade_action"])
    _add_rating(storage, seller_id, RATING_REWARD["trade_action"])
    storage.add_player_stat(seller_id, "money_earned", seller_income)
    achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
    seller_achievements = _progress_and_unlock_achievements(storage, seller_id)
    suffix = achievements_text + seller_achievements
    return ActionResult(
        True,
        f"Куплен лот #{auction_id}: {ITEM_LABELS.get(item_key, item_key)} x{amount} за {price} RU.\n"
        f"Продавец получил {seller_income} RU (комиссия {fee} RU).{suffix}",
    )


def cancel_own_first_auction(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Сначала создай персонажа и выбери группировку.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    auctions = sorted(_list_open_exchange_lots(storage), key=lambda a: int(a["id"]))
    target = next((a for a in auctions if int(a["seller_id"]) == telegram_id), None)
    if target is None:
        return ActionResult(False, "У тебя нет открытых лотов для отмены.")

    auction_id = int(target["id"])
    item_key = str(target["item_key"])
    amount = int(target["amount"])
    if not storage.close_auction(auction_id, buyer_id=None, status="cancelled"):
        return ActionResult(False, "Не удалось отменить лот.")
    storage.add_item(telegram_id, item_key, amount)
    return ActionResult(
        True,
        f"Лот #{auction_id} отменен, предметы возвращены: {ITEM_LABELS.get(item_key, item_key)} x{amount}.",
    )


def _is_equipment_item(item_key: str) -> bool:
    return item_key in WEAPON_CATALOG or item_key in ARMOR_CATALOG


def _list_open_exchange_lots(storage: Storage) -> list[dict[str, Any]]:
    """Биржа: общие лоты расходников/артефактов (не экипировка)."""
    return [
        lot
        for lot in storage.list_open_auctions()
        if not _is_equipment_item(str(lot.get("item_key", "")))
    ]


def _equipment_sell_price(base_sell_price: int, durability: int | None = None) -> int:
    base = max(1, int(round(base_sell_price * TRADER_EQUIPMENT_SELL_RATE)))
    if durability is None:
        return base
    return _price_with_durability(base, durability)


def list_market_lots(storage: Storage, telegram_id: int) -> list[dict[str, Any]]:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return []
    return [
        lot
        for lot in storage.list_open_equipment_market_lots()
        if int(lot.get("seller_id", 0)) != telegram_id and _is_equipment_item(str(lot.get("item_key", "")))
    ]


def list_sellable_market_equipment(storage: Storage, telegram_id: int) -> list[dict[str, int | str]]:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return []
    rows: list[dict[str, int | str]] = []
    for item_key, owned in sorted(player.inventory.items()):
        amount = int(owned)
        if amount <= 0 or not _is_equipment_item(item_key):
            continue
        rows.append(
            {
                "item_key": item_key,
                "title": ITEM_LABELS.get(item_key, item_key),
                "amount": amount,
            }
        )
    return rows


def create_market_lot(
    storage: Storage,
    telegram_id: int,
    item_key: str,
    amount: int,
    price: int | None = None,
) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if amount <= 0:
        return ActionResult(False, "Количество для лота должно быть больше нуля.")
    if item_key in {"first_gear", "auto"}:
        available_equipment_keys = [
            key
            for key, owned in sorted(player.inventory.items())
            if int(owned) > 0 and _is_equipment_item(key)
        ]
        if not available_equipment_keys:
            return ActionResult(
                False,
                "В инвентаре нет оружия или брони для выставления на рынок.",
            )
        item_key = available_equipment_keys[0]
    if not _is_equipment_item(item_key):
        return ActionResult(False, "На рынок можно выставить только оружие или броню.")
    if item_key in WEAPON_CATALOG:
        item_name = str(WEAPON_CATALOG[item_key]["name"])
    else:
        item_name = str(ARMOR_CATALOG[item_key]["name"])
    if not storage.remove_item(telegram_id, item_key, amount):
        return ActionResult(False, f"У тебя нет нужного количества: {item_name}.")
    base_sell = int(SHOP_ITEMS.get(item_key, {}).get("sell_price", 0))
    if base_sell <= 0:
        base_sell = max(1, int(float(SHOP_ITEMS[item_key]["buy_price"]) / 3))
    suggested_price = max(1, _equipment_sell_price(base_sell) * amount)
    lot_price = suggested_price if price is None else int(price)
    if lot_price <= 0:
        storage.add_item(telegram_id, item_key, amount)
        return ActionResult(False, "Цена лота должна быть больше нуля.")
    auction_id = storage.create_auction(
        seller_id=telegram_id,
        faction=player.faction or "market",
        item_key=item_key,
        amount=amount,
        price=lot_price,
    )
    return ActionResult(
        True,
        f"Рыночный лот #{auction_id} выставлен: {item_name} x{amount} за {lot_price} RU.\n"
        f"Комиссия при продаже: {MARKET_SELL_FEE_PERCENT}%.",
    )


def buy_first_market_lot(storage: Storage, telegram_id: int) -> ActionResult:
    buyer = storage.get_character(telegram_id, refresh_energy=False)
    if buyer is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(buyer):
        return ActionResult(False, _dead_block_text())
    auctions = list_market_lots(storage, telegram_id)
    target = auctions[0] if auctions else None
    if target is None:
        return ActionResult(False, "Открытых рыночных лотов экипировки нет.")
    auction_id = int(target["id"])
    price = int(target["price"])
    item_key = str(target["item_key"])
    amount = int(target["amount"])
    seller_id = int(target["seller_id"])
    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, "Недостаточно денег для покупки лота.")
    if not storage.close_auction(auction_id, buyer_id=telegram_id, status="sold"):
        storage.change_money(telegram_id, price)
        return ActionResult(False, "Лот уже недоступен.")
    fee = max(1, int(round(price * (MARKET_SELL_FEE_PERCENT / 100))))
    seller_income = max(0, price - fee)
    storage.change_money(seller_id, seller_income)
    storage.add_item(telegram_id, item_key, amount)
    item_name = ITEM_LABELS.get(item_key, item_key)
    return ActionResult(
        True,
        f"Куплен рыночный лот #{auction_id}: {item_name} x{amount} за {price} RU.\n"
        f"Продавец получил {seller_income} RU (комиссия {fee} RU).",
    )


def buy_market_lot(storage: Storage, telegram_id: int, lot_id: int) -> ActionResult:
    buyer = storage.get_character(telegram_id, refresh_energy=False)
    if buyer is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(buyer):
        return ActionResult(False, _dead_block_text())
    lot = storage.get_open_auction(lot_id)
    if lot is None:
        return ActionResult(False, "Лот не найден или уже закрыт.")
    if not _is_equipment_item(str(lot["item_key"])):
        return ActionResult(False, "Этот лот не относится к снаряге.")
    seller_id = int(lot["seller_id"])
    if seller_id == telegram_id:
        return ActionResult(False, "Нельзя выкупить собственный лот.")
    price = int(lot["price"])
    item_key = str(lot["item_key"])
    amount = int(lot["amount"])
    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, "Недостаточно денег для покупки лота.")
    if not storage.close_auction(lot_id, buyer_id=telegram_id, status="sold"):
        storage.change_money(telegram_id, price)
        return ActionResult(False, "Лот уже недоступен.")
    fee = max(1, int(round(price * (MARKET_SELL_FEE_PERCENT / 100))))
    seller_income = max(0, price - fee)
    storage.change_money(seller_id, seller_income)
    storage.add_item(telegram_id, item_key, amount)
    item_name = ITEM_LABELS.get(item_key, item_key)
    return ActionResult(
        True,
        f"Куплен рыночный лот #{lot_id}: {item_name} x{amount} за {price} RU.\n"
        f"Продавец получил {seller_income} RU (комиссия {fee} RU).",
    )


def build_market_lots_overview(
    storage: Storage,
    telegram_id: int,
    limit: int = 12,
) -> tuple[str, list[dict[str, int | str]]]:
    lots = list_market_lots(storage, telegram_id)
    shown = lots[: max(1, limit)]
    if not shown:
        return ("Открытых рыночных лотов снаряги сейчас нет.", [])
    rows: list[dict[str, int | str]] = []
    lines = ["Рынок снаряги (выбери лот по кнопке):"]
    for lot in shown:
        item_key = str(lot["item_key"])
        title = ITEM_LABELS.get(item_key, item_key)
        lot_id = int(lot["id"])
        amount = int(lot["amount"])
        price = int(lot["price"])
        seller_id = int(lot["seller_id"])
        rows.append({"id": lot_id, "title": title, "amount": amount, "price": price, "seller_id": seller_id})
        lines.append(f"• #{lot_id} {title} x{amount} — {price} RU (продавец {seller_id})")
    return ("\n".join(lines), rows)


def cancel_own_first_market_lot(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    auctions = [
        lot
        for lot in storage.list_open_auctions()
        if int(lot.get("seller_id", 0)) == telegram_id and _is_equipment_item(str(lot.get("item_key", "")))
    ]
    target = next(iter(auctions), None)
    if target is None:
        return ActionResult(False, "У тебя нет открытых рыночных лотов экипировки.")
    auction_id = int(target["id"])
    item_key = str(target["item_key"])
    amount = int(target["amount"])
    if not storage.close_auction(auction_id, buyer_id=None, status="cancelled"):
        return ActionResult(False, "Не удалось отменить рыночный лот.")
    storage.add_item(telegram_id, item_key, amount)
    return ActionResult(True, f"Рыночный лот #{auction_id} отменен, предметы возвращены.")


def find_open_war_lobby_for_character(storage: Storage, player: Character) -> dict[str, Any] | None:
    if player.faction is None:
        return None
    lobby = storage.get_open_war_lobby_for_faction(player.faction)
    if lobby is not None:
        return lobby
    for ally in storage.list_faction_alliances(player.faction):
        ally_lobby = storage.get_open_war_lobby_for_faction(ally)
        if ally_lobby is not None:
            return ally_lobby
    return None


def create_or_join_war_lobby(storage: Storage, telegram_id: int, location_name: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    location = storage.get_location(location_name)
    if location is None:
        return ActionResult(False, "Локация не найдена.")
    if _location_is_friendly_to_faction(storage, location, player.faction):
        return ActionResult(False, "Нельзя штурмовать свою или союзническую точку.")
    open_lobby = find_open_war_lobby_for_character(storage, player)
    if open_lobby is None:
        for ally in storage.list_faction_alliances(player.faction):
            ally_lobby = storage.get_open_war_lobby_for_faction(ally)
            if ally_lobby is not None and str(ally_lobby["location"]) == location_name:
                open_lobby = ally_lobby
                break
    if open_lobby is None:
        war_id = storage.create_war_lobby(player.faction, location_name, telegram_id)
        return ActionResult(True, f"Создано военное лобби #{war_id} на «{location_name}».")
    war_id = int(open_lobby["id"])
    host_faction = str(open_lobby["host_faction"])
    if host_faction != player.faction and not storage.are_factions_allied(host_faction, player.faction):
        return ActionResult(False, "В это лобби могут вступать только союзники хоста.")
    if not storage.add_war_lobby_member(war_id, telegram_id):
        return ActionResult(False, "Не удалось вступить в военное лобби.")
    members = storage.get_war_lobby_member_ids(war_id)
    return ActionResult(True, f"Ты вступил в военное лобби #{war_id}. Участников: {len(members)}.")


def build_war_lobby_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return "Военное лобби доступно после выбора группировки."
    lobby = find_open_war_lobby_for_character(storage, player)
    if lobby is None:
        return (
            "Открытых военных лобби нет. Создай лобби на нужную локацию.\n"
            f"Для захвата точки нужно минимум {WAR_MIN_FACTION_MEMBERS} живых бойцов в лобби."
        )
    war_id = int(lobby["id"])
    leader_id = int(lobby["leader_id"])
    creator = storage.get_character(leader_id, refresh_energy=False)
    creator_label = (
        f"{creator.nickname} (ID {leader_id})"
        if creator is not None
        else f"ID {leader_id}"
    )
    member_ids = storage.get_war_lobby_member_ids(war_id)
    members = storage.get_characters_by_ids(member_ids)
    by_faction: dict[str, int] = {}
    member_lines: list[str] = []
    for member in members:
        if member.faction is None:
            continue
        by_faction[member.faction] = by_faction.get(member.faction, 0) + 1
        mark = " 👑" if member.telegram_id == leader_id else ""
        member_lines.append(f"• {member.nickname} — {member.faction}{mark}")
    total = sum(by_faction.values())
    share_lines = []
    for faction_name, count in sorted(by_faction.items()):
        percent = int(round((count / total) * 100)) if total > 0 else 0
        share_lines.append(f"• {faction_name}: {count} бойцов ({percent}%)")
    shares_block = "\n".join(share_lines) if share_lines else "• Нет данных"
    roster_block = "\n".join(member_lines) if member_lines else "• Пока никого"
    return (
        f"Военное лобби #{war_id}\n"
        f"Локация: {lobby['location']}\n"
        f"Хост: {lobby['host_faction']}\n"
        f"Создал: {creator_label}\n"
        f"Участников: {len(member_ids)} / мин. {WAR_MIN_FACTION_MEMBERS} для запуска\n\n"
        f"Бойцы в лобби:\n{roster_block}\n\n"
        f"Распределение сил:\n{shares_block}"
    )


def can_dissolve_war_lobby(storage: Storage, telegram_id: int) -> bool:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return False
    lobby = find_open_war_lobby_for_character(storage, player)
    if lobby is None:
        return False
    return int(lobby["leader_id"]) == telegram_id


def dissolve_war_lobby(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    lobby = find_open_war_lobby_for_character(storage, player)
    if lobby is None:
        return ActionResult(False, "Открытого военного лобби нет.")
    war_id = int(lobby["id"])
    if int(lobby["leader_id"]) != telegram_id:
        return ActionResult(False, "Распустить лобби может только его создатель.")
    cancelled = storage.cancel_war_lobby(war_id, telegram_id)
    if cancelled is None:
        return ActionResult(False, "Не удалось распустить лобби.")
    location = str(cancelled.get("location", lobby["location"]))
    return ActionResult(True, f"Военное лобби #{war_id} на «{location}» распущено.")


def launch_war_lobby(storage: Storage, telegram_id: int) -> ActionResult:
    leader = storage.get_character(telegram_id, refresh_energy=False)
    if leader is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(leader):
        return ActionResult(False, _dead_block_text())
    if leader.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    lobby = storage.get_open_war_lobby_for_faction(leader.faction)
    if lobby is None:
        return ActionResult(False, "У твоей группировки нет открытого военного лобби.")
    if int(lobby["leader_id"]) != telegram_id:
        return ActionResult(False, "Запускать лобби может только лидер, который его создал.")
    war_id = int(lobby["id"])
    location_name = str(lobby["location"])
    host_faction = str(lobby.get("host_faction") or leader.faction)
    member_ids = storage.get_war_lobby_member_ids(war_id)
    members = [m for m in storage.get_characters_by_ids(member_ids) if m.health > 0 and m.faction]
    if len(members) < WAR_MIN_FACTION_MEMBERS:
        return ActionResult(False, f"Для запуска нужно минимум {WAR_MIN_FACTION_MEMBERS} живых бойцов.")
    active: list[Character] = []
    spent_ids: list[int] = []
    for member in members:
        if storage.spend_energy(member.telegram_id, 24):
            active.append(member)
            spent_ids.append(member.telegram_id)
    if len(active) < WAR_MIN_FACTION_MEMBERS:
        _refund_spent_energy(storage, spent_ids, 24)
        return ActionResult(False, "Недостаточно энергии у бойцов лобби.")
    winner = host_faction
    target = storage.get_location(location_name)
    if target is None:
        _refund_spent_energy(storage, spent_ids, 24)
        return ActionResult(False, "Локация лобби не найдена.")
    if _location_is_friendly_to_faction(storage, target, host_faction):
        _refund_spent_energy(storage, spent_ids, 24)
        return ActionResult(False, "Нельзя штурмовать свою или союзническую точку.")
    enemy_power = int(target["npc_power"])
    total_power = sum(equipment_power(member) for member in active)
    chance = int(round((total_power / (total_power + enemy_power + 10)) * 100))
    chance = max(10, min(90, chance))
    success = random.randint(1, 100) <= chance
    if success:
        previous_owner = str(target.get("controlled_by") or "")
        captured_enemy_base = (
            str(target.get("point_type") or "") == "база"
            and bool(previous_owner)
            and previous_owner != winner
        )
        storage.set_location_control(location_name, winner)
        storage.finish_war_lobby(war_id, "success", f"Победа: {winner}")
        achievement_notes: list[str] = []
        for member in active:
            if str(member.faction) != winner:
                continue
            storage.add_player_stat(member.telegram_id, "wars_won", 1)
            if captured_enemy_base:
                storage.add_player_stat(member.telegram_id, "enemy_bases_captured", 1)
            _add_rating(storage, member.telegram_id, RATING_REWARD["war_success"])
            note = _progress_and_unlock_achievements(storage, member.telegram_id)
            if note and member.telegram_id == telegram_id:
                achievement_notes.append(note)
        breakdown = ", ".join(f"{f}:{faction_counts[f]}" for f in sorted(faction_counts))
        base_note = "\nЗахвачена вражеская база!" if captured_enemy_base else ""
        return ActionResult(
            True,
            f"Штурм лобби #{war_id} успешен (шанс {chance}%).\n"
            f"Локация «{location_name}» перешла под контроль: {winner}.{base_note}\n"
            f"Распределение бойцов: {breakdown}."
            f"{''.join(achievement_notes)}",
        )
    storage.finish_war_lobby(war_id, "failed", "Поражение штурма")
    return ActionResult(False, f"Штурм лобби #{war_id} провален (шанс {chance}%).")


def transfer_location_to_ally(storage: Storage, telegram_id: int, location_name: str, ally_faction: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Сначала создай персонажа и выбери группировку.")
    if storage.get_faction_leader_id(player.faction) != telegram_id:
        return ActionResult(False, "Передавать локацию может только лидер группировки.")
    if not storage.are_factions_allied(player.faction, ally_faction):
        return ActionResult(False, "Локацию можно передать только союзнику.")
    location = storage.get_location(location_name)
    if location is None:
        return ActionResult(False, "Локация не найдена.")
    if str(location.get("controlled_by") or "") != player.faction:
        return ActionResult(False, "Передавать можно только локацию своей группировки.")
    storage.set_location_control(location_name, ally_faction)
    return ActionResult(True, f"Локация «{location_name}» передана союзнику: {ally_faction}.")


def build_faction_group_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return "Группировка доступна только после выбора группировки."

    income_result = apply_controlled_points_income(storage)
    income_note = f"\n{income_result.text}\n" if income_result.ok else "\n"

    warehouse = storage.get_faction_warehouse(player.faction)
    factions = storage.get_factions()
    faction_info = next((f for f in factions if f["name"] == player.faction), None)
    treasury = int(faction_info["treasury"]) if faction_info else 0
    warehouse_lines = [
        f"• {ITEM_LABELS.get(k, k)}: {v}"
        for k, v in sorted(warehouse.items())
        if v > 0
    ]
    if not warehouse_lines:
        warehouse_lines = ["• Склад пуст"]

    leader_hint = ""
    if storage.get_faction_leader_id(player.faction) == telegram_id:
        leader_hint = "\nТебе доступны вывод со склада/из казны и назначение званий."
    elif can_withdraw_faction_treasury(storage, player):
        leader_hint = "\nТебе доступен вывод со склада и из казны (ранг 5+)."

    return (
        f"Группировка «{player.faction}»\n"
        f"Казна: {treasury} RU"
        f"{income_note}"
        f"Склад:\n{chr(10).join(warehouse_lines)}\n\n"
        f"Пассивный доход с точек:\n"
        f"• точка ресурсов: {RESOURCE_POINT_INCOME_PER_HOUR} RU/ч\n"
        f"• база: {BASE_POINT_INCOME_PER_HOUR} RU/ч\n\n"
        f"Любой боец может сдать патроны/аптечки на склад и пополнить казну.\n"
        f"Забирать со склада и из казны — с 5 ранга (или лидер)."
        f"{leader_hint}"
    )


def build_economy_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return "Экономика доступна только после выбора группировки."

    auctions = _list_open_exchange_lots(storage)
    auctions_lines = [
        f"• #{a['id']} {ITEM_LABELS.get(str(a['item_key']), str(a['item_key']))} x{a['amount']} "
        f"за {a['price']} RU (продавец {a['seller_id']})"
        for a in auctions[:5]
    ]
    if not auctions_lines:
        auctions_lines = ["• Открытых лотов нет"]

    market_lots = list_market_lots(storage, telegram_id)
    market_lines = [
        f"• #{lot['id']} {ITEM_LABELS.get(str(lot['item_key']), str(lot['item_key']))} "
        f"x{lot['amount']} за {lot['price']} RU (продавец {lot['seller_id']})"
        for lot in market_lots[:5]
    ]
    if not market_lines:
        market_lines = ["• Открытых лотов нет"]

    return (
        f"Биржа:\n{chr(10).join(auctions_lines)}\n\n"
        f"Рынок экипировки:\n{chr(10).join(market_lines)}"
    )


def apply_controlled_points_income(storage: Storage) -> ActionResult:
    """Начисляет доход с контролируемых точек в казну группировок."""
    raw_last = storage.get_meta(POINTS_INCOME_META_KEY)
    now = datetime.now(timezone.utc)
    if raw_last:
        try:
            last = datetime.fromisoformat(raw_last)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except ValueError:
            last = now - timedelta(hours=1)
    else:
        last = now - timedelta(hours=1)

    hours = int((now - last).total_seconds() // 3600)
    if hours <= 0:
        return ActionResult(False, "Приток с точек пока не начислен (меньше часа).")
    hours = min(hours, POINTS_INCOME_MAX_HOURS)

    totals: dict[str, int] = {}
    for location in storage.get_locations():
        owner = location.get("controlled_by")
        if not owner:
            continue
        point_type = str(location.get("point_type") or "")
        if point_type == "точка ресурсов":
            income = RESOURCE_POINT_INCOME_PER_HOUR * hours
        elif point_type == "база":
            income = BASE_POINT_INCOME_PER_HOUR * hours
        else:
            continue
        storage.change_faction_treasury(str(owner), income)
        totals[str(owner)] = totals.get(str(owner), 0) + income

    paid_until = last + timedelta(hours=hours)
    storage.set_meta(POINTS_INCOME_META_KEY, paid_until.isoformat())

    if not totals:
        return ActionResult(True, f"Прошло {hours} ч., но контролируемых ресурсных точек/баз нет.")
    lines = [f"Приток за {hours} ч.:"]
    for faction, amount in sorted(totals.items()):
        lines.append(f"• {faction}: +{amount} RU в казну")
    return ActionResult(True, "\n".join(lines))


PLAYERS_PAGE_SIZE = 10
PLAYERS_FACTION_ORDER = ("Долг", "Свобода", "Нейтралы", "Бандиты")
PLAYERS_NO_FACTION_KEY = "_none"
PLAYERS_NO_FACTION_LABEL = "Без группировки"


def _players_nickname_sort_key(row: dict[str, Any]) -> str:
    return str(row.get("nickname") or "").casefold()


def group_players_by_faction(storage: Storage) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """[(faction_key, title, players_sorted), ...] с известными гп сверху."""
    rows = storage.list_players(limit=500)
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in PLAYERS_FACTION_ORDER}
    buckets[PLAYERS_NO_FACTION_KEY] = []
    extra: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        faction = str(row.get("faction") or "").strip()
        if not faction:
            buckets[PLAYERS_NO_FACTION_KEY].append(row)
        elif faction in buckets:
            buckets[faction].append(row)
        else:
            extra.setdefault(faction, []).append(row)

    result: list[tuple[str, str, list[dict[str, Any]]]] = []
    for faction in PLAYERS_FACTION_ORDER:
        players = sorted(buckets[faction], key=_players_nickname_sort_key)
        result.append((faction, faction, players))
    for faction in sorted(extra.keys(), key=lambda name: name.casefold()):
        players = sorted(extra[faction], key=_players_nickname_sort_key)
        result.append((faction, faction, players))
    none_players = sorted(buckets[PLAYERS_NO_FACTION_KEY], key=_players_nickname_sort_key)
    result.append((PLAYERS_NO_FACTION_KEY, PLAYERS_NO_FACTION_LABEL, none_players))
    return result


def build_players_root_text(storage: Storage) -> tuple[str, list[tuple[str, str, int]]]:
    groups = group_players_by_faction(storage)
    total = sum(len(players) for _, _, players in groups)
    menu_items = [(key, title, len(players)) for key, title, players in groups]
    if total == 0:
        return ("Игроков пока нет.", menu_items)

    lines = [
        "👥 Игроки Зоны",
        "Выбери группировку. Ники внутри — по алфавиту, по 10 на страницу.",
        f"Всего игроков: {total}",
        "",
    ]
    for _key, title, count in menu_items:
        lines.append(f"• {title}: {count}")
    return ("\n".join(lines), menu_items)


def build_players_faction_page_text(
    storage: Storage,
    faction_key: str,
    page: int = 0,
) -> tuple[str, str, int, int]:
    """Возвращает (text, faction_key, page, total_pages)."""
    groups = {key: (title, players) for key, title, players in group_players_by_faction(storage)}
    if faction_key not in groups:
        return ("Группировка не найдена. Вернись к списку группировок.", faction_key, 0, 1)

    title, players = groups[faction_key]
    total = len(players)
    if total == 0:
        return (f"👥 {title}\nПока никого нет.", faction_key, 0, 1)

    total_pages = max(1, (total + PLAYERS_PAGE_SIZE - 1) // PLAYERS_PAGE_SIZE)
    safe_page = max(0, min(int(page), total_pages - 1))
    start = safe_page * PLAYERS_PAGE_SIZE
    chunk = players[start : start + PLAYERS_PAGE_SIZE]

    lines = [
        f"👥 {title}",
        f"Страница {safe_page + 1}/{total_pages} • игроков: {total}",
        "",
    ]
    for row in chunk:
        member = storage.get_character(int(row["telegram_id"]), refresh_energy=False)
        rank = character_rank_title(storage, member) if member else None
        rank_part = f" [{rank}]" if rank else ""
        lines.append(f"• {row['nickname']}{rank_part} — {row['telegram_id']}")
    return ("\n".join(lines), faction_key, safe_page, total_pages)


def build_players_directory(storage: Storage, limit: int = 50) -> str:
    """Совместимость: текстовый обзор без inline-меню."""
    text, _items = build_players_root_text(storage)
    return text


def build_faction_broadcast_text(
    storage: Storage,
    telegram_id: int,
    custom_text: str | None = None,
) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if storage.get_faction_leader_id(player.faction) != telegram_id:
        return ActionResult(False, "Рассылку может делать только командир группировки.")
    body = (custom_text or "Бойцы, общий сбор!").strip()
    if not body:
        return ActionResult(False, "Текст рассылки пустой.")
    text = f"📣 [{player.faction}] {player.nickname}:\n{body}"
    return ActionResult(True, text)


def list_faction_broadcast_targets(storage: Storage, telegram_id: int) -> list[int]:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return []
    return [tid for tid in storage.list_faction_member_ids(player.faction) if tid != telegram_id]


def _safe_base_location_names(storage: Storage) -> set[str]:
    return {
        str(location["name"])
        for location in storage.get_locations()
        if str(location.get("point_type") or "") == "база"
    }


def _parse_meta_datetime(raw: str | None, fallback: datetime) -> datetime:
    if not raw:
        return fallback
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def process_emission_cycle(storage: Storage) -> tuple[str, list[int]]:
    """Цикл Выброса: предупреждения за 60/30 мин, убийство вне базы.

    Возвращает (текст оповещения, telegram_id для рассылки).
    Пустой текст — нечего слать.
    """
    now = datetime.now(timezone.utc)
    notify_ids = storage.list_player_ids()
    raw_at = storage.get_meta(EMISSION_META_AT)
    warn60 = storage.get_meta(EMISSION_META_WARN60) == "1"
    warn30 = storage.get_meta(EMISSION_META_WARN30) == "1"

    if raw_at is None:
        emission_at = now + timedelta(hours=EMISSION_INTERVAL_HOURS)
        storage.set_meta(EMISSION_META_AT, emission_at.isoformat())
        storage.set_meta(EMISSION_META_WARN60, "0")
        storage.set_meta(EMISSION_META_WARN30, "0")
        return ("", [])

    emission_at = _parse_meta_datetime(raw_at, now + timedelta(hours=EMISSION_INTERVAL_HOURS))
    minutes_left = (emission_at - now).total_seconds() / 60.0

    if minutes_left > EMISSION_WARN_60_MINUTES:
        return ("", [])

    base_names = ", ".join(sorted(_safe_base_location_names(storage))) or "базы группировок"

    if minutes_left > EMISSION_WARN_30_MINUTES and not warn60:
        storage.set_meta(EMISSION_META_WARN60, "1")
        return (
            "⚠️ ВЫБРОС через 60 минут!\n"
            "Если ты не на базе к моменту Выброса — персонаж погибнет.\n"
            f"Безопасные базы: {base_names}.",
            notify_ids,
        )

    if 0 < minutes_left <= EMISSION_WARN_30_MINUTES:
        if not warn60:
            storage.set_meta(EMISSION_META_WARN60, "1")
        if not warn30:
            storage.set_meta(EMISSION_META_WARN30, "1")
            return (
                "☢️ ВЫБРОС через 30 минут!\n"
                "Срочно уходи на базу — вне базы Выброс убивает.\n"
                f"Безопасные базы: {base_names}.",
                notify_ids,
            )
        return ("", [])

    if minutes_left > 0:
        return ("", [])

    safe_bases = _safe_base_location_names(storage)
    killed: list[str] = []
    for row in storage.list_players(limit=500):
        if int(row.get("health") or 0) <= 0:
            continue
        location = str(row.get("location") or "")
        if location in safe_bases:
            continue
        telegram_id = int(row["telegram_id"])
        storage.change_health(telegram_id, -int(row["health"]))
        killed.append(str(row.get("nickname") or telegram_id))

    next_at = now + timedelta(hours=EMISSION_INTERVAL_HOURS)
    storage.set_meta(EMISSION_META_AT, next_at.isoformat())
    storage.set_meta(EMISSION_META_WARN60, "0")
    storage.set_meta(EMISSION_META_WARN30, "0")

    killed_text = (
        ", ".join(killed[:20]) + ("…" if len(killed) > 20 else "")
        if killed
        else "никто не пострадал (все были на базах)"
    )
    return (
        f"💥 ВЫБРОС прошел по Зоне!\n"
        f"Погибшие вне баз: {killed_text}.\n"
        f"Следующий Выброс примерно через {EMISSION_INTERVAL_HOURS} ч.",
        notify_ids,
    )


def build_emission_status(storage: Storage) -> str:
    now = datetime.now(timezone.utc)
    raw_at = storage.get_meta(EMISSION_META_AT)
    if raw_at is None:
        return (
            f"Выброс: расписание ещё не запущено "
            f"(цикл раз в {EMISSION_INTERVAL_HOURS} ч., предупреждения за 60 и 30 мин)."
        )
    emission_at = _parse_meta_datetime(raw_at, now + timedelta(hours=EMISSION_INTERVAL_HOURS))
    minutes_left = max(0, int((emission_at - now).total_seconds() // 60))
    hours_left = minutes_left // 60
    mins = minutes_left % 60
    bases = ", ".join(sorted(_safe_base_location_names(storage))) or "базы"
    return (
        f"Выброс через ~{hours_left} ч. {mins} мин.\n"
        f"Вне базы ({bases}) Выброс убивает персонажа.\n"
        "Оповещения: за 60 и 30 минут."
    )


def _roll_smuggling_loot(storage: Storage, telegram_id: int) -> list[str]:
    """Независимые роллы дропа контрабанды. Возвращает строки для отчёта."""
    drops: list[str] = []

    if random.randint(1, 100) <= SMUGGLING_CONSUMABLE_CHANCE:
        amount = random.randint(1, 2)
        storage.add_item(telegram_id, "medkit", amount)
        drops.append(f"{ITEM_LABELS['medkit']} x{amount}")

    if random.randint(1, 100) <= SMUGGLING_CONSUMABLE_CHANCE:
        food_key = random.choice(SMUGGLING_FOOD_DROP_KEYS)
        amount = random.randint(1, 2)
        storage.add_item(telegram_id, food_key, amount)
        drops.append(f"{ITEM_LABELS.get(food_key, food_key)} x{amount}")

    if random.randint(1, 100) <= SMUGGLING_CONSUMABLE_CHANCE:
        water_key = random.choice(SMUGGLING_WATER_DROP_KEYS)
        amount = random.randint(1, 2)
        storage.add_item(telegram_id, water_key, amount)
        drops.append(f"{ITEM_LABELS.get(water_key, water_key)} x{amount}")

    if random.randint(1, 100) <= SMUGGLING_ARMOR_T2_CHANCE:
        armor_key = random.choice(SMUGGLING_ARMOR_T2_KEYS)
        storage.add_item(telegram_id, armor_key, 1)
        drops.append(ITEM_LABELS.get(armor_key, armor_key))

    if random.randint(1, 100) <= SMUGGLING_WEAPON_T1_CHANCE:
        weapon_key = random.choice(SMUGGLING_WEAPON_T1_KEYS)
        storage.add_item(telegram_id, weapon_key, 1)
        drops.append(ITEM_LABELS.get(weapon_key, weapon_key))

    if random.randint(1, 100) <= SMUGGLING_OTKLIK_CHANCE:
        storage.add_item(telegram_id, "detector_otklik", 1)
        drops.append(ITEM_LABELS["detector_otklik"])

    return drops


def attempt_smuggling(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")

    energy_cost = 14
    if not storage.spend_energy(telegram_id, energy_cost):
        return ActionResult(False, f"Не хватает энергии для контрабанды (нужно {energy_cost}).")

    truck_bonus = 12 if player.truck_owned and player.fuel > 0 else 0
    if truck_bonus > 0 and not storage.change_fuel(telegram_id, -1):
        truck_bonus = 0
    event_modifier = _active_location_event_modifier(storage, player.location)
    chance = min(90, max(20, 42 + equipment_power(player) * 3 + truck_bonus - max(0, event_modifier)))
    roll = random.randint(1, 100)
    success = roll <= chance

    if success:
        reward = random.randint(280, 520)
        warehouse_bonus = random.randint(1, 3)
        durability_text = _apply_durability_decay(storage, telegram_id, weapon_loss=4, armor_loss=2)
        storage.change_money(telegram_id, reward)
        storage.change_faction_treasury(player.faction, reward // 3)
        storage.change_faction_warehouse_item(player.faction, "ammo_pack", warehouse_bonus)
        loot_lines = _roll_smuggling_loot(storage, telegram_id)
        loot_text = (
            "\nДроп:\n" + "\n".join(f"• {line}" for line in loot_lines)
            if loot_lines
            else "\nДроп: пусто (не повезло с доп. находками)."
        )
        _add_rating(storage, telegram_id, RATING_REWARD["smuggle_success"])
        storage.add_player_stat(telegram_id, "smuggling_success", 1)
        storage.add_player_stat(telegram_id, "money_earned", reward)
        achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
        return ActionResult(
            True,
            f"Контрабанда удалась! Шанс {chance}% (бросок {roll}).\n"
            f"Ты получил {reward} RU, в казну ушло {reward // 3} RU.\n"
            f"На склад добавлено патронов: +{warehouse_bonus}."
            f"{loot_text}{durability_text}{achievements_text}",
        )

    penalty = random.randint(120, 240)
    durability_text = _apply_durability_decay(storage, telegram_id, weapon_loss=5, armor_loss=3)
    storage.change_money(telegram_id, -penalty)
    storage.change_health(telegram_id, -12)
    _add_rating(storage, telegram_id, -RATING_REWARD["smuggle_fail"])
    return ActionResult(
        False,
        f"Контрабанда сорвана. Шанс {chance}% (бросок {roll}).\n"
        f"Потери: {penalty} RU и ранение (-12 HP).{durability_text}",
    )


def _schedule_next_zone_event(storage: Storage, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    delay = random.randint(ZONE_EVENT_INTERVAL_MIN_MINUTES, ZONE_EVENT_INTERVAL_MAX_MINUTES)
    next_at = now + timedelta(minutes=delay)
    storage.set_meta(ZONE_EVENT_META_NEXT_AT, next_at.isoformat())
    return next_at


def apply_dynamic_zone_event(storage: Storage) -> ActionResult:
    storage.delete_expired_map_events()
    locations = storage.get_locations()
    if not locations:
        return ActionResult(False, "Локации пока недоступны.")
    target = random.choice(locations)
    event_type, modifier, description = random.choice(ZONE_EVENT_POOL)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
    location_name = str(target["name"])
    storage.upsert_map_event(
        location=location_name,
        event_type=event_type,
        modifier=modifier,
        description=description,
        expires_at=expires_at,
    )

    # Динамический спавн/ослабление NPC под событие.
    current_power = int(target["npc_power"])
    mutated_power = max(8, current_power + random.randint(-3, 7) + modifier // 2)
    storage.set_location_npc_power(location_name, mutated_power)
    return ActionResult(
        True,
        f"Новое событие в Зоне: {location_name}\n{description}\n"
        f"Модификатор силы NPC: {modifier:+d}, текущая сила NPC: {mutated_power}.",
    )


def process_zone_event_cycle(storage: Storage) -> tuple[str, list[int]]:
    """Автогенерация событий Зоны в случайный момент (каждые 30–90 мин)."""
    now = datetime.now(timezone.utc)
    storage.delete_expired_map_events()
    raw_at = storage.get_meta(ZONE_EVENT_META_NEXT_AT)
    if raw_at is None:
        _schedule_next_zone_event(storage, now)
        return ("", [])

    next_at = _parse_meta_datetime(
        raw_at,
        now + timedelta(minutes=ZONE_EVENT_INTERVAL_MIN_MINUTES),
    )
    if next_at > now:
        return ("", [])

    result = apply_dynamic_zone_event(storage)
    _schedule_next_zone_event(storage, now)
    if not result.ok:
        return ("", [])
    return (result.text, storage.list_player_ids())


def build_events_overview(storage: Storage) -> str:
    storage.delete_expired_map_events()
    events = storage.get_map_events()
    emission_status = build_emission_status(storage)
    if not events:
        return (
            f"{emission_status}\n\n"
            "Активных событий на карте нет. Зона затихла.\n"
            "Новые события появляются сами через некоторое время."
        )

    now = datetime.now(timezone.utc)
    by_location = {loc["name"]: int(loc["npc_power"]) for loc in storage.get_locations()}
    lines = [emission_status, "", "Активные события Зоны:"]
    for event in events:
        location = str(event.get("location"))
        expires_at = _safe_fromiso(str(event.get("expires_at", "")))
        minutes_left = max(0, int((expires_at - now).total_seconds() // 60))
        modifier = int(event.get("modifier", 0))
        npc_power = by_location.get(location, 0)
        lines.append(
            f"• {location}: {event.get('description')} (мод {modifier:+d}, NPC {npc_power}, ~{minutes_left} мин)"
        )
    return "\n".join(lines)
