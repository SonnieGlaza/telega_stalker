from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.skins import resolve_skin
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
    "easy": QuestType("easy", "Легко", 96, 10, 170, 310, 0, 0),
    "hard": QuestType("hard", "Сложно", 80, 16, 250, 450, 0, 0),
    "heavy": QuestType("heavy", "Тяжело", 70, 22, 400, 650, 2, 1),
    "impossible": QuestType("impossible", "Невозможно", 60, 28, 550, 900, 3, 1),
}


SHOP_ITEMS: dict[str, dict[str, int | str]] = {
    "energy_drink": {"name": "Энергетик", "buy_price": 250, "sell_price": 170},
    "medkit": {"name": "Аптечка", "buy_price": 260, "sell_price": 120},
    "ammo_pack": {"name": "Патроны", "buy_price": 120, "sell_price": 55},
    "artifact": {"name": "Артефакт", "buy_price": 0, "sell_price": 650},
    "gear_upgrade": {"name": "Улучшение снаряги", "buy_price": 1200, "sell_price": 0},
    "truck": {"name": "Грузовик", "buy_price": 7000, "sell_price": 0},
    "fuel_can": {"name": "Канистра топлива (+5)", "buy_price": 450, "sell_price": 200},
}

ARMOR_CATALOG: dict[str, dict[str, int | str]] = {
    "armor_leather": {"name": "Кожаная куртка", "buy_price": 900, "sell_price": 420},
    "armor_stalker_vest": {"name": "Сталкерский бронежилет", "buy_price": 1800, "sell_price": 850},
    "armor_psz7d": {"name": "ПСЗ-7 «Долг»", "buy_price": 2900, "sell_price": 1400},
    "armor_zarya": {"name": "Комбинезон «Заря»", "buy_price": 3800, "sell_price": 1850},
    "armor_bulat": {"name": "ПСЗ-9д «Булат»", "buy_price": 5200, "sell_price": 2550},
    "armor_seva": {"name": "Костюм СЕВА", "buy_price": 7600, "sell_price": 3700},
    "armor_scientific": {"name": "Научный костюм", "buy_price": 9800, "sell_price": 4800},
    "armor_exo": {"name": "Экзоскелет", "buy_price": 12000, "sell_price": 5800},
    "armor_nosorog": {"name": "Носорог", "buy_price": 18000, "sell_price": 8800},
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
    "weapon_an94": {"name": "АН-94", "buy_price": 6200, "sell_price": 3000},
    "weapon_vintar": {"name": "Винтарь ВС", "buy_price": 8700, "sell_price": 4300},
    "weapon_svd": {"name": "СВДм-2", "buy_price": 9800, "sell_price": 4800},
    "weapon_rp74": {"name": "РП-74", "buy_price": 10500, "sell_price": 5200},
    "weapon_gauss": {"name": "Гаусс-пушка", "buy_price": 22000, "sell_price": 11000},
}

# Legacy callback alias used in keyboards.
WEAPON_CATALOG["weapon_fora12"] = WEAPON_CATALOG["weapon_fort12"]
ARMOR_CATALOG["armor_sunrise"] = ARMOR_CATALOG["armor_zarya"]
ARMOR_CATALOG["armor_berill5m"] = ARMOR_CATALOG["armor_bulat"]
ARMOR_CATALOG["armor_exoskeleton"] = ARMOR_CATALOG["armor_exo"]

SHOP_ITEMS.update(ARMOR_CATALOG)
SHOP_ITEMS.update(WEAPON_CATALOG)

def _build_level_map(catalog: dict[str, dict[str, int | str]]) -> dict[str, int]:
    ranked: list[tuple[str, int]] = []
    seen_names: set[str] = set()
    for item in sorted(catalog.values(), key=lambda entry: int(entry["buy_price"])):
        name = str(item["name"])
        if name in seen_names:
            continue
        seen_names.add(name)
        ranked.append((name, len(ranked) + 1))
    return {name: level for name, level in ranked}


