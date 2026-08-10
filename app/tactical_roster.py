"""Общие операции с рoster игроков в тактических group-сессиях."""

from __future__ import annotations

from typing import Any


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
