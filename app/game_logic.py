from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

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
    "easy": QuestType("easy", "Легко", 90, 12, 150, 300, 0, 0),
    "hard": QuestType("hard", "Сложно", 80, 16, 250, 450, 0, 0),
    "heavy": QuestType("heavy", "Тяжело", 70, 22, 400, 650, 2, 1),
    "impossible": QuestType("impossible", "Невозможно", 60, 28, 550, 900, 3, 1),
}


SHOP_ITEMS: dict[str, dict[str, int | str]] = {
    "energy_drink": {"name": "Энергетик", "buy_price": 350, "sell_price": 170},
    "medkit": {"name": "Аптечка", "buy_price": 260, "sell_price": 120},
    "ammo_pack": {"name": "Патроны", "buy_price": 120, "sell_price": 55},
    "gear_upgrade": {"name": "Улучшение снаряги", "buy_price": 1200, "sell_price": 0},
    "truck": {"name": "Грузовик", "buy_price": 7000, "sell_price": 0},
    "fuel_can": {"name": "Канистра топлива (+5)", "buy_price": 450, "sell_price": 200},
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

SHOP_ITEMS.update(WEAPON_CATALOG)

WEAPON_RATING_BY_NAME: dict[str, int] = {
    "Нож": 1,
    "ПМ": 3,
    "Фора-12": 4,
    "Обрез": 4,
    "Chaser-13": 6,
    "СПАС-12": 8,
    "Гадюка-5": 5,
    "АКС-74У": 6,
    "АК-74": 7,
    "TRs 301": 8,
    "ИЛ86": 8,
    "ГП37": 10,
    "СВДм-2": 11,
    "Винтарь ВС": 11,
    "РП-74": 12,
    "АН-94": 10,
    "Гаусс-пушка": 16,
}


ITEM_LABELS = {
    "energy_drink": "Энергетик",
    "medkit": "Аптечка",
    "ammo_pack": "Патроны",
    "artifact": "Артефакт",
    "weapon_pm": "ПМ",
    "weapon_fort12": "Фора-12",
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


def calculate_equipment_bonus(character: Character) -> int:
    armor_name = character.equipment.get("armor", "")
    weapon_name = character.equipment.get("weapon", "")

    # Явный бонус от фактической экипировки (не только от числовой силы).
    armor_bonus = {
        "Куртка новичка": 0,
        "Бронежилет сталкера": 3,
        "Усиленный бронекостюм": 6,
        "Штурмовой экзоскелет": 9,
    }.get(armor_name, 0)
    weapon_bonus = max(0, _weapon_rating(weapon_name) - 1)
    return armor_bonus + weapon_bonus


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
        gear_power=character.gear_power,
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
        gear_power=updated.gear_power,
        gear_bonus=gear_bonus,
        max_success=quest.max_success,
        ammo_stock=ammo_after,
        medkit_stock=medkit_after,
        ammo_required=quest.ammo_required,
        medkit_required=quest.medkit_required,
    )
    roll = random.randint(1, 100)
    success = roll <= breakdown.chance

    if success:
        reward = random.randint(quest.reward_min, quest.reward_max)
        storage.change_money(telegram_id, reward)

        if random.random() < 0.30:
            storage.add_item(telegram_id, "artifact", 1)
            extra = "\nТы нашел редкий артефакт!"
        else:
            extra = ""
        return ActionResult(
            True,
            f"Задание «{quest.title}» выполнено! Шанс {breakdown.chance}% (бросок {roll}).\n"
            f"Формула: база {breakdown.base_chance}% (включая снарягу +{breakdown.gear_bonus}%) "
            f"+ патроны {breakdown.ammo_bonus}% + аптечки {breakdown.medkit_bonus}%.\n"
            f"Расход: патроны {quest.ammo_required}, аптечки {quest.medkit_required}.\n"
            f"Награда: {reward} RU.{extra}",
        )

    penalty = random.randint(50, 120)
    storage.change_money(telegram_id, -penalty)
    return ActionResult(
        False,
        f"Провал задания «{quest.title}».\n"
        f"Расход: патроны {quest.ammo_required}, аптечки {quest.medkit_required}.\n"
        f"Потери на расходники: {penalty} RU.",
    )


def use_energy_drink(storage: Storage, telegram_id: int) -> ActionResult:
    if not storage.remove_item(telegram_id, "energy_drink", 1):
        return ActionResult(False, "У тебя нет энергетика в инвентаре.")
    storage.restore_energy(telegram_id, 35)
    return ActionResult(True, "Ты выпил энергетик и восстановил 35 энергии.")


def buy_item(storage: Storage, telegram_id: int, item_key: str) -> ActionResult:
    item = SHOP_ITEMS.get(item_key)
    if item is None:
        return ActionResult(False, "Такого товара нет у торговца.")
    price = int(item["buy_price"])
    title = str(item["name"])

    character = storage.get_character(telegram_id)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")

    if item_key == "truck" and character.truck_owned:
        return ActionResult(False, "У тебя уже есть грузовик.")
    if item_key in WEAPON_CATALOG:
        weapon_name = str(item["name"])
        current_weapon = character.equipment.get("weapon", "")
        if current_weapon == weapon_name:
            return ActionResult(False, f"У тебя уже экипировано оружие: {weapon_name}.")

    if not storage.change_money(telegram_id, -price):
        return ActionResult(False, f"Недостаточно денег для покупки: {title}.")

    if item_key == "gear_upgrade":
        storage.change_gear_power(telegram_id, 1)
        updated = storage.get_character(telegram_id, refresh_energy=False)
        if updated is not None:
            armor_name, weapon_name = resolve_equipment_by_power(updated.gear_power)
            storage.set_equipment_item(telegram_id, "armor", armor_name)
            storage.set_equipment_item(telegram_id, "weapon", weapon_name)
            return ActionResult(
                True,
                f"Ты улучшил снарягу (+1 сила). Потрачено {price} RU.\n"
                f"Новый комплект: {armor_name}, оружие: {weapon_name}.",
            )
        return ActionResult(True, f"Ты улучшил снарягу (+1 сила). Потрачено {price} RU.")
    if item_key == "truck":
        storage.set_truck_owned(telegram_id)
        return ActionResult(True, "Покупка оформлена: грузовик теперь в твоем распоряжении.")
    if item_key == "fuel_can":
        storage.change_fuel(telegram_id, 5)
        return ActionResult(True, f"Куплена канистра топлива. Топливо +5 (стоимость {price} RU).")
    if item_key in WEAPON_CATALOG:
        weapon_name = str(item["name"])
        storage.set_equipment_item(telegram_id, "weapon", weapon_name)
        return ActionResult(
            True,
            f"Куплено и экипировано оружие: {weapon_name} (стоимость {price} RU).",
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
    if item_key == "truck":
        if not character.truck_owned:
            return ActionResult(False, "У тебя нет грузовика для продажи.")
        storage.clear_truck_owned(telegram_id)
        storage.change_money(telegram_id, sell_price)
        return ActionResult(True, f"Продано: {title} за {sell_price} RU.")
    if item_key in WEAPON_CATALOG:
        weapon_name = str(item["name"])
        equipped_weapon = character.equipment.get("weapon", "")
        if equipped_weapon != weapon_name:
            return ActionResult(False, f"Нельзя продать {weapon_name}: это оружие не экипировано.")
        if weapon_name == "Нож":
            return ActionResult(False, "Нож продать нельзя.")
        storage.set_equipment_item(telegram_id, "weapon", "Нож")
    if item_key == "fuel_can":
        if not storage.change_fuel(telegram_id, -5):
            return ActionResult(False, "Недостаточно топлива для продажи канистры.")
    else:
        if item_key not in WEAPON_CATALOG and not storage.remove_item(telegram_id, item_key, 1):
            return ActionResult(False, f"У тебя нет предмета: {title}.")
    storage.change_money(telegram_id, sell_price)
    return ActionResult(True, f"Продано: {title} за {sell_price} RU.")


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
    }
    equipment = "\n".join(
        f"• {equipment_labels.get(k, k)}: {v}" for k, v in character.equipment.items()
    )

    return (
        f"👤 {character.nickname} ({character.gender})\n"
        f"ID-адрес: {character.player_uid}\n"
        f"Telegram ID: {character.telegram_id}\n"
        f"Фракция: {character.faction or 'не выбрана'}\n"
        f"Локация: {character.location}\n"
        f"Здоровье: {character.health}\n"
        f"Энергия: {character.energy}/{character.max_energy}\n"
        f"Сила снаряги: {character.gear_power}\n"
        f"Скин: {skin.title}\n"
        f"Баланс: {character.money} RU\n"
        f"Транспорт: {vehicle}\n"
        f"Топливо: {character.fuel}\n\n"
        f"Снаряга:\n{equipment}\n\n"
        f"Вещи:\n{items}"
    )


def travel_to(storage: Storage, telegram_id: int, destination: str) -> ActionResult:
    character = storage.get_character(telegram_id)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа.")
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
    if character.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")

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
    roll = random.randint(1, 100)
    success = roll <= chance

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
        return ActionResult(
            True,
            f"Штурм успешен! Шанс {chance}% (бросок {roll}).\n"
            f"Точка «{location_name}» под контролем {character.faction}.\n"
            f"Личная награда: {personal_reward} RU.\n"
            f"В казну группировки: {treasury_reward} RU.",
        )

    loss = random.randint(80, 170)
    storage.change_money(telegram_id, -loss)
    return ActionResult(
        False,
        f"Штурм провален. Шанс {chance}% (бросок {roll}).\n"
        f"Потери отряда на снабжение: {loss} RU.",
    )


def _weapon_rating(weapon_name: str) -> int:
    return WEAPON_RATING_BY_NAME.get(weapon_name, 2)


def _armor_rating(armor_name: str) -> int:
    return {
        "Куртка новичка": 1,
        "Бронежилет сталкера": 3,
        "Усиленный бронекостюм": 5,
        "Штурмовой экзоскелет": 8,
    }.get(armor_name, 2)


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
    for member in members:
        weapon_bonus = _weapon_rating(member.equipment.get("weapon", ""))
        armor_bonus = _armor_rating(member.equipment.get("armor", ""))
        squad_attack_bonus[member.telegram_id] = weapon_bonus
        squad_armor_bonus[member.telegram_id] = armor_bonus
        squad_hp[member.telegram_id] = 75 + member.gear_power * 4 + armor_bonus * 3

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
            base_damage = 6 + member.gear_power * 2 + squad_attack_bonus[member.telegram_id]
            damage = base_damage + random.randint(0, 8)
            crit_chance = min(35, 8 + member.gear_power * 2)
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
        max_hp = 75 + member.gear_power * 4 + squad_armor_bonus[member.telegram_id] * 3
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
            f"Создан рейд #{raid_id} на локацию «{location_name}».\n"
            "Позови товарищей по группировке и нажми «Запустить».",
        )

    if str(open_raid["location"]) != location_name:
        return ActionResult(
            False,
            f"У твоей группировки уже есть открытый рейд #{open_raid['id']} на «{open_raid['location']}».\n"
            "Сначала запусти или закрой его.",
        )

    raid_id = int(open_raid["id"])
    if not storage.add_raid_member(raid_id, telegram_id):
        return ActionResult(False, "Не удалось присоединиться к рейду. Вступать могут только бойцы той же группировки.")
    member_ids = storage.get_raid_member_ids(raid_id)
    return ActionResult(
        True,
        f"Ты в составе рейда #{raid_id} на «{location_name}».\n"
        f"Состав рейда: {len(member_ids)} бойцов.",
    )


