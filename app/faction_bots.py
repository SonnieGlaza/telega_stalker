"""Оборонительные боты группировки на базе (склад/гараж). Т1 по умолчанию, апгрейд до Т2."""

from __future__ import annotations

import json
import random
from typing import Any

from app.game_logic import ActionResult, h
from app.storage import Storage

FACTION_BOTS_META_PREFIX = "faction_bots:"
FACTION_BOT_UPGRADE_COST = 50_000
FACTION_BOT_DEFAULT_COUNT = 3
FACTION_BOT_MAX_COUNT = 5

BOT_T1_WEAPONS: tuple[str, ...] = ("ПМ", "Фора-12", "Обрез")
BOT_T2_WEAPONS: tuple[str, ...] = ("Гадюка-5", "Чейзер-13", "АКС-74У")
BOT_T1_ARMOR = "Кожаная куртка"
BOT_T2_ARMOR = "Сталкерский бронежилет"


def _meta_key(faction: str) -> str:
    return f"{FACTION_BOTS_META_PREFIX}{faction}"


def get_faction_bots(storage: Storage, faction: str) -> dict[str, Any]:
    raw = storage.get_meta(_meta_key(faction))
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                tier = int(parsed.get("tier") or 1)
                count = int(parsed.get("count") or FACTION_BOT_DEFAULT_COUNT)
                return {
                    "tier": max(1, min(2, tier)),
                    "count": max(1, min(FACTION_BOT_MAX_COUNT, count)),
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    default = {"tier": 1, "count": FACTION_BOT_DEFAULT_COUNT}
    storage.set_meta(_meta_key(faction), json.dumps(default, ensure_ascii=False))
    return default


def bot_weapons_for_tier(tier: int) -> tuple[str, ...]:
    return BOT_T2_WEAPONS if int(tier) >= 2 else BOT_T1_WEAPONS


def bot_armor_for_tier(tier: int) -> str:
    return BOT_T2_ARMOR if int(tier) >= 2 else BOT_T1_ARMOR


def pick_bot_weapon(tier: int) -> str:
    return random.choice(bot_weapons_for_tier(tier))


def build_faction_bots_overview(storage: Storage, faction: str) -> str:
    bots = get_faction_bots(storage, faction)
    tier = int(bots["tier"])
    count = int(bots["count"])
    weapons = ", ".join(bot_weapons_for_tier(tier))
    armor = bot_armor_for_tier(tier)
    lines = [
        f"🤖 Оборонительные боты: {count} шт.",
        f"Тир {tier}: {armor}, оружие — {weapons}.",
    ]
    if tier < 2:
        lines.append(
            f"Улучшение до Т2 ({BOT_T2_ARMOR}, {', '.join(BOT_T2_WEAPONS)}): "
            f"{FACTION_BOT_UPGRADE_COST:,} RU из казны."
        )
    else:
        lines.append("Боты уже на максимальном тире (Т2).")
    return "\n".join(lines)


def upgrade_faction_bots(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if not player.faction:
        return ActionResult(False, "Сначала выбери группировку.")
    leader_id = storage.get_faction_leader_id(player.faction)
    if leader_id is None or int(leader_id) != telegram_id:
        return ActionResult(False, "Улучшать ботов может только лидер группировки.")

    bots = get_faction_bots(storage, player.faction)
    if int(bots["tier"]) >= 2:
        return ActionResult(False, "Боты уже улучшены до Т2.")

    treasury = storage.get_faction_treasury(player.faction)
    if treasury < FACTION_BOT_UPGRADE_COST:
        return ActionResult(
            False,
            f"В казне недостаточно средств. Нужно {FACTION_BOT_UPGRADE_COST:,} RU, сейчас {treasury:,}.",
        )

    storage.change_faction_treasury(player.faction, -FACTION_BOT_UPGRADE_COST)
    bots["tier"] = 2
    storage.set_meta(_meta_key(player.faction), json.dumps(bots, ensure_ascii=False))
    return ActionResult(
        True,
        f"🤖 Боты «{player.faction}» улучшены до Т2!\n"
        f"Снаряжение: {BOT_T2_ARMOR}, оружие — {', '.join(BOT_T2_WEAPONS)}.\n"
        f"Списано из казны: {FACTION_BOT_UPGRADE_COST:,} RU.",
    )