WEAPON_RATING_BY_NAME: dict[str, int] = _build_level_map(WEAPON_CATALOG)
WEAPON_RATING_BY_NAME.setdefault("Нож", 1)

ARMOR_RATING_BY_NAME: dict[str, int] = _build_level_map(ARMOR_CATALOG)
ARMOR_RATING_BY_NAME.setdefault("Куртка новичка", 1)
# Совместимость с историческими названиями экипировки из старых сохранений.
ARMOR_RATING_BY_NAME.setdefault("Бронежилет сталкера", ARMOR_RATING_BY_NAME.get("Сталкерский бронежилет", 2))
ARMOR_RATING_BY_NAME.setdefault("Усиленный бронекостюм", ARMOR_RATING_BY_NAME.get("ПСЗ-7 «Долг»", 3))
ARMOR_RATING_BY_NAME.setdefault("Штурмовой экзоскелет", ARMOR_RATING_BY_NAME.get("Экзоскелет", 7))


ITEM_LABELS = {
    "energy_drink": "Энергетик",
    "medkit": "Аптечка",
    "ammo_pack": "Патроны",
    "artifact": "Артефакт",
    "armor_leather": "Кожаная куртка",
    "armor_stalker_vest": "Сталкерский бронежилет",
    "armor_psz7d": "ПСЗ-7 «Долг»",
    "armor_zarya": "Комбинезон «Заря»",
    "armor_bulat": "ПСЗ-9д «Булат»",
    "armor_seva": "Костюм СЕВА",
    "armor_scientific": "Научный костюм",
    "armor_exo": "Экзоскелет",
    "armor_nosorog": "Носорог",
    "armor_sunrise": "Комбинезон «Заря»",
    "armor_berill5m": "ПСЗ-9д «Булат»",
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

WAREHOUSE_ITEM_KEYS = ("ammo_pack", "medkit", "energy_drink", "artifact")

AUCTION_DEFAULT_LOTS: dict[str, tuple[str, int, int]] = {
    "artifact": ("artifact", 1, 900),
    "ammo_pack": ("ammo_pack", 5, 520),
    "medkit": ("medkit", 2, 420),
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


@dataclass(frozen=True)
class AchievementRule:
    key: str
    title: str
    description: str
    reward_ru: int
    reward_rating: int
    check: Callable[[dict[str, int], Character], bool]


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    text: str


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
    artifact_bonus = 2 if artifact_name and artifact_name != "Нет" else 0
    durability_penalty = _durability_penalty(weapon_durability, 6) + _durability_penalty(armor_durability, 6)
    return max(1, weapon_level + armor_level + artifact_bonus - durability_penalty)


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
RESPAWN_BASE_LOCATION = "Росток"


def _is_dead(character: Character) -> bool:
    return character.health <= 0


def _dead_block_text() -> str:
    return "Персонаж мертв (HP=0). Используй респавн из инвентаря."


def build_dead_character_text(character: Character) -> str:
    return (
        f"☠️ {character.nickname}, ты погиб в Зоне.\n"
        f"HP: {character.health}/100\n"
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
    storage.set_location(telegram_id, RESPAWN_BASE_LOCATION)
    return ActionResult(
        True,
        f"Ты был эвакуирован в «{RESPAWN_BASE_LOCATION}».\n"
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
            key="raid_5",
            title="Рейд-лидер",
            description="Заверши 5 успешных рейдов",
            reward_ru=700,
            reward_rating=55,
            check=lambda stats, _: stats["raids_completed"] >= 5,
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
            key="smuggle_10",
            title="Контрабандист",
            description="Успешно проведи 10 контрабанд",
            reward_ru=500,
            reward_rating=35,
            check=lambda stats, _: stats["smuggling_success"] >= 10,
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
            key="money_20000",
            title="Толстый кошелек",
            description="Заработай суммарно 20 000 RU",
            reward_ru=1200,
            reward_rating=80,
            check=lambda stats, _: stats["money_earned"] >= 20_000,
        ),
        AchievementRule(
            key="gear_14",
            title="Экзоветеран",
            description="Достигни силы снаряги 14+",
            reward_ru=1000,
            reward_rating=70,
            check=lambda _stats, character: compute_total_gear_power(character) >= 14,
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
        if not rule.check(stats, character):
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
    for rule in ACHIEVEMENT_RULES[:6]:
        marker = "✅" if rule.key in unlocked_keys else "⬜"
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
    artifact_bonus = 2 if artifact_name and artifact_name != "Нет" else 0
    armor_penalty = _durability_penalty(armor_durability, max_penalty=6)
    weapon_penalty = _durability_penalty(weapon_durability, max_penalty=6)
    return max(0, armor_bonus + weapon_bonus + artifact_bonus - armor_penalty - weapon_penalty)


def calculate_quest_success(
    gear_power: int,
    gear_bonus: int,
    max_success: int,
    ammo_stock: int,
    medkit_stock: int,
    ammo_required: int,
    medkit_required: int,
) -> QuestChanceBreakdown:
    # Шанс складывается из силы и качества снаряги + запасов амуниции/аптечек.
    base_chance = 18 + gear_power * 4 + gear_bonus
    extra_ammo = max(0, ammo_stock - ammo_required)
    extra_medkits = max(0, medkit_stock - medkit_required)
    ammo_bonus = min(18, extra_ammo * 2)
    medkit_bonus = min(12, extra_medkits * 4)
    chance = max(10, min(max_success, base_chance + ammo_bonus + medkit_bonus))
    return QuestChanceBreakdown(
        chance=chance,
        base_chance=base_chance,
        gear_bonus=gear_bonus,
        ammo_bonus=ammo_bonus,
        medkit_bonus=medkit_bonus,
    )


def build_quest_overview(character: Character) -> str:
    ammo_stock = int(character.inventory.get("ammo_pack", 0))
    medkit_stock = int(character.inventory.get("medkit", 0))
    lines = [
        "Текущие запасы расходников:",
        f"• Запас патронов: {ammo_stock}",
        f"• Запас аптечек: {medkit_stock}",
        "",
    ]
    for quest in QUESTS.values():
        if quest.ammo_required == 0 and quest.medkit_required == 0:
            lines.append(f"• {quest.title}: без обязательного расхода расходников")
            continue
        lines.append(f"• {quest.title}: расход патроны {quest.ammo_required}, аптечки {quest.medkit_required}")
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
    ammo_stock = int(character.inventory.get("ammo_pack", 0))
    medkit_stock = int(character.inventory.get("medkit", 0))
    gear_bonus = calculate_equipment_bonus(character)
    breakdown = calculate_quest_success(
        gear_power=compute_total_gear_power(character),
        gear_bonus=gear_bonus,
        max_success=quest.max_success,
        ammo_stock=ammo_stock,
        medkit_stock=medkit_stock,
        ammo_required=quest.ammo_required,
        medkit_required=quest.medkit_required,
    )
    return breakdown.chance


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

    ammo_after = int(updated.inventory.get("ammo_pack", 0))
    medkit_after = int(updated.inventory.get("medkit", 0))
    gear_bonus = calculate_equipment_bonus(updated)
    breakdown = calculate_quest_success(
        gear_power=compute_total_gear_power(updated),
        gear_bonus=gear_bonus,
        max_success=quest.max_success,
        ammo_stock=ammo_after,
        medkit_stock=medkit_after,
        ammo_required=quest.ammo_required,
        medkit_required=quest.medkit_required,
    )
    roll = random.randint(1, 100)
    success = roll <= breakdown.chance

    durability_text = _apply_durability_decay(storage, telegram_id, weapon_loss=3, armor_loss=2)
    if success:
        reward = random.randint(quest.reward_min, quest.reward_max)
        storage.change_money(telegram_id, reward)
        _add_rating(storage, telegram_id, RATING_REWARD["quest_success"])
        storage.add_player_stat(telegram_id, "quests_completed", 1)
        storage.add_player_stat(telegram_id, "money_earned", reward)

        if random.random() < 0.18:
            storage.add_item(telegram_id, "artifact", 1)
            extra = "\nТы нашел редкий артефакт!"
        else:
            extra = ""
        achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
        return ActionResult(
            True,
            f"Задание «{quest.title}» выполнено! Шанс {breakdown.chance}% (бросок {roll}).\n"
            f"Формула: база {breakdown.base_chance}% (включая снарягу +{breakdown.gear_bonus}%) "
            f"+ патроны {breakdown.ammo_bonus}% + аптечки {breakdown.medkit_bonus}%.\n"
            f"Расход: патроны {quest.ammo_required}, аптечки {quest.medkit_required}.\n"
            f"Награда: {reward} RU.{extra}{durability_text}{achievements_text}",
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
    if player.health >= 100:
        return ActionResult(False, "Здоровье уже полное, аптечка не требуется.")
    if not storage.remove_item(telegram_id, "medkit", 1):
        return ActionResult(False, "У тебя нет аптечки в инвентаре.")
    heal_amount = min(25, 100 - player.health)
    storage.change_health(telegram_id, heal_amount)
    return ActionResult(True, f"Ты использовал аптечку и восстановил {heal_amount} HP.")


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
    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, f"Недостаточно денег для покупки: {title}.")

    if item_key == "gear_upgrade":
        return ActionResult(False, "Улучшение снаряги отключено. Сила теперь зависит от оружия и брони.")
    if item_key == "truck":
        storage.set_truck_owned(telegram_id)
        return ActionResult(True, "Покупка оформлена: грузовик теперь в твоем распоряжении.")
    if item_key == "fuel_can":
        storage.change_fuel(telegram_id, 5)
        return ActionResult(True, f"Куплена канистра топлива. Топливо +5 (стоимость {price} RU).")
    if item_key in WEAPON_CATALOG:
        storage.add_item(telegram_id, item_key, 1)
        return ActionResult(
            True,
            f"Куплено оружие: {title} (стоимость {price} RU).\n"
            "Предмет добавлен в инвентарь, экипируй его вручную в разделе снаряжения.",
        )
    if item_key in ARMOR_CATALOG:
        storage.add_item(telegram_id, item_key, 1)
        return ActionResult(
            True,
            f"Куплена броня: {title}.\n"
            "Предмет добавлен в инвентарь, экипируй его вручную в разделе снаряжения.",
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
    if item_key == "artifact":
        removed_from_inventory = storage.remove_item(telegram_id, "artifact", 1)
        if not removed_from_inventory:
            equipped_artifact = str(character.equipment.get("artifact", "Нет"))
            if equipped_artifact and equipped_artifact != "Нет":
                storage.set_equipment_item(telegram_id, "artifact", "Нет")
            else:
                return ActionResult(False, "У тебя нет артефакта для продажи.")
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


def equip_artifact(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    equipped_artifact = str(player.equipment.get("artifact", "Нет"))
    if equipped_artifact != "Нет":
        return ActionResult(False, "Артефакт уже экипирован.")
    if not storage.remove_item(telegram_id, "artifact", 1):
        return ActionResult(False, "У тебя нет артефакта в инвентаре.")
    storage.set_equipment_item(telegram_id, "artifact", "Артефакт Зоны")
    achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
    return ActionResult(True, f"Артефакт экипирован. Бонус к выживаемости активирован.{achievements_text}")


def format_inventory(character: Character) -> str:
    skin = resolve_skin(character)
    if character.inventory:
        items = "\n".join(
            f"• {ITEM_LABELS.get(key, key)} x{amount}"
            for key, amount in sorted(character.inventory.items())
        )
    else:
        items = "• Пусто"

    vehicle = "Есть грузовик" if character.truck_owned else "Нет транспорта"
    equipment_labels = {
        "weapon": "Оружие",
        "armor": "Броня",
        "artifact": "Артефакт",
    }
    weapon_durability = _durability_percent(character, "weapon")
    armor_durability = _durability_percent(character, "armor")
    equipment = "\n".join(
        (
            f"• {equipment_labels.get(k, k)}: {v}"
            if k in {"weapon", "armor"}
            else f"• {k}: {v}"
        )
        for k, v in character.equipment.items()
        if k in {"weapon", "armor", "artifact"}
    )
    durability_block = (
        f"• Прочность оружия: {weapon_durability}%\n"
        f"• Прочность брони: {armor_durability}%"
    )

    current_gear_power = equipment_power(character)
    return (
        f"👤 {character.nickname} ({character.gender})\n"
        f"ID-адрес: {character.player_uid}\n"
        f"Telegram ID: {character.telegram_id}\n"
        f"Фракция: {character.faction or 'не выбрана'}\n"
        f"Локация: {character.location}\n"
        f"Здоровье: {character.health}\n"
        f"Энергия: {character.energy}/{character.max_energy}\n"
        f"Сила снаряги: {current_gear_power}\n"
        f"Скин: {skin.title}\n"
        f"Баланс: {character.money} RU\n"
        f"Транспорт: {vehicle}\n"
        f"Топливо: {character.fuel}\n\n"
        f"Снаряга:\n{equipment}\n{durability_block}\n\n"
        f"Вещи:\n{items}"
    )


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

    will_use_truck = character.truck_owned and character.fuel > 0
    energy_cost = 8 if will_use_truck else 16
    travel_minutes = 10 if will_use_truck else 30

    if target["point_type"] == "точка интереса" and target["controlled_by"] == character.faction:
        travel_minutes = max(5, int(travel_minutes * 0.7))

    if not storage.spend_energy(telegram_id, energy_cost):
        return ActionResult(False, f"Не хватает энергии для перехода (нужно {energy_cost}).")
    if will_use_truck and not storage.change_fuel(telegram_id, -1):
        storage.restore_energy(telegram_id, energy_cost)
        return ActionResult(False, "Не удалось списать топливо, переход отменен.")

    storage.set_location(telegram_id, destination)
    return ActionResult(
        True,
        f"Переход в «{destination}» выполнен.\n"
        f"Затрачено энергии: {energy_cost}.\n"
        f"Оценка времени пути: ~{travel_minutes} мин.",
    )


def attack_location(storage: Storage, telegram_id: int, location_name: str) -> ActionResult:
    character = storage.get_character(telegram_id)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(character):
        return ActionResult(False, _dead_block_text())
    if character.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")
    if storage.get_faction_active_members_count(character.faction) < WAR_MIN_FACTION_MEMBERS:
        return ActionResult(
            False,
            f"Для войны нужно минимум {WAR_MIN_FACTION_MEMBERS} бойцов группировки с живым персонажем.",
        )

    locations = {loc["name"]: loc for loc in storage.get_locations()}
    if location_name not in locations:
        return ActionResult(False, "Локация не найдена.")

    target = locations[location_name]
    if target["point_type"] == "база" and target["controlled_by"] == character.faction:
        return ActionResult(False, "Нельзя атаковать собственную базу своей группировки.")

    faction_power = storage.get_faction_power(character.faction)
    squad_power = max(1, faction_power)
    enemy_power = int(target["npc_power"])
    if target["controlled_by"] and target["controlled_by"] != character.faction:
        enemy_power += 10

    if not storage.spend_energy(telegram_id, 24):
        return ActionResult(False, "Недостаточно энергии для штурма (нужно 24).")

    chance = int(round((squad_power / (squad_power + enemy_power)) * 100))
    chance = max(10, min(90, chance))
    weapon_penalty = _durability_penalty(_durability_percent(character, "weapon"), max_penalty=18)
    armor_penalty = _durability_penalty(_durability_percent(character, "armor"), max_penalty=12)
    chance = max(8, chance - weapon_penalty - armor_penalty // 2)
    roll = random.randint(1, 100)
    success = roll <= chance

    durability_text = _apply_durability_decay(storage, telegram_id, weapon_loss=5, armor_loss=4)
    if success:
        storage.set_location_control(location_name, character.faction)
        personal_reward = 250
        treasury_reward = 0

        if target["point_type"] == "точка ресурсов":
            treasury_reward = 1800
            storage.change_faction_treasury(character.faction, treasury_reward)
        elif target["point_type"] == "база":
            treasury_reward = 900
            storage.change_faction_treasury(character.faction, treasury_reward)

        storage.change_money(telegram_id, personal_reward)
        _add_rating(storage, telegram_id, RATING_REWARD["war_success"])
        storage.add_player_stat(telegram_id, "wars_won", 1)
        storage.add_player_stat(telegram_id, "money_earned", personal_reward)
        achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
        return ActionResult(
            True,
            f"Штурм успешен! Шанс {chance}% (бросок {roll}).\n"
            f"Точка «{location_name}» под контролем {character.faction}.\n"
            f"Личная награда: {personal_reward} RU.\n"
            f"В казну группировки: {treasury_reward} RU.{durability_text}{achievements_text}",
        )

    loss = random.randint(80, 170)
    storage.change_money(telegram_id, -loss)
    _add_rating(storage, telegram_id, -RATING_REWARD["war_fail"])
    return ActionResult(
        False,
        f"Штурм провален. Шанс {chance}% (бросок {roll}).\n"
        f"Потери отряда на снабжение: {loss} RU.{durability_text}",
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

    open_raid = storage.get_open_raid_for_faction(player.faction)
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
    if not storage.add_raid_member(raid_id, telegram_id):
        return ActionResult(False, "Не удалось присоединиться к рейду. Вступать могут только бойцы той же группировки.")
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
    members = [member for member in members if member.faction == leader.faction and member.health > 0]
    if len(members) < 2:
        return RaidLaunchResult(False, "Недостаточно бойцов с нормальным здоровьем для запуска рейда.", ())

    raid_energy_cost = 18
    ready_members: list[Character] = []
    for member in members:
        if storage.spend_energy(member.telegram_id, raid_energy_cost):
            ready_members.append(member)
    if len(ready_members) < 2:
        return RaidLaunchResult(
            False,
            "У бойцов не хватает энергии для начала рейда. Нужно минимум 2 подготовленных сталкера.",
            (),
        )

    location_name = str(open_raid["location"])
    location = storage.get_location(location_name)
    if location is None:
        return RaidLaunchResult(False, "Локация рейда недоступна.", ())

    event_modifier = _active_location_event_modifier(storage, location_name)
    enemy_power = max(10, int(location["npc_power"]) + event_modifier)
    battle = _simulate_raid_battle(ready_members, enemy_power)

    if battle["success"]:
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
        for member in ready_members:
            durability_text = _apply_durability_decay(
                storage,
                member.telegram_id,
                weapon_loss=6,
                armor_loss=5,
            )
            if artifacts_reward > 0:
                storage.add_item(member.telegram_id, "artifact", artifacts_reward)
            _add_rating(storage, member.telegram_id, RATING_REWARD["raid_success"])
            storage.add_player_stat(member.telegram_id, "raids_completed", 1)
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
        return RaidLaunchResult(
            True,
            f"Рейд #{raid_id} завершен успешно на логове «{location_name}».\n"
            f"Бойцов: {len(ready_members)}, критические попадания: {battle['total_crits']}.\n"
            f"Награда каждому: артефакты x{artifacts_reward} (максимум {RAID_ARTIFACT_REWARD_CAP} за рейд).\n"
            f"Порог сложности для награды артефактами: от {RAID_ARTIFACT_MIN_ENEMY_POWER} силы.\n"
            f"В казну группировки: {treasury_gain} RU.\n"
            f"Раненых: {len(battle['wounds'])}."
            f"{''.join(notes)}",
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
        f"Состав:\n{members_text or '• Пока пусто'}"
    )


def _normalize_item_key(item_key: str) -> str:
    return item_key if item_key in WAREHOUSE_ITEM_KEYS else "ammo_pack"


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
    key = _normalize_item_key(item_key)
    if not storage.change_faction_warehouse_item(player.faction, key, -amount):
        return ActionResult(False, "На складе недостаточно ресурсов.")
    storage.add_item(telegram_id, key, amount)
    return ActionResult(True, f"Со склада получено: {ITEM_LABELS.get(key, key)} x{amount}.")


def create_faction_auction(storage: Storage, telegram_id: int, lot_key: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Аукцион доступен только бойцам группировки.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
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
        f"Лот #{auction_id} создан: {ITEM_LABELS.get(item_key, item_key)} x{amount} за {price} RU.{achievements_text}",
    )


def buy_first_faction_auction(storage: Storage, telegram_id: int) -> ActionResult:
    buyer = storage.get_character(telegram_id, refresh_energy=False)
    if buyer is None or buyer.faction is None:
        return ActionResult(False, "Покупка на аукционе доступна только бойцам группировки.")
    if _is_dead(buyer):
        return ActionResult(False, _dead_block_text())
    auctions = storage.list_open_auctions(buyer.faction)
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
    storage.change_money(seller_id, price)
    storage.add_item(telegram_id, item_key, amount)
    storage.add_player_stat(telegram_id, "trades_done", 1)
    storage.add_player_stat(seller_id, "trades_done", 1)
    _add_rating(storage, telegram_id, RATING_REWARD["trade_action"])
    _add_rating(storage, seller_id, RATING_REWARD["trade_action"])
    storage.add_player_stat(seller_id, "money_earned", price)
    achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
    seller_achievements = _progress_and_unlock_achievements(storage, seller_id)
    suffix = achievements_text + seller_achievements
    return ActionResult(
        True,
        f"Куплен лот #{auction_id}: {ITEM_LABELS.get(item_key, item_key)} x{amount} за {price} RU.{suffix}",
    )


def cancel_own_first_auction(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Сначала создай персонажа и выбери группировку.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    auctions = storage.list_open_auctions(player.faction)
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


def build_economy_overview(storage: Storage, telegram_id: int) -> str:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return "Экономика доступна только после выбора группировки."

    warehouse = storage.get_faction_warehouse(player.faction)
    factions = storage.get_factions()
    faction_info = next((f for f in factions if f["name"] == player.faction), None)
    treasury = int(faction_info["treasury"]) if faction_info else 0
    auctions = storage.list_open_auctions(player.faction)
    warehouse_lines = [
        f"• {ITEM_LABELS.get(k, k)}: {v}"
        for k, v in sorted(warehouse.items())
        if v > 0
    ]
    if not warehouse_lines:
        warehouse_lines = ["• Склад пуст"]

    auctions_lines = [
        f"• #{a['id']} {ITEM_LABELS.get(str(a['item_key']), str(a['item_key']))} x{a['amount']} "
        f"за {a['price']} RU (продавец {a['seller_id']})"
        for a in auctions[:5]
    ]
    if not auctions_lines:
        auctions_lines = ["• Открытых лотов нет"]

    return (
        f"Экономика группировки «{player.faction}»\n"
        f"Казна: {treasury} RU\n\n"
        f"Склад:\n{chr(10).join(warehouse_lines)}\n\n"
        f"Аукцион:\n{chr(10).join(auctions_lines)}"
    )


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
        _add_rating(storage, telegram_id, RATING_REWARD["smuggle_success"])
        storage.add_player_stat(telegram_id, "smuggling_success", 1)
        storage.add_player_stat(telegram_id, "money_earned", reward)
        achievements_text = _progress_and_unlock_achievements(storage, telegram_id)
        return ActionResult(
            True,
            f"Контрабанда удалась! Шанс {chance}% (бросок {roll}).\n"
            f"Ты получил {reward} RU, в казну ушло {reward // 3} RU.\n"
            f"На склад добавлено патронов: +{warehouse_bonus}.{durability_text}{achievements_text}",
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


def build_events_overview(storage: Storage) -> str:
    storage.delete_expired_map_events()
    events = storage.get_map_events()
    if not events:
        return "Активных событий на карте нет. Зона затихла."

    now = datetime.now(timezone.utc)
    by_location = {loc["name"]: int(loc["npc_power"]) for loc in storage.get_locations()}
    lines = ["Активные события Зоны:"]
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
