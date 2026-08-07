"""Тактический рейд на логово / склад / гараж: поле 9×9, 2–5 игроков, 6–10 врагов."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from app.faction_bots import FACTION_BOT_DEFAULT_COUNT, get_faction_bots, pick_bot_weapon
from app.game_logic import (
    ActionResult,
    DEPOT_RAID_FAIL_MONEY_PENALTY,
    DEPOT_RAID_LABELS,
    RATING_REWARD,
    RAID_ARTIFACT_DROP_CHANCE,
    RAID_ARTIFACT_MIN_ENEMY_POWER,
    _add_rating,
    _apply_durability_decay,
    _maybe_drop_stash,
    _progress_and_unlock_achievements,
    _steal_faction_garage,
    _steal_faction_warehouse,
    apply_incoming_damage,
    h,
    pick_weighted_raid_artifact_key,
)
from app.mutant_assets import pick_mutant_kind
from app.npc_assets import pick_npc_kind
from app.storage import Character, Storage
from app.tactical_combat import (
    BASE_COVER_ARMOR_BONUS,
    MOVE_DELTAS,
    cover_blocks_shot,
    random_hostile_shots,
    ray_cast_first_hit,
    weapon_shoot_range,
)
from app.tactical_hp import sync_session_hp_to_db, use_tactical_medkit
from app.tactical_render import (
    load_tactical_font,
    paste_mutant_sprite,
    paste_npc_sprite,
    paste_player_avatar,
)

RAID_GRID_SIZE = 9
RAID_MIN_MEMBERS = 2
RAID_MAX_MEMBERS = 5
RAID_HOSTILE_MIN = 6
RAID_HOSTILE_MAX = 10
RAID_TURN_SECONDS = 12
RAID_MATCH_SECONDS = 15 * 60
RAID_CAPTURE_TURNS = 3
RAID_LOOT_TURNS = 2

SESSION_PREFIX = "rgrid:session:"
PLAYER_PREFIX = "rgrid:player:"
ACTIVE_IDS_KEY = "rgrid:active_ids"

PLAYER_COLORS = [
    (80, 200, 255),
    (255, 180, 70),
    (120, 255, 140),
    (255, 120, 200),
    (180, 140, 255),
]

LOOT_ZONE_LABELS = {"warehouse": "СКЛ", "garage": "ГЖ", "lair": "ЦЕЛЬ"}


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
class RaidGridSession:
    session_id: str
    raid_id: int
    raid_kind: str
    location_label: str
    attacker_faction: str
    player_ids: list[int]
    target_faction: str | None = None
    enemy_power: int = 0
    energy_cost: int = 18
    grid: int = RAID_GRID_SIZE
    cover: list[tuple[int, int]] = field(default_factory=list)
    base_cover: list[tuple[int, int]] = field(default_factory=list)
    hostiles: list[tuple[int, int]] = field(default_factory=list)
    hostile_types: list[str] = field(default_factory=list)
    hostile_kinds: list[str] = field(default_factory=list)
    hostile_weapons: list[str] = field(default_factory=list)
    control_point: tuple[int, int] = (4, 4)
    loot_zone: tuple[int, int] | None = None
    loot_zone_kind: str = "lair"
    positions: dict[str, list[int]] = field(default_factory=dict)
    hp: dict[str, int] = field(default_factory=dict)
    medkits_used: dict[str, bool] = field(default_factory=dict)
    turn_order: list[int] = field(default_factory=list)
    active_index: int = 0
    turn_seq: int = 0
    turn_deadline: str | None = None
    match_deadline: str | None = None
    capture_progress: int = 0
    loot_progress: int = 0
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
            "raid_id": self.raid_id,
            "raid_kind": self.raid_kind,
            "location_label": self.location_label,
            "attacker_faction": self.attacker_faction,
            "target_faction": self.target_faction,
            "enemy_power": self.enemy_power,
            "energy_cost": self.energy_cost,
            "grid": self.grid,
            "cover": [list(p) for p in self.cover],
            "base_cover": [list(p) for p in self.base_cover],
            "hostiles": [list(p) for p in self.hostiles],
            "hostile_types": list(self.hostile_types),
            "hostile_kinds": list(self.hostile_kinds),
            "hostile_weapons": list(self.hostile_weapons),
            "control_point": list(self.control_point),
            "loot_zone": list(self.loot_zone) if self.loot_zone else None,
            "loot_zone_kind": self.loot_zone_kind,
            "positions": {k: list(v) for k, v in self.positions.items()},
            "hp": dict(self.hp),
            "medkits_used": {k: bool(v) for k, v in self.medkits_used.items()},
            "turn_order": list(self.turn_order),
            "active_index": self.active_index,
            "turn_seq": self.turn_seq,
            "turn_deadline": self.turn_deadline,
            "match_deadline": self.match_deadline,
            "capture_progress": self.capture_progress,
            "loot_progress": self.loot_progress,
            "finished": self.finished,
            "success": self.success,
            "log": list(self.log),
            "message_ids": {str(k): int(v) for k, v in self.message_ids.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RaidGridSession:
        lz = raw.get("loot_zone")
        cp = raw.get("control_point") or [4, 4]
        return cls(
            session_id=str(raw.get("session_id") or ""),
            raid_id=int(raw.get("raid_id") or 0),
            raid_kind=str(raw.get("raid_kind") or "lair"),
            location_label=str(raw.get("location_label") or ""),
            attacker_faction=str(raw.get("attacker_faction") or ""),
            player_ids=[int(x) for x in (raw.get("player_ids") or [])],
            target_faction=str(raw["target_faction"]) if raw.get("target_faction") else None,
            enemy_power=int(raw.get("enemy_power") or 0),
            energy_cost=int(raw.get("energy_cost") or 18),
            grid=int(raw.get("grid") or RAID_GRID_SIZE),
            cover=[(int(p[0]), int(p[1])) for p in (raw.get("cover") or [])],
            base_cover=[(int(p[0]), int(p[1])) for p in (raw.get("base_cover") or [])],
            hostiles=[(int(p[0]), int(p[1])) for p in (raw.get("hostiles") or [])],
            hostile_types=[str(x) for x in (raw.get("hostile_types") or [])],
            hostile_kinds=[str(x) for x in (raw.get("hostile_kinds") or [])],
            hostile_weapons=[str(x) for x in (raw.get("hostile_weapons") or [])],
            control_point=(int(cp[0]), int(cp[1])),
            loot_zone=(int(lz[0]), int(lz[1])) if lz else None,
            loot_zone_kind=str(raw.get("loot_zone_kind") or "lair"),
            positions={str(k): [int(v[0]), int(v[1])] for k, v in (raw.get("positions") or {}).items()},
            hp={str(k): int(v) for k, v in (raw.get("hp") or {}).items()},
            medkits_used={str(k): bool(v) for k, v in (raw.get("medkits_used") or {}).items()},
            turn_order=[int(x) for x in (raw.get("turn_order") or [])],
            active_index=int(raw.get("active_index") or 0),
            turn_seq=int(raw.get("turn_seq") or 0),
            turn_deadline=raw.get("turn_deadline"),
            match_deadline=raw.get("match_deadline"),
            capture_progress=int(raw.get("capture_progress") or 0),
            loot_progress=int(raw.get("loot_progress") or 0),
            finished=bool(raw.get("finished")),
            success=bool(raw.get("success")),
            log=[str(x) for x in (raw.get("log") or [])],
            message_ids={str(k): int(v) for k, v in (raw.get("message_ids") or {}).items()},
        )


def _session_key(sid: str) -> str:
    return f"{SESSION_PREFIX}{sid}"


def _player_key(tid: int) -> str:
    return f"{PLAYER_PREFIX}{int(tid)}"


def get_raid_grid_session_by_player(storage: Storage, telegram_id: int) -> RaidGridSession | None:
    sid = storage.get_meta(_player_key(telegram_id))
    if not sid:
        return None
    raw = storage.get_meta(_session_key(sid))
    if not raw:
        storage.delete_meta(_player_key(telegram_id))
        return None
    try:
        session = RaidGridSession.from_dict(json.loads(raw))
    except Exception:
        storage.delete_meta(_player_key(telegram_id))
        return None
    if session.finished:
        return None
    return session


def clear_stale_raid_grid_session(storage: Storage, telegram_id: int) -> None:
    """Снять зависшую сессию, если рейд в БД уже не in_progress."""
    session = get_raid_grid_session_by_player(storage, telegram_id)
    if session is None:
        return
    raid = storage.get_raid(session.raid_id)
    if raid is not None and str(raid.get("status") or "") == "in_progress":
        return
    clear_raid_grid_session(storage, session)


def save_raid_grid_session(storage: Storage, session: RaidGridSession) -> None:
    storage.set_meta(_session_key(session.session_id), json.dumps(session.to_dict(), ensure_ascii=False))
    for pid in session.player_ids:
        storage.set_meta(_player_key(pid), session.session_id)


def clear_raid_grid_session(storage: Storage, session: RaidGridSession) -> None:
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


def _hostile_count() -> int:
    return random.randint(RAID_HOSTILE_MIN, RAID_HOSTILE_MAX)


def _spawn_hostiles(
    session: RaidGridSession,
    *,
    bot_count: int = 0,
    bot_tier: int = 1,
) -> None:
    total = _hostile_count()
    bots = min(bot_count, total)
    mutants = total - bots
    forbidden = (
        set(session.cover)
        | set(session.base_cover)
        | {session.control_point}
        | (set([session.loot_zone]) if session.loot_zone else set())
    )
    for pid in session.player_ids:
        forbidden.add(session.pos(pid))

    for _ in range(bots):
        cell = _free_cell(session.grid, forbidden)
        session.hostiles.append(cell)
        session.hostile_types.append("bot")
        session.hostile_kinds.append(pick_npc_kind())
        session.hostile_weapons.append(pick_bot_weapon(bot_tier))
        forbidden.add(cell)

    for _ in range(mutants):
        cell = _free_cell(session.grid, forbidden)
        session.hostiles.append(cell)
        session.hostile_types.append("mutant")
        session.hostile_kinds.append(pick_mutant_kind())
        session.hostile_weapons.append("")
        forbidden.add(cell)


def _build_lair_map(session: RaidGridSession) -> None:
    grid = session.grid
    forbidden: set[tuple[int, int]] = {session.control_point}
    for _ in range(random.randint(10, 14)):
        cell = _free_cell(grid, forbidden)
        session.cover.append(cell)
        forbidden.add(cell)
    spawn_cols = list(range(0, 3))
    for pid in session.player_ids:
        for _ in range(40):
            cell = (random.choice(spawn_cols), random.randint(0, grid - 1))
            if cell not in forbidden:
                session.set_pos(pid, cell)
                forbidden.add(cell)
                break
        else:
            cell = _free_cell(grid, forbidden)
            session.set_pos(pid, cell)
            forbidden.add(cell)
    _spawn_hostiles(session, bot_count=random.randint(0, 2))


def _build_depot_map_with_storage(session: RaidGridSession, storage: Storage, depot_kind: str) -> None:
    grid = session.grid
    forbidden: set[tuple[int, int]] = set()
    for y in range(grid):
        for x in range(grid - 3, grid):
            session.base_cover.append((x, y))
    if depot_kind == "warehouse":
        session.loot_zone = (grid - 2, 2)
    else:
        session.loot_zone = (grid - 2, grid - 3)
    session.loot_zone_kind = depot_kind
    forbidden.update(session.base_cover)
    if session.loot_zone:
        forbidden.add(session.loot_zone)
    for y in range(1, grid - 1):
        for x in range(grid - 2, grid):
            if random.random() < 0.4:
                cell = (x, y)
                if cell not in forbidden:
                    session.cover.append(cell)
                    forbidden.add(cell)
    spawn_cols = list(range(0, 3))
    for pid in session.player_ids:
        for _ in range(40):
            cell = (random.choice(spawn_cols), random.randint(0, grid - 1))
            if cell not in forbidden:
                session.set_pos(pid, cell)
                forbidden.add(cell)
                break
        else:
            cell = _free_cell(grid, forbidden)
            session.set_pos(pid, cell)
            forbidden.add(cell)
    bot_count = FACTION_BOT_DEFAULT_COUNT if not session.target_faction else int(
        get_faction_bots(storage, session.target_faction).get("count", 3)
    )
    bot_tier = int(get_faction_bots(storage, session.target_faction or "").get("tier", 1)) if session.target_faction else 1
    _spawn_hostiles(session, bot_count=bot_count, bot_tier=bot_tier)


def _occupied(session: RaidGridSession, *, exclude: int | None = None) -> set[tuple[int, int]]:
    blocked = set(session.cover) | set(session.base_cover) | set(session.hostiles)
    for pid in session.player_ids:
        if exclude is not None and pid == exclude:
            continue
        blocked.add(session.pos(pid))
    return blocked


def _remove_hostile_at(session: RaidGridSession, pos: tuple[int, int]) -> None:
    if pos not in session.hostiles:
        return
    idx = session.hostiles.index(pos)
    session.hostiles.pop(idx)
    if idx < len(session.hostile_types):
        session.hostile_types.pop(idx)
    if idx < len(session.hostile_kinds):
        session.hostile_kinds.pop(idx)
    if idx < len(session.hostile_weapons):
        session.hostile_weapons.pop(idx)


def _bot_shooters(session: RaidGridSession) -> tuple[list[tuple[int, int]], list[str]]:
    positions: list[tuple[int, int]] = []
    weapons: list[str] = []
    for i, pos in enumerate(session.hostiles):
        if i < len(session.hostile_types) and session.hostile_types[i] == "bot":
            positions.append(pos)
            w = session.hostile_weapons[i] if i < len(session.hostile_weapons) else "ПМ"
            weapons.append(w or "ПМ")
    return positions, weapons


def _hostile_damage(weapon: str) -> int:
    return max(4, weapon_shoot_range(weapon) * 3 + random.randint(0, 4))


def _hostile_turn(storage: Storage, session: RaidGridSession) -> list[str]:
    notes: list[str] = []
    cover_set = set(session.cover)
    base_set = set(session.base_cover)
    alive_ids = [pid for pid in session.player_ids if session.hp.get(str(pid), 0) > 0]
    player_pos = {pid: session.pos(pid) for pid in alive_ids}
    player_chars = {pid: storage.get_character(pid, refresh_energy=False) for pid in alive_ids}

    bot_pos, bot_weapons = _bot_shooters(session)
    if bot_pos:
        notes.extend(
            random_hostile_shots(
                bot_pos,
                bot_weapons,
                grid=session.grid,
                player_positions=player_pos,
                player_hp=session.hp,
                player_characters=player_chars,
                cover=cover_set,
                base_cover=base_set,
                damage_fn=_hostile_damage,
            )
        )

    occupied = _occupied(session)
    new_hostiles: list[tuple[int, int]] = []
    for i, pos in enumerate(session.hostiles):
        if i < len(session.hostile_types) and session.hostile_types[i] != "mutant":
            new_hostiles.append(pos)
            continue
        occupied.discard(pos)
        if not alive_ids:
            new_hostiles.append(pos)
            occupied.add(pos)
            continue
        targets = [session.pos(pid) for pid in alive_ids]
        target = min(targets, key=lambda p: abs(p[0] - pos[0]) + abs(p[1] - pos[1]))
        current = pos
        for dx, dy in MOVE_DELTAS.values():
            nx, ny = current[0] + dx, current[1] + dy
            if 0 <= nx < session.grid and 0 <= ny < session.grid:
                nxt = (nx, ny)
                if nxt not in occupied or nxt in targets:
                    dist_old = abs(current[0] - target[0]) + abs(current[1] - target[1])
                    dist_new = abs(nxt[0] - target[0]) + abs(nxt[1] - target[1])
                    if dist_new < dist_old:
                        current = nxt
        new_hostiles.append(current)
        occupied.add(current)
        for pid in alive_ids:
            if session.pos(pid) == current:
                ch = player_chars.get(pid)
                if ch is None:
                    continue
                dmg = apply_incoming_damage(random.randint(6, 14), ch, min_damage=2)
                session.hp[str(pid)] = max(0, session.hp.get(str(pid), 0) - dmg)
                notes.append(f"Мутант ранит {h(ch.nickname)}: −{dmg} HP.")
    session.hostiles = new_hostiles
    return notes


def _all_hostiles_cleared(session: RaidGridSession) -> bool:
    return len(session.hostiles) == 0


def _check_capture(session: RaidGridSession) -> bool:
    if not _all_hostiles_cleared(session):
        return False
    alive_on_point = [
        pid
        for pid in session.player_ids
        if session.hp.get(str(pid), 0) > 0 and session.pos(pid) == session.control_point
    ]
    if alive_on_point:
        session.capture_progress += 1
        session.log.append(f"Захват: {session.capture_progress}/{RAID_CAPTURE_TURNS}.")
        return session.capture_progress >= RAID_CAPTURE_TURNS
    session.capture_progress = 0
    return False


def _check_loot(session: RaidGridSession) -> bool:
    if session.raid_kind not in ("warehouse", "garage") or session.loot_zone is None:
        return False
    if not _all_hostiles_cleared(session):
        return False
    alive_on_loot = [
        pid
        for pid in session.player_ids
        if session.hp.get(str(pid), 0) > 0 and session.pos(pid) == session.loot_zone
    ]
    if alive_on_loot:
        session.loot_progress += 1
        label = DEPOT_RAID_LABELS.get(session.raid_kind, "объект")
        session.log.append(f"Ограбление {label}а: {session.loot_progress}/{RAID_LOOT_TURNS}.")
        return session.loot_progress >= RAID_LOOT_TURNS
    session.loot_progress = 0
    return False


def _end_session(storage: Storage, session: RaidGridSession, result: ActionResult) -> ActionResult:
    for pid in session.player_ids:
        hp_val = session.hp.get(str(pid))
        if hp_val is not None:
            sync_session_hp_to_db(storage, pid, int(hp_val))
    message_ids = dict(session.message_ids)
    session.finished = True
    save_raid_grid_session(storage, session)
    clear_raid_grid_session(storage, session)
    _unregister_active(storage, session.session_id)
    payload = dict(result.payload or {})
    payload["message_ids"] = message_ids
    payload["session_id"] = session.session_id
    return ActionResult(result.ok, result.text, payload=payload)


def _finalize_lair_success(storage: Storage, session: RaidGridSession) -> ActionResult:
    location_name = session.location_label
    location = storage.get_location(location_name)
    enemy_power = session.enemy_power or 30
    storage.set_location_control(location_name, session.attacker_faction)
    treasury_gain = 1400 + len(session.player_ids) * 180
    storage.change_faction_treasury(session.attacker_faction, treasury_gain)
    artifacts_given = 0
    for pid in session.player_ids:
        if session.hp.get(str(pid), 0) <= 0:
            continue
        durability_text = _apply_durability_decay(storage, pid, weapon_loss=6, armor_loss=5)
        if enemy_power >= RAID_ARTIFACT_MIN_ENEMY_POWER and random.randint(1, 100) <= RAID_ARTIFACT_DROP_CHANCE:
            art_key = pick_weighted_raid_artifact_key()
            storage.add_item(pid, art_key, 1)
            storage.add_player_stat(pid, "artifacts_found", 1)
            artifacts_given += 1
        _maybe_drop_stash(storage, pid)
        _add_rating(storage, pid, RATING_REWARD["raid_success"])
        storage.add_player_stat(pid, "raids_completed", 1)
        _progress_and_unlock_achievements(storage, pid)
        _ = durability_text
    new_npc_power = max(12, enemy_power - random.randint(4, 10))
    if location:
        storage.set_location_npc_power(location_name, new_npc_power)
    storage.finish_raid(
        session.raid_id,
        status="success",
        result_text=f"Тактический рейд успешен. Врагов было: {enemy_power}.",
    )
    text = (
        f"🏆 Рейд #{session.raid_id} на «{location_name}» успешен!\n"
        f"Точка захвачена группировкой «{session.attacker_faction}».\n"
        f"Казна: +{treasury_gain} RU. Артефакты: {artifacts_given}/{len(session.player_ids)}.\n"
        f"+{RATING_REWARD['raid_success']} рейтинга выжившим."
    )
    return ActionResult(
        True,
        text,
        payload={"rgrid_done": True, "success": True, "member_ids": session.player_ids, "raid_id": session.raid_id},
    )


def _finalize_lair_fail(storage: Storage, session: RaidGridSession, reason: str) -> ActionResult:
    location_name = session.location_label
    location = storage.get_location(location_name)
    enemy_power = session.enemy_power or 30
    for pid in session.player_ids:
        _apply_durability_decay(storage, pid, weapon_loss=7, armor_loss=6)
        storage.change_money(pid, -110)
        _add_rating(storage, pid, -RATING_REWARD["raid_fail"])
        storage.add_player_stat(pid, "raids_failed", 1)
        _progress_and_unlock_achievements(storage, pid)
    new_npc_power = min(80, enemy_power + random.randint(2, 7))
    if location:
        storage.set_location_npc_power(location_name, new_npc_power)
    storage.finish_raid(session.raid_id, status="failed", result_text=f"Тактический рейд провален: {reason}")
    text = f"💀 Рейд #{session.raid_id} на «{location_name}» провален.\n{reason}\n−110 RU, −{RATING_REWARD['raid_fail']} рейтинга."
    return ActionResult(
        False,
        text,
        payload={"rgrid_done": True, "success": False, "member_ids": session.player_ids, "raid_id": session.raid_id},
    )


def _finalize_depot_success(storage: Storage, session: RaidGridSession) -> ActionResult:
    target = session.target_faction or "?"
    label = DEPOT_RAID_LABELS.get(session.raid_kind, "склад")
    loot_lines = (
        _steal_faction_warehouse(storage, target, session.attacker_faction)
        if session.raid_kind == "warehouse"
        else _steal_faction_garage(storage, target, session.attacker_faction)
    )
    defender_leader_id = storage.get_faction_leader_id(target)
    for pid in session.player_ids:
        if session.hp.get(str(pid), 0) <= 0:
            continue
        _apply_durability_decay(storage, pid, weapon_loss=5, armor_loss=4)
        _add_rating(storage, pid, RATING_REWARD["depot_raid_success"])
        storage.add_player_stat(pid, "raids_completed", 1)
        _progress_and_unlock_achievements(storage, pid)
    storage.finish_raid(
        session.raid_id,
        status="success",
        result_text=f"Тактический рейд на {label} «{target}» успешен.",
    )
    loot_text = "\n".join(loot_lines) if loot_lines else "Трофеев не найдено."
    text = (
        f"🏚 Рейд #{session.raid_id} на {label} «{target}» успешен!\n"
        f"Добыча:\n{loot_text}\n"
        f"+{RATING_REWARD['depot_raid_success']} рейтинга."
    )
    payload: dict[str, Any] = {
        "rgrid_done": True,
        "success": True,
        "member_ids": session.player_ids,
        "raid_id": session.raid_id,
    }
    if defender_leader_id is not None:
        payload["defender_leader_id"] = int(defender_leader_id)
    return ActionResult(True, text, payload=payload)


def _finalize_depot_fail(storage: Storage, session: RaidGridSession, reason: str) -> ActionResult:
    target = session.target_faction or "?"
    label = DEPOT_RAID_LABELS.get(session.raid_kind, "склад")
    defender_leader_id = storage.get_faction_leader_id(target)
    for pid in session.player_ids:
        _apply_durability_decay(storage, pid, weapon_loss=6, armor_loss=5)
        storage.change_money(pid, -DEPOT_RAID_FAIL_MONEY_PENALTY)
        _add_rating(storage, pid, -RATING_REWARD["depot_raid_fail"])
        storage.add_player_stat(pid, "raids_failed", 1)
        _progress_and_unlock_achievements(storage, pid)
    if defender_leader_id is not None:
        _add_rating(storage, int(defender_leader_id), RATING_REWARD["depot_raid_defense"])
    storage.finish_raid(session.raid_id, status="failed", result_text=f"Тактический рейд провален: {reason}")
    text = (
        f"💀 Рейд #{session.raid_id} на {label} «{target}» провален.\n{reason}\n"
        f"−{DEPOT_RAID_FAIL_MONEY_PENALTY} RU, −{RATING_REWARD['depot_raid_fail']} рейтинга."
    )
    payload: dict[str, Any] = {
        "rgrid_done": True,
        "success": False,
        "member_ids": session.player_ids,
        "raid_id": session.raid_id,
    }
    if defender_leader_id is not None:
        payload["defender_leader_id"] = int(defender_leader_id)
    return ActionResult(False, text, payload=payload)


def _check_squad_wiped(storage: Storage, session: RaidGridSession) -> ActionResult | None:
    alive = [pid for pid in session.player_ids if session.hp.get(str(pid), 0) > 0]
    if alive:
        return None
    if session.raid_kind in ("warehouse", "garage"):
        return _end_session(storage, session, _finalize_depot_fail(storage, session, "Все бойцы выведены из строя."))
    return _end_session(storage, session, _finalize_lair_fail(storage, session, "Все бойцы выведены из строя."))


def _check_end(storage: Storage, session: RaidGridSession) -> ActionResult | None:
    wiped = _check_squad_wiped(storage, session)
    if wiped:
        return wiped
    deadline = _parse_deadline(session.match_deadline)
    if deadline and _utc_now() > deadline:
        reason = "Время рейда истекло."
        if session.raid_kind in ("warehouse", "garage"):
            return _end_session(storage, session, _finalize_depot_fail(storage, session, reason))
        return _end_session(storage, session, _finalize_lair_fail(storage, session, reason))
    if session.raid_kind in ("warehouse", "garage"):
        if _check_loot(session):
            return _end_session(storage, session, _finalize_depot_success(storage, session))
        return None
    if _all_hostiles_cleared(session) and _check_capture(session):
        return _end_session(storage, session, _finalize_lair_success(storage, session))
    return None


def start_raid_grid(
    storage: Storage,
    *,
    raid_id: int,
    raid_kind: str,
    location_label: str,
    attacker_faction: str,
    player_ids: list[int],
    target_faction: str | None = None,
    enemy_power: int = 0,
    energy_cost: int = 18,
) -> tuple[ActionResult, RaidGridSession | None]:
    from app.player_busy import player_busy_reason

    if len(player_ids) < RAID_MIN_MEMBERS or len(player_ids) > RAID_MAX_MEMBERS:
        return ActionResult(False, f"В рейде должно быть от {RAID_MIN_MEMBERS} до {RAID_MAX_MEMBERS} бойцов."), None

    members: list[Character] = []
    for pid in player_ids:
        clear_stale_raid_grid_session(storage, pid)
        existing = get_raid_grid_session_by_player(storage, pid)
        if existing is not None:
            ch = storage.get_character(pid, refresh_energy=False)
            name = h(ch.nickname) if ch else str(pid)
            return ActionResult(False, f"{name} уже в тактическом рейде."), None
        ch = storage.get_character(pid, refresh_energy=False)
        if ch is None or ch.health <= 0:
            return ActionResult(False, "Не все бойцы доступны."), None
        busy = player_busy_reason(storage, pid, skip="rgrid")
        if busy:
            return ActionResult(False, f"{h(ch.nickname)}: {busy}"), None
        members.append(ch)

    session_id = uuid.uuid4().hex[:12]
    session = RaidGridSession(
        session_id=session_id,
        raid_id=raid_id,
        raid_kind=raid_kind,
        location_label=location_label,
        attacker_faction=attacker_faction,
        target_faction=target_faction,
        player_ids=list(player_ids),
        enemy_power=enemy_power,
        energy_cost=energy_cost,
        turn_order=list(player_ids),
        turn_deadline=_deadline_iso(RAID_TURN_SECONDS),
        match_deadline=_deadline_iso(RAID_MATCH_SECONDS),
    )
    if raid_kind in ("warehouse", "garage"):
        _build_depot_map_with_storage(session, storage, raid_kind)
    else:
        _build_lair_map(session)

    for ch in members:
        session.hp[str(ch.telegram_id)] = int(ch.health)
        session.medkits_used[str(ch.telegram_id)] = False

    hostile_n = len(session.hostiles)
    session.log.append(
        f"Рейд «{location_label}»: поле {RAID_GRID_SIZE}×{RAID_GRID_SIZE}, "
        f"врагов {hostile_n}, таймер {RAID_MATCH_SECONDS // 60} мин."
    )
    if raid_kind in ("warehouse", "garage"):
        label = DEPOT_RAID_LABELS.get(raid_kind, "объект")
        session.log.append(f"Зачисти врагов и удерживай клетку {label}а {RAID_LOOT_TURNS} хода.")
    else:
        session.log.append(f"Зачисти врагов и удерживай центр {RAID_CAPTURE_TURNS} хода.")

    save_raid_grid_session(storage, session)
    _register_active(storage, session_id)
    text = (
        f"🪖 Тактический рейд «{location_label}»!\n"
        f"Бойцов: {len(player_ids)}, врагов: {hostile_n}.\n"
        f"Каждый ход — свой ход: ходи и стреляй сам.\n"
        f"Голубой квадрат на карте = ты."
    )
    return ActionResult(True, text, payload={"rgrid_started": True, "session_id": session_id}), session


def _save_turn(storage: Storage, session: RaidGridSession, expected_seq: int) -> bool:
    raw = storage.get_meta(_session_key(session.session_id))
    if not raw:
        return False
    try:
        fresh = RaidGridSession.from_dict(json.loads(raw))
    except Exception:
        return False
    if fresh.finished or fresh.turn_seq != expected_seq:
        return False
    save_raid_grid_session(storage, session)
    return True


def _advance(session: RaidGridSession) -> None:
    if not session.turn_order:
        return
    session.active_index = (session.active_index + 1) % len(session.turn_order)
    for _ in range(len(session.turn_order)):
        pid = session.turn_order[session.active_index % len(session.turn_order)]
        if session.hp.get(str(pid), 0) > 0:
            break
        session.active_index = (session.active_index + 1) % len(session.turn_order)
    session.turn_seq += 1
    session.turn_deadline = _deadline_iso(RAID_TURN_SECONDS)


def _after_player_turn(storage: Storage, session: RaidGridSession) -> ActionResult | None:
    session.log.extend(_hostile_turn(storage, session))
    return _check_end(storage, session)


def rgrid_move(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_raid_grid_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного тактического рейда.")
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
    if ch and nxt in session.hostiles:
        idx = session.hostiles.index(nxt)
        htype = session.hostile_types[idx] if idx < len(session.hostile_types) else "mutant"
        _remove_hostile_at(session, nxt)
        dmg = apply_incoming_damage(random.randint(8, 16), ch, min_damage=3)
        session.hp[str(telegram_id)] = max(0, session.hp.get(str(telegram_id), 0) - dmg)
        label = "Бот" if htype == "bot" else "Мутант"
        session.log.append(f"{h(ch.nickname)} схватился с {label.lower()}ом: −{dmg} HP.")
    done = _check_squad_wiped(storage, session)
    if done:
        return done
    _advance(session)
    done = _after_player_turn(storage, session)
    if done:
        return done
    if not _save_turn(storage, session, turn_seq):
        return ActionResult(False, "Ход уже выполнен.")
    return ActionResult(True, "Шаг.", payload={"rgrid_active": True})


def rgrid_shoot(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_raid_grid_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного тактического рейда.")
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
    targets = {pos: "host" for pos in session.hostiles}
    hit_cell, hit_kind = ray_cast_first_hit(
        origin, direction, grid=session.grid, max_range=rng, blockers=set(session.cover), targets=targets
    )
    note = "Промах."
    if hit_cell and hit_kind == "host":
        if cover_blocks_shot(hit_cell, cover_set):
            session.log.append("Враг за укрытием — промах.")
        elif hit_cell in session.hostiles:
            _remove_hostile_at(session, hit_cell)
            session.log.append(f"{h(attacker.nickname)} поразил врага ({weapon}).")
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
    return ActionResult(True, note, payload={"rgrid_active": True})


def rgrid_use_medkit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_raid_grid_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного тактического рейда.")
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
    return ActionResult(True, result.text, payload={"rgrid_active": True})


def rgrid_forfeit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_raid_grid_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Нет активного тактического рейда.")
    ch = storage.get_character(telegram_id, refresh_energy=False)
    name = h(ch.nickname) if ch else str(telegram_id)
    reason = f"{name} отступил."
    if session.raid_kind in ("warehouse", "garage"):
        return _end_session(storage, session, _finalize_depot_fail(storage, session, reason))
    return _end_session(storage, session, _finalize_lair_fail(storage, session, reason))


def process_rgrid_turn_timeouts(storage: Storage) -> list[tuple[int, ActionResult]]:
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
            session = RaidGridSession.from_dict(json.loads(raw_s))
        except Exception:
            continue
        if session.finished:
            continue
        match_deadline = _parse_deadline(session.match_deadline)
        if match_deadline and now > match_deadline:
            reason = "Время рейда истекло."
            if session.raid_kind in ("warehouse", "garage"):
                outcomes.append((session.active_player(), _end_session(storage, session, _finalize_depot_fail(storage, session, reason))))
            else:
                outcomes.append((session.active_player(), _end_session(storage, session, _finalize_lair_fail(storage, session, reason))))
            continue
        turn_deadline = _parse_deadline(session.turn_deadline)
        if turn_deadline is None or now <= turn_deadline:
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
            outcomes.append((active, ActionResult(True, "Ход пропущен.", payload={"rgrid_active": True})))
    storage.set_meta(ACTIVE_IDS_KEY, json.dumps(still, ensure_ascii=False))
    return outcomes


def find_raid_grid_session_for_faction(storage: Storage, faction: str) -> RaidGridSession | None:
    in_progress = storage.get_in_progress_raid_for_faction(faction)
    if in_progress is None:
        return None
    raid_id = int(in_progress["id"])
    for pid in storage.get_raid_member_ids(raid_id):
        session = get_raid_grid_session_by_player(storage, pid)
        if session is not None and int(session.raid_id) == raid_id:
            return session
    return None


def rgrid_status_caption(storage: Storage, session: RaidGridSession, viewer_id: int) -> str:
    active = storage.get_character(session.active_player(), refresh_energy=False)
    active_name = active.nickname if active else str(session.active_player())
    lines = [f"🪖 Тактический рейд «{session.location_label}» · ход {active_name}"]
    deadline = _parse_deadline(session.match_deadline)
    if deadline:
        secs = max(0, int((deadline - _utc_now()).total_seconds()))
        lines.append(f"⏱ {secs // 60}:{secs % 60:02d}")
    lines.append(f"Врагов: {len(session.hostiles)} · живых бойцов: {sum(1 for pid in session.player_ids if session.hp.get(str(pid), 0) > 0)}")
    if session.raid_kind in ("warehouse", "garage"):
        lines.append(f"Ограбление: {session.loot_progress}/{RAID_LOOT_TURNS}")
    else:
        lines.append(f"Захват: {session.capture_progress}/{RAID_CAPTURE_TURNS}")
    for pid in session.player_ids[:5]:
        ch = storage.get_character(pid, refresh_energy=False)
        name = ch.nickname if ch else str(pid)
        hp = session.hp.get(str(pid), 0)
        mark = " ◀" if pid == session.active_player() else ""
        if pid == viewer_id:
            mark += " (ты)"
        lines.append(f"{name}{mark}: HP {hp}")
    lines.append("🔷 голубой квадрат на карте = вы")
    if session.log:
        lines.append(session.log[-1][:80])
    return "\n".join(lines)


def render_rgrid_frame(storage: Storage, session: RaidGridSession, viewer_id: int) -> bytes:
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
    if session.raid_kind == "lair":
        draw.rectangle(
            (margin + cp[0] * cell + 4, margin + cp[1] * cell + 4, margin + (cp[0] + 1) * cell - 4, margin + (cp[1] + 1) * cell - 4),
            outline=(255, 220, 60),
            width=3,
        )
    if session.loot_zone:
        lx, ly = session.loot_zone
        label = LOOT_ZONE_LABELS.get(session.loot_zone_kind, "ЦЕЛЬ")
        draw.rectangle(
            (margin + lx * cell + 4, margin + ly * cell + 4, margin + (lx + 1) * cell - 4, margin + (ly + 1) * cell - 4),
            outline=(255, 140, 50),
            width=3,
        )
        zone_font = load_tactical_font(10)
        draw.text((margin + lx * cell + 8, margin + ly * cell + cell // 2 - 6), label, fill=(255, 180, 100), font=zone_font)
    for cx, cy in session.cover:
        left = margin + cx * cell + 4
        top = margin + cy * cell + 4
        draw.rounded_rectangle((left, top, left + cell - 8, top + cell - 8), radius=6, fill=(70, 62, 48, 200), outline=(100, 90, 70))
    cover_font = load_tactical_font(10)
    for bx, by in session.base_cover:
        if (bx, by) in session.cover:
            continue
        left = margin + bx * cell + 2
        top = margin + by * cell + 2
        draw.rectangle((left, top, left + cell - 4, top + cell - 4), outline=(80, 100, 140), width=1)
    for i, (hx, hy) in enumerate(session.hostiles):
        cxp = margin + hx * cell + cell // 2
        cyp = margin + hy * cell + cell // 2
        htype = session.hostile_types[i] if i < len(session.hostile_types) else "mutant"
        kind = session.hostile_kinds[i] if i < len(session.hostile_kinds) else None
        if htype == "mutant":
            paste_mutant_sprite(canvas, draw, cx=cxp, cy=cyp, kind=kind, diameter=52)
        else:
            paste_npc_sprite(canvas, draw, cx=cxp, cy=cyp, kind=kind, diameter=52, ring_color=(255, 90, 70))
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
    draw.text((pl + 10, y), f"Рейд {session.location_label[:18]}", fill=(240, 240, 240), font=small)
    y += 22
    deadline = _parse_deadline(session.match_deadline)
    if deadline:
        secs = max(0, int((deadline - _utc_now()).total_seconds()))
        draw.text((pl + 10, y), f"Осталось: {secs // 60}:{secs % 60:02d}", fill=(200, 200, 120), font=small)
        y += 15
    draw.text((pl + 10, y), f"Врагов: {len(session.hostiles)}", fill=(180, 180, 180), font=small)
    y += 15
    draw.text((pl + 10, y), "Голубой квадрат = вы", fill=(120, 200, 230), font=small)
    y += 15
    for pid in session.player_ids[:5]:
        ch = storage.get_character(pid, refresh_energy=False)
        name = ch.nickname if ch else str(pid)
        hp = session.hp.get(str(pid), 0)
        mark = " <" if pid == session.active_player() else ""
        draw.text((pl + 10, y), f"{h(name)}{mark}: HP {hp}"[:38], fill=(180, 180, 180), font=small)
        y += 15
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
