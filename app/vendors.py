"""Поэтапный ассортимент: бармен, медик, техник."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.game_logic import ActionResult
    from app.storage import Storage

VENDOR_TIER_MAX = 4

VENDOR_KEYS = ("barkeep", "medic", "tech")

VENDOR_TITLES: dict[str, str] = {
    "barkeep": "Бармен",
    "medic": "Медик",
    "tech": "Техник",
}

VENDOR_META_PREFIX: dict[str, str] = {
    "barkeep": "vendor:barkeep_tier:",
    "medic": "vendor:medic_tier:",
    "tech": "vendor:tech_tier:",
}

# Стоимость перехода на этап (с предыдущего).
VENDOR_UPGRADE_COST: dict[str, dict[int, int]] = {
    "barkeep": {2: 15000, 3: 40000, 4: 100000},
    "medic": {2: 8000, 3: 20000, 4: 45000},
    "tech": {2: 10000, 3: 25000, 4: 50000},
}

VENDOR_STAGE_LABELS: dict[str, dict[int, str]] = {
    "barkeep": {
        1: "еда/вода, T1 стволы и броня, «Отклик», велосипед",
        2: "+ T2, Нива, «Медведь», колбаса/минералка",
        3: "+ T3, броня среднего класса, «Велес», спальник, тушёнка",
        4: "+ T4/T5 и Гаусс, экзо/Носорог, «Сварог», грузовик",
    },
    "medic": {
        1: "обычная аптечка",
        2: "+ армейская аптечка",
        3: "+ антирад",
        4: "+ научная аптечка",
    },
    "tech": {
        1: "улучшение брони, скидка на ремонт 2%",
        2: "скидка на ремонт 4%",
        3: "скидка на ремонт 6%",
        4: "скидка на ремонт 8%",
    },
}

# Скидка техника на ремонт по этапу.
TECH_REPAIR_DISCOUNT_PERCENT: dict[int, int] = {1: 2, 2: 4, 3: 6, 4: 8}

# Добавки ассортимента бармена по этапам (накопительно).
_BARKEEP_STAGE_ITEMS: dict[int, tuple[str, ...]] = {
    1: (
        "bread",
        "water_bottle",
        "energy_drink",
        "ammo_pack",
        "vodka",
        "diesel_can",
        "gasoline_can",
        "stash_case",
        "weapon_pm",
        "weapon_fort12",
        "weapon_fora12",
        "weapon_sawedoff",
        "armor_leather",
        "detector_otklik",
        "bicycle",
    ),
    2: (
        "sausage",
        "mineral_water",
        "weapon_mp5",
        "weapon_chaser13",
        "weapon_aks74u",
        "armor_stalker_vest",
        "armor_zarya",
        "armor_sunrise",
        "detector_medved",
        "niva",
    ),
    3: (
        "stew",
        "beard_tea",
        "weapon_ak74",
        "weapon_spas12",
        "armor_psz7d",
        "armor_bulat",
        "armor_berill5m",
        "armor_seva",
        "armor_scientific",
        "detector_veles",
        "sleeping_bag",
    ),
    4: (
        "weapon_lr300",
        "weapon_il86",
        "weapon_an94",
        "weapon_gp37",
        "weapon_vintar",
        "weapon_svd",
        "weapon_rp74",
        "weapon_gauss",
        "armor_exo",
        "armor_exoskeleton",
        "armor_nosorog",
        "detector_svarog",
        "truck",
    ),
}

_MEDIC_STAGE_ITEMS: dict[int, tuple[str, ...]] = {
    1: ("medkit",),
    2: ("medkit_army",),
    3: ("antirad",),
    4: ("medkit_science",),
}

_TECH_STAGE_ITEMS: dict[int, tuple[str, ...]] = {
    1: ("armor_upgrade", "gear_upgrade"),
    2: (),
    3: (),
    4: (),
}


def _vendor_meta_key(vendor: str, telegram_id: int) -> str:
    prefix = VENDOR_META_PREFIX[vendor]
    return f"{prefix}{int(telegram_id)}"


def get_vendor_tier(storage: Storage, telegram_id: int, vendor: str) -> int:
    if vendor not in VENDOR_META_PREFIX:
        return 1
    raw = storage.get_meta(_vendor_meta_key(vendor, telegram_id))
    if raw is None or str(raw).strip() == "":
        return 1
    try:
        tier = int(raw)
    except (TypeError, ValueError):
        return 1
    return max(1, min(VENDOR_TIER_MAX, tier))


def set_vendor_tier(storage: Storage, telegram_id: int, vendor: str, tier: int) -> None:
    if vendor not in VENDOR_META_PREFIX:
        return
    safe = max(1, min(VENDOR_TIER_MAX, int(tier)))
    storage.set_meta(_vendor_meta_key(vendor, telegram_id), str(safe))


def unlocked_vendor_item_keys(vendor: str, tier: int) -> frozenset[str]:
    safe = max(1, min(VENDOR_TIER_MAX, int(tier)))
    table = {
        "barkeep": _BARKEEP_STAGE_ITEMS,
        "medic": _MEDIC_STAGE_ITEMS,
        "tech": _TECH_STAGE_ITEMS,
    }.get(vendor)
    if table is None:
        return frozenset()
    unlocked: set[str] = set()
    for stage in range(1, safe + 1):
        unlocked.update(table.get(stage, ()))
    return frozenset(unlocked)


def _build_item_vendor_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for items in _MEDIC_STAGE_ITEMS.values():
        for key in items:
            mapping[key] = "medic"
    for items in _TECH_STAGE_ITEMS.values():
        for key in items:
            mapping[key] = "tech"
    for items in _BARKEEP_STAGE_ITEMS.values():
        for key in items:
            mapping[key] = "barkeep"
    return mapping


_ITEM_VENDOR_MAP = _build_item_vendor_map()


def shop_item_vendor(item_key: str) -> str | None:
    """Какой специалист продаёт товар. None — не из ассортимента специалистов."""
    from app.game_logic import (
        ARMOR_CATALOG,
        SEASON_REWARD_ITEM_KEYS,
        WEAPON_CATALOG,
        normalize_shop_item_key,
    )

    key = normalize_shop_item_key(item_key)
    if key in _ITEM_VENDOR_MAP:
        return _ITEM_VENDOR_MAP[key]
    if key in SEASON_REWARD_ITEM_KEYS:
        return None
    if key in WEAPON_CATALOG or key in ARMOR_CATALOG:
        return "barkeep"
    return None


def vendor_item_is_unlocked(storage: Storage, telegram_id: int, item_key: str) -> bool:
    from app.game_logic import normalize_shop_item_key

    key = normalize_shop_item_key(item_key)
    vendor = shop_item_vendor(key)
    if vendor is None:
        return True
    unlocked = unlocked_vendor_item_keys(vendor, get_vendor_tier(storage, telegram_id, vendor))
    if key in unlocked:
        return True
    aliases = {
        "weapon_fora12": "weapon_fort12",
        "weapon_fort12": "weapon_fora12",
        "armor_sunrise": "armor_zarya",
        "armor_zarya": "armor_sunrise",
        "armor_berill5m": "armor_bulat",
        "armor_bulat": "armor_berill5m",
        "armor_exoskeleton": "armor_exo",
        "armor_exo": "armor_exoskeleton",
        "gear_upgrade": "armor_upgrade",
        "armor_upgrade": "gear_upgrade",
    }
    alt = aliases.get(key)
    return bool(alt and alt in unlocked)


def tech_repair_discount_percent(storage: Storage, telegram_id: int) -> int:
    tier = get_vendor_tier(storage, telegram_id, "tech")
    return int(TECH_REPAIR_DISCOUNT_PERCENT.get(tier, 2))


def apply_tech_repair_discount(
    storage: Storage, telegram_id: int, price: int
) -> tuple[int, int]:
    """Вернуть (цена_со_скидкой, процент_скидки)."""
    pct = tech_repair_discount_percent(storage, telegram_id)
    if pct <= 0 or price <= 0:
        return max(0, int(price)), 0
    discounted = max(1, int(round(int(price) * (100 - pct) / 100.0)))
    return discounted, pct


def vendor_assortment_blurb(storage: Storage, telegram_id: int, vendor: str) -> str:
    title = VENDOR_TITLES.get(vendor, vendor)
    tier = get_vendor_tier(storage, telegram_id, vendor)
    label = VENDOR_STAGE_LABELS.get(vendor, {}).get(tier, f"этап {tier}")
    lines = [f"{title}: этап ассортимента {tier}/{VENDOR_TIER_MAX} — {label}."]
    if vendor == "tech":
        lines.append(f"Скидка на ремонт сейчас: {tech_repair_discount_percent(storage, telegram_id)}%.")
    if tier < VENDOR_TIER_MAX:
        nxt = tier + 1
        cost = int(VENDOR_UPGRADE_COST.get(vendor, {}).get(nxt, 0))
        nxt_label = VENDOR_STAGE_LABELS.get(vendor, {}).get(nxt, f"этап {nxt}")
        lines.append(f"Следующий этап ({nxt_label}) — {cost} RU.")
    else:
        lines.append("Ассортимент на максимуме.")
    return "\n".join(lines)


def upgrade_vendor_tier(storage: Storage, telegram_id: int, vendor: str) -> ActionResult:
    from app.game_logic import ActionResult, _dead_block_text, _is_dead, _reject_if_player_busy

    if vendor not in VENDOR_META_PREFIX:
        return ActionResult(False, "Неизвестный торговец.")
    character = storage.get_character(telegram_id)
    if character is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(character):
        return ActionResult(False, _dead_block_text())
    blocked = _reject_if_player_busy(storage, telegram_id)
    if blocked is not None:
        return blocked
    current = get_vendor_tier(storage, telegram_id, vendor)
    title = VENDOR_TITLES[vendor]
    if current >= VENDOR_TIER_MAX:
        return ActionResult(
            False,
            f"Ассортимент «{title}» уже максимальный "
            f"(этап {VENDOR_TIER_MAX}/{VENDOR_TIER_MAX}).",
        )
    nxt = current + 1
    cost = int(VENDOR_UPGRADE_COST.get(vendor, {}).get(nxt, 0))
    if cost <= 0:
        return ActionResult(False, "Улучшение недоступно.")
    if not storage.change_money(telegram_id, -cost):
        return ActionResult(False, f"Недостаточно денег для улучшения «{title}» ({cost} RU).")
    set_vendor_tier(storage, telegram_id, vendor, nxt)
    label = VENDOR_STAGE_LABELS.get(vendor, {}).get(nxt, f"этап {nxt}")
    extra = ""
    if vendor == "tech":
        extra = f"\nСкидка на ремонт: {TECH_REPAIR_DISCOUNT_PERCENT.get(nxt, 0)}%."
    return ActionResult(
        True,
        f"«{title}»: ассортимент улучшен до этапа {nxt}/{VENDOR_TIER_MAX} (−{cost} RU).\n"
        f"Теперь: {label}.{extra}",
        payload={"vendor": vendor, "vendor_tier": nxt},
    )


def vendor_purge_meta_keys(telegram_id: int) -> list[str]:
    tid = int(telegram_id)
    return [f"{prefix}{tid}" for prefix in VENDOR_META_PREFIX.values()]
