from __future__ import annotations

import json
import random
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.artifact_hunt import (
    FONT_CANDIDATES,
    PROJECT_ROOT,
    _cover_crop,
    _draw_cell,
    _glow,
    _load_font,
    _load_hunt_map,
    _load_location_thumb,
    _paste_circle,
)
from app.game_logic import (
    ActionResult,
    ITEM_LABELS,
    STASH_CONSUMABLE_KEYS,
    STASH_GEAR_TIER_CHANCES,
    STASH_ARMOR_BY_TIER,
    STASH_WEAPON_BY_TIER,
    STASH_CONSUMABLE_DROP_CHANCE,
    STASH_CONSUMABLE_DROP_CHANCE_BY_KEY,
    _is_dead,
    _dead_block_text,
    effective_max_health,
    is_traveling,
    travel_block_text,
)
from app.storage import Storage


STASH_META_PREFIX = "stash_hunt:"
STASH_GRID_SIZE = 15
STASH_MAX_MOVES = 60
STASH_RAD_EVERY_STEPS = 3
STASH_RAD_PER_TICK = 1
STASH_MINUTE_MOVES = 10
STASH_RAD_PER_MINUTE = 5
STASH_AMBUSH_CHANCE_MIN = 2
STASH_AMBUSH_CHANCE_MAX = 5
STASH_COORDINATE_PRICE = 3500
STASH_COORDINATE_KEY = "stash_coordinates"

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

AMBUSH_TYPES: tuple[tuple[str, str, int], ...] = (
    ("Слепые псы", "слепые псы", 8),
    ("Псевдособаки", "псевдособаки", 10),
    ("Кабаны", "кабаны", 7),
    ("Бандиты", "бандиты", 12),
    ("Снорк", "снорк", 15),
    ("Кровосос", "кровосос", 18),
)


@dataclass
class StashSession:
    location: str
    player: tuple[int, int]
    stash: tuple[int, int]
    moves: int
    steps: int
    rad_gained: int
    grid: int = STASH_GRID_SIZE
    max_moves: int = STASH_MAX_MOVES
    found: bool = False
    source: str = "found"

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "player": list(self.player),
            "stash": list(self.stash),
            "moves": self.moves,
            "steps": self.steps,
            "rad_gained": self.rad_gained,
            "grid": self.grid,
            "max_moves": self.max_moves,
            "found": self.found,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StashSession:
        return cls(
            location=str(raw.get("location") or ""),
            player=(int(raw["player"][0]), int(raw["player"][1])),
            stash=(int(raw["stash"][0]), int(raw["stash"][1])),
            moves=int(raw.get("moves") or 0),
            steps=int(raw.get("steps") or 0),
            rad_gained=int(raw.get("rad_gained") or 0),
            grid=int(raw.get("grid") or STASH_GRID_SIZE),
            max_moves=int(raw.get("max_moves") or STASH_MAX_MOVES),
            found=bool(raw.get("found")),
            source=str(raw.get("source") or "found"),
        )


def _stash_meta_key(telegram_id: int) -> str:
    return f"{STASH_META_PREFIX}{int(telegram_id)}"


