"""Карта локации: зоны для тактических вылазок на текущей локации.

Блок «карта локации»: на каждой из 12 локаций есть 2 зоны —
аномальный участок (ловля артефактов) и зона обыска (поиск схрона).
Внутриигровые мини-игры переиспользуются как есть: art.hunt (аномалии +
артефакт) и stash hunt (схрон). Встроенные шансы засады в обеих мини-играх
покрывают «риск нападения», дополнительно их здесь не увеличиваем.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.game_logic import ActionResult
from app.storage import Storage

SEARCH_ZONE_COOLDOWN_HOURS = 2

# Для каждой локации ровно 2 зоны: аномальный участок + зона обыска.
# Зоны обыска тематически названы под лор S.T.A.L.K.E.R.
LOCATION_ZONES: dict[str, list[dict]] = {
    "Кордон": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Заброшенный гараж"},
    ],
    "Свалка": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Сортировочная"},
    ],
    "Росток": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Тоннели под баром"},
    ],
    "Армейские склады": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Секретные ангары"},
    ],
    "НИИ Агропром": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Тоннели Агропрома"},
    ],
    "Янтарь": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Лаборатория X-16"},
        {"id": "lab_limit2", "kind": "lab", "label": "Лаборатория «Предел-2»"},
    ],
    "Болото": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Затопленный бункер"},
    ],
    "Темная долина": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Развалины деревни"},
        {"id": "lab_limit1", "kind": "lab", "label": "Лаборатория «Предел-1»"},
    ],
    "Рыжий лес": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Заброшенная лесопилка"},
    ],
    "Радар": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Ангары Радара"},
        {"id": "lab_limit3", "kind": "lab", "label": "Лаборатория «Предел-3»"},
    ],
    "Припять": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Заброшенный универмаг"},
    ],
    "ЧАЭС": [
        {"id": "anomaly", "kind": "anomaly", "label": "Аномальный участок"},
        {"id": "search_1", "kind": "search", "label": "Машинный зал"},
    ],
}


def location_zones_for(location: str) -> list[dict]:
    return list(LOCATION_ZONES.get(location, []))


def _zone_cooldown_key(telegram_id: int, location: str, zone_id: str) -> str:
    return f"zonecd:{location}:{zone_id}:{int(telegram_id)}"


def zone_ready_at(
    storage: Storage,
    telegram_id: int,
    location: str,
    zone_id: str,
) -> datetime | None:
    """Когда зона обыска снова доступна; None — записей нет или кулдаун истёк.

    Соглашение по времени такое же, как в остальном проекте
    (см. arena_grid/coop_mission/faction_change): храним ISO-строку
    _utc_now().isoformat(), при чтении наивный datetime трактуем как UTC.
    """
    raw = storage.get_meta(_zone_cooldown_key(telegram_id, location, zone_id))
    if not raw:
        return None
    try:
        ready_at = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    if ready_at.tzinfo is None:
        ready_at = ready_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return ready_at if ready_at > now else None


def zone_cooldown_remaining_text(
    storage: Storage,
    telegram_id: int,
    location: str,
    zone_id: str,
) -> str | None:
    """Человекочитаемый остаток кулдауна («1ч 20м»); None — зона готова."""
    ready_at = zone_ready_at(storage, telegram_id, location, zone_id)
    if ready_at is None:
        return None
    total_sec = max(0, int((ready_at - datetime.now(timezone.utc)).total_seconds()))
    hours, rem = divmod(total_sec, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{hours}ч {minutes}м"
    if hours:
        return f"{hours}ч"
    return f"{minutes}м"


def start_search_zone(
    storage: Storage,
    telegram_id: int,
    location: str,
    zone_id: str,
) -> ActionResult:
    """Начать обыск зоны локации (переиспользует мини-игру схрона).

    Проверки «мёртв / в пути / занят / уже есть сессия» делает сама
    start_stash_hunt(source="zone"): кулдаун ставится только когда новая
    вылазка реально началась (payload["stash_started"] == True) — повторный
    вход в уже идущую сессию не штрафуется новым кулдауном.
    """
    zones = location_zones_for(location)
    zone = next((z for z in zones if str(z.get("id") or "") == zone_id), None)
    if zone is None or str(zone.get("kind") or "") != "search":
        return ActionResult(False, "Такой зоны здесь нет.")

    remaining = zone_cooldown_remaining_text(storage, telegram_id, location, zone_id)
    if remaining is not None:
        return ActionResult(False, f"Зона обыска ещё восстанавливается: {remaining}.")

    from app.stash_hunt import start_stash_hunt

    result = start_stash_hunt(storage, telegram_id, source="zone")
    if result.ok and (result.payload or {}).get("stash_started"):
        ready_at = datetime.now(timezone.utc) + timedelta(hours=SEARCH_ZONE_COOLDOWN_HOURS)
        storage.set_meta(
            _zone_cooldown_key(telegram_id, location, zone_id),
            ready_at.isoformat(),
        )
    return result