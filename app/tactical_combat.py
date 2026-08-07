"""Общая логика тактической стрельбы: дальность оружия, луч, укрытия."""

from __future__ import annotations

import random
from typing import Callable

from app.game_logic import _weapon_rating, apply_incoming_damage
from app.storage import Character

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

COVER_HIT_CHANCE = 0.5
BASE_COVER_ARMOR_BONUS = 5
NPC_MOVE_CHANCE = 0.25

# Пистолеты и дробовики — 1 клетка.
_PISTOL_SHOTGUN = frozenset(
    {"ПМ", "Фора-12", "Обрез", "Гадюка-5", "Чейзер-13", "АКС-74У", "СПАС-12"}
)
# Автоматы — 2 клетки.
_ASSAULT = frozenset({"АК-74", "ТРс-301", "ИЛ86", "АН-94", "ГП37", "РП-74"})
# Снайперки — 3 клетки.
_SNIPER = frozenset({"Винтарь ВС", "СВДм-2"})
_GAUSS = frozenset({"Гаусс-пушка", "РПК «Чемпион Зоны»"})

# Оружие для NPC-защитников (рандом при спавне).
NPC_WEAPONS = ("ПМ", "Обрез", "АК-74", "СПАС-12", "СВДм-2", "Гаусс-пушка")


def weapon_shoot_range(weapon_name: str) -> int:
    """Пистолеты/дробовики=1, автоматы=2, снайперки=3, гаус=4, нож=1."""
    if weapon_name == "Нож":
        return 1
    if weapon_name in _GAUSS:
        return 4
    if weapon_name in _SNIPER:
        return 3
    if weapon_name in _ASSAULT:
        return 2
    if weapon_name in _PISTOL_SHOTGUN:
        return 1
    rating = _weapon_rating(weapon_name)
    if rating <= 3:
        return 1
    if rating <= 6:
        return 2
    if rating <= 8:
        return 3
    return 4


def ray_cast_first_hit(
    origin: tuple[int, int],
    direction: str,
    *,
    grid: int,
    max_range: int,
    blockers: set[tuple[int, int]],
    targets: dict[tuple[int, int], str],
) -> tuple[tuple[int, int] | None, str]:
    """Луч по карте. Возвращает (клетка, kind) или (None, '')."""
    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return None, ""
    for step in range(1, max_range + 1):
        cell = (origin[0] + delta[0] * step, origin[1] + delta[1] * step)
        if not (0 <= cell[0] < grid and 0 <= cell[1] < grid):
            break
        if cell in targets:
            return cell, targets[cell]
        if cell in blockers:
            break
    return None, ""


def cover_blocks_shot(cell: tuple[int, int], cover: set[tuple[int, int]]) -> bool:
    return cell in cover and random.random() > COVER_HIT_CHANCE


def extra_armor_from_cell(
    cell: tuple[int, int],
    base_cover: set[tuple[int, int]],
    *,
    bonus: int = BASE_COVER_ARMOR_BONUS,
) -> int:
    return bonus if cell in base_cover else 0


def apply_armor_bonus(raw_damage: int, extra_armor: int, *, min_damage: int = 1) -> int:
    return max(min_damage, raw_damage - extra_armor)


def random_cardinal_direction() -> str:
    return random.choice(list(MOVE_DELTAS.keys()))


def random_hostile_shots(
    hostiles: list[tuple[int, int]],
    weapons: list[str],
    *,
    grid: int,
    player_positions: dict[int, tuple[int, int]],
    player_hp: dict[str, int],
    player_characters: dict[int, Character | None],
    cover: set[tuple[int, int]],
    base_cover: set[tuple[int, int]],
    damage_fn: Callable[[str], int],
) -> list[str]:
    """«Танчики»: каждый враждебный юнит с шансом стреляет в случайном направлении."""
    notes: list[str] = []
    if not hostiles:
        return notes
    for idx, pos in enumerate(hostiles):
        if random.random() > 0.55:
            continue
        weapon = weapons[idx] if idx < len(weapons) else "ПМ"
        direction = random_cardinal_direction()
        rng = weapon_shoot_range(weapon)
        targets = {player_positions[pid]: str(pid) for pid in player_positions}
        hit_cell, hit_kind = ray_cast_first_hit(
            pos,
            direction,
            grid=grid,
            max_range=rng,
            blockers=cover,
            targets=targets,
        )
        if hit_cell is None:
            continue
        if cover_blocks_shot(hit_cell, cover):
            notes.append("Враг промахнулся — цель за укрытием.")
            continue
        pid = int(hit_kind)
        raw = damage_fn(weapon)
        extra = extra_armor_from_cell(hit_cell, base_cover)
        pre = apply_armor_bonus(raw, extra)
        character = player_characters.get(pid)
        if character is not None:
            dmg = apply_incoming_damage(pre, character, min_damage=1)
        else:
            dmg = pre
        key = str(pid)
        player_hp[key] = max(0, player_hp.get(key, 0) - dmg)
        notes.append(f"Вражеский огонь ({weapon}): −{dmg} HP.")
    return notes


def move_toward(pos: tuple[int, int], target: tuple[int, int], steps: int = 1) -> tuple[int, int]:
    """Движение по манхэттену на steps клеток (только 90°)."""
    x, y = pos
    for _ in range(steps):
        dx = 0 if x == target[0] else (1 if target[0] > x else -1)
        dy = 0 if y == target[1] else (1 if target[1] > y else -1)
        if abs(target[0] - x) >= abs(target[1] - y):
            x += dx
        else:
            y += dy
    return x, y


def spawn_edge_positions(grid: int, count: int, forbidden: set[tuple[int, int]]) -> list[tuple[int, int]]:
    edges: list[tuple[int, int]] = []
    for x in range(grid):
        for y in (0, grid - 1):
            cell = (x, y)
            if cell not in forbidden:
                edges.append(cell)
    for y in range(1, grid - 1):
        for x in (0, grid - 1):
            cell = (x, y)
            if cell not in forbidden:
                edges.append(cell)
    random.shuffle(edges)
    return edges[:count]


def manhattan_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def iter_adjacent_cells(pos: tuple[int, int], grid: int):
    for dx, dy in MOVE_DELTAS.values():
        nx, ny = pos[0] + dx, pos[1] + dy
        if 0 <= nx < grid and 0 <= ny < grid:
            yield (nx, ny)


def best_step_toward(
    origin: tuple[int, int],
    target: tuple[int, int],
    *,
    grid: int,
    blocked: set[tuple[int, int]],
    forbidden: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """Один шаг к цели, не заходя на forbidden (клетки игроков)."""
    forbidden = forbidden or set()
    best = origin
    best_dist = manhattan_distance(origin, target)
    for nxt in iter_adjacent_cells(origin, grid):
        if nxt in forbidden or nxt in blocked:
            continue
        dist_new = manhattan_distance(nxt, target)
        if dist_new < best_dist:
            best_dist = dist_new
            best = nxt
    return best
