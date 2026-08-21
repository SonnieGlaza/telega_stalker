"""Закрытая ГП «Монолит»: окно 15 мин на вход в бой, боты, процентный исход 90/10."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.game_logic import (
    RATING_REWARD,
    WAR_MIN_FACTION_MEMBERS,
    WAR_SUCCESS_PAY_RU,
    ActionResult,
    WarLobbyResult,
    _add_rating,
    h,
)
from app.storage import Storage

MONOLITH_FACTION = "Монолит"
MONOLITH_BASE = "ЧАЭС"
MONOLITH_JOIN_MINUTES = 15
MONOLITH_PERCENT_WIN = 90  # шанс победы Монолита при авто-исходе

PENDING_META = "monolith_war:pending"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(raw: str | None, fallback: datetime) -> datetime:
    if not raw:
        return fallback
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return fallback


def is_monolith_base(location_name: str) -> bool:
    return str(location_name) == MONOLITH_BASE


def location_controlled_by_monolith(storage: Storage, location_name: str) -> bool:
    loc = storage.get_location(location_name)
    if loc is None:
        return False
    return str(loc.get("controlled_by") or "") == MONOLITH_FACTION


def get_pending_monolith_war(storage: Storage) -> dict[str, Any] | None:
    raw = storage.get_meta(PENDING_META)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("resolved"):
        return None
    return data


def _save_pending(storage: Storage, pending: dict[str, Any]) -> None:
    storage.set_meta(PENDING_META, json.dumps(pending, ensure_ascii=False))


def save_pending_monolith_war(storage: Storage, pending: dict[str, Any]) -> None:
    _save_pending(storage, pending)


def clear_pending_monolith_war(storage: Storage) -> None:
    storage.set_meta(PENDING_META, "")


def should_defer_war_for_monolith(
    storage: Storage,
    *,
    host_faction: str,
    location_name: str,
) -> str | None:
    """Вернуть режим 'defend' | 'attack' если нужен 15‑мин таймер Монолита."""
    if get_pending_monolith_war(storage) is not None:
        return None  # уже ждём
    if location_controlled_by_monolith(storage, location_name) and host_faction != MONOLITH_FACTION:
        return "defend"
    if host_faction == MONOLITH_FACTION:
        return "attack"
    return None


def begin_monolith_war_window(
    storage: Storage,
    *,
    war_id: int,
    location_name: str,
    host_faction: str,
    attacker_ids: list[int],
    mode: str,
    energy_spent_ids: list[int],
) -> dict[str, Any]:
    now = _utc_now()
    pending = {
        "war_id": int(war_id),
        "location": str(location_name),
        "host_faction": str(host_faction),
        "mode": str(mode),
        "attacker_ids": [int(x) for x in attacker_ids],
        "monolith_ids": [],
        "monolith_names": [],
        "bots_sent": False,
        "bot_count": 0,
        "energy_spent_ids": [int(x) for x in energy_spent_ids],
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=MONOLITH_JOIN_MINUTES)).isoformat(),
        "resolved": False,
    }
    # Людей не префиллим: даже лидер жмёт «вступить», иначе при одних ботах — 90/10.
    _save_pending(storage, pending)
    # Лобби помечаем in_progress, чтобы не запускали второй раз.
    storage.start_war_lobby_assault(war_id)
    return pending


def format_monolith_war_call(pending: dict[str, Any]) -> str:
    loc = h(str(pending.get("location") or "?"))
    host = h(str(pending.get("host_faction") or "?"))
    mode = str(pending.get("mode") or "")
    mins = MONOLITH_JOIN_MINUTES
    if mode == "defend":
        return (
            f"☢ <b>Штурм базы Монолита</b>\n"
            f"«{host}» идёт на «{loc}».\n"
            f"У Монолита {mins} мин: вступить в бой или послать ботов.\n"
            f"Если никто не зайдёт — исход 90/10 (авто)."
        )
    return (
        f"☢ <b>Вылазка Монолита</b>\n"
        f"Цель: «{loc}». Окно {mins} мин на подключение бойцов.\n"
        f"Можно послать ботов. Без живых Монолита — исход 90/10."
    )


def monolith_war_status_line(storage: Storage) -> str | None:
    pending = get_pending_monolith_war(storage)
    if pending is None:
        return None
    expires = _parse_iso(str(pending.get("expires_at") or ""), _utc_now())
    left = max(0, int((expires - _utc_now()).total_seconds() // 60))
    humans = len(pending.get("monolith_ids") or [])
    bots = "боты+" if pending.get("bots_sent") else "боты−"
    mode = "оборона" if pending.get("mode") == "defend" else "атака"
    return (
        f"Монолит: {mode} «{pending.get('location')}» "
        f"(~{left} мин, людей {humans}, {bots})."
    )


def join_monolith_war(storage: Storage, telegram_id: int) -> ActionResult:
    from app.player_busy import player_busy_reason

    pending = get_pending_monolith_war(storage)
    if pending is None:
        return ActionResult(False, "Сейчас нет окна боя Монолита.")
    expires = _parse_iso(str(pending.get("expires_at") or ""), _utc_now())
    if expires <= _utc_now():
        return ActionResult(False, "Окно уже закрылось — жди авто-исход.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if player.faction != MONOLITH_FACTION:
        return ActionResult(False, "В этот бой могут войти только бойцы Монолита.")
    if player.health <= 0:
        return ActionResult(False, "Мёртвый монолитовец в бой не идёт.")
    busy = player_busy_reason(storage, telegram_id)
    if busy:
        return ActionResult(False, busy)
    ids = [int(x) for x in (pending.get("monolith_ids") or [])]
    if telegram_id in ids:
        return ActionResult(False, "Ты уже в окне боя Монолита.")
    ids.append(telegram_id)
    names = list(pending.get("monolith_names") or [])
    names.append(str(player.nickname))
    pending["monolith_ids"] = ids
    pending["monolith_names"] = names
    _save_pending(storage, pending)
    return ActionResult(
        True,
        f"Ты в окне боя Монолита ({len(ids)} чел.). "
        f"До авто-исхода или старта поля — жди таймер / команду.",
    )


def send_monolith_bots(storage: Storage, telegram_id: int) -> ActionResult:
    from app.faction_bots import get_faction_bots

    pending = get_pending_monolith_war(storage)
    if pending is None:
        return ActionResult(False, "Сейчас нет окна боя Монолита.")
    expires = _parse_iso(str(pending.get("expires_at") or ""), _utc_now())
    if expires <= _utc_now():
        return ActionResult(False, "Окно уже закрылось.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction != MONOLITH_FACTION:
        return ActionResult(False, "Посылать ботов может только Монолит.")
    leader_id = storage.get_faction_leader_id(MONOLITH_FACTION)
    if leader_id is None or int(leader_id) != telegram_id:
        # Админ-игроки Монолита тоже могут — если лидер не назначен, пускаем любого монолита.
        if leader_id is not None:
            return ActionResult(False, "Посылать ботов может лидер Монолита.")
    bots = get_faction_bots(storage, MONOLITH_FACTION)
    count = int(bots.get("count") or 3)
    pending["bots_sent"] = True
    pending["bot_count"] = count
    _save_pending(storage, pending)
    return ActionResult(
        True,
        f"🤖 В бой послано ботов Монолита: {count} (тир {bots.get('tier', 1)}).",
    )


def _refund_energy(storage: Storage, ids: list[int], amount: int) -> None:
    for tid in ids:
        storage.restore_energy(tid, amount)


def _percent_roll_monolith_wins() -> bool:
    return random.randint(1, 100) <= MONOLITH_PERCENT_WIN


def _pay_attackers_success(storage: Storage, attacker_ids: list[int], host_faction: str, location: str) -> str:
    paid = 0
    for pid in attacker_ids:
        ch = storage.get_character(pid, refresh_energy=False)
        if ch is None or ch.faction != host_faction:
            continue
        if ch.health <= 0:
            continue
        storage.add_player_stat(pid, "wars_won", 1)
        storage.change_money(pid, WAR_SUCCESS_PAY_RU)
        storage.add_player_stat(pid, "money_earned", WAR_SUCCESS_PAY_RU)
        _add_rating(storage, pid, RATING_REWARD["war_success"])
        paid += 1
    storage.set_location_control(location, host_faction)
    return (
        f"Процентный исход (10%): «{location}» захвачена «{host_faction}». "
        f"Награда хоста: {paid} бойц. ×{WAR_SUCCESS_PAY_RU} RU."
    )


def _fail_attackers(storage: Storage, attacker_ids: list[int], location: str, reason: str) -> str:
    for pid in attacker_ids:
        _add_rating(storage, pid, -RATING_REWARD["war_fail"])
    return (
        f"{reason} Штурм «{location}» отбит. "
        f"−{RATING_REWARD['war_fail']} рейтинга атакующим."
    )


def resolve_pending_monolith_war(storage: Storage, *, force: bool = False) -> dict[str, Any] | None:
    """Закрыть окно: процент 90/10 или тактическая сетка с людьми Монолита."""
    pending = get_pending_monolith_war(storage)
    if pending is None:
        return None
    expires = _parse_iso(str(pending.get("expires_at") or ""), _utc_now())
    if not force and expires > _utc_now():
        return None

    war_id = int(pending.get("war_id") or 0)
    location = str(pending.get("location") or "")
    host_faction = str(pending.get("host_faction") or "")
    mode = str(pending.get("mode") or "defend")
    attacker_ids = [int(x) for x in (pending.get("attacker_ids") or [])]
    monolith_ids = [int(x) for x in (pending.get("monolith_ids") or [])]
    bots_sent = bool(pending.get("bots_sent"))
    bot_count = int(pending.get("bot_count") or 0)
    energy_spent = [int(x) for x in (pending.get("energy_spent_ids") or [])]

    pending["resolved"] = True
    _save_pending(storage, pending)

    notify_ids = list(dict.fromkeys(attacker_ids + monolith_ids))
    humans_ready = len(monolith_ids) > 0

    # Живые монолитовцы → тактическое поле.
    if humans_ready:
        from app.clan_war_grid import start_clan_war_grid
        from app.game_logic import WAR_LOBBY_ENERGY_COST

        if mode == "defend":
            # Монолит играет на сетке; провал отдаёт точку захватчикам.
            result, session = start_clan_war_grid(
                storage,
                war_id=war_id,
                location_name=location,
                host_faction=MONOLITH_FACTION,
                player_ids=monolith_ids,
                monolith_defense=True,
                invader_faction=host_faction,
                extra_defenders=bot_count if bots_sent else 0,
            )
            clear_pending_monolith_war(storage)
            if not result.ok or session is None:
                _refund_energy(storage, energy_spent, WAR_LOBBY_ENERGY_COST)
                storage.finish_war_lobby(war_id, "failed", "Не удалось стартовать оборону Монолита")
                return {
                    "kind": "error",
                    "text": result.text or "Не удалось начать бой Монолита.",
                    "notify_ids": notify_ids,
                }
            return {
                "kind": "tactical",
                "text": (
                    f"Монолит вступил в бой за «{location}» "
                    f"({len(monolith_ids)} чел."
                    + (f", +{bot_count} ботов" if bots_sent else "")
                    + "). Тактическое поле!"
                ),
                "notify_ids": notify_ids,
                "session": session,
                "member_ids": monolith_ids,
            }

        # Атака Монолита людьми → обычный штурм.
        result, session = start_clan_war_grid(
            storage,
            war_id=war_id,
            location_name=location,
            host_faction=MONOLITH_FACTION,
            player_ids=monolith_ids,
            extra_defenders=0,
        )
        clear_pending_monolith_war(storage)
        if not result.ok or session is None:
            _refund_energy(storage, energy_spent, WAR_LOBBY_ENERGY_COST)
            storage.finish_war_lobby(war_id, "failed", "Не удалось стартовать атаку Монолита")
            return {
                "kind": "error",
                "text": result.text or "Не удалось начать бой Монолита.",
                "notify_ids": notify_ids,
            }
        return {
            "kind": "tactical",
            "text": (
                f"Монолит штурмует «{location}» "
                f"({len(monolith_ids)} чел."
                + (f", боты в резерве ×{bot_count}" if bots_sent else "")
                + ")."
            ),
            "notify_ids": notify_ids,
            "session": session,
            "member_ids": monolith_ids,
        }

    # Нет людей Монолита → процентный исход 90/10 (боты или пустой ответ).
    from app.game_logic import WAR_LOBBY_ENERGY_COST

    monolith_wins = _percent_roll_monolith_wins()
    clear_pending_monolith_war(storage)

    if mode == "defend":
        if monolith_wins:
            storage.finish_war_lobby(war_id, "failed", "Монолит удержал базу (90%)")
            text = _fail_attackers(
                storage,
                attacker_ids,
                location,
                f"Авто-исход 90/10: Монолит удержал «{location}»"
                + (" с ботами." if bots_sent else "."),
            )
            return {"kind": "percent", "text": text, "notify_ids": notify_ids, "monolith_wins": True}
        storage.finish_war_lobby(war_id, "success", f"Пробита оборона Монолита (10%): {host_faction}")
        text = _pay_attackers_success(storage, attacker_ids, host_faction, location)
        text = f"Авто-исход 90/10 (крит 10%): {text}"
        return {"kind": "percent", "text": text, "notify_ids": notify_ids, "monolith_wins": False}

    # Атака без людей: нужны посланные боты, иначе откат.
    if not bots_sent and bot_count <= 0:
        _refund_energy(storage, energy_spent, WAR_LOBBY_ENERGY_COST)
        storage.finish_war_lobby(war_id, "failed", "Монолит не вышел в бой")
        text = (
            f"Никто из Монолита не вступил и ботов не послали. "
            f"Штурм «{location}» отменён, энергия возвращена."
        )
        return {"kind": "percent", "text": text, "notify_ids": notify_ids, "monolith_wins": False}

    if monolith_wins:
        storage.finish_war_lobby(war_id, "success", "Монолит взял точку (90%)")
        if attacker_ids:
            text = _pay_attackers_success(storage, attacker_ids, MONOLITH_FACTION, location)
        else:
            storage.set_location_control(location, MONOLITH_FACTION)
            text = f"Процентный исход (90%): «{location}» взята Монолитом (боты ×{bot_count})."
        text = f"Авто-исход 90/10: {text}"
        return {"kind": "percent", "text": text, "notify_ids": notify_ids, "monolith_wins": True}

    storage.finish_war_lobby(war_id, "failed", "Атака Монолита провалена (10%)")
    text = _fail_attackers(
        storage,
        attacker_ids or energy_spent,
        location,
        "Авто-исход 90/10: атака Монолита сорвалась (10%).",
    )
    return {"kind": "percent", "text": text, "notify_ids": notify_ids, "monolith_wins": False}


def process_monolith_war_cycle(storage: Storage) -> dict[str, Any] | None:
    return resolve_pending_monolith_war(storage, force=False)


def monolith_join_button_visible(storage: Storage, telegram_id: int) -> bool:
    pending = get_pending_monolith_war(storage)
    if pending is None:
        return False
    expires = _parse_iso(str(pending.get("expires_at") or ""), _utc_now())
    if expires <= _utc_now():
        return False
    player = storage.get_character(telegram_id, refresh_energy=False)
    return player is not None and player.faction == MONOLITH_FACTION


def filter_travel_locations_for_faction(
    locations: list[dict[str, Any]],
    faction: str | None,
) -> list[dict[str, Any]]:
    """ЧАЭС видна в переходах только Монолиту."""
    if faction == MONOLITH_FACTION:
        return locations
    return [loc for loc in locations if str(loc.get("name") or "") != MONOLITH_BASE]
