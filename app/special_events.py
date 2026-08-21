"""Особые события Зоны: вертушка, шторм, бандиты, тёмный сталкер.

Волна 1 — на существующем движке (рация / clear / travel / shop meta).
Тяжёлые сценарии (Завод, Монолит, Гигант, зомби-волны) — отдельно.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.game_logic import ActionResult, QuestContractTemplate, QUESTS, h
from app.storage import Storage

SPECIAL_EVENT_META = "special_event:active"
SPECIAL_EVENT_NEXT_META = "special_event:next_at"
SHOP_STOCK_META = "shop:stock:consumables"

SPECIAL_EVENT_INTERVAL_MIN_MINUTES = 50
SPECIAL_EVENT_INTERVAL_MAX_MINUTES = 110
SPECIAL_EVENT_DURATION_MINUTES = 20

# Расходники, которые «заканчиваются» при блокаде бандитов.
BLOCKADE_STOCK_KEYS: tuple[str, ...] = ("medkit", "vodka", "sausage")
BLOCKADE_STOCK_AMOUNT = 2  # штук на всю Зону, пока логово не зачищено

SPECIAL_LOCATIONS: tuple[str, ...] = (
    "Болото",
    "Свалка",
    "НИИ Агропром",
    "Темная долина",
    "Янтарь",
    "Рыжий лес",
    "Радар",
)

EVENT_KINDS: tuple[str, ...] = (
    "heli_crash",
    "anomaly_storm",
    "bandit_blockade",
    "dark_stalker",
)


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


def schedule_next_special_event(storage: Storage, now: datetime | None = None) -> None:
    now = now or _utc_now()
    delay = random.randint(SPECIAL_EVENT_INTERVAL_MIN_MINUTES, SPECIAL_EVENT_INTERVAL_MAX_MINUTES)
    storage.set_meta(SPECIAL_EVENT_NEXT_META, (now + timedelta(minutes=delay)).isoformat())


def get_active_special_event(storage: Storage) -> dict[str, Any] | None:
    raw = storage.get_meta(SPECIAL_EVENT_META)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    expires = _parse_iso(str(data.get("expires_at") or ""), _utc_now())
    if expires <= _utc_now() and not data.get("resolved"):
        return data  # ещё нужно закрыть в process_*
    if data.get("resolved"):
        return None
    if expires <= _utc_now():
        return None
    return data


def _save_event(storage: Storage, event: dict[str, Any]) -> None:
    storage.set_meta(SPECIAL_EVENT_META, json.dumps(event, ensure_ascii=False))


def _clear_event(storage: Storage) -> None:
    storage.set_meta(SPECIAL_EVENT_META, "")


def get_shop_stock(storage: Storage) -> dict[str, int] | None:
    """None = обычный бесконечный ассортимент."""
    raw = storage.get_meta(SHOP_STOCK_META)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    return {str(k): max(0, int(v)) for k, v in data.items()}


def set_shop_stock(storage: Storage, stock: dict[str, int] | None) -> None:
    if stock is None:
        storage.set_meta(SHOP_STOCK_META, "")
        return
    storage.set_meta(SHOP_STOCK_META, json.dumps(stock, ensure_ascii=False))


def consume_shop_stock(storage: Storage, item_key: str, amount: int = 1) -> str | None:
    """Списать со стока. None = ок / стока нет. Строка = ошибка."""
    stock = get_shop_stock(storage)
    if stock is None:
        return None
    if item_key not in stock:
        return None
    left = int(stock.get(item_key, 0))
    need = max(1, int(amount))
    if left < need:
        return (
            f"Поставки перебиты бандитами: «{item_key}» закончился у торговцев "
            f"(осталось {left}). Зачисти логово, чтобы открыть поставки."
        )
    stock[item_key] = left - need
    set_shop_stock(storage, stock)
    return None


def travel_blocked_by_special_event(
    storage: Storage,
    *,
    from_location: str,
    to_location: str,
) -> str | None:
    event = get_active_special_event(storage)
    if event is None:
        return None
    kind = str(event.get("kind") or "")
    if kind == "anomaly_storm":
        if event.get("passages_open"):
            return None
        mins = _minutes_left(event)
        return (
            f"🌪 Аномальный шторм перекрыл переходы (~{mins} мин).\n"
            "Жди или ищи проходы среди аномалий (кнопка в заданиях)."
        )
    if kind == "bandit_blockade":
        loc = str(event.get("location") or "")
        # На локацию пускаем штурмовать логово; уйти нельзя, пока бандиты держат проход.
        if from_location == loc and to_location != loc:
            dens_left = int(event.get("dens_left") or 1)
            return (
                f"🔫 Бандиты перекрыли выход с «{loc}» (логовищ осталось: {dens_left}).\n"
                "Зачисти логово на месте, чтобы снова уйти с локации."
            )
    return None


def _minutes_left(event: dict[str, Any]) -> int:
    expires = _parse_iso(str(event.get("expires_at") or ""), _utc_now())
    return max(0, int((expires - _utc_now()).total_seconds() // 60))


def _build_heli_crash(location: str, now: datetime) -> dict[str, Any]:
    return {
        "id": now.strftime("%Y%m%d%H%M%S"),
        "kind": "heli_crash",
        "location": location,
        "title": "Военная тайна",
        "call_text": (
            f"Приём всем! Военная вертушка рухнула на «{location}». "
            "В обломках может быть ценный хабар, но охрана ещё жива — стычка неизбежна. "
            f"Окно ~{SPECIAL_EVENT_DURATION_MINUTES} мин."
        ),
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=SPECIAL_EVENT_DURATION_MINUTES)).isoformat(),
        "helpers": [],
        "helper_names": [],
        "resolved": False,
        "looters_done": [],
    }


def _build_anomaly_storm(now: datetime) -> dict[str, Any]:
    return {
        "id": now.strftime("%Y%m%d%H%M%S"),
        "kind": "anomaly_storm",
        "location": random.choice(SPECIAL_LOCATIONS),
        "title": "Аномальный шторм",
        "call_text": (
            "🌪 Аномальный шторм перекрыл переходы между локациями. "
            f"Либо ждите ~{SPECIAL_EVENT_DURATION_MINUTES} мин, либо добровольцы ищут проходы "
            "в аномальных полях — тогда пути откроются раньше."
        ),
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=SPECIAL_EVENT_DURATION_MINUTES)).isoformat(),
        "helpers": [],
        "helper_names": [],
        "passages_open": False,
        "resolved": False,
    }


def _build_bandit_blockade(location: str, now: datetime) -> dict[str, Any]:
    dens = random.randint(1, 2)
    return {
        "id": now.strftime("%Y%m%d%H%M%S"),
        "kind": "bandit_blockade",
        "location": location,
        "title": "Блокада бандитов",
        "call_text": (
            f"Бандиты перекрыли проход на «{location}». "
            "Поставки аптечек, водки и колбасы приостановлены. "
            f"Нужно перебить логово (осталось {dens}). Можно в соло или с кем-то."
        ),
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=SPECIAL_EVENT_DURATION_MINUTES + 10)).isoformat(),
        "helpers": [],
        "helper_names": [],
        "dens_left": dens,
        "dens_total": dens,
        "resolved": False,
    }


def _build_dark_stalker(location: str, now: datetime) -> dict[str, Any]:
    return {
        "id": now.strftime("%Y%m%d%H%M%S"),
        "kind": "dark_stalker",
        "location": location,
        "title": "Тёмный сталкер",
        "call_text": (
            f"На «{location}» замечен Тёмный сталкер. "
            "Говорят, это твой двойник. Дуэль один на один — кто выдержит."
        ),
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=SPECIAL_EVENT_DURATION_MINUTES)).isoformat(),
        "challengers": [],
        "resolved": False,
    }


def start_special_event(storage: Storage, *, kind: str | None = None) -> dict[str, Any]:
    now = _utc_now()
    picked = kind or random.choice(EVENT_KINDS)
    location = random.choice(SPECIAL_LOCATIONS)
    if picked == "heli_crash":
        event = _build_heli_crash(location, now)
    elif picked == "anomaly_storm":
        event = _build_anomaly_storm(now)
    elif picked == "bandit_blockade":
        event = _build_bandit_blockade(location, now)
        set_shop_stock(
            storage,
            {key: BLOCKADE_STOCK_AMOUNT for key in BLOCKADE_STOCK_KEYS},
        )
    elif picked == "dark_stalker":
        event = _build_dark_stalker(location, now)
    else:
        event = _build_heli_crash(location, now)
    _save_event(storage, event)
    return event


def format_special_call_html(event: dict[str, Any]) -> str:
    title = h(str(event.get("title") or "Событие Зоны"))
    body = h(str(event.get("call_text") or ""))
    kind = str(event.get("kind") or "")
    emoji = {
        "heli_crash": "🚁",
        "anomaly_storm": "🌪",
        "bandit_blockade": "🔫",
        "dark_stalker": "🕶",
    }.get(kind, "📡")
    return f"{emoji} <b>{title}</b>\n{body}"


def format_special_resolve_html(text: str) -> str:
    return f"📡 {h(text)}"


def special_event_is_joinable(storage: Storage, telegram_id: int) -> bool:
    event = get_active_special_event(storage)
    if event is None:
        return False
    expires = _parse_iso(str(event.get("expires_at") or ""), _utc_now())
    if expires <= _utc_now():
        return False
    kind = str(event.get("kind") or "")
    if kind == "anomaly_storm":
        return not bool(event.get("passages_open"))
    if kind == "heli_crash":
        helpers = [int(x) for x in (event.get("helpers") or [])]
        return int(telegram_id) not in helpers and len(helpers) < 4
    if kind == "bandit_blockade":
        return int(event.get("dens_left") or 0) > 0
    if kind == "dark_stalker":
        return True
    return False


def join_special_event(storage: Storage, telegram_id: int) -> ActionResult:
    """Вступить в активное особое событие (вертушка / шторм / бандиты / дуэль)."""
    from app.player_busy import player_busy_reason
    from app.quest_mission import start_or_resume_quest_mission

    event = get_active_special_event(storage)
    if event is None:
        return ActionResult(False, "Сейчас нет особого события Зоны.")
    kind = str(event.get("kind") or "")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    busy = player_busy_reason(storage, telegram_id)
    if busy:
        return ActionResult(False, busy)

    if kind == "heli_crash":
        loc = str(event.get("location") or "")
        if player.location != loc:
            return ActionResult(False, f"Нужно быть на «{loc}», чтобы обыскать обломки.")
        helpers = [int(x) for x in (event.get("helpers") or [])]
        if telegram_id in helpers:
            return ActionResult(False, "Ты уже в деле у обломков.")
        if len(helpers) >= 4:
            return ActionResult(False, "У обломков уже толпа — мест нет.")
        template = QuestContractTemplate(
            key=f"heli_{event['id']}",
            difficulty="hard",
            title=f"Обломки вертушки: {loc}",
            work_location=loc,
            return_home=False,
            mission_kind="clear_marauder",
        )
        result = start_or_resume_quest_mission(storage, telegram_id, template, QUESTS["hard"])
        if not result.ok:
            return result
        helpers.append(telegram_id)
        names = list(event.get("helper_names") or [])
        names.append(str(player.nickname))
        event["helpers"] = helpers
        event["helper_names"] = names
        _save_event(storage, event)
        return ActionResult(
            True,
            f"Ты у обломков на «{loc}». Зачисти охрану — хабар военный.",
            payload=result.payload,
        )

    if kind == "anomaly_storm":
        if event.get("passages_open"):
            return ActionResult(False, "Проходы уже открыты — можно ехать.")
        loc = str(event.get("location") or player.location)
        # Искать проход можно с текущей локации — аномальное поле «рядом».
        template = QuestContractTemplate(
            key=f"storm_{event['id']}",
            difficulty="hard",
            title="Поиск прохода в шторме",
            work_location=str(player.location),
            return_home=False,
            mission_kind="anomaly",
        )
        result = start_or_resume_quest_mission(storage, telegram_id, template, QUESTS["hard"])
        if not result.ok:
            return result
        helpers = [int(x) for x in (event.get("helpers") or [])]
        if telegram_id not in helpers:
            helpers.append(telegram_id)
            names = list(event.get("helper_names") or [])
            names.append(str(player.nickname))
            event["helpers"] = helpers
            event["helper_names"] = names
            _save_event(storage, event)
        return ActionResult(
            True,
            "Ищешь стабильный проход среди аномалий. Успех откроет переходы для всех.",
            payload=result.payload,
        )

    if kind == "bandit_blockade":
        loc = str(event.get("location") or "")
        if player.location != loc:
            return ActionResult(
                False,
                f"Логово на «{loc}». Доберись туда (если ещё пускают) и жми снова.",
            )
        dens = int(event.get("dens_left") or 0)
        if dens <= 0:
            return ActionResult(False, "Логова уже выжжены.")
        template = QuestContractTemplate(
            key=f"bandit_den_{event['id']}_{dens}",
            difficulty="hard",
            title=f"Логово бандитов: {loc}",
            work_location=loc,
            return_home=False,
            mission_kind="clear_marauder",
        )
        result = start_or_resume_quest_mission(storage, telegram_id, template, QUESTS["hard"])
        if not result.ok:
            return result
        helpers = [int(x) for x in (event.get("helpers") or [])]
        if telegram_id not in helpers:
            helpers.append(telegram_id)
            names = list(event.get("helper_names") or [])
            names.append(str(player.nickname))
            event["helpers"] = helpers
            event["helper_names"] = names
            _save_event(storage, event)
        return ActionResult(
            True,
            f"Штурм логова на «{loc}» (осталось {dens}).",
            payload=result.payload,
        )

    if kind == "dark_stalker":
        loc = str(event.get("location") or "")
        if player.location != loc:
            return ActionResult(False, f"Тёмный сталкер ждёт на «{loc}».")
        from app.game_logic import equipment_power

        power = max(1, equipment_power(player))
        diff = "heavy" if power >= 14 else "hard"
        template = QuestContractTemplate(
            key=f"dark_{event['id']}_{telegram_id}",
            difficulty=diff,
            title=f"Дуэль: Тёмный сталкер ({loc})",
            work_location=loc,
            return_home=False,
            mission_kind="clear_marauder",
        )
        # На hard патроны не нужны — дуэль доступнее; heavy для жирных стволов.
        if diff == "heavy":
            # Подстрахуем сообщение, если нет патронов — откатим на hard.
            ammo = int(player.inventory.get("ammo_pack", 0))
            med = int(player.inventory.get("medkit", 0)) + int(player.inventory.get("medkit_army", 0))
            if ammo < 2 or med < 1:
                diff = "hard"
                template = QuestContractTemplate(
                    key=f"dark_{event['id']}_{telegram_id}",
                    difficulty=diff,
                    title=f"Дуэль: Тёмный сталкер ({loc})",
                    work_location=loc,
                    return_home=False,
                    mission_kind="clear_marauder",
                )
        result = start_or_resume_quest_mission(storage, telegram_id, template, QUESTS[diff])
        if not result.ok:
            return result
        challengers = [int(x) for x in (event.get("challengers") or [])]
        if telegram_id not in challengers:
            challengers.append(telegram_id)
            event["challengers"] = challengers
            _save_event(storage, event)
        return ActionResult(
            True,
            f"Тёмный сталкер принял вызов. Он бьёт примерно как ты (сила снаряги {power}).",
            payload=result.payload,
        )

    return ActionResult(False, "Неизвестный тип события.")


def complete_special_event_objective(
    storage: Storage,
    telegram_id: int,
    *,
    title: str,
) -> str | None:
    """Вызвать после успеха миссии, запущенной из особого события."""
    event = get_active_special_event(storage)
    if event is None:
        return None
    kind = str(event.get("kind") or "")
    title_l = str(title or "")

    if kind == "heli_crash" and title_l.startswith("Обломки вертушки"):
        done = {int(x) for x in (event.get("looters_done") or [])}
        if telegram_id in done:
            return None
        done.add(telegram_id)
        event["looters_done"] = list(done)
        _save_event(storage, event)
        # Военный хабар сверх обычного квеста.
        storage.change_money(telegram_id, 800)
        storage.add_item(telegram_id, "ammo_pack", 1)
        return "С обломков: +800 RU и патроны."

    if kind == "anomaly_storm" and "шторме" in title_l:
        if event.get("passages_open"):
            return "Проходы уже открыты."
        event["passages_open"] = True
        player = storage.get_character(telegram_id, refresh_energy=False)
        nick = player.nickname if player else str(telegram_id)
        event["opener"] = nick
        _save_event(storage, event)
        return f"Проход найден! Переходы снова открыты (спасибо, {nick})."

    if kind == "bandit_blockade" and title_l.startswith("Логово бандитов"):
        dens = max(0, int(event.get("dens_left") or 0) - 1)
        event["dens_left"] = dens
        _save_event(storage, event)
        if dens <= 0:
            set_shop_stock(storage, None)
            event["resolved"] = True
            _save_event(storage, event)
            return "Последнее логово выжжено. Поставки аптечек/водки/колбасы восстановлены."
        return f"Логово зачищено. Осталось логовищ: {dens}."

    if kind == "dark_stalker" and title_l.startswith("Дуэль: Тёмный сталкер"):
        return "Тёмный сталкер повержен. Двойник рассеялся в аномальной дымке."

    return None


def resolve_expired_special_event(storage: Storage) -> dict[str, Any] | None:
    raw = storage.get_meta(SPECIAL_EVENT_META)
    if not raw:
        return None
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict) or event.get("resolved"):
        return None
    expires = _parse_iso(str(event.get("expires_at") or ""), _utc_now())
    if expires > _utc_now():
        return None
    kind = str(event.get("kind") or "")
    event["resolved"] = True
    _save_event(storage, event)
    if kind == "bandit_blockade":
        # Время вышло — поставки всё равно восстанавливаем, блокада слабеет.
        set_shop_stock(storage, None)
    if kind == "anomaly_storm" and not event.get("passages_open"):
        event["passages_open"] = True
        text = "Аномальный шторм утих. Переходы снова открыты."
    elif kind == "heli_crash":
        names = [str(n) for n in (event.get("helper_names") or [])]
        text = (
            f"Обломки на «{event.get('location')}» остыли. "
            + (f"Успели: {', '.join(names)}." if names else "Хабар растащили военные.")
        )
    elif kind == "bandit_blockade":
        dens = int(event.get("dens_left") or 0)
        text = (
            f"Бандиты ушли с «{event.get('location')}». "
            + ("Поставки восстановлены." if dens > 0 else "Логова были выжжены раньше.")
        )
    elif kind == "dark_stalker":
        text = f"Тёмный сталкер исчез с «{event.get('location')}»."
    else:
        text = "Особое событие Зоны завершилось."
    schedule_next_special_event(storage)
    return {"kind": "resolve", "text": text, "event": event}


def process_special_event_cycle(storage: Storage) -> dict[str, Any] | None:
    """Тик: закрыть просрок или запустить новое событие."""
    resolved = resolve_expired_special_event(storage)
    if resolved:
        return resolved

    active = get_active_special_event(storage)
    if active is not None:
        return None

    now = _utc_now()
    next_raw = storage.get_meta(SPECIAL_EVENT_NEXT_META)
    if next_raw is None:
        schedule_next_special_event(storage, now)
        return None
    next_at = _parse_iso(next_raw, now + timedelta(minutes=SPECIAL_EVENT_INTERVAL_MIN_MINUTES))
    if next_at > now:
        return None
    event = start_special_event(storage)
    schedule_next_special_event(storage, now)
    return {"kind": "call", "text": event.get("call_text") or "", "event": event}


def special_event_button_label(storage: Storage) -> str | None:
    event = get_active_special_event(storage)
    if event is None:
        return None
    kind = str(event.get("kind") or "")
    return {
        "heli_crash": "🚁 К обломкам вертушки",
        "anomaly_storm": "🌪 Искать проход в шторме",
        "bandit_blockade": "🔫 Штурмовать логово бандитов",
        "dark_stalker": "🕶 Вызвать Тёмного сталкера",
    }.get(kind)


def special_events_status_line(storage: Storage) -> str:
    event = get_active_special_event(storage)
    if event is None:
        stock = get_shop_stock(storage)
        if stock:
            bits = ", ".join(f"{k}:{v}" for k, v in stock.items())
            return f"Сток торговцев ограничен: {bits}."
        return "Особых событий сейчас нет."
    kind = str(event.get("kind") or "")
    mins = _minutes_left(event)
    title = str(event.get("title") or kind)
    loc = event.get("location")
    extra = ""
    if kind == "anomaly_storm":
        extra = " · проходы открыты" if event.get("passages_open") else " · переходы закрыты"
    if kind == "bandit_blockade":
        extra = f" · логовищ {event.get('dens_left')}/{event.get('dens_total')}"
    loc_part = f" «{loc}»" if loc else ""
    return f"{title}{loc_part} (~{mins} мин){extra}."
