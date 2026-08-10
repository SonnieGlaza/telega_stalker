"""Общие операции с roster игроков в тактических group-сессиях."""

from __future__ import annotations

from typing import Any


def resolve_active_player(
    session: Any,
    *,
    check_evacuated: bool = False,
    empty_fallback: int | None = None,
) -> int:
    """Кто ходит сейчас — только чтение, без изменения active_index."""
    turn_order = list(getattr(session, "turn_order", None) or [])
    active_index = int(getattr(session, "active_index", 0) or 0)
    hp_map: dict[str, int] = getattr(session, "hp", None) or {}
    evacuated = set(getattr(session, "evacuated", None) or [])

    def _alive(pid: int) -> bool:
        if hp_map.get(str(pid), 0) <= 0:
            return False
        return not check_evacuated or pid not in evacuated

    if not turn_order:
        if empty_fallback is not None and _alive(empty_fallback):
            return int(empty_fallback)
        for pid in getattr(session, "player_ids", None) or []:
            if _alive(int(pid)):
                return int(pid)
        return 0

    n = len(turn_order)
    for offset in range(n):
        pid = int(turn_order[(active_index + offset) % n])
        if _alive(pid):
            return pid
    return 0


def is_downed_in_group_session(session: Any, telegram_id: int) -> bool:
    """HP=0 на поле, сессия ещё идёт — смерть в БД откладывается до конца боя."""
    if getattr(session, "finished", False):
        return False
    hp_map = getattr(session, "hp", None)
    if not isinstance(hp_map, dict):
        return False
    if int(hp_map.get(str(telegram_id), 0)) > 0:
        return False
    evacuated = getattr(session, "evacuated", None)
    if isinstance(evacuated, list) and int(telegram_id) in evacuated:
        return False
    return True


def drop_player_from_tactical_roster(session: Any, telegram_id: int) -> None:
    """Убрать игрока из списков сессии (кооп / рейд / захват / клан-война)."""
    pid = int(telegram_id)
    key = str(pid)

    player_ids = getattr(session, "player_ids", None)
    if isinstance(player_ids, list) and pid in player_ids:
        session.player_ids = [p for p in player_ids if p != pid]

    turn_order = getattr(session, "turn_order", None)
    if isinstance(turn_order, list) and pid in turn_order:
        session.turn_order = [p for p in turn_order if p != pid]

    evacuated = getattr(session, "evacuated", None)
    if isinstance(evacuated, list) and pid in evacuated:
        session.evacuated = [p for p in evacuated if p != pid]

    for attr in ("hp", "positions", "medkits_used", "death_causes", "death_killers", "message_ids"):
        mapping = getattr(session, attr, None)
        if isinstance(mapping, dict):
            mapping.pop(key, None)

    carrying = getattr(session, "carrying", None)
    if isinstance(carrying, dict):
        carrying.pop(key, None)
        for carrier, carried in list(carrying.items()):
            if str(carried) == key:
                carrying.pop(carrier, None)

    if hasattr(session, "active_index") and getattr(session, "turn_order", None):
        order = session.turn_order
        if order:
            session.active_index %= len(order)
        else:
            session.active_index = 0
