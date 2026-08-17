"""Лут с мутантов и НПС на тактических полях."""

from __future__ import annotations

import random

from app.game_logic import ITEM_LABELS, ActionResult
from app.storage import Storage

MUTANT_LOOT_TABLE: tuple[tuple[str, int, int], ...] = (
    ("medkit", 24, 1),
    ("ammo_pack", 28, 1),
    ("diesel_can", 10, 1),
    ("sausage", 10, 1),
    ("vodka", 8, 1),
)
NPC_LOOT_TABLE: tuple[tuple[str, int, int], ...] = (
    ("medkit", 22, 1),
    ("ammo_pack", 30, 1),
    ("diesel_can", 12, 1),
    ("gasoline_can", 10, 1),
    ("antirad", 8, 1),
    ("bread", 10, 1),
)


def _roll_from_table(table: tuple[tuple[str, int, int], ...]) -> tuple[str, int] | None:
    roll = random.randint(1, 100)
    acc = 0
    for item_key, chance, amount in table:
        acc += chance
        if roll <= acc:
            return item_key, amount
    return None


def roll_mutant_loot() -> tuple[str, int] | None:
    return _roll_from_table(MUTANT_LOOT_TABLE)


def roll_npc_loot() -> tuple[str, int] | None:
    return _roll_from_table(NPC_LOOT_TABLE)


def grant_combat_loot(
    storage: Storage,
    telegram_id: int,
    *,
    npc: bool,
) -> str | None:
    """Выдаёт лут убийце. Возвращает короткую строку для лога или None."""
    drop = roll_npc_loot() if npc else roll_mutant_loot()
    if drop is None:
        return None
    item_key, amount = drop
    if item_key == "diesel_can":
        storage.change_diesel(telegram_id, 5 * amount)
        return "дизель +5"
    if item_key == "gasoline_can":
        storage.change_gasoline(telegram_id, 5 * amount)
        return "бензин +5"
    storage.add_item(telegram_id, item_key, amount)
    label = ITEM_LABELS.get(item_key, item_key)
    return f"{label} x{amount}"
