from __future__ import annotations

import random
from typing import Iterable


STASH_DROP_CHANCE = 0.05
STASH_BUY_PRICE = 1000
STASH_ITEM_KEY = "stash_case"

# Smuggling personal drop chances (percent).
SMUGGLE_ARMOR_CHANCE = 3.0
SMUGGLE_WEAPON_CHANCE = 3.0
SMUGGLE_DETECTOR_CHANCE = 7.0

SMUGGLE_ARMOR_POOL = ("armor_stalker_vest", "armor_zarya")
SMUGGLE_WEAPON_POOL = ("weapon_pm", "weapon_sawedoff", "weapon_fort12")
SMUGGLE_CONSUMABLE_POOL = (
    "medkit",
    "bread",
    "sausage",
    "stew",
    "water_bottle",
    "mineral_water",
    "ammo_pack",
)

ARMOR_TIER_POOLS: dict[int, tuple[str, ...]] = {
    1: ("armor_leather",),
    2: ("armor_stalker_vest", "armor_zarya"),
    3: ("armor_bulat", "armor_seva", "armor_scientific"),
    4: ("armor_exo",),
    5: ("armor_nosorog",),
}

WEAPON_TIER_POOLS: dict[int, tuple[str, ...]] = {
    1: ("weapon_pm", "weapon_fort12", "weapon_sawedoff"),
    2: ("weapon_mp5", "weapon_chaser13", "weapon_aks74u"),
    3: ("weapon_ak74", "weapon_spas12"),
    4: ("weapon_lr300", "weapon_il86", "weapon_an94", "weapon_gp37", "weapon_vintar", "weapon_svd", "weapon_rp74"),
    5: ("weapon_gauss",),
}

# Stash gear drop: exclusive armor OR weapon, never both.
STASH_GEAR_ROLLS: tuple[tuple[str, int, float], ...] = (
    ("armor", 1, 4.0),
    ("armor", 2, 4.0),
    ("armor", 3, 2.0),
    ("armor", 4, 0.5),
    ("armor", 5, 0.01),
    ("weapon", 1, 4.0),
    ("weapon", 2, 4.0),
    ("weapon", 3, 2.0),
    ("weapon", 4, 0.5),
    ("weapon", 5, 0.01),
)

STASH_CONSUMABLES: tuple[str, ...] = (
    "bread",
    "sausage",
    "stew",
    "water_bottle",
    "mineral_water",
    "beard_tea",
    "vodka",
    "antirad",
    "medkit",
    "ammo_pack",
    "energy_drink",
)


def maybe_stash_drop() -> bool:
    return random.random() < STASH_DROP_CHANCE


def roll_smuggling_personal_loot() -> list[tuple[str, int]]:
    drops: list[tuple[str, int]] = []
    consumable = random.choice(SMUGGLE_CONSUMABLE_POOL)
    drops.append((consumable, random.randint(1, 2)))
    if random.random() * 100 < SMUGGLE_ARMOR_CHANCE:
        drops.append((random.choice(SMUGGLE_ARMOR_POOL), 1))
    if random.random() * 100 < SMUGGLE_WEAPON_CHANCE:
        drops.append((random.choice(SMUGGLE_WEAPON_POOL), 1))
    if random.random() * 100 < SMUGGLE_DETECTOR_CHANCE:
        drops.append(("detector_otklik", 1))
    return drops


def _pick_from_pool(pool: Iterable[str]) -> str | None:
    options = list(pool)
    if not options:
        return None
    return random.choice(options)


def open_stash_loot() -> list[tuple[str, int]]:
    """Open one stash case. Returns inventory item drops."""
    drops: list[tuple[str, int]] = []

    # Always 1-2 stacks of consumables (1-2 units each).
    for _ in range(random.randint(2, 4)):
        item = random.choice(STASH_CONSUMABLES)
        drops.append((item, random.randint(1, 2)))

    # Exclusive gear roll: at most one armor OR one weapon.
    roll = random.random() * 100.0
    cursor = 0.0
    for kind, tier, chance in STASH_GEAR_ROLLS:
        cursor += chance
        if roll <= cursor:
            pool = ARMOR_TIER_POOLS if kind == "armor" else WEAPON_TIER_POOLS
            item_key = _pick_from_pool(pool.get(tier, ()))
            if item_key:
                drops.append((item_key, 1))
            break
    return drops
