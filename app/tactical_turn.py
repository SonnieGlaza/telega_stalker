"""Общая optimistic-concurrency для тактических ходов (turn_seq)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.storage import Storage


def patch_session_message_ids(
    storage: Storage,
    *,
    meta_key: str,
    message_ids: dict[str, int],
    from_dict: Callable[[dict[str, Any]], Any],
    save_fn: Callable[..., None],
    save_extra: tuple[Any, ...] = (),
) -> None:
    """Обновить только message_ids на свежей сессии из meta (не затирать ход)."""
    raw = storage.get_meta(meta_key)
    if not raw:
        return
    try:
        fresh = from_dict(json.loads(raw))
    except Exception:
        return
    for key, val in message_ids.items():
        fresh.message_ids[str(key)] = int(val)
    if save_extra:
        save_fn(storage, *save_extra, fresh)
    else:
        save_fn(storage, fresh)


def save_turn_if_seq_ok(
    storage: Storage,
    *,
    meta_key: str,
    session: Any,
    from_dict: Callable[[dict[str, Any]], Any],
    save_fn: Callable[[Storage, Any], None],
    expected_seq: int,
) -> bool:
    raw = storage.get_meta(meta_key)
    if not raw:
        return False
    try:
        fresh = from_dict(json.loads(raw))
    except Exception:
        return False
    if getattr(fresh, "finished", False) or int(getattr(fresh, "turn_seq", -1)) != int(expected_seq):
        return False
    save_fn(storage, session)
    return True
