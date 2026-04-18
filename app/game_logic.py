from __future__ import annotations

import random
from dataclasses import dataclass

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
    "easy": QuestType("easy", "Легко", 90, 12, 150, 300, 1, 0),
    "hard": QuestType("hard", "Сложно", 80, 16, 250, 450, 2, 0),
    "heavy": QuestType("heavy", "Тяжело", 70, 22, 400, 650, 3, 1),
    "impossible": QuestType("impossible", "Невозможно", 60, 28, 550, 900, 4, 1),
}


SHOP_ITEMS: dict[str, dict[str, int | str]] = {
    "energy_drink": {"name": "Энергетик", "buy_price": 350, "sell_price": 170},
    "medkit": {"name": "Аптечка", "buy_price": 260, "sell_price": 120},
    "ammo_pack": {"name": "Патроны", "buy_price": 120, "sell_price": 55},
    "gear_upgrade": {"name": "Улучшение снаряги", "buy_price": 1200, "sell_price": 0},
    "truck": {"name": "Грузовик", "buy_price": 7000, "sell_price": 0},
    "fuel_can": {"name": "Канистра топлива (+5)", "buy_price": 450, "sell_price": 200},
}


ITEM_LABELS = {
    "energy_drink": "Энергетик",
    "medkit": "Аптечка",
    "ammo_pack": "Патроны",
    "artifact": "Артефакт",
}


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
class QuestChanceBreakdown:
    chance: int
    base_chance: int
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


def calculate_quest_success(
    gear_power: int,
    max_success: int,
    ammo_stock: int,
    medkit_stock: int,
    ammo_required: int,
    medkit_required: int,
) -> QuestChanceBreakdown:
    # Шанс складывается из силы снаряги и запасов амуниции/аптечек.
    base_chance = 28 + gear_power * 6
    extra_ammo = max(0, ammo_stock - ammo_required)
    extra_medkits = max(0, medkit_stock - medkit_required)
    ammo_bonus = min(18, extra_ammo * 2)
    medkit_bonus = min(12, extra_medkits * 4)
    chance = max(10, min(max_success, base_chance + ammo_bonus + medkit_bonus))
    return QuestChanceBreakdown(
        chance=chance,
        base_chance=base_chance,
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
        lines.append(
            f"• {quest.title}: расход патроны {quest.ammo_required}, аптечки {quest.medkit_required}"
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
    ammo_stock = int(character.inventory.get("ammo_pack", 0))
    medkit_stock = int(character.inventory.get("medkit", 0))
    breakdown = calculate_quest_success(
        gear_power=character.gear_power,
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
    breakdown = calculate_quest_success(
        gear_power=updated.gear_power,
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
            f"Формула: база {breakdown.base_chance}% + патроны {breakdown.ammo_bonus}% + аптечки {breakdown.medkit_bonus}%.\n"
            f"Расход: патроны {quest.ammo_required}, аптечки {quest.medkit_required}.\n"
            f"Награда: {reward} RU.{extra}",
        )

    penalty = random.randint(50, 120)
    storage.change_money(telegram_id, -penalty)
    return ActionResult(
        False,
        f"Провал задания «{quest.title}». Шанс {breakdown.chance}% (бросок {roll}).\n"
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
    if item_key == "fuel_can":
        if not storage.change_fuel(telegram_id, -5):
            return ActionResult(False, "Недостаточно топлива для продажи канистры.")
    else:
        if not storage.remove_item(telegram_id, item_key, 1):
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
    equipment = "\n".join(f"• {k}: {v}" for k, v in character.equipment.items())

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
