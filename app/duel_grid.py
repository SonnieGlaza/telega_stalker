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
    DUEL_ENERGY_COST,
    DUEL_LOSER_HP_REMAINING,
    DUEL_LOSER_MONEY_CAP,
    DUEL_LOSER_MONEY_PERCENT,
    DUEL_WINNER_WOUND_MAX,
    DUEL_WINNER_WOUND_MIN,
    RATING_REWARD,
    ActionResult,
    _add_rating,
    _is_dead,
    _weapon_rating,
    apply_incoming_damage,
    effective_max_health,
    equipment_power,
    h,
    use_medkit_item,
)
from app.storage import Character, Storage

DUEL_GRID_SIZE = 8
DUEL_TURN_SECONDS = 10
DUEL_COVER_HIT_CHANCE = 0.5
DUEL_MUTANT_COUNT = 2

DUEL_SESSION_PREFIX = "duel:grid:session:"
DUEL_PLAYER_PREFIX = "duel:grid:player:"

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


def weapon_shoot_range(weapon_name: str) -> int:
    """Нож=1, пистолеты=2, автоматы=3, топ/гаусс=4."""
    if weapon_name == "Нож":
        return 1
    rating = _weapon_rating(weapon_name)
    if rating <= 3:
        return 2
    if rating <= 6:
        return 3
    return 4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _deadline_iso(seconds: int = DUEL_TURN_SECONDS) -> str:
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


def _duel_damage(attacker: Character) -> int:
    base = max(4, equipment_power(attacker) * 2)
    lo = max(1, base - 2)
    hi = base + 2
    return random.randint(lo, hi)


