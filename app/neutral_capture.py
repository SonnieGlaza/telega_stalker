"""Захват нейтральной точки: бандиты/мутанты стреляют как в «Танчиках»."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.artifact_hunt import FONT_CANDIDATES, _paste_circle
from app.game_logic import (
    RATING_REWARD,
    ActionResult,
    _add_rating,
    apply_incoming_damage,
    equipment_power,
    h,
)
from app.storage import Character, Storage
from app.tactical_combat import (
    MOVE_DELTAS,
    NPC_WEAPONS,
    cover_blocks_shot,
    random_hostile_shots,
    ray_cast_first_hit,
    weapon_shoot_range,
)
from app.tactical_hp import sync_session_hp_to_db, use_tactical_medkit

NCAP_GRID_SIZE = 6
NCAP_TURN_SECONDS = 10
NCAP_MATCH_SECONDS = 8 * 60
NCAP_HOSTILE_COUNT = 6
NCAP_ENERGY_COST = 18
NCAP_CAPTURE_TURNS = 2

SESSION_PREFIX = "ncap:session:"
PLAYER_PREFIX = "ncap:player:"
ACTIVE_IDS_KEY = "ncap:active_ids"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _deadline_iso(seconds: int) -> str:
    return (_utc_now() + timedelta(seconds=seconds)).isoformat()


def _parse_deadline(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


@dataclass
class NeutralCaptureSession:
    session_id: str
    telegram_id: int
    location_name: str
    faction: str
    grid: int = NCAP_GRID_SIZE
    cover: list[tuple[int, int]] = field(default_factory=list)
    hostiles: list[tuple[int, int]] = field(default_factory=list)
    hostile_weapons: list[str] = field(default_factory=list)
    hostile_kinds: list[str] = field(default_factory=list)  # bandit | mutant
    capture_point: tuple[int, int] = (2, 2)
    player_pos: tuple[int, int] = (0, 0)
    hp: int = 0
    medkit_used: bool = False
    turn_seq: int = 0
    turn_deadline: str | None = None
    match_deadline: str | None = None
    capture_progress: int = 0
    finished: bool = False
    success: bool = False
    log: list[str] = field(default_factory=list)
    message_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "telegram_id": self.telegram_id,
            "location_name": self.location_name,
            "faction": self.faction,
            "grid": self.grid,
            "cover": [list(p) for p in self.cover],
            "hostiles": [list(p) for p in self.hostiles],
            "hostile_weapons": self.hostile_weapons,
            "hostile_kinds": self.hostile_kinds,
            "capture_point": list(self.capture_point),
            "player_pos": list(self.player_pos),
            "hp": self.hp,
            "medkit_used": self.medkit_used,
            "turn_seq": self.turn_seq,
            "turn_deadline": self.turn_deadline,
            "match_deadline": self.match_deadline,
            "capture_progress": self.capture_progress,
            "finished": self.finished,
            "success": self.success,
            "log": self.log[-12:],
            "message_id": self.message_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> NeutralCaptureSession:
        pp = raw.get("player_pos") or [0, 0]
        cp = raw.get("capture_point") or [2, 2]
        return cls(
            session_id=str(raw.get("session_id") or ""),
            telegram_id=int(raw.get("telegram_id") or 0),
            location_name=str(raw.get("location_name") or ""),
            faction=str(raw.get("faction") or ""),
            grid=int(raw.get("grid") or NCAP_GRID_SIZE),
            cover=[(int(p[0]), int(p[1])) for p in (raw.get("cover") or [])],
            hostiles=[(int(p[0]), int(p[1])) for p in (raw.get("hostiles") or [])],
            hostile_weapons=[str(w) for w in (raw.get("hostile_weapons") or [])],
            hostile_kinds=[str(k) for k in (raw.get("hostile_kinds") or [])],
            capture_point=(int(cp[0]), int(cp[1])),
            player_pos=(int(pp[0]), int(pp[1])),
            hp=int(raw.get("hp") or 0),
            medkit_used=bool(raw.get("medkit_used")),
            turn_seq=int(raw.get("turn_seq") or 0),
            turn_deadline=raw.get("turn_deadline"),
            match_deadline=raw.get("match_deadline"),
            capture_progress=int(raw.get("capture_progress") or 0),
            finished=bool(raw.get("finished")),
            success=bool(raw.get("success")),
            log=[str(x) for x in (raw.get("log") or [])],
            message_id=int(raw["message_id"]) if raw.get("message_id") is not None else None,
        )


def _session_key(sid: str) -> str:
    return f"{SESSION_PREFIX}{sid}"


def _player_key(tid: int) -> str:
    return f"{PLAYER_PREFIX}{int(tid)}"


def get_ncap_session(storage: Storage, telegram_id: int) -> NeutralCaptureSession | None:
    sid = storage.get_meta(_player_key(telegram_id))
    if not sid:
        return None
    raw = storage.get_meta(_session_key(sid))
    if not raw:
        storage.delete_meta(_player_key(telegram_id))
        return None
    try:
        session = NeutralCaptureSession.from_dict(json.loads(raw))
    except Exception:
        storage.delete_meta(_player_key(telegram_id))
        return None
    if session.finished:
        return None
    return session


def save_ncap_session(storage: Storage, session: NeutralCaptureSession) -> None:
    storage.set_meta(_session_key(session.session_id), json.dumps(session.to_dict(), ensure_ascii=False))
    storage.set_meta(_player_key(session.telegram_id), session.session_id)


def clear_ncap_session(storage: Storage, session: NeutralCaptureSession) -> None:
    storage.delete_meta(_session_key(session.session_id))
    storage.delete_meta(_player_key(session.telegram_id))
    _unregister_active(storage, session.session_id)


def _register_active(storage: Storage, session_id: str) -> None:
    raw = storage.get_meta(ACTIVE_IDS_KEY)
    ids: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                ids = [str(x) for x in parsed]
        except json.JSONDecodeError:
            ids = []
    if session_id not in ids:
        ids.append(session_id)
    storage.set_meta(ACTIVE_IDS_KEY, json.dumps(ids, ensure_ascii=False))


def _unregister_active(storage: Storage, session_id: str) -> None:
    raw = storage.get_meta(ACTIVE_IDS_KEY)
    if not raw:
        return
    try:
        ids = [str(x) for x in json.loads(raw) if str(x) != session_id]
    except json.JSONDecodeError:
        ids = []
    storage.set_meta(ACTIVE_IDS_KEY, json.dumps(ids, ensure_ascii=False))


def _free_cell(grid: int, forbidden: set[tuple[int, int]]) -> tuple[int, int]:
    opts = [(x, y) for x in range(grid) for y in range(grid) if (x, y) not in forbidden]
    return random.choice(opts)


def _build_map(session: NeutralCaptureSession) -> None:
    grid = session.grid
    forbidden: set[tuple[int, int]] = {session.capture_point}
    for _ in range(random.randint(5, 8)):
        cell = _free_cell(grid, forbidden)
        session.cover.append(cell)
        forbidden.add(cell)
    for i in range(NCAP_HOSTILE_COUNT):
        cell = _free_cell(grid, forbidden)
        session.hostiles.append(cell)
        kind = "bandit" if random.random() < 0.65 else "mutant"
        session.hostile_kinds.append(kind)
        if kind == "bandit":
            session.hostile_weapons.append(random.choice(NPC_WEAPONS))
        else:
            session.hostile_weapons.append("ПМ")
        forbidden.add(cell)
    session.player_pos = _free_cell(grid, forbidden)


def _occupied(session: NeutralCaptureSession) -> set[tuple[int, int]]:
    return set(session.cover) | set(session.hostiles) | {session.player_pos}


def _hostile_damage(weapon: str) -> int:
    return max(3, weapon_shoot_range(weapon) * 2 + random.randint(0, 3))


def _hostile_shoot_turn(storage: Storage, session: NeutralCaptureSession) -> list[str]:
    cover_set = set(session.cover)
    player_pos = {session.telegram_id: session.player_pos}
    player = storage.get_character(session.telegram_id, refresh_energy=False)
    return random_hostile_shots(
        session.hostiles,
        session.hostile_weapons,
        grid=session.grid,
        player_positions=player_pos,
        player_hp={str(session.telegram_id): session.hp},
        player_characters={session.telegram_id: player},
        cover=cover_set,
        base_cover=set(),
        damage_fn=_hostile_damage,
    )


def _finalize_success(storage: Storage, session: NeutralCaptureSession) -> ActionResult:
    storage.set_location_control(session.location_name, session.faction)
    storage.add_player_stat(session.telegram_id, "wars_won", 1)
    reward_ru = 1200
    storage.change_money(session.telegram_id, reward_ru)
    storage.add_player_stat(session.telegram_id, "money_earned", reward_ru)
    _add_rating(storage, session.telegram_id, RATING_REWARD["war_success"])
    text = (
        f"🏆 Нейтральная точка «{session.location_name}» захвачена!\n"
        f"Контроль: {session.faction}. +{reward_ru} RU, +{RATING_REWARD['war_success']} рейтинга."
    )
    return ActionResult(True, text, payload={"ncap_done": True, "success": True})


def _finalize_fail(storage: Storage, session: NeutralCaptureSession, reason: str) -> ActionResult:
    _add_rating(storage, session.telegram_id, -RATING_REWARD["war_fail"])
    return ActionResult(
        False,
        f"💀 Захват «{session.location_name}» провален.\n{reason}",
        payload={"ncap_done": True, "success": False},
    )


def _end_session(storage: Storage, session: NeutralCaptureSession, result: ActionResult) -> ActionResult:
    sync_session_hp_to_db(storage, session.telegram_id, session.hp)
    msg_id = session.message_id
    session.finished = True
    save_ncap_session(storage, session)
    clear_ncap_session(storage, session)
    _unregister_active(storage, session.session_id)
    payload = dict(result.payload or {})
    payload["message_id"] = msg_id
    payload["telegram_id"] = session.telegram_id
    return ActionResult(result.ok, result.text, payload=payload)


def start_neutral_capture(
    storage: Storage,
    telegram_id: int,
    location_name: str,
) -> tuple[ActionResult, NeutralCaptureSession | None]:
    from app.player_busy import player_busy_reason

    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return ActionResult(False, "Нужен персонаж с группировкой."), None
    if player.health <= 0:
        return ActionResult(False, "Ты мёртв."), None
    if get_ncap_session(storage, telegram_id):
        return ActionResult(False, "Уже идёт захват точки."), None
    busy = player_busy_reason(storage, telegram_id, skip="ncap")
    if busy:
        return ActionResult(False, busy), None
    loc = storage.get_location(location_name)
    if loc is None:
        return ActionResult(False, "Локация не найдена."), None
    if loc.get("controlled_by"):
        return ActionResult(False, "Точка уже под контролем."), None
    if not storage.spend_energy(telegram_id, NCAP_ENERGY_COST):
        return ActionResult(False, f"Нужно {NCAP_ENERGY_COST} энергии."), None

    session_id = uuid.uuid4().hex[:12]
    session = NeutralCaptureSession(
        session_id=session_id,
        telegram_id=telegram_id,
        location_name=location_name,
        faction=str(player.faction),
        turn_deadline=_deadline_iso(NCAP_TURN_SECONDS),
        match_deadline=_deadline_iso(NCAP_MATCH_SECONDS),
        hp=int(player.health),
    )
    _build_map(session)
    session.log.append(
        f"Захват «{location_name}»: {NCAP_HOSTILE_COUNT} врагов, стрельба как в танчиках. "
        f"Дойди до центра и удержи {NCAP_CAPTURE_TURNS} хода."
    )
    save_ncap_session(storage, session)
    _register_active(storage, session_id)
    text = (
        f"🎯 Захват нейтральной точки «{location_name}»!\n"
        f"Поле {NCAP_GRID_SIZE}×{NCAP_GRID_SIZE}, враги стреляют наугад.\n"
        f"Цель: центр карты ({NCAP_CAPTURE_TURNS} хода). Таймер {NCAP_MATCH_SECONDS // 60} мин."
    )
    return ActionResult(True, text, payload={"ncap_started": True}), session


def _check_capture(session: NeutralCaptureSession) -> bool:
    if session.player_pos == session.capture_point:
        session.capture_progress += 1
        session.log.append(f"Удержание точки: {session.capture_progress}/{NCAP_CAPTURE_TURNS}.")
        return session.capture_progress >= NCAP_CAPTURE_TURNS
    session.capture_progress = 0
    return False


def _check_player_dead(storage: Storage, session: NeutralCaptureSession) -> ActionResult | None:
    if session.hp <= 0:
        return _end_session(storage, session, _finalize_fail(storage, session, "Ты выведен из строя."))
    return None


def _check_end(storage: Storage, session: NeutralCaptureSession) -> ActionResult | None:
    dead = _check_player_dead(storage, session)
    if dead:
        return dead
    deadline = _parse_deadline(session.match_deadline)
    if deadline and _utc_now() > deadline:
        return _end_session(storage, session, _finalize_fail(storage, session, "Время вышло."))
    if not session.hostiles and _check_capture(session):
        return _end_session(storage, session, _finalize_success(storage, session))
    if _check_capture(session):
        return _end_session(storage, session, _finalize_success(storage, session))
    return None


def _advance(session: NeutralCaptureSession) -> None:
    session.turn_seq += 1
    session.turn_deadline = _deadline_iso(NCAP_TURN_SECONDS)


def _after_turn(storage: Storage, session: NeutralCaptureSession) -> ActionResult | None:
    session.log.extend(_hostile_shoot_turn(storage, session))
    return _check_end(storage, session)


def _save_turn(storage: Storage, session: NeutralCaptureSession, expected_seq: int) -> bool:
    raw = storage.get_meta(_session_key(session.session_id))
    if not raw:
        return False
    try:
        fresh = NeutralCaptureSession.from_dict(json.loads(raw))
    except Exception:
        return False
    if fresh.finished or fresh.turn_seq != expected_seq:
        return False
    save_ncap_session(storage, session)
    return True


def ncap_move(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_ncap_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного захвата.")
    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return ActionResult(False, "Некорректное направление.")
    turn_seq = session.turn_seq
    pos = session.player_pos
    nxt = (pos[0] + delta[0], pos[1] + delta[1])
    if not (0 <= nxt[0] < session.grid and 0 <= nxt[1] < session.grid):
        return ActionResult(False, "Край поля.")
    blocked = _occupied(session)
    blocked.discard(pos)
    if nxt in blocked and nxt not in session.cover:
        return ActionResult(False, "Клетка занята.")
    session.player_pos = nxt
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player and nxt in session.hostiles:
        idx = session.hostiles.index(nxt)
        kind = session.hostile_kinds[idx] if idx < len(session.hostile_kinds) else "bandit"
        session.hostiles.pop(idx)
        if idx < len(session.hostile_weapons):
            session.hostile_weapons.pop(idx)
        if idx < len(session.hostile_kinds):
            session.hostile_kinds.pop(idx)
        dmg = apply_incoming_damage(random.randint(6, 12), player, min_damage=2)
        session.hp = max(0, session.hp - dmg)
        label = "Бандит" if kind == "bandit" else "Мутант"
        session.log.append(f"{label} в ближнем бою: −{dmg} HP.")
    done = _check_player_dead(storage, session)
    if done:
        return done
    _advance(session)
    done = _after_turn(storage, session)
    if done:
        return done
    if not _save_turn(storage, session, turn_seq):
        return ActionResult(False, "Ход уже выполнен.")
    return ActionResult(True, "Шаг.", payload={"ncap_active": True})


def ncap_shoot(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_ncap_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного захвата.")
    if direction not in MOVE_DELTAS:
        return ActionResult(False, "Некорректный выстрел.")
    turn_seq = session.turn_seq
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Персонаж не найден.")
    weapon = str(player.equipment.get("weapon", "Нож"))
    rng = weapon_shoot_range(weapon)
    origin = session.player_pos
    cover_set = set(session.cover)
    targets = {pos: "host" for pos in session.hostiles}
    hit_cell, hit_kind = ray_cast_first_hit(
        origin, direction, grid=session.grid, max_range=rng, blockers=cover_set, targets=targets
    )
    note = "Промах."
    if hit_cell and hit_kind == "host":
        if cover_blocks_shot(hit_cell, cover_set):
            session.log.append("Враг за укрытием — промах.")
        else:
            idx = session.hostiles.index(hit_cell)
            session.hostiles.pop(idx)
            if idx < len(session.hostile_weapons):
                session.hostile_weapons.pop(idx)
            if idx < len(session.hostile_kinds):
                session.hostile_kinds.pop(idx)
            session.log.append(f"Попадание ({weapon})!")
            note = "Попал!"
    else:
        session.log.append("Промах.")
    done = _check_player_dead(storage, session)
    if done:
        return done
    _advance(session)
    done = _after_turn(storage, session)
    if done:
        return done
    if not _save_turn(storage, session, turn_seq):
        return ActionResult(False, "Ход уже выполнен.")
    return ActionResult(True, note, payload={"ncap_active": True})


def ncap_use_medkit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_ncap_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного захвата.")
    if session.medkit_used:
        return ActionResult(False, "Аптечку уже использовал.")
    turn_seq = session.turn_seq
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Персонаж не найден.")
    result, new_hp = use_tactical_medkit(storage, telegram_id, session.hp)
    if not result.ok:
        return result
    session.hp = new_hp
    session.medkit_used = True
    session.log.append("Аптечка.")
    _advance(session)
    done = _after_turn(storage, session)
    if done:
        return done
    if not _save_turn(storage, session, turn_seq):
        return ActionResult(False, "Ход уже выполнен.")
    return ActionResult(True, result.text, payload={"ncap_active": True})


def ncap_forfeit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_ncap_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного захвата.")
    return _end_session(storage, session, _finalize_fail(storage, session, "Отступление."))


def process_ncap_turn_timeouts(storage: Storage) -> list[tuple[int, ActionResult]]:
    outcomes: list[tuple[int, ActionResult]] = []
    now = _utc_now()
    raw = storage.get_meta(ACTIVE_IDS_KEY)
    if not raw:
        return outcomes
    try:
        sids = json.loads(raw)
    except json.JSONDecodeError:
        return outcomes
    if not isinstance(sids, list):
        return outcomes
    still: list[str] = []
    for sid in sids:
        raw_s = storage.get_meta(_session_key(str(sid)))
        if not raw_s:
            continue
        try:
            session = NeutralCaptureSession.from_dict(json.loads(raw_s))
        except Exception:
            continue
        if session.finished:
            continue
        match_deadline = _parse_deadline(session.match_deadline)
        if match_deadline and now > match_deadline:
            done = _end_session(storage, session, _finalize_fail(storage, session, "Время вышло."))
            outcomes.append((session.telegram_id, done))
            continue
        deadline = _parse_deadline(session.turn_deadline)
        if deadline is None or now <= deadline:
            still.append(str(sid))
            continue
        turn_seq = session.turn_seq
        session.log.append("Тайм-аут хода.")
        _advance(session)
        done = _after_turn(storage, session)
        if done:
            outcomes.append((session.telegram_id, done))
            continue
        still.append(str(sid))
        if _save_turn(storage, session, turn_seq):
            outcomes.append((session.telegram_id, ActionResult(True, "Ход пропущен.", payload={"ncap_active": True})))
    storage.set_meta(ACTIVE_IDS_KEY, json.dumps(still, ensure_ascii=False))
    return outcomes


def ncap_status_caption(session: NeutralCaptureSession, player: Character | None) -> str:
    lines = [f"🎯 Захват «{session.location_name}»"]
    deadline = _parse_deadline(session.match_deadline)
    if deadline:
        secs = max(0, int((deadline - _utc_now()).total_seconds()))
        lines.append(f"⏱ {secs // 60}:{secs % 60:02d}")
    lines.append(f"Врагов: {len(session.hostiles)} · захват {session.capture_progress}/{NCAP_CAPTURE_TURNS}")
    if player:
        weapon = str(player.equipment.get("weapon", "Нож"))
        lines.append(f"HP {session.hp} · дальность {weapon_shoot_range(weapon)}")
    if session.log:
        lines.append(session.log[-1][:80])
    return "\n".join(lines)


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_ncap_frame(storage: Storage, session: NeutralCaptureSession) -> bytes:
    cell = 72
    grid = session.grid
    grid_px = grid * cell
    margin = 20
    panel_w = 260
    width = margin + grid_px + 16 + panel_w + margin
    height = max(margin + grid_px + margin, 520)
    canvas = Image.new("RGBA", (width, height), (18, 20, 22, 255))
    draw = ImageDraw.Draw(canvas)
    cp = session.capture_point
    for gy in range(grid):
        for gx in range(grid):
            left = margin + gx * cell
            top = margin + gy * cell
            tone = 62 + ((gx * 17 + gy * 23) % 18)
            draw.rectangle((left, top, left + cell - 1, top + cell - 1), fill=(tone, tone - 4, tone - 8))
            draw.rectangle((left, top, left + cell - 1, top + cell - 1), outline=(28, 30, 34), width=1)
    draw.rectangle(
        (margin + cp[0] * cell + 6, margin + cp[1] * cell + 6, margin + (cp[0] + 1) * cell - 6, margin + (cp[1] + 1) * cell - 6),
        outline=(255, 200, 50),
        width=3,
    )
    for cx, cy in session.cover:
        left = margin + cx * cell + 6
        top = margin + cy * cell + 6
        draw.rounded_rectangle((left, top, left + cell - 12, top + cell - 12), radius=8, fill=(70, 62, 48, 220), outline=(110, 95, 70))
    for i, (hx, hy) in enumerate(session.hostiles):
        cx = margin + hx * cell + cell // 2
        cy = margin + hy * cell + cell // 2
        kind = session.hostile_kinds[i] if i < len(session.hostile_kinds) else "bandit"
        if kind == "mutant":
            draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(60, 90, 45), outline=(130, 200, 80), width=2)
        else:
            draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(120, 50, 50), outline=(200, 80, 80), width=2)
    px, py = session.player_pos
    pcx = margin + px * cell + cell // 2
    pcy = margin + py * cell + cell // 2
    draw.rectangle(
        (margin + px * cell, margin + py * cell, margin + (px + 1) * cell - 1, margin + (py + 1) * cell - 1),
        outline=(80, 230, 255),
        width=3,
    )
    token = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    td = ImageDraw.Draw(token)
    td.ellipse((4, 4, 60, 60), fill=(40, 100, 120))
    _paste_circle(canvas, token, pcx, pcy, 52, ring_color=(80, 200, 255), ring_width=3)
    pl = margin + grid_px + 16
    draw.rounded_rectangle((pl, margin, width - margin, height - margin), radius=14, fill=(44, 46, 50), outline=(90, 94, 100), width=2)
    small = _load_font(13)
    y = margin + 16
    player = storage.get_character(session.telegram_id, refresh_energy=False)
    for line in ncap_status_caption(session, player).split("\n"):
        draw.text((pl + 14, y), line[:40], fill=(200, 200, 200), font=small)
        y += 18
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
