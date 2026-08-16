"""Сезонные custom title в чатах Зоны (админ без прав + титул)."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiogram import Bot

from app.storage import Storage

logger = logging.getLogger(__name__)

# Числовые id супергрупп (не invite-ссылки).
ZONE_COMMON_CHAT_ID = -1003958853707
ZONE_FACTION_CHAT_IDS: dict[str, int] = {
    "Бандиты": -1004375297519,
    "Свобода": -1003883863150,
    "Долг": -1004377044940,
    "Нейтралы": -1004295857240,
}

# Telegram: custom_title ≤ 16 символов, без эмодзи.
SEASON_CHAT_TITLE_BY_PLACE: dict[int, str] = {
    1: "Чемпион Зоны",
    2: "Серебро сезона",
    3: "Бронза сезона",
}

SEASON_CHAT_TITLE_HOLDERS_META = "season_chat_title_holders"
SEASON_CHAT_TITLE_PENDING_META = "season_chat_title_pending"


def season_chat_title_for_place(place: int) -> str | None:
    title = SEASON_CHAT_TITLE_BY_PLACE.get(int(place))
    if not title:
        return None
    # Защита от случайного превышения лимита Telegram.
    return title[:16]


def build_season_chat_title_jobs(
    storage: Storage, top: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Список назначений: общий чат + чат группировки победителя."""
    jobs: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for place, row in enumerate(top[:3], start=1):
        title = season_chat_title_for_place(place)
        if not title:
            continue
        try:
            user_id = int(row.get("telegram_id") or 0)
        except (TypeError, ValueError):
            continue
        if user_id <= 0:
            continue
        chat_targets = [ZONE_COMMON_CHAT_ID]
        character = storage.get_character(user_id, refresh_energy=False)
        faction = str(getattr(character, "faction", "") or "") if character else ""
        faction_chat = ZONE_FACTION_CHAT_IDS.get(faction)
        if faction_chat is not None:
            chat_targets.append(int(faction_chat))
        for chat_id in chat_targets:
            key = (chat_id, user_id)
            if key in seen:
                continue
            seen.add(key)
            jobs.append(
                {
                    "chat_id": int(chat_id),
                    "user_id": user_id,
                    "title": title,
                    "place": place,
                    "faction": faction,
                }
            )
    return jobs


def queue_season_chat_titles(storage: Storage, top: list[dict[str, Any]]) -> int:
    """Сохраняет задания на титулы после конца сезона (бот применит асинхронно)."""
    jobs = build_season_chat_title_jobs(storage, top)
    storage.set_meta(SEASON_CHAT_TITLE_PENDING_META, json.dumps({"jobs": jobs}, ensure_ascii=False))
    return len(jobs)


def _load_json_meta(storage: Storage, key: str) -> dict[str, Any]:
    raw = storage.get_meta(key)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_holders(storage: Storage, holders: list[dict[str, Any]]) -> None:
    storage.set_meta(
        SEASON_CHAT_TITLE_HOLDERS_META,
        json.dumps({"holders": holders}, ensure_ascii=False),
    )


async def _demote_member(bot: Bot, chat_id: int, user_id: int) -> None:
    """Снять админку (все права False = demote по Bot API)."""
    await bot.promote_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        is_anonymous=False,
        can_manage_chat=False,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_post_messages=False,
        can_edit_messages=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )


async def _promote_title_only(bot: Bot, chat_id: int, user_id: int, title: str) -> None:
    """Админ почти без прав + custom title.

    Bot API: если все права False — это demote. Поэтому оставляем только
    can_invite_users (без бана/удаления/смены инфо чата).
    """
    await bot.promote_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        is_anonymous=False,
        can_manage_chat=False,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_post_messages=False,
        can_edit_messages=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )
    await bot.set_chat_administrator_custom_title(
        chat_id=chat_id,
        user_id=user_id,
        custom_title=title[:16],
    )


async def apply_pending_season_chat_titles(bot: Bot, storage: Storage) -> list[str]:
    """Снимает прошлые титулы и ставит новые из pending. Возвращает лог-строки."""
    pending = _load_json_meta(storage, SEASON_CHAT_TITLE_PENDING_META)
    jobs = pending.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        return []

    notes: list[str] = []
    old = _load_json_meta(storage, SEASON_CHAT_TITLE_HOLDERS_META)
    old_holders = old.get("holders") if isinstance(old.get("holders"), list) else []

    for holder in old_holders:
        try:
            chat_id = int(holder.get("chat_id") or 0)
            user_id = int(holder.get("user_id") or 0)
        except (TypeError, ValueError):
            continue
        if chat_id == 0 or user_id <= 0:
            continue
        try:
            await _demote_member(bot, chat_id, user_id)
            notes.append(f"снят титул у {user_id} в {chat_id}")
        except Exception:
            logger.exception("Failed to demote season title holder %s in %s", user_id, chat_id)

    new_holders: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        try:
            chat_id = int(job.get("chat_id") or 0)
            user_id = int(job.get("user_id") or 0)
            title = str(job.get("title") or "")[:16]
        except (TypeError, ValueError):
            continue
        if chat_id == 0 or user_id <= 0 or not title:
            continue
        try:
            await _promote_title_only(bot, chat_id, user_id, title)
            new_holders.append({"chat_id": chat_id, "user_id": user_id, "title": title})
            notes.append(f"{user_id} → «{title}» в {chat_id}")
        except Exception:
            logger.exception(
                "Failed to set season title %r for %s in %s", title, user_id, chat_id
            )

    _save_holders(storage, new_holders)
    storage.set_meta(SEASON_CHAT_TITLE_PENDING_META, "")
    return notes
