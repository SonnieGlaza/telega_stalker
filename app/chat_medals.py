"""Медальки в беседах: custom title у ника (ставит админ командой /medal)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from aiogram import Bot

from app.season_chat_titles import (
    ZONE_COMMON_CHAT_ID,
    ZONE_FACTION_CHAT_IDS,
    _demote_member,
    _promote_title_only,
)
from app.storage import Storage

logger = logging.getLogger(__name__)

CHAT_MEDAL_META_PREFIX = "chat_medal:"
CHAT_MEDAL_INDEX_META = "chat_medals:index"
CHAT_MEDAL_MAX_LEN = 16


def _medal_key(telegram_id: int) -> str:
    return f"{CHAT_MEDAL_META_PREFIX}{int(telegram_id)}"


def sanitize_medal_title(raw: str) -> str:
    """Telegram: custom title ≤ 16 символов, без эмодзи."""
    text = (raw or "").strip()
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[\u2600-\u27bf\u2300-\u23ff\ufe0f]", "", text)
    text = " ".join(text.split())
    return text[:CHAT_MEDAL_MAX_LEN]


def get_chat_medal(storage: Storage, telegram_id: int) -> str | None:
    raw = storage.get_meta(_medal_key(telegram_id))
    title = sanitize_medal_title(str(raw or ""))
    return title or None


def _load_index(storage: Storage) -> list[int]:
    raw = storage.get_meta(CHAT_MEDAL_INDEX_META)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[int] = []
    for item in data:
        try:
            tid = int(item)
        except (TypeError, ValueError):
            continue
        if tid > 0 and tid not in out:
            out.append(tid)
    return out


def _save_index(storage: Storage, ids: list[int]) -> None:
    storage.set_meta(CHAT_MEDAL_INDEX_META, json.dumps(ids))


def save_chat_medal(storage: Storage, telegram_id: int, title: str) -> str:
    clean = sanitize_medal_title(title)
    if not clean:
        raise ValueError("Пустой титул. Нужен текст без эмодзи, до 16 символов.")
    storage.set_meta(_medal_key(telegram_id), clean)
    ids = _load_index(storage)
    if int(telegram_id) not in ids:
        ids.append(int(telegram_id))
        _save_index(storage, ids)
    return clean


def clear_saved_chat_medal(storage: Storage, telegram_id: int) -> None:
    storage.delete_meta(_medal_key(telegram_id))
    ids = [tid for tid in _load_index(storage) if tid != int(telegram_id)]
    _save_index(storage, ids)


def medal_chat_targets(storage: Storage, telegram_id: int) -> list[int]:
    chats = [ZONE_COMMON_CHAT_ID]
    player = storage.get_character(telegram_id, refresh_energy=False)
    faction = str(getattr(player, "faction", "") or "") if player else ""
    faction_chat = ZONE_FACTION_CHAT_IDS.get(faction)
    if faction_chat is not None:
        chats.append(int(faction_chat))
    return chats


async def apply_chat_medal(bot: Bot, storage: Storage, telegram_id: int, title: str) -> list[str]:
    clean = save_chat_medal(storage, telegram_id, title)
    notes: list[str] = []
    for chat_id in medal_chat_targets(storage, telegram_id):
        try:
            await _promote_title_only(bot, chat_id, telegram_id, clean)
            notes.append(f"«{clean}» в чате {chat_id}")
        except Exception:
            logger.exception("Failed to set medal %r for %s in %s", clean, telegram_id, chat_id)
            notes.append(f"не вышло в {chat_id} (бот должен быть админом, игрок — в чате)")
    return notes


async def remove_chat_medal(bot: Bot, storage: Storage, telegram_id: int) -> list[str]:
    notes: list[str] = []
    for chat_id in medal_chat_targets(storage, telegram_id):
        try:
            await _demote_member(bot, chat_id, telegram_id)
            notes.append(f"снята в чате {chat_id}")
        except Exception:
            logger.exception("Failed to clear medal for %s in %s", telegram_id, chat_id)
            notes.append(f"не снялась в {chat_id}")
    clear_saved_chat_medal(storage, telegram_id)
    return notes


async def reapply_all_chat_medals(bot: Bot, storage: Storage) -> list[str]:
    """После сезонных титулов вернуть админские медальки (они приоритетнее)."""
    notes: list[str] = []
    for telegram_id in _load_index(storage):
        title = get_chat_medal(storage, telegram_id)
        if not title:
            continue
        notes.extend(await apply_chat_medal(bot, storage, telegram_id, title))
    return notes


def format_medal_profile_line(storage: Storage, telegram_id: int) -> str:
    title = get_chat_medal(storage, telegram_id)
    if not title:
        return ""
    return f"🎖 Медаль в беседах: {title}\n"