def launch_open_raid(storage: Storage, telegram_id: int) -> RaidLaunchResult:
    leader = storage.get_character(telegram_id, refresh_energy=False)
    if leader is None:
        return RaidLaunchResult(False, "Сначала создай персонажа.", ())
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
        personal_reward = 240 + len(ready_members) * 35
        for member in ready_members:
            storage.change_money(member.telegram_id, personal_reward)
            if member.telegram_id in battle["wounds"]:
                storage.change_health(member.telegram_id, -14)
        new_npc_power = max(12, enemy_power - random.randint(4, 10))
        storage.set_location_npc_power(location_name, new_npc_power)
        storage.finish_raid(
            raid_id,
            status="success",
            result_text=f"Рейд успешен. Критов: {battle['total_crits']}.",
        )
        return RaidLaunchResult(
            True,
            f"Рейд #{raid_id} завершен успешно на «{location_name}».\n"
            f"Бойцов: {len(ready_members)}, критические попадания: {battle['total_crits']}.\n"
            f"Личная награда каждому: {personal_reward} RU.\n"
            f"В казну группировки: {treasury_gain} RU.\n"
            f"Раненых: {len(battle['wounds'])}.",
            tuple(member_ids),
        )

    for member in ready_members:
        storage.change_money(member.telegram_id, -110)
        damage_taken = int(battle["member_damage_taken"].get(member.telegram_id, 0))
        health_penalty = min(30, max(8, damage_taken // 4))
        storage.change_health(member.telegram_id, -health_penalty)
    new_npc_power = min(80, enemy_power + random.randint(2, 7))
    storage.set_location_npc_power(location_name, new_npc_power)
    storage.finish_raid(
        raid_id,
        status="failed",
        result_text=f"Рейд провален. Остаток силы противника: {battle['enemy_hp_left']}.",
    )
    return RaidLaunchResult(
        False,
        f"Рейд #{raid_id} провален на «{location_name}».\n"
        f"Сила врага осталась: {battle['enemy_hp_left']}.\n"
        "Каждый участник потерял 110 RU и получил ранения.",
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
            "• Создай рейд на нужную локацию.\n"
            "• Другие бойцы твоей группировки могут присоединиться.\n"
            "• Для запуска нужно минимум 2 участника."
        )

    raid_id = int(open_raid["id"])
    member_ids = storage.get_raid_member_ids(raid_id)
    members = storage.get_characters_by_ids(member_ids)
    members_text = "\n".join(
        f"• {member.nickname} (сила {member.gear_power}, HP {member.health})"
        for member in members
    )
    location_name = str(open_raid["location"])
    location = storage.get_location(location_name)
    npc_power = int(location["npc_power"]) if location else 0
    event_modifier = _active_location_event_modifier(storage, location_name)
    return (
        f"Открытый рейд #{raid_id}\n"
        f"Локация: {location_name}\n"
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
    key = _normalize_item_key(item_key)
    if not storage.change_faction_warehouse_item(player.faction, key, -amount):
        return ActionResult(False, "На складе недостаточно ресурсов.")
    storage.add_item(telegram_id, key, amount)
    return ActionResult(True, f"Со склада получено: {ITEM_LABELS.get(key, key)} x{amount}.")


def create_faction_auction(storage: Storage, telegram_id: int, lot_key: str) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Аукцион доступен только бойцам группировки.")
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
    return ActionResult(
        True,
        f"Лот #{auction_id} создан: {ITEM_LABELS.get(item_key, item_key)} x{amount} за {price} RU.",
    )


def buy_first_faction_auction(storage: Storage, telegram_id: int) -> ActionResult:
    buyer = storage.get_character(telegram_id, refresh_energy=False)
    if buyer is None or buyer.faction is None:
        return ActionResult(False, "Покупка на аукционе доступна только бойцам группировки.")
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
    return ActionResult(
        True,
        f"Куплен лот #{auction_id}: {ITEM_LABELS.get(item_key, item_key)} x{amount} за {price} RU.",
    )


def cancel_own_first_auction(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Сначала создай персонажа и выбери группировку.")
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
    if player.faction is None:
        return ActionResult(False, "Сначала выбери группировку.")

    energy_cost = 14
    if not storage.spend_energy(telegram_id, energy_cost):
        return ActionResult(False, f"Не хватает энергии для контрабанды (нужно {energy_cost}).")

    truck_bonus = 12 if player.truck_owned and player.fuel > 0 else 0
    if truck_bonus > 0 and not storage.change_fuel(telegram_id, -1):
        truck_bonus = 0
    event_modifier = _active_location_event_modifier(storage, player.location)
    chance = min(90, max(20, 42 + player.gear_power * 3 + truck_bonus - max(0, event_modifier)))
    roll = random.randint(1, 100)
    success = roll <= chance

    if success:
        reward = random.randint(280, 520)
        warehouse_bonus = random.randint(1, 3)
        storage.change_money(telegram_id, reward)
        storage.change_faction_treasury(player.faction, reward // 3)
        storage.change_faction_warehouse_item(player.faction, "ammo_pack", warehouse_bonus)
        return ActionResult(
            True,
            f"Контрабанда удалась! Шанс {chance}% (бросок {roll}).\n"
            f"Ты получил {reward} RU, в казну ушло {reward // 3} RU.\n"
            f"На склад добавлено патронов: +{warehouse_bonus}.",
        )

    penalty = random.randint(120, 240)
    storage.change_money(telegram_id, -penalty)
    storage.change_health(telegram_id, -12)
    return ActionResult(
        False,
        f"Контрабанда сорвана. Шанс {chance}% (бросок {roll}).\n"
        f"Потери: {penalty} RU и ранение (-12 HP).",
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
