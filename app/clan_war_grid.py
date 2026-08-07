"""Тактический штурм точки в КВ: поле 9×9, база защиты, таймер 10 мин."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from app.game_logic import (
    RATING_REWARD,
    WAR_SUCCESS_PAY_RU,
    ActionResult,
    _add_rating,
    apply_incoming_damage,
    h,
)
from app.npc_assets import NPC_SPRITE_KEYS, pick_npc_kind
from app.storage import Character, Storage
from app.tactical_render import load_tactical_font, paste_npc_sprite, paste_player_avatar
from app.tactical_combat import (
    BASE_COVER_ARMOR_BONUS,
    MOVE_DELTAS,
    NPC_WEAPONS,
    cover_blocks_shot,
    random_hostile_shots,
    ray_cast_first_hit,
    weapon_shoot_range,
)
from app.tactical_hp import sync_session_hp_to_db, use_tactical_medkit

CWAR_GRID_SIZE = 9
CWAR_TURN_SECONDS = 10
CWAR_MATCH_SECONDS = 10 * 60
CWAR_DEFENDER_COUNT = 6
CWAR_CAPTURE_TURNS = 3
CWAR_ENERGY_COST = 24

SESSION_PREFIX = "cwar:session:"
PLAYER_PREFIX = "cwar:player:"
ACTIVE_IDS_KEY = "cwar:active_ids"

PLAYER_COLORS = [
    (80, 200, 255),
    (255, 180, 70),
    (120, 255, 140),
    (255, 120, 200),
    (180, 140, 255),
]


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
class ClanWarGridSession:
    session_id: str
    war_id: int
    location_name: str
    host_faction: str
    player_ids: list[int]
    grid: int = CWAR_GRID_SIZE
    cover: list[tuple[int, int]] = field(default_factory=list)
    base_cover: list[tuple[int, int]] = field(default_factory=list)
    defenders: list[tuple[int, int]] = field(default_factory=list)
    defender_weapons: list[str] = field(default_factory=list)
    defender_kinds: list[str] = field(default_factory=list)
    control_point: tuple[int, int] = (4, 4)
    positions: dict[str, list[int]] = field(default_factory=dict)
    hp: dict[str, int] = field(default_factory=dict)
    medkits_used: dict[str, bool] = field(default_factory=dict)
    turn_order: list[int] = field(default_factory=list)
    active_index: int = 0
    turn_seq: int = 0
    turn_deadline: str | None = None
    match_deadline: str | None = None
    capture_progress: int = 0
    finished: bool = False
    success: bool = False
    log: list[str] = field(default_factory=list)
    message_ids: dict[str, int] = field(default_factory=dict)

    def active_player(self) -> int:
        if not self.turn_order:
            return 0
        for _ in range(len(self.turn_order)):
            pid = self.turn_order[self.active_index % len(self.turn_order)]
            if self.hp.get(str(pid), 0) > 0:
                return pid
            self.active_index += 1
        return self.turn_order[0]

    def pos(self, player_id: int) -> tuple[int, int]:
        raw = self.positions.get(str(player_id), [0, 0])
        return int(raw[0]), int(raw[1])

    def set_pos(self, player_id: int, pos: tuple[int, int]) -> None:
        self.positions[str(player_id)] = [pos[0], pos[1]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "war_id": self.war_id,
            "location_name": self.location_name,
            "host_faction": self.host_faction,
            "player_ids": self.player_ids,
            "grid": self.grid,
            "cover": [list(p) for p in self.cover],
            "base_cover": [list(p) for p in self.base_cover],
            "defenders": [list(p) for p in self.defenders],
            "defender_weapons": self.defender_weapons,
            "defender_kinds": self.defender_kinds,
            "control_point": list(self.control_point),
            "positions": self.positions,
            "hp": self.hp,
            "medkits_used": self.medkits_used,
            "turn_order": self.turn_order,
            "active_index": self.active_index,
            "turn_seq": self.turn_seq,
            "turn_deadline": self.turn_deadline,
            "match_deadline": self.match_deadline,
            "capture_progress": self.capture_progress,
            "finished": self.finished,
            "success": self.success,
            "log": self.log[-14:],
            "message_ids": {str(k): int(v) for k, v in self.message_ids.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ClanWarGridSession:
        cp = raw.get("control_point") or [4, 4]
        return cls(
            session_id=str(raw.get("session_id") or ""),
            war_id=int(raw.get("war_id") or 0),
            location_name=str(raw.get("location_name") or ""),
            host_faction=str(raw.get("host_faction") or ""),
            player_ids=[int(x) for x in (raw.get("player_ids") or [])],
            grid=int(raw.get("grid") or CWAR_GRID_SIZE),
            cover=[(int(p[0]), int(p[1])) for p in (raw.get("cover") or [])],
            base_cover=[(int(p[0]), int(p[1])) for p in (raw.get("base_cover") or [])],
            defenders=[(int(p[0]), int(p[1])) for p in (raw.get("defenders") or [])],
            defender_weapons=[str(w) for w in (raw.get("defender_weapons") or [])],
            defender_kinds=[str(k) for k in (raw.get("defender_kinds") or [])],
            control_point=(int(cp[0]), int(cp[1])),
            positions={str(k): list(v) for k, v in (raw.get("positions") or {}).items()},
            hp={str(k): int(v) for k, v in (raw.get("hp") or {}).items()},
            medkits_used={str(k): bool(v) for k, v in (raw.get("medkits_used") or {}).items()},
            turn_order=[int(x) for x in (raw.get("turn_order") or [])],
            active_index=int(raw.get("active_index") or 0),
            turn_seq=int(raw.get("turn_seq") or 0),
            turn_deadline=raw.get("turn_deadline"),
            match_deadline=raw.get("match_deadline"),
            capture_progress=int(raw.get("capture_progress") or 0),
            finished=bool(raw.get("finished")),
            success=bool(raw.get("success")),
            log=[str(x) for x in (raw.get("log") or [])],
            message_ids={str(k): int(v) for k, v in (raw.get("message_ids") or {}).items()},
        )


def _session_key(sid: str) -> str:
    return f"{SESSION_PREFIX}{sid}"


def _player_key(tid: int) -> str:
    return f"{PLAYER_PREFIX}{int(tid)}"


def _ensure_defender_kinds(session: ClanWarGridSession) -> None:
    while len(session.defender_kinds) < len(session.defenders):
        session.defender_kinds.append(pick_npc_kind())
    if len(session.defender_kinds) > len(session.defenders):
        session.defender_kinds = session.defender_kinds[: len(session.defenders)]


def get_cwar_session_by_player(storage: Storage, telegram_id: int) -> ClanWarGridSession | None:
    sid = storage.get_meta(_player_key(telegram_id))
    if not sid:
        return None
    raw = storage.get_meta(_session_key(sid))
    if not raw:
        storage.delete_meta(_player_key(telegram_id))
        return None
    try:
        session = ClanWarGridSession.from_dict(json.loads(raw))
    except Exception:
        storage.delete_meta(_player_key(telegram_id))
        return None
    if session.finished:
        return None
    _ensure_defender_kinds(session)
    return session


def save_cwar_session(storage: Storage, session: ClanWarGridSession) -> None:
    storage.set_meta(_session_key(session.session_id), json.dumps(session.to_dict(), ensure_ascii=False))
    for pid in session.player_ids:
        storage.set_meta(_player_key(pid), session.session_id)


def clear_cwar_session(storage: Storage, session: ClanWarGridSession) -> None:
    storage.delete_meta(_session_key(session.session_id))
    for pid in session.player_ids:
        storage.delete_meta(_player_key(pid))
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


def _build_map(session: ClanWarGridSession) -> None:
    grid = session.grid
    forbidden: set[tuple[int, int]] = {session.control_point}
    # База защиты — правый край (+5 брони).
    for y in range(grid):
        for x in range(grid - 3, grid):
            session.base_cover.append((x, y))
    for y in range(1, grid - 1):
        for x in range(grid - 2, grid):
            cell = (x, y)
            if cell != session.control_point and random.random() < 0.45:
                session.cover.append(cell)
                forbidden.add(cell)
    for _ in range(random.randint(10, 14)):
        cell = _free_cell(grid, forbidden)
        session.cover.append(cell)
        forbidden.add(cell)
    for _ in range(CWAR_DEFENDER_COUNT):
        cell = _free_cell(grid, forbidden | set(session.base_cover))
        session.defenders.append(cell)
        session.defender_weapons.append(random.choice(NPC_WEAPONS))
        session.defender_kinds.append(pick_npc_kind())
        forbidden.add(cell)
    spawn_cols = list(range(0, 3))
    for pid in session.player_ids:
        placed = False
        for _ in range(40):
            cell = (random.choice(spawn_cols), random.randint(0, grid - 1))
            if cell not in forbidden:
                session.set_pos(pid, cell)
                forbidden.add(cell)
                placed = True
                break
        if not placed:
            cell = _free_cell(grid, forbidden)
            session.set_pos(pid, cell)
            forbidden.add(cell)


def _occupied(session: ClanWarGridSession, *, exclude: int | None = None) -> set[tuple[int, int]]:
    blocked = set(session.cover) | set(session.base_cover) | set(session.defenders)
    for pid in session.player_ids:
        if exclude is not None and pid == exclude:
            continue
        blocked.add(session.pos(pid))
    return blocked


def _defender_damage(weapon: str) -> int:
    return max(4, weapon_shoot_range(weapon) * 3 + random.randint(0, 4))


def _hostile_turn(storage: Storage, session: ClanWarGridSession) -> list[str]:
    cover_set = set(session.cover)
    base_set = set(session.base_cover)
    alive_ids = [pid for pid in session.player_ids if session.hp.get(str(pid), 0) > 0]
    player_pos = {pid: session.pos(pid) for pid in alive_ids}
    player_chars = {pid: storage.get_character(pid, refresh_energy=False) for pid in alive_ids}
    return random_hostile_shots(
        session.defenders,
        session.defender_weapons,
        grid=session.grid,
        player_positions=player_pos,
        player_hp=session.hp,
        player_characters=player_chars,
        cover=cover_set,
        base_cover=base_set,
        damage_fn=_defender_damage,
    )


def _check_capture(session: ClanWarGridSession) -> bool:
    alive_on_point = [
        pid
        for pid in session.player_ids
        if session.hp.get(str(pid), 0) > 0 and session.pos(pid) == session.control_point
    ]
    if alive_on_point:
        session.capture_progress += 1
        session.log.append(f"Захват точки: {session.capture_progress}/{CWAR_CAPTURE_TURNS}.")
        return session.capture_progress >= CWAR_CAPTURE_TURNS
    session.capture_progress = 0
    return False


def _finalize_success(storage: Storage, session: ClanWarGridSession) -> ActionResult:
    storage.set_location_control(session.location_name, session.host_faction)
    storage.finish_war_lobby(session.war_id, "success", f"Тактическая победа: {session.host_faction}")
    notes: list[str] = []
    for pid in session.player_ids:
        ch = storage.get_character(pid, refresh_energy=False)
        if ch is None or str(ch.faction) != session.host_faction:
            continue
        storage.add_player_stat(pid, "wars_won", 1)
        storage.change_money(pid, WAR_SUCCESS_PAY_RU)
        storage.add_player_stat(pid, "money_earned", WAR_SUCCESS_PAY_RU)
        _add_rating(storage, pid, RATING_REWARD["war_success"])
    text = (
        f"🏆 Тактический штурм «{session.location_name}» успешен!\n"
        f"Точка перешла под контроль {session.host_faction}.\n"
        f"Награда: +{WAR_SUCCESS_PAY_RU} RU, +{RATING_REWARD['war_success']} рейтинга."
    )
    return ActionResult(True, text, payload={"cwar_done": True, "success": True, "member_ids": session.player_ids})


def _finalize_fail(storage: Storage, session: ClanWarGridSession, reason: str) -> ActionResult:
    storage.finish_war_lobby(session.war_id, "failed", reason)
    for pid in session.player_ids:
        _add_rating(storage, pid, -RATING_REWARD["war_fail"])
    text = f"💀 Штурм «{session.location_name}» провален.\n{reason}\n−{RATING_REWARD['war_fail']} рейтинга."
    return ActionResult(False, text, payload={"cwar_done": True, "success": False, "member_ids": session.player_ids})


def _end_session(storage: Storage, session: ClanWarGridSession, result: ActionResult) -> ActionResult:
    for pid in session.player_ids:
        hp_val = session.hp.get(str(pid))
        if hp_val is not None:
            sync_session_hp_to_db(storage, pid, int(hp_val))
    message_ids = dict(session.message_ids)
    session.finished = True
    save_cwar_session(storage, session)
    clear_cwar_session(storage, session)
    _unregister_active(storage, session.session_id)
    payload = dict(result.payload or {})
    payload["message_ids"] = message_ids
    payload["session_id"] = session.session_id
    return ActionResult(result.ok, result.text, payload=payload)


def start_clan_war_grid(
    storage: Storage,
    *,
    war_id: int,
    location_name: str,
    host_faction: str,
    player_ids: list[int],
) -> tuple[ActionResult, ClanWarGridSession | None]:
    from app.player_busy import player_busy_reason

    members: list[Character] = []
    for pid in player_ids:
        if get_cwar_session_by_player(storage, pid):
            ch = storage.get_character(pid, refresh_energy=False)
            name = h(ch.nickname) if ch else str(pid)
            return ActionResult(False, f"{name} уже в тактическом штурме."), None
        ch = storage.get_character(pid, refresh_energy=False)
        if ch is None or ch.health <= 0:
            return ActionResult(False, "Не все бойцы доступны."), None
        busy = player_busy_reason(storage, pid)
        if busy:
            return ActionResult(False, f"{h(ch.nickname)}: {busy}"), None
        members.append(ch)

    session_id = uuid.uuid4().hex[:12]
    session = ClanWarGridSession(
        session_id=session_id,
        war_id=war_id,
        location_name=location_name,
        host_faction=host_faction,
        player_ids=list(player_ids),
        turn_order=list(player_ids),
        turn_deadline=_deadline_iso(CWAR_TURN_SECONDS),
        match_deadline=_deadline_iso(CWAR_MATCH_SECONDS),
    )
    _build_map(session)
    for ch in members:
        session.hp[str(ch.telegram_id)] = int(ch.health)
        session.medkits_used[str(ch.telegram_id)] = False
    session.log.append(
        f"Штурм «{location_name}»: поле {CWAR_GRID_SIZE}×{CWAR_GRID_SIZE}, "
        f"база справа (+{BASE_COVER_ARMOR_BONUS} брони). Таймер {CWAR_MATCH_SECONDS // 60} мин."
    )
    save_cwar_session(storage, session)
    _register_active(storage, session_id)
    text = (
        f"⚔️ Тактический штурм «{location_name}»!\n"
        f"Бойцов: {len(player_ids)}. Захвати центр ({CWAR_CAPTURE_TURNS} хода на точке).\n"
        f"Укрытия базы справа дают +{BASE_COVER_ARMOR_BONUS} брони защитникам.\n"
        f"Таймер: {CWAR_MATCH_SECONDS // 60} мин."
    )
    return ActionResult(True, text, payload={"cwar_started": True, "session_id": session_id}), session


def _check_squad_wiped(storage: Storage, session: ClanWarGridSession) -> ActionResult | None:
    alive = [pid for pid in session.player_ids if session.hp.get(str(pid), 0) > 0]
    if not alive:
        return _end_session(storage, session, _finalize_fail(storage, session, "Все бойцы выведены из строя."))
    return None


def _check_end(storage: Storage, session: ClanWarGridSession) -> ActionResult | None:
    wiped = _check_squad_wiped(storage, session)
    if wiped:
        return wiped
    deadline = _parse_deadline(session.match_deadline)
    if deadline and _utc_now() > deadline:
        return _end_session(storage, session, _finalize_fail(storage, session, "Время штурма истекло."))
    if not session.defenders and _check_capture(session):
        return _end_session(storage, session, _finalize_success(storage, session))
    if _check_capture(session):
        return _end_session(storage, session, _finalize_success(storage, session))
    return None


def _save_turn(storage: Storage, session: ClanWarGridSession, expected_seq: int) -> bool:
    raw = storage.get_meta(_session_key(session.session_id))
    if not raw:
        return False
    try:
        fresh = ClanWarGridSession.from_dict(json.loads(raw))
    except Exception:
        return False
    if fresh.finished or fresh.turn_seq != expected_seq:
        return False
    save_cwar_session(storage, session)
    return True


def _advance(session: ClanWarGridSession) -> None:
    if not session.turn_order:
        return
    session.active_index = (session.active_index + 1) % len(session.turn_order)
    for _ in range(len(session.turn_order)):
        pid = session.turn_order[session.active_index % len(session.turn_order)]
        if session.hp.get(str(pid), 0) > 0:
            break
        session.active_index = (session.active_index + 1) % len(session.turn_order)
    session.turn_seq += 1
    session.turn_deadline = _deadline_iso(CWAR_TURN_SECONDS)


def _after_player_turn(storage: Storage, session: ClanWarGridSession) -> ActionResult | None:
    session.log.extend(_hostile_turn(storage, session))
    return _check_end(storage, session)


def cwar_move(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_cwar_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного тактического штурма.")
    if session.active_player() != telegram_id:
        return ActionResult(False, "Сейчас ход другого бойца.")
    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return ActionResult(False, "Некорректное направление.")
    turn_seq = session.turn_seq
    pos = session.pos(telegram_id)
    nxt = (pos[0] + delta[0], pos[1] + delta[1])
    if not (0 <= nxt[0] < session.grid and 0 <= nxt[1] < session.grid):
        return ActionResult(False, "Край поля.")
    blocked = _occupied(session, exclude=telegram_id)
    if nxt in blocked and nxt not in session.cover and nxt not in session.base_cover:
        return ActionResult(False, "Клетка занята.")
    session.set_pos(telegram_id, nxt)
    ch = storage.get_character(telegram_id, refresh_energy=False)
    if ch and nxt in session.defenders:
        idx = session.defenders.index(nxt)
        session.defenders.pop(idx)
        if idx < len(session.defender_weapons):
            session.defender_weapons.pop(idx)
        if idx < len(session.defender_kinds):
            session.defender_kinds.pop(idx)
        dmg = apply_incoming_damage(random.randint(8, 14), ch, min_damage=3)
        session.hp[str(telegram_id)] = max(0, session.hp.get(str(telegram_id), 0) - dmg)
        session.log.append(f"{h(ch.nickname)} схватился с защитником: −{dmg} HP.")
    done = _check_squad_wiped(storage, session)
    if done:
        return done
    _advance(session)
    done = _after_player_turn(storage, session)
    if done:
        return done
    if not _save_turn(storage, session, turn_seq):
        return ActionResult(False, "Ход уже выполнен.")
    return ActionResult(True, "Шаг.", payload={"cwar_active": True})


def cwar_shoot(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_cwar_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного тактического штурма.")
    if session.active_player() != telegram_id:
        return ActionResult(False, "Сейчас ход другого бойца.")
    if direction not in MOVE_DELTAS:
        return ActionResult(False, "Некорректный выстрел.")
    turn_seq = session.turn_seq
    attacker = storage.get_character(telegram_id, refresh_energy=False)
    if attacker is None:
        return ActionResult(False, "Персонаж не найден.")
    weapon = str(attacker.equipment.get("weapon", "Нож"))
    rng = weapon_shoot_range(weapon)
    origin = session.pos(telegram_id)
    cover_set = set(session.cover) | set(session.base_cover)
    targets = {pos: "def" for pos in session.defenders}
    hit_cell, hit_kind = ray_cast_first_hit(
        origin, direction, grid=session.grid, max_range=rng, blockers=set(session.cover), targets=targets
    )
    note = "Промах."
    if hit_cell and hit_kind == "def":
        if cover_blocks_shot(hit_cell, cover_set):
            session.log.append("Защитник за укрытием — промах.")
        else:
            if hit_cell in session.defenders:
                idx = session.defenders.index(hit_cell)
                session.defenders.pop(idx)
                if idx < len(session.defender_weapons):
                    session.defender_weapons.pop(idx)
                if idx < len(session.defender_kinds):
                    session.defender_kinds.pop(idx)
                session.log.append(f"{h(attacker.nickname)} снял защитника ({weapon}).")
                note = "Попадание!"
    else:
        session.log.append(f"{h(attacker.nickname)} промахнулся.")
    done = _check_squad_wiped(storage, session)
    if done:
        return done
    _advance(session)
    done = _after_player_turn(storage, session)
    if done:
        return done
    if not _save_turn(storage, session, turn_seq):
        return ActionResult(False, "Ход уже выполнен.")
    return ActionResult(True, note, payload={"cwar_active": True})


def cwar_use_medkit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_cwar_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного тактического штурма.")
    if session.active_player() != telegram_id:
        return ActionResult(False, "Сейчас ход другого бойца.")
    if session.medkits_used.get(str(telegram_id)):
        return ActionResult(False, "Аптечку уже использовал.")
    turn_seq = session.turn_seq
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Персонаж не найден.")
    current_hp = session.hp.get(str(telegram_id), int(player.health))
    result, new_hp = use_tactical_medkit(storage, telegram_id, int(current_hp))
    if not result.ok:
        return result
    session.hp[str(telegram_id)] = new_hp
    session.medkits_used[str(telegram_id)] = True
    session.log.append(f"{h(player.nickname)} использовал аптечку.")
    _advance(session)
    done = _after_player_turn(storage, session)
    if done:
        return done
    if not _save_turn(storage, session, turn_seq):
        return ActionResult(False, "Ход уже выполнен.")
    return ActionResult(True, result.text, payload={"cwar_active": True})


def process_cwar_turn_timeouts(storage: Storage) -> list[tuple[int, ActionResult]]:
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
            session = ClanWarGridSession.from_dict(json.loads(raw_s))
        except Exception:
            continue
        if session.finished:
            continue
        match_deadline = _parse_deadline(session.match_deadline)
        if match_deadline and now > match_deadline:
            done = _end_session(storage, session, _finalize_fail(storage, session, "Время штурма истекло."))
            outcomes.append((session.player_ids[0], done))
            continue
        deadline = _parse_deadline(session.turn_deadline)
        if deadline is None or now <= deadline:
            still.append(str(sid))
            continue
        active = session.active_player()
        turn_seq = session.turn_seq
        session.log.append("Тайм-аут хода.")
        _advance(session)
        done = _after_player_turn(storage, session)
        if done:
            outcomes.append((active, done))
            continue
        still.append(str(sid))
        if _save_turn(storage, session, turn_seq):
            outcomes.append((active, ActionResult(True, "Ход пропущен.", payload={"cwar_active": True})))
    storage.set_meta(ACTIVE_IDS_KEY, json.dumps(still, ensure_ascii=False))
    return outcomes


def cwar_status_caption(storage: Storage, session: ClanWarGridSession, viewer_id: int) -> str:
    active = storage.get_character(session.active_player(), refresh_energy=False)
    active_name = h(active.nickname) if active else str(session.active_player())
    lines = [f"⚔️ Штурм «{session.location_name}» · ход {active_name}"]
    deadline = _parse_deadline(session.match_deadline)
    if deadline:
        secs = max(0, int((deadline - _utc_now()).total_seconds()))
        lines.append(f"⏱ Осталось: {secs // 60}:{secs % 60:02d}")
    lines.append(f"🎯 Захват: {session.capture_progress}/{CWAR_CAPTURE_TURNS} · защитников {len(session.defenders)}")
    for pid in session.player_ids:
        ch = storage.get_character(pid, refresh_energy=False)
        name = h(ch.nickname) if ch else str(pid)
        hp = session.hp.get(str(pid), 0)
        mark = " ◀" if pid == session.active_player() else ""
        if pid == viewer_id:
            mark += " (ты)"
        lines.append(f"{name}{mark}: HP {hp}")
    if session.log:
        lines.append(session.log[-1][:80])
    return "\n".join(lines)


def render_cwar_frame(storage: Storage, session: ClanWarGridSession, viewer_id: int) -> bytes:
    _ensure_defender_kinds(session)
    cell = 64
    grid = session.grid
    grid_px = grid * cell
    margin = 16
    panel_w = 280
    width = margin + grid_px + 12 + panel_w + margin
    height = max(margin + grid_px + margin, 620)
    canvas = Image.new("RGBA", (width, height), (18, 20, 22, 255))
    draw = ImageDraw.Draw(canvas)
    cp = session.control_point
    for gy in range(grid):
        for gx in range(grid):
            left = margin + gx * cell
            top = margin + gy * cell
            tone = 62 + ((gx * 13 + gy * 19) % 16)
            fill = (tone, tone - 4, tone - 8)
            if (gx, gy) in session.base_cover:
                fill = (tone - 8, tone - 12, tone - 6)
            draw.rectangle((left, top, left + cell - 1, top + cell - 1), fill=fill)
            draw.rectangle((left, top, left + cell - 1, top + cell - 1), outline=(28, 30, 34), width=1)
    cx, cy = cp
    draw.rectangle(
        (margin + cx * cell + 4, margin + cy * cell + 4, margin + (cx + 1) * cell - 4, margin + (cy + 1) * cell - 4),
        outline=(255, 220, 60),
        width=3,
    )
    for bx, by in session.cover:
        left = margin + bx * cell + 4
        top = margin + by * cell + 4
        draw.rounded_rectangle((left, top, left + cell - 8, top + cell - 8), radius=6, fill=(70, 62, 48, 200), outline=(100, 90, 70))
    for bx, by in session.base_cover:
        if (bx, by) in session.cover:
            continue
        left = margin + bx * cell + 2
        top = margin + by * cell + 2
        draw.rectangle((left, top, left + cell - 4, top + cell - 4), outline=(80, 100, 140), width=1)
    for i, (dx, dy) in enumerate(session.defenders):
        cxp = margin + dx * cell + cell // 2
        cyp = margin + dy * cell + cell // 2
        kind = session.defender_kinds[i] if i < len(session.defender_kinds) else NPC_SPRITE_KEYS[i % len(NPC_SPRITE_KEYS)]
        paste_npc_sprite(canvas, draw, cx=cxp, cy=cyp, kind=kind, diameter=52)
    for i, pid in enumerate(session.player_ids):
        px, py = session.pos(pid)
        cxp = margin + px * cell + cell // 2
        cyp = margin + py * cell + cell // 2
        ring = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        viewer_cell = (margin, cell, px, py) if pid == viewer_id else None
        paste_player_avatar(
            canvas,
            draw,
            storage,
            pid=pid,
            cx=cxp,
            cy=cyp,
            diameter=46,
            ring_color=ring,
            hp=session.hp.get(str(pid), 0),
            is_active=pid == session.active_player(),
            viewer_cell=viewer_cell,
        )
    pl = margin + grid_px + 12
    draw.rounded_rectangle((pl, margin, width - margin, height - margin), radius=12, fill=(44, 46, 50), outline=(90, 94, 100), width=2)
    small = load_tactical_font(12)
    y = margin + 12
    draw.text((pl + 10, y), f"Штурм {session.location_name[:18]}", fill=(240, 240, 240), font=small)
    y += 22
    deadline = _parse_deadline(session.match_deadline)
    if deadline:
        secs = max(0, int((deadline - _utc_now()).total_seconds()))
        draw.text((pl + 10, y), f"Осталось: {secs // 60}:{secs % 60:02d}", fill=(200, 200, 120), font=small)
        y += 15
    draw.text((pl + 10, y), f"Захват: {session.capture_progress}/{CWAR_CAPTURE_TURNS}", fill=(180, 180, 180), font=small)
    y += 15
    draw.text((pl + 10, y), f"Защитников: {len(session.defenders)}", fill=(180, 180, 180), font=small)
    y += 15
    for pid in session.player_ids[:5]:
        ch = storage.get_character(pid, refresh_energy=False)
        name = (ch.nickname if ch else str(pid))[:24]
        hp = session.hp.get(str(pid), 0)
        mark = " <" if pid == session.active_player() else ""
        if pid == viewer_id:
            mark += " (ты)"
        draw.text((pl + 10, y), f"{name}{mark}: HP {hp}"[:38], fill=(180, 180, 180), font=small)
        y += 15
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