def get_stash_session(storage: Storage, telegram_id: int) -> StashSession | None:
    raw = storage.get_meta(_stash_meta_key(telegram_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return StashSession.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_stash_session(storage: Storage, telegram_id: int, session: StashSession) -> None:
    storage.set_meta(_stash_meta_key(telegram_id), json.dumps(session.to_dict(), ensure_ascii=False))


def clear_stash_session(storage: Storage, telegram_id: int) -> None:
    storage.delete_meta(_stash_meta_key(telegram_id))


def _chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _random_free_cell(grid: int, forbidden: set[tuple[int, int]]) -> tuple[int, int]:
    free = [(x, y) for x in range(grid) for y in range(grid) if (x, y) not in forbidden]
    if not free:
        return (0, 0)
    return random.choice(free)


def _build_stash_session(character: Any, source: str) -> StashSession:
    grid = STASH_GRID_SIZE
    player = (random.randrange(grid), random.randrange(grid))
    forbidden: set[tuple[int, int]] = {player}
    stash = _random_free_cell(grid, forbidden)
    while _chebyshev(player, stash) < grid // 3:
        stash = _random_free_cell(grid, forbidden)
    forbidden.add(stash)
    return StashSession(
        location=character.location,
        player=player,
        stash=stash,
        moves=0,
        steps=0,
        rad_gained=0,
        source=source,
    )


def stash_status_caption(session: StashSession, character: Any | None = None) -> str:
    lines = [
        f"Поиск схрона — {session.location}",
        f"Ход {session.moves}/{session.max_moves} · рад +{session.rad_gained}",
    ]
    if character is not None:
        lines.append(
            f"HP {character.health}/{effective_max_health(character)} · "
            f"☢ {character.radiation} · ⚡ {character.energy}"
        )
    lines.append("Найди схрон на карте. Берегись мутантов и бандитов.")
    return "\n".join(lines)


def start_stash_hunt(storage: Storage, telegram_id: int, *, source: str = "found") -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    blocked = travel_block_text(player)
    if blocked:
        return ActionResult(False, blocked)
    if is_traveling(player):
        return ActionResult(False, "Нельзя искать схроны в пути.")

    existing = get_stash_session(storage, telegram_id)
    if existing is not None and not existing.found:
        image = render_stash_frame(existing, player)
        return ActionResult(
            False,
            "У тебя уже идёт поиск схрона. Продолжай с карты.",
            payload={"stash_image": image, "stash_active": True, "caption": stash_status_caption(existing, player)},
        )

    # buy_item already deducted the price before calling us; no double-charge.

    session = _build_stash_session(player, source)
    save_stash_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = render_stash_frame(session, player)
    caption = stash_status_caption(session, player)
    if source == "buy":
        note = f"Координаты схрона куплены за {STASH_COORDINATE_PRICE} RU."
    else:
        note = "Ты нашёл координаты схрона! Ищи на карте."
    return ActionResult(
        True,
        note,
        payload={"stash_image": image, "stash_active": True, "caption": caption, "stash_started": True},
    )


def abandon_stash_hunt(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_stash_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активного поиска схрона нет.")
    clear_stash_session(storage, telegram_id)
    return ActionResult(
        True,
        f"Ты бросил поиск схрона на «{session.location}».\n"
        f"Ходов потрачено: {session.moves}, рад +{session.rad_gained}.",
        payload={"stash_active": False},
    )


def _roll_stash_loot(storage: Storage, telegram_id: int, location: str) -> list[str]:
    loot: list[str] = []
    if random.random() * 100 < STASH_CONSUMABLE_DROP_CHANCE:
        consumable = random.choice(STASH_CONSUMABLE_KEYS)
        if random.random() * 100 < STASH_CONSUMABLE_DROP_CHANCE_BY_KEY.get(consumable, 100):
            loot.append(consumable)
    gear_roll = random.random() * 100
    cumulative = 0.0
    for tier, chance in STASH_GEAR_TIER_CHANCES:
        cumulative += chance
        if gear_roll < cumulative:
            if random.random() < 0.5:
                pool = STASH_WEAPON_BY_TIER.get(tier, ())
            else:
                pool = STASH_ARMOR_BY_TIER.get(tier, ())
            if pool:
                loot.append(random.choice(pool))
            break
    if not loot:
        loot.append(random.choice(STASH_CONSUMABLE_KEYS))
    return loot


def _finish_stash_success(storage: Storage, telegram_id: int, session: StashSession) -> ActionResult:
    clear_stash_session(storage, telegram_id)
    loot_keys = _roll_stash_loot(storage, telegram_id, session.location)
    labels: list[str] = []
    for key in loot_keys:
        storage.add_item(telegram_id, key, 1)
        label = ITEM_LABELS.get(key, key)
        labels.append(f"{label} x1")
    storage.add_player_stat(telegram_id, "quests_completed", 1)
    loot_text = ", ".join(labels)
    return ActionResult(
        True,
        f"Схрон найден на «{session.location}»!\n"
        f"Содержимое: {loot_text}.\n"
        f"Ходов: {session.moves}, рад +{session.rad_gained}.",
        payload={"stash_active": False, "stash_done": True, "loot": loot_keys},
    )


def _try_ambush(storage: Storage, telegram_id: int, location: str) -> dict[str, Any] | None:
    chance = random.randint(STASH_AMBUSH_CHANCE_MIN, STASH_AMBUSH_CHANCE_MAX)
    if random.random() * 100 >= chance:
        return None
    name, short, enemy_power = random.choice(AMBUSH_TYPES)
    character = storage.get_character(telegram_id, refresh_energy=False)
    if character is None:
        return None
    player_power = max(1, int(character.gear_power))
    if player_power >= enemy_power * 2:
        damage = random.randint(3, 8)
    elif player_power >= enemy_power:
        damage = random.randint(8, 18)
    else:
        damage = random.randint(15, 30)
    storage.change_health(telegram_id, -damage)
    survived = True
    updated = storage.get_character(telegram_id, refresh_energy=False)
    if updated is not None and updated.health <= 0:
        survived = False
    return {
        "name": name,
        "short": short,
        "damage": damage,
        "survived": survived,
    }


def move_stash_hunt(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_stash_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Сначала начни поиск схрона.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        clear_stash_session(storage, telegram_id)
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        clear_stash_session(storage, telegram_id)
        return ActionResult(False, _dead_block_text())

    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return ActionResult(False, "Некорректное направление.")
    nx = session.player[0] + delta[0]
    ny = session.player[1] + delta[1]
    if not (0 <= nx < session.grid and 0 <= ny < session.grid):
        image = render_stash_frame(session, player)
        return ActionResult(
            False,
            "Край карты — туда не пройти.",
            payload={"stash_image": image, "stash_active": True, "caption": stash_status_caption(session, player)},
        )

    session.player = (nx, ny)
    session.moves += 1
    session.steps += 1

    rad_add = 0
    if session.steps % STASH_RAD_EVERY_STEPS == 0:
        rad_add += STASH_RAD_PER_TICK
    if session.moves % STASH_MINUTE_MOVES == 0:
        rad_add += STASH_RAD_PER_MINUTE
    if rad_add > 0:
        storage.adjust_survival(telegram_id, radiation_delta=rad_add)
        session.rad_gained += rad_add

    ambush = _try_ambush(storage, telegram_id, session.location)
    if ambush is not None and not ambush["survived"]:
        clear_stash_session(storage, telegram_id)
        return ActionResult(
            False,
            f"На тебя напали — {ambush['name']}!\n"
            f"Урон: {ambush['damage']} HP. Ты погиб в Зоне.\n"
            "Респавн из инвентаря (мутанты обшарят рюкзак).",
            payload={"stash_active": False, "stash_dead": True},
        )

    dist = _chebyshev(session.player, session.stash)
    if dist <= 1:
        return _finish_stash_success(storage, telegram_id, session)

    if session.moves >= session.max_moves:
        clear_stash_session(storage, telegram_id)
        return ActionResult(
            False,
            f"Время поиска вышло на «{session.location}».\n"
            f"Схрон не найден. Рад +{session.rad_gained}.",
            payload={"stash_active": False, "stash_done": True},
        )

    save_stash_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = render_stash_frame(session, player)

    if dist <= 3:
        note = "Рядом! Схрон где-то совсем близко."
    elif dist <= 6:
        note = "Тёплый след… продолжай искать."
    elif dist <= 10:
        note = "Холодно. Схрон ещё далеко."
    else:
        note = "Очень далеко от схрона."
    if rad_add:
        note += f" Рад +{rad_add}."
    if ambush is not None:
        note += f" ⚠ Нападение: {ambush['name']}! Урон −{ambush['damage']} HP."

    return ActionResult(
        True,
        note,
        payload={
            "stash_image": image,
            "stash_active": True,
            "caption": stash_status_caption(session, player),
            "move_note": note,
        },
    )


def render_stash_frame(session: StashSession, character: Any | None = None) -> bytes:
    cell = 44
    grid = session.grid
    grid_px = grid * cell
    margin = 20
    panel_w = 280
    width = margin + grid_px + 16 + panel_w + margin
    height = max(margin + grid_px + margin, 720)
    canvas = Image.new("RGBA", (width, height), (16, 18, 20, 255))
    draw = ImageDraw.Draw(canvas)

    field = (margin - 6, margin - 6, margin + grid_px + 6, margin + grid_px + 6)
    draw.rounded_rectangle(field, radius=10, fill=(34, 36, 40, 255), outline=(70, 74, 80), width=2)

    loc_bg = _load_location_thumb(session.location)
    if loc_bg is not None:
        field_img = _cover_crop(loc_bg, grid_px, grid_px).convert("RGBA")
        field_img.putalpha(225)
        canvas.paste(field_img, (margin, margin), field_img)

    for gy in range(grid):
        for gx in range(grid):
            left = margin + gx * cell
            top = margin + gy * cell
            if loc_bg is None:
                _draw_cell(canvas, left, top, cell)
            else:
                overlay = Image.new("RGBA", (cell, cell), (12, 14, 16, 28))
                canvas.alpha_composite(overlay, (left, top))
                ImageDraw.Draw(canvas).rectangle(
                    (left, top, left + cell - 1, top + cell - 1),
                    outline=(28, 30, 32),
                    width=1,
                )

    px, py = session.player
    pcx = margin + px * cell + cell // 2
    pcy = margin + py * cell + cell // 2
    token = None
    if character is not None:
        try:
            from app.avatar_render import render_avatar

            token = render_avatar(character, width=80, height=80)
        except Exception:
            token = None
    if token is None:
        token = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
        td = ImageDraw.Draw(token)
        td.ellipse((10, 5, 70, 65), fill=(75, 85, 65), outline=(30, 35, 28), width=2)
        td.ellipse((22, 18, 58, 42), fill=(40, 48, 40))
        td.rectangle((22, 60, 58, 78), fill=(95, 75, 50))
    _paste_circle(canvas, token, pcx, pcy, 34, ring_color=(72, 220, 90), ring_width=3)

    dist = _chebyshev(session.player, session.stash)
    if dist <= 3:
        _glow(canvas, margin + session.stash[0] * cell + cell // 2,
              margin + session.stash[1] * cell + cell // 2, (255, 200, 50), radius=16)

    pl = margin + grid_px + 16
    pr = width - margin
    pt = margin - 6
    pb = height - margin + 6
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((pl, pt, pr, pb), radius=14, fill=(48, 50, 54, 255), outline=(100, 104, 110), width=2)

    thumb = (pl + 12, pt + 10, pr - 12, pt + 100)
    loc_img = _load_location_thumb(session.location)
    if loc_img is not None:
        from app.artifact_hunt import _paste_rounded

        _paste_rounded(canvas, loc_img, thumb, radius=8)
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=8, outline=(110, 120, 100), width=2)
    else:
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=8, fill=(30, 34, 28), outline=(90, 100, 80), width=2)

    title_font = _load_font(20)
    body = _load_font(16)
    small = _load_font(13)
    loc_font = title_font if len(session.location) <= 14 else _load_font(16)
    draw.text((pl + 14, pt + 106), session.location, fill=(245, 245, 245), font=loc_font)
    draw.text((pl + 14, pt + 132), "Поиск схрона", fill=(200, 180, 120), font=body)

    info_y = pt + 162
    draw.text((pl + 14, info_y), f"Ход {session.moves}/{session.max_moves}", fill=(200, 200, 200), font=body)
    draw.text((pl + 14, info_y + 24), f"Рад +{session.rad_gained}", fill=(200, 160, 120), font=small)

    if dist <= 3:
        hint = "🔥 Схрон очень близко!"
    elif dist <= 6:
        hint = "🌡 Тёплый след"
    elif dist <= 10:
        hint = "❄ Холодно"
    else:
        hint = "🧊 Очень далеко"
    draw.text((pl + 14, info_y + 48), hint, fill=(220, 220, 200), font=small)

    hp = int(character.health) if character else 0
    max_hp = int(effective_max_health(character)) if character else 100
    energy = int(character.energy) if character else 0
    max_energy = int(character.max_energy) if character else 100
    rad = int(character.radiation) if character else 0

    bar_top = info_y + 80
    draw.rounded_rectangle((pl + 12, bar_top, pr - 12, bar_top + 24), radius=6, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 36) * (hp / max(1, max_hp)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 14, bar_top + 2, pl + 14 + fill_w, bar_top + 22), radius=4, fill=(200, 60, 50))
    draw.text((pl + 16, bar_top + 4), f"HP {hp}/{max_hp}", fill=(255, 255, 255), font=small)

    draw.rounded_rectangle((pl + 12, bar_top + 34, pr - 12, bar_top + 58), radius=6, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 36) * min(1.0, rad / 100))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 14, bar_top + 36, pl + 14 + fill_w, bar_top + 56), radius=4, fill=(180, 200, 40))
    draw.text((pl + 16, bar_top + 38), f"RAD {rad}", fill=(255, 255, 255), font=small)

    draw.rounded_rectangle((pl + 12, bar_top + 68, pr - 12, bar_top + 92), radius=6, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 36) * (energy / max(1, max_energy)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 14, bar_top + 70, pl + 14 + fill_w, bar_top + 90), radius=4, fill=(50, 120, 210))
    draw.text((pl + 16, bar_top + 72), f"EN {energy}/{max_energy}", fill=(255, 255, 255), font=small)

    draw.text((pl + 14, pb - 42), "Ищи схрон на карте", fill=(210, 210, 210), font=small)
    draw.text((pl + 14, pb - 24), "Стрелки — ход, кнопка — уйти", fill=(190, 190, 190), font=small)

    out = canvas.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def try_random_stash_coordinates(storage: Storage, telegram_id: int) -> bool:
    """Small chance to find stash coordinates during normal play (called from hunt)."""
    if random.random() * 100 < 3:
        existing = get_stash_session(storage, telegram_id)
        if existing is None or existing.found:
            session = _build_stash_session(
                storage.get_character(telegram_id, refresh_energy=False),
                "found",
            )
            save_stash_session(storage, telegram_id, session)
            return True
    return False