@dataclass
class DuelGridSession:
    duel_id: str
    challenger_id: int
    target_id: int
    grid: int = DUEL_GRID_SIZE
    cover: list[tuple[int, int]] = field(default_factory=list)
    mutants: list[tuple[int, int]] = field(default_factory=list)
    positions: dict[str, list[int]] = field(default_factory=dict)  # telegram_id -> [x,y]
    hp: dict[str, int] = field(default_factory=dict)
    medkits_used: dict[str, bool] = field(default_factory=dict)
    turn_order: list[int] = field(default_factory=list)
    active_index: int = 0
    turn_deadline: str | None = None
    finished: bool = False
    winner_id: int | None = None
    loser_id: int | None = None
    log: list[str] = field(default_factory=list)
    message_ids: dict[str, int] = field(default_factory=dict)

    def active_player(self) -> int:
        return self.turn_order[self.active_index % len(self.turn_order)]

    def opponent_of(self, player_id: int) -> int:
        return self.target_id if player_id == self.challenger_id else self.challenger_id

    def pos(self, player_id: int) -> tuple[int, int]:
        raw = self.positions.get(str(player_id), [0, 0])
        return int(raw[0]), int(raw[1])

    def set_pos(self, player_id: int, pos: tuple[int, int]) -> None:
        self.positions[str(player_id)] = [pos[0], pos[1]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "duel_id": self.duel_id,
            "challenger_id": self.challenger_id,
            "target_id": self.target_id,
            "grid": self.grid,
            "cover": [list(p) for p in self.cover],
            "mutants": [list(p) for p in self.mutants],
            "positions": self.positions,
            "hp": self.hp,
            "medkits_used": self.medkits_used,
            "turn_order": self.turn_order,
            "active_index": self.active_index,
            "turn_deadline": self.turn_deadline,
            "finished": self.finished,
            "winner_id": self.winner_id,
            "loser_id": self.loser_id,
            "log": self.log[-12:],
            "message_ids": {str(k): int(v) for k, v in self.message_ids.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DuelGridSession:
        return cls(
            duel_id=str(raw.get("duel_id") or ""),
            challenger_id=int(raw.get("challenger_id") or 0),
            target_id=int(raw.get("target_id") or 0),
            grid=int(raw.get("grid") or DUEL_GRID_SIZE),
            cover=[(int(p[0]), int(p[1])) for p in (raw.get("cover") or [])],
            mutants=[(int(p[0]), int(p[1])) for p in (raw.get("mutants") or [])],
            positions={str(k): list(v) for k, v in (raw.get("positions") or {}).items()},
            hp={str(k): int(v) for k, v in (raw.get("hp") or {}).items()},
            medkits_used={str(k): bool(v) for k, v in (raw.get("medkits_used") or {}).items()},
            turn_order=[int(x) for x in (raw.get("turn_order") or [])],
            active_index=int(raw.get("active_index") or 0),
            turn_deadline=raw.get("turn_deadline"),
            finished=bool(raw.get("finished")),
            winner_id=int(raw["winner_id"]) if raw.get("winner_id") is not None else None,
            loser_id=int(raw["loser_id"]) if raw.get("loser_id") is not None else None,
            log=[str(x) for x in (raw.get("log") or [])],
            message_ids={str(k): int(v) for k, v in (raw.get("message_ids") or {}).items()},
        )


def _session_key(duel_id: str) -> str:
    return f"{DUEL_SESSION_PREFIX}{duel_id}"


def _player_key(telegram_id: int) -> str:
    return f"{DUEL_PLAYER_PREFIX}{int(telegram_id)}"


def get_duel_session_by_player(storage: Storage, telegram_id: int) -> DuelGridSession | None:
    duel_id = storage.get_meta(_player_key(telegram_id))
    if not duel_id:
        return None
    raw = storage.get_meta(_session_key(duel_id))
    if not raw:
        storage.delete_meta(_player_key(telegram_id))
        return None
    try:
        session = DuelGridSession.from_dict(json.loads(raw))
    except Exception:
        return None
    if session.finished:
        return None
    return session


def save_duel_session(storage: Storage, session: DuelGridSession) -> None:
    storage.set_meta(_session_key(session.duel_id), json.dumps(session.to_dict(), ensure_ascii=False))
    for pid in (session.challenger_id, session.target_id):
        storage.set_meta(_player_key(pid), session.duel_id)


def clear_duel_session(storage: Storage, session: DuelGridSession) -> None:
    storage.delete_meta(_session_key(session.duel_id))
    storage.delete_meta(_player_key(session.challenger_id))
    storage.delete_meta(_player_key(session.target_id))


def _free_cell(grid: int, forbidden: set[tuple[int, int]]) -> tuple[int, int]:
    opts = [(x, y) for x in range(grid) for y in range(grid) if (x, y) not in forbidden]
    return random.choice(opts) if opts else (0, 0)


def _build_duel_map(session: DuelGridSession) -> None:
    grid = session.grid
    forbidden: set[tuple[int, int]] = set()
    c_pos = _free_cell(grid, forbidden)
    forbidden.add(c_pos)
    t_pos = _free_cell(grid, forbidden)
    forbidden.add(t_pos)
    session.set_pos(session.challenger_id, c_pos)
    session.set_pos(session.target_id, t_pos)
    cover_n = random.randint(8, 12)
    for _ in range(cover_n):
        cell = _free_cell(grid, forbidden)
        session.cover.append(cell)
        forbidden.add(cell)
    for _ in range(DUEL_MUTANT_COUNT):
        cell = _free_cell(grid, forbidden)
        session.mutants.append(cell)
        forbidden.add(cell)


def _finalize_duel_rewards(storage: Storage, winner_id: int, loser_id: int) -> tuple[str, str]:
    winner = storage.get_character(winner_id, refresh_energy=False)
    loser = storage.get_character(loser_id, refresh_energy=False)
    if winner is None or loser is None:
        return ("Дуэль завершена.", "Дуэль завершена.")
    winner_max_hp = effective_max_health(winner)
    loser_max_hp = effective_max_health(loser)
    wound = random.randint(DUEL_WINNER_WOUND_MIN, DUEL_WINNER_WOUND_MAX)
    storage.change_health(winner_id, -wound, max_health=winner_max_hp)
    loser_hp_target = min(DUEL_LOSER_HP_REMAINING, loser_max_hp)
    loser_hp_delta = loser_hp_target - int(loser.health)
    if loser_hp_delta != 0:
        storage.change_health(loser_id, loser_hp_delta, max_health=loser_max_hp)
    money_taken = max(0, int(loser.money * DUEL_LOSER_MONEY_PERCENT // 100))
    money_taken = min(money_taken, DUEL_LOSER_MONEY_CAP)
    if money_taken > 0:
        if storage.change_money(loser_id, -money_taken):
            storage.change_money(winner_id, money_taken)
        else:
            money_taken = 0
    _add_rating(storage, winner_id, RATING_REWARD["duel_win"])
    _add_rating(storage, loser_id, -RATING_REWARD["duel_lose"])
    winner_after = storage.get_character(winner_id, refresh_energy=False)
    loser_after = storage.get_character(loser_id, refresh_energy=False)
    common = (
        f"⚔️ Тактическая дуэль завершена.\n"
        f"Победитель: {h(winner.nickname)} (HP {winner_after.health if winner_after else 0}, "
        f"ранение −{wound}{f', +{money_taken} RU' if money_taken else ''}).\n"
        f"Проигравший: {h(loser.nickname)} (HP {loser_after.health if loser_after else 0}"
        f"{f', −{money_taken} RU' if money_taken else ''})."
    )
    win_text = f"🏆 Ты победил!\n{common}"
    lose_text = f"💀 Ты проиграл.\n{common}"
    return win_text, lose_text


def start_duel_grid(
    storage: Storage,
    challenger_id: int,
    target_id: int,
) -> tuple[ActionResult, DuelGridSession | None]:
    challenger = storage.get_character(challenger_id, refresh_energy=False)
    target = storage.get_character(target_id, refresh_energy=False)
    if challenger is None or target is None:
        return ActionResult(False, "Один из бойцов не найден."), None
    if get_duel_session_by_player(storage, challenger_id) or get_duel_session_by_player(storage, target_id):
        return ActionResult(False, "Один из бойцов уже в дуэли."), None

    duel_id = uuid.uuid4().hex[:12]
    session = DuelGridSession(
        duel_id=duel_id,
        challenger_id=challenger_id,
        target_id=target_id,
        turn_order=[challenger_id, target_id],
        active_index=0,
        turn_deadline=_deadline_iso(),
    )
    _build_duel_map(session)
    session.hp[str(challenger_id)] = int(challenger.health)
    session.hp[str(target_id)] = int(target.health)
    session.medkits_used[str(challenger_id)] = False
    session.medkits_used[str(target_id)] = False
    session.log.append(
        f"Дуэль: {h(challenger.nickname)} vs {h(target.nickname)}. "
        f"Ход {DUEL_TURN_SECONDS} сек. Укрытие = 50% промах."
    )
    save_duel_session(storage, session)
    register_active_duel(storage, duel_id)
    text = (
        f"⚔️ Тактическая дуэль началась!\n"
        f"{h(challenger.nickname)} vs {h(target.nickname)}\n"
        f"Дальность: нож 1 / пистолет 2 / автомат 3 / снайпер·гаусс 4 клетки.\n"
        f"Урон ≈ сила×2 ±2. Аптечка — 1 раз за бой.\n"
        f"Первый ход: {h(challenger.nickname)}."
    )
    return ActionResult(True, text, payload={"duel_id": duel_id}), session


def _end_duel(storage: Storage, session: DuelGridSession, winner_id: int, loser_id: int, note: str) -> ActionResult:
    session.finished = True
    session.winner_id = winner_id
    session.loser_id = loser_id
    session.log.append(note)
    save_duel_session(storage, session)
    win_text, lose_text = _finalize_duel_rewards(storage, winner_id, loser_id)
    clear_duel_session(storage, session)
    unregister_active_duel(storage, session.duel_id)
    winner = storage.get_character(winner_id, refresh_energy=False)
    loser = storage.get_character(loser_id, refresh_energy=False)
    payload = {
        "duel_done": True,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "winner_text": win_text,
        "loser_text": lose_text,
        "winner_name": winner.nickname if winner else str(winner_id),
        "loser_name": loser.nickname if loser else str(loser_id),
    }
    return ActionResult(True, note, payload=payload)


def _check_hp_end(storage: Storage, session: DuelGridSession) -> ActionResult | None:
    for pid in (session.challenger_id, session.target_id):
        if session.hp.get(str(pid), 0) <= 0:
            loser_id = pid
            winner_id = session.opponent_of(pid)
            return _end_duel(
                storage,
                session,
                winner_id,
                loser_id,
                f"{h(storage.get_character(winner_id).nickname if storage.get_character(winner_id) else str(winner_id))} победил — HP противника 0.",
            )
    return None


def _occupied(session: DuelGridSession, *, exclude: int | None = None) -> set[tuple[int, int]]:
    blocked = set(session.cover)
    blocked.update(session.mutants)
    for pid in (session.challenger_id, session.target_id):
        if exclude is not None and pid == exclude:
            continue
        blocked.add(session.pos(pid))
    return blocked


def _advance_turn(session: DuelGridSession) -> None:
    session.active_index = (session.active_index + 1) % len(session.turn_order)
    session.turn_deadline = _deadline_iso()


def _move_mutants(session: DuelGridSession) -> None:
    occupied = _occupied(session)
    new_positions: list[tuple[int, int]] = []
    for pos in session.mutants:
        occupied.discard(pos)
        players = [session.pos(session.challenger_id), session.pos(session.target_id)]
        target = min(players, key=lambda p: abs(p[0] - pos[0]) + abs(p[1] - pos[1]))
        candidates = []
        for dx, dy in MOVE_DELTAS.values():
            nx, ny = pos[0] + dx, pos[1] + dy
            if 0 <= nx < session.grid and 0 <= ny < session.grid:
                nxt = (nx, ny)
                if nxt not in occupied or nxt in players:
                    candidates.append(nxt)
        if not candidates:
            new_positions.append(pos)
            occupied.add(pos)
            continue
        best = min(
            candidates,
            key=lambda c: abs(c[0] - target[0]) + abs(c[1] - target[1]),
        )
        new_positions.append(best)
        occupied.add(best)
    session.mutants = new_positions


def _mutants_attack(session: DuelGridSession, storage: Storage) -> list[str]:
    notes: list[str] = []
    for mpos in session.mutants:
        for pid in (session.challenger_id, session.target_id):
            if session.pos(pid) == mpos:
                player = storage.get_character(pid, refresh_energy=False)
                if player is None:
                    continue
                dmg = apply_incoming_damage(random.randint(6, 12), player, min_damage=2)
                session.hp[str(pid)] = max(0, session.hp.get(str(pid), 0) - dmg)
                notes.append(f"Мутант ранит {h(player.nickname)}: −{dmg} HP.")
    return notes


def duel_move(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_duel_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активной дуэли нет.")
    if session.active_player() != telegram_id:
        return ActionResult(False, "Сейчас ход соперника.")
    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return ActionResult(False, "Некорректное направление.")
    pos = session.pos(telegram_id)
    nxt = (pos[0] + delta[0], pos[1] + delta[1])
    if not (0 <= nxt[0] < session.grid and 0 <= nxt[1] < session.grid):
        return ActionResult(False, "Край поля.")
    blocked = _occupied(session, exclude=telegram_id)
    opp = session.opponent_of(telegram_id)
    if nxt == session.pos(opp):
        return ActionResult(False, "Нельзя встать на клетку соперника — стреляй.")
    if nxt in blocked and nxt not in session.cover:
        return ActionResult(False, "Клетка занята.")
    session.set_pos(telegram_id, nxt)
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player and nxt in session.mutants:
        dmg = apply_incoming_damage(random.randint(8, 14), player, min_damage=3)
        session.hp[str(telegram_id)] = max(0, session.hp.get(str(telegram_id), 0) - dmg)
        session.log.append(f"{h(player.nickname)} задел мутанта: −{dmg} HP.")
    done = _check_hp_end(storage, session)
    if done:
        return done
    _advance_turn(session)
    _move_mutants(session)
    session.log.extend(_mutants_attack(session, storage))
    done = _check_hp_end(storage, session)
    if done:
        return done
    save_duel_session(storage, session)
    return ActionResult(True, "Сделал шаг.", payload={"duel_active": True, "duel_id": session.duel_id})


def duel_shoot(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_duel_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активной дуэли нет.")
    if session.active_player() != telegram_id:
        return ActionResult(False, "Сейчас ход соперника.")
    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return ActionResult(False, "Некорректный выстрел.")
    attacker = storage.get_character(telegram_id, refresh_energy=False)
    if attacker is None:
        return ActionResult(False, "Персонаж не найден.")
    weapon = str(attacker.equipment.get("weapon", "Нож"))
    rng = weapon_shoot_range(weapon)
    origin = session.pos(telegram_id)
    hit_pos: tuple[int, int] | None = None
    hit_kind = ""
    for step in range(1, rng + 1):
        cell = (origin[0] + delta[0] * step, origin[1] + delta[1] * step)
        if not (0 <= cell[0] < session.grid and 0 <= cell[1] < session.grid):
            break
        if cell == session.pos(session.opponent_of(telegram_id)):
            hit_pos = cell
            hit_kind = "player"
            break
        if cell in session.mutants:
            hit_pos = cell
            hit_kind = "mutant"
            break
    if hit_pos is None:
        session.log.append(f"{h(attacker.nickname)} промахнулся.")
        _advance_turn(session)
        _move_mutants(session)
        session.log.extend(_mutants_attack(session, storage))
        save_duel_session(storage, session)
        return ActionResult(True, "Промах — пуля не нашла цель.", payload={"duel_active": True})

    if hit_kind == "mutant":
        if hit_pos in session.mutants:
            session.mutants.remove(hit_pos)
        session.log.append(f"{h(attacker.nickname)} убил мутанта.")
        note = "Мутант уничтожен."
    else:
        defender_id = session.opponent_of(telegram_id)
        defender = storage.get_character(defender_id, refresh_energy=False)
        if defender is None:
            return ActionResult(False, "Соперник не найден.")
        if hit_pos in session.cover and random.random() > DUEL_COVER_HIT_CHANCE:
            session.log.append(f"{h(defender.nickname)} укрылся — промах!")
            _advance_turn(session)
            _move_mutants(session)
            save_duel_session(storage, session)
            return ActionResult(True, "Промах — цель за укрытием.", payload={"duel_active": True})
        raw = _duel_damage(attacker)
        dmg = apply_incoming_damage(raw, defender, min_damage=1)
        session.hp[str(defender_id)] = max(0, session.hp.get(str(defender_id), 0) - dmg)
        session.log.append(f"{h(attacker.nickname)} попал в {h(defender.nickname)}: −{dmg} HP.")
        note = f"Попадание: −{dmg} HP."
        done = _check_hp_end(storage, session)
        if done:
            return done

    _advance_turn(session)
    _move_mutants(session)
    session.log.extend(_mutants_attack(session, storage))
    done = _check_hp_end(storage, session)
    if done:
        return done
    save_duel_session(storage, session)
    return ActionResult(True, note, payload={"duel_active": True, "duel_id": session.duel_id})


def duel_use_medkit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_duel_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активной дуэли нет.")
    if session.active_player() != telegram_id:
        return ActionResult(False, "Сейчас ход соперника.")
    if session.medkits_used.get(str(telegram_id)):
        return ActionResult(False, "Аптечку в этой дуэли уже использовал.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Персонаж не найден.")
    for key in ("medkit_science", "medkit_army", "medkit"):
        if int(player.inventory.get(key, 0)) <= 0:
            continue
        result = use_medkit_item(storage, telegram_id, key)
        if not result.ok:
            continue
        refreshed = storage.get_character(telegram_id, refresh_energy=False)
        if refreshed:
            session.hp[str(telegram_id)] = int(refreshed.health)
        session.medkits_used[str(telegram_id)] = True
        session.log.append(f"{h(player.nickname)} использовал аптечку.")
        _advance_turn(session)
        _move_mutants(session)
        session.log.extend(_mutants_attack(session, storage))
        done = _check_hp_end(storage, session)
        if done:
            return done
        save_duel_session(storage, session)
        return ActionResult(True, result.text, payload={"duel_active": True})
    return ActionResult(False, "Нет аптечки в инвентаре.")


def duel_forfeit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_duel_session_by_player(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активной дуэли нет.")
    winner_id = session.opponent_of(telegram_id)
    player = storage.get_character(telegram_id, refresh_energy=False)
    note = f"{h(player.nickname) if player else telegram_id} сдался."
    return _end_duel(storage, session, winner_id, telegram_id, note)


def process_duel_turn_timeouts(storage: Storage) -> list[tuple[int, ActionResult]]:
    """Автопропуск хода по таймеру. Возвращает (player_id, result) для уведомлений."""
    outcomes: list[tuple[int, ActionResult]] = []
    now = _utc_now()
    # scan via meta keys — only active duel sessions stored under duel:grid:session:*
    # Storage has no list_meta; iterate players is hard. Store active duel ids list?
    # For MVP: check both players of known sessions via player keys only when timeout triggered from bot tick on active travels pattern.
    # Use a registry meta key duel:grid:active -> json list of duel ids
    raw = storage.get_meta("duel:grid:active_ids")
    if not raw:
        return outcomes
    try:
        duel_ids = json.loads(raw)
    except json.JSONDecodeError:
        return outcomes
    if not isinstance(duel_ids, list):
        return outcomes
    still_active: list[str] = []
    for duel_id in duel_ids:
        raw_s = storage.get_meta(_session_key(str(duel_id)))
        if not raw_s:
            continue
        try:
            session = DuelGridSession.from_dict(json.loads(raw_s))
        except Exception:
            continue
        if session.finished:
            continue
        deadline = _parse_deadline(session.turn_deadline)
        if deadline is None or now <= deadline:
            still_active.append(str(duel_id))
            continue
        active = session.active_player()
        player = storage.get_character(active, refresh_energy=False)
        session.log.append(f"Тайм-аут хода {h(player.nickname) if player else active}.")
        _advance_turn(session)
        _move_mutants(session)
        session.log.extend(_mutants_attack(session, storage))
        done = _check_hp_end(storage, session)
        if done:
            outcomes.append((active, done))
            outcomes.append((session.opponent_of(active), done))
            continue
        session.turn_deadline = _deadline_iso()
        save_duel_session(storage, session)
        still_active.append(str(duel_id))
        outcomes.append(
            (
                active,
                ActionResult(True, "Время вышло — ход пропущен.", payload={"duel_active": True}),
            )
        )
    storage.set_meta("duel:grid:active_ids", json.dumps(still_active, ensure_ascii=False))
    return outcomes


def register_active_duel(storage: Storage, duel_id: str) -> None:
    raw = storage.get_meta("duel:grid:active_ids")
    ids: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                ids = [str(x) for x in parsed]
        except json.JSONDecodeError:
            ids = []
    if duel_id not in ids:
        ids.append(duel_id)
    storage.set_meta("duel:grid:active_ids", json.dumps(ids, ensure_ascii=False))


def unregister_active_duel(storage: Storage, duel_id: str) -> None:
    raw = storage.get_meta("duel:grid:active_ids")
    if not raw:
        return
    try:
        ids = [str(x) for x in json.loads(raw) if str(x) != duel_id]
    except json.JSONDecodeError:
        ids = []
    storage.set_meta("duel:grid:active_ids", json.dumps(ids, ensure_ascii=False))


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_duel_frame(
    storage: Storage,
    session: DuelGridSession,
    viewer_id: int,
) -> bytes:
    cell = 72
    grid = session.grid
    grid_px = grid * cell
    margin = 20
    panel_w = 300
    width = margin + grid_px + 16 + panel_w + margin
    height = max(margin + grid_px + margin, 640)
    canvas = Image.new("RGBA", (width, height), (18, 20, 22, 255))
    draw = ImageDraw.Draw(canvas)
    for gy in range(grid):
        for gx in range(grid):
            left = margin + gx * cell
            top = margin + gy * cell
            tone = 62 + ((gx * 17 + gy * 23) % 18)
            draw.rectangle((left, top, left + cell - 1, top + cell - 1), fill=(tone, tone - 4, tone - 8))
            draw.rectangle((left, top, left + cell - 1, top + cell - 1), outline=(28, 30, 34), width=1)
    for cx, cy in session.cover:
        left = margin + cx * cell + 6
        top = margin + cy * cell + 6
        draw.rounded_rectangle(
            (left, top, left + cell - 12, top + cell - 12),
            radius=8,
            fill=(70, 62, 48, 220),
            outline=(110, 95, 70),
            width=2,
        )
        draw.text((left + 8, top + cell // 2 - 16), "УКР", fill=(180, 160, 120))
    for mx, my in session.mutants:
        cx = margin + mx * cell + cell // 2
        cy = margin + my * cell + cell // 2
        draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(60, 90, 45), outline=(130, 200, 80), width=2)
    colors = {session.challenger_id: (80, 200, 255), session.target_id: (255, 120, 90)}
    for pid in (session.challenger_id, session.target_id):
        px, py = session.pos(pid)
        cx = margin + px * cell + cell // 2
        cy = margin + py * cell + cell // 2
        ring = colors.get(pid, (200, 200, 200))
        if pid == session.active_player():
            draw.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), outline=(255, 230, 80), width=3)
        token = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        td = ImageDraw.Draw(token)
        td.ellipse((4, 4, 60, 60), fill=(ring[0] // 2, ring[1] // 2, ring[2] // 2))
        _paste_circle(canvas, token, cx, cy, 52, ring_color=ring, ring_width=3)
    pl = margin + grid_px + 16
    draw.rounded_rectangle((pl, margin, width - margin, height - margin), radius=14, fill=(44, 46, 50), outline=(90, 94, 100), width=2)
    body = _load_font(16)
    small = _load_font(13)
    y = margin + 16
    draw.text((pl + 14, y), "⚔️ Тактическая дуэль", fill=(240, 240, 240), font=body)
    y += 28
    for pid in (session.challenger_id, session.target_id):
        ch = storage.get_character(pid, refresh_energy=False)
        name = ch.nickname if ch else str(pid)
        hp = session.hp.get(str(pid), 0)
        mark = " ◀ ход" if pid == session.active_player() else ""
        draw.text((pl + 14, y), f"{h(name)}{mark}: HP {hp}", fill=(210, 210, 210), font=small)
        y += 20
    y += 8
    for line in session.log[-8:]:
        draw.text((pl + 14, y), line[:42], fill=(170, 170, 170), font=small)
        y += 16
    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
