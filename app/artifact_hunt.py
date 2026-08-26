from __future__ import annotations

import json
import random
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.game_logic import (
    ARTIFACT_DETECTORS,
    ARTIFACT_JUNK_KEYS,
    ARTIFACT_SEARCH_ENERGY_COST,
    ITEM_LABELS,
    MAP_TRAVEL_POINTS,
    ActionResult,
    _apply_active_survival,
    _dead_block_text,
    _is_dead,
    describe_location_artifact_spawns,
    effective_max_health,
    is_traveling,
    roll_location_artifact_drop,
    travel_block_text,
)
from app.mission_icons import (
    ANOMALY_ICON_KEY,
    MISSION_ICON_GRID_DIAMETER,
    mission_icon_image,
)
from app.storage import Character, Storage


HUNT_META_PREFIX = "artifact_hunt:"
HUNT_ACTIVE_IDS_META = "artifact_hunt:active_ids"
HUNT_GRID_SIZE = 6
HUNT_MAX_MOVES = 24
HUNT_RAD_EVERY_STEPS = 2
HUNT_RAD_PER_TICK = 1
HUNT_MINUTE_MOVES = 6
HUNT_RAD_PER_MINUTE = 5

# Лучший детектор → меньше кружков до находки.
DETECTOR_CIRCLES_NEEDED: dict[str, int] = {
    "detector_otklik": 5,
    "detector_medved": 4,
    "detector_veles": 3,
    "detector_svarog": 2,
}

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
LOCAL_NOTO_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"
FONT_CANDIDATES = (
    str(LOCAL_NOTO_FONT_PATH),
    str(LOCAL_FONT_PATH),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


@dataclass
class HuntSession:
    location: str
    detector_key: str
    detector_name: str
    circles_needed: int
    circles_filled: int
    player: tuple[int, int]
    artifact: tuple[int, int]
    anomalies: list[tuple[int, int]]
    moves: int
    steps: int
    rad_gained: int
    grid: int = HUNT_GRID_SIZE
    max_moves: int = HUNT_MAX_MOVES

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "detector_key": self.detector_key,
            "detector_name": self.detector_name,
            "circles_needed": self.circles_needed,
            "circles_filled": self.circles_filled,
            "player": list(self.player),
            "artifact": list(self.artifact),
            "anomalies": [list(p) for p in self.anomalies],
            "moves": self.moves,
            "steps": self.steps,
            "rad_gained": self.rad_gained,
            "grid": self.grid,
            "max_moves": self.max_moves,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> HuntSession:
        return cls(
            location=str(raw.get("location") or ""),
            detector_key=str(raw.get("detector_key") or ""),
            detector_name=str(raw.get("detector_name") or ""),
            circles_needed=int(raw.get("circles_needed") or 5),
            circles_filled=int(raw.get("circles_filled") or 0),
            player=(int(raw["player"][0]), int(raw["player"][1])),
            artifact=(int(raw["artifact"][0]), int(raw["artifact"][1])),
            anomalies=[(int(p[0]), int(p[1])) for p in (raw.get("anomalies") or [])],
            moves=int(raw.get("moves") or 0),
            steps=int(raw.get("steps") or 0),
            rad_gained=int(raw.get("rad_gained") or 0),
            grid=int(raw.get("grid") or HUNT_GRID_SIZE),
            max_moves=int(raw.get("max_moves") or HUNT_MAX_MOVES),
        )


def _hunt_meta_key(telegram_id: int) -> str:
    return f"{HUNT_META_PREFIX}{int(telegram_id)}"


def get_hunt_session(storage: Storage, telegram_id: int) -> HuntSession | None:
    raw = storage.get_meta(_hunt_meta_key(telegram_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return HuntSession.from_dict(data)
    except Exception:
        return None


def _register_active_hunt(storage: Storage, telegram_id: int) -> None:
    raw = storage.get_meta(HUNT_ACTIVE_IDS_META)
    ids: list[int] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                ids = [int(x) for x in parsed]
        except json.JSONDecodeError:
            ids = []
    tid = int(telegram_id)
    if tid not in ids:
        ids.append(tid)
    storage.set_meta(HUNT_ACTIVE_IDS_META, json.dumps(ids, ensure_ascii=False))


def _unregister_active_hunt(storage: Storage, telegram_id: int) -> None:
    raw = storage.get_meta(HUNT_ACTIVE_IDS_META)
    if not raw:
        return
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return
        ids = [int(x) for x in parsed if int(x) != int(telegram_id)]
    except json.JSONDecodeError:
        return
    if ids:
        storage.set_meta(HUNT_ACTIVE_IDS_META, json.dumps(ids, ensure_ascii=False))
    else:
        storage.delete_meta(HUNT_ACTIVE_IDS_META)


def list_active_hunt_player_ids(storage: Storage) -> list[int]:
    raw = storage.get_meta(HUNT_ACTIVE_IDS_META)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
    except json.JSONDecodeError:
        pass
    return []


def save_hunt_session(storage: Storage, telegram_id: int, session: HuntSession) -> None:
    storage.set_meta(_hunt_meta_key(telegram_id), json.dumps(session.to_dict(), ensure_ascii=False))
    _register_active_hunt(storage, telegram_id)


def clear_hunt_session(storage: Storage, telegram_id: int) -> None:
    storage.delete_meta(_hunt_meta_key(telegram_id))
    _unregister_active_hunt(storage, telegram_id)


def _pick_best_detector(character: Character) -> tuple[str, str, int] | None:
    chosen: tuple[str, str, int] | None = None
    for detector in ARTIFACT_DETECTORS:
        key, name, base = detector
        if int(character.inventory.get(key, 0)) > 0:
            chosen = (key, name, base)
    return chosen


def location_anomaly_count(location: str) -> int:
    """Чем севернее (меньше Y на карте) — тем больше аномалий."""
    point = MAP_TRAVEL_POINTS.get(location)
    if point is None:
        return 5
    _x, y = point
    if y >= 450:
        return 3
    if y >= 300:
        return 5
    if y >= 180:
        return 7
    return 9


def _chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _signal_gain(player: tuple[int, int], artifact: tuple[int, int]) -> int:
    dist = _chebyshev(player, artifact)
    if dist <= 1:
        return 2
    if dist == 2:
        return 1
    return 0


def _random_free_cell(
    grid: int,
    forbidden: set[tuple[int, int]],
) -> tuple[int, int]:
    free = [(x, y) for x in range(grid) for y in range(grid) if (x, y) not in forbidden]
    if not free:
        return 0, 0
    return random.choice(free)


def _build_session(character: Character, detector_key: str, detector_name: str) -> HuntSession:
    grid = HUNT_GRID_SIZE
    anomaly_n = location_anomaly_count(character.location)
    player = (random.randrange(grid), random.randrange(grid))
    forbidden: set[tuple[int, int]] = {player}
    artifact = _random_free_cell(grid, forbidden)
    forbidden.add(artifact)
    anomalies: list[tuple[int, int]] = []
    for _ in range(anomaly_n):
        cell = _random_free_cell(grid, forbidden)
        anomalies.append(cell)
        forbidden.add(cell)
    circles_needed = DETECTOR_CIRCLES_NEEDED.get(detector_key, 5)
    session = HuntSession(
        location=character.location,
        detector_key=detector_key,
        detector_name=detector_name,
        circles_needed=circles_needed,
        circles_filled=0,
        player=player,
        artifact=artifact,
        anomalies=anomalies,
        moves=0,
        steps=0,
        rad_gained=0,
    )
    # Стартовый замер сигнала на месте появления.
    session.circles_filled = min(
        session.circles_needed,
        _signal_gain(session.player, session.artifact),
    )
    return session


def hunt_status_caption(session: HuntSession, character: Character | None = None) -> str:
    filled = min(session.circles_filled, session.circles_needed)
    dots = "●" * filled + "○" * max(0, session.circles_needed - filled)
    lines = [
        f"Детектор «{session.detector_name}»: {dots} ({filled}/{session.circles_needed})",
        f"Ход {session.moves}/{session.max_moves} · рад за вылазку +{session.rad_gained}",
    ]
    if character is not None:
        lines.append(
            f"HP {character.health}/{effective_max_health(character)} · "
            f"☢ {character.radiation} · ⚡ {character.energy}"
        )
    lines.append("Аномалия = смерть. Схрон не трогают.")
    return "\n".join(lines)


def start_artifact_hunt(storage: Storage, telegram_id: int) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    blocked = travel_block_text(player)
    if blocked:
        return ActionResult(False, blocked)
    if is_traveling(player):
        return ActionResult(False, "Нельзя искать арты в пути.")
    if get_hunt_session(storage, telegram_id) is not None:
        session = get_hunt_session(storage, telegram_id)
        assert session is not None
        image = render_hunt_frame(session, player)
        return ActionResult(
            True,
            "У тебя уже идёт вылазка. Продолжай с поля.",
            payload={"hunt_image": image, "hunt_active": True, "caption": hunt_status_caption(session, player)},
        )

    chosen = _pick_best_detector(player)
    if chosen is None:
        return ActionResult(
            False,
            "У тебя нет детектора. Купи его у торговца в разделе снаряжения.",
        )
    detector_key, detector_name, _base = chosen
    energy_cost = ARTIFACT_SEARCH_ENERGY_COST
    if not storage.spend_energy(telegram_id, energy_cost):
        return ActionResult(False, f"Не хватает энергии для поиска артов (нужно {energy_cost}).")

    session = _build_session(player, detector_key, detector_name)
    save_hunt_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = render_hunt_frame(session, player)
    caption = hunt_status_caption(session, player)
    return ActionResult(
        True,
        f"Энергия −{energy_cost}.",
        payload={
            "hunt_image": image,
            "hunt_active": True,
            "caption": caption,
            "hunt_started": True,
        },
    )


def abandon_artifact_hunt(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_hunt_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активной вылазки нет.")
    clear_hunt_session(storage, telegram_id)
    return ActionResult(
        True,
        f"Ты свалил с поля «{session.location}» без арта.\n"
        f"Ходов потрачено: {session.moves}, рад за вылазку: +{session.rad_gained}.",
        payload={"hunt_active": False},
    )


def _finish_success(storage: Storage, telegram_id: int, session: HuntSession) -> ActionResult:
    clear_hunt_session(storage, telegram_id)
    player = storage.get_character(telegram_id, refresh_energy=False)
    base_chance = 17
    for key, _name, chance in ARTIFACT_DETECTORS:
        if key == session.detector_key:
            base_chance = chance
            break
    art_key = roll_location_artifact_drop(session.location, base_chance)
    survival_text = _apply_active_survival(storage, telegram_id)
    spawn_hint = describe_location_artifact_spawns(session.location)
    if art_key is None:
        return ActionResult(
            True,
            f"Сигнал пойман на «{session.location}», но арт сорвался в аномалию.\n"
            f"Ходов: {session.moves}, рад +{session.rad_gained}.\n"
            f"Базовые шансы здесь: {spawn_hint}.{survival_text}",
            payload={"hunt_active": False, "hunt_done": True},
        )
    storage.add_item(telegram_id, art_key, 1)
    storage.add_player_stat(telegram_id, "artifacts_found", 1)
    label = ITEM_LABELS.get(art_key, art_key)
    kind = "мусорный артефакт (без бонусов)" if art_key in ARTIFACT_JUNK_KEYS else "артефакт"
    return ActionResult(
        True,
        f"Арт найден на «{session.location}»!\n"
        f"Детектор «{session.detector_name}»: {session.circles_filled}/{session.circles_needed}.\n"
        f"Найден {kind}: {label} x1.\n"
        f"Ходов: {session.moves}, рад за вылазку +{session.rad_gained}.{survival_text}",
        payload={"hunt_active": False, "hunt_done": True, "art_key": art_key},
    )


def process_hunt_timeouts(storage: Storage) -> list[tuple[int, ActionResult]]:
    outcomes: list[tuple[int, ActionResult]] = []
    for telegram_id in list_active_hunt_player_ids(storage):
        session = get_hunt_session(storage, telegram_id)
        if session is None:
            _unregister_active_hunt(storage, telegram_id)
            continue
        if session.moves >= session.max_moves:
            clear_hunt_session(storage, telegram_id)
            outcomes.append(
                (
                    telegram_id,
                    ActionResult(
                        False,
                        "Время вылазки вышло на «" + session.location + "».\n"
                        "Сигнал " + str(session.circles_filled) + "/" + str(session.circles_needed) + ", арт не взят.\n"
                        "Рад за вылазку +" + str(session.rad_gained) + ".",
                        payload={"hunt_active": False, "hunt_done": True, "hunt_timeout": True},
                    ),
                )
            )
    return outcomes


def move_artifact_hunt(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_hunt_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Сначала начни поиск артефактов.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        clear_hunt_session(storage, telegram_id)
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        clear_hunt_session(storage, telegram_id)
        return ActionResult(False, _dead_block_text())

    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return ActionResult(False, "Некорректное направление.")
    nx = session.player[0] + delta[0]
    ny = session.player[1] + delta[1]
    if not (0 <= nx < session.grid and 0 <= ny < session.grid):
        image = render_hunt_frame(session, player)
        return ActionResult(
            False,
            "Край поля — туда не пройти.",
            payload={
                "hunt_image": image,
                "hunt_active": True,
                "caption": hunt_status_caption(session, player),
            },
        )

    session.player = (nx, ny)
    session.moves += 1
    session.steps += 1

    # Радиация: каждые 2 шага +1, каждые 6 ходов +5.
    rad_add = 0
    if session.steps % HUNT_RAD_EVERY_STEPS == 0:
        rad_add += HUNT_RAD_PER_TICK
    if session.moves % HUNT_MINUTE_MOVES == 0:
        rad_add += HUNT_RAD_PER_MINUTE
    if rad_add > 0:
        storage.adjust_survival(telegram_id, radiation_delta=rad_add)
        session.rad_gained += rad_add

    # Аномалия = смерть.
    if session.player in set(session.anomalies):
        clear_hunt_session(storage, telegram_id)
        storage.change_health(telegram_id, -10_000)
        return ActionResult(
            False,
            f"Ты влетел в аномалию на «{session.location}».\n"
            "Сознание гаснет… Респавн из инвентаря (мутанты обшарят рюкзак).",
            payload={"hunt_active": False, "hunt_dead": True},
        )

    gain = _signal_gain(session.player, session.artifact)
    if gain > 0:
        session.circles_filled = min(session.circles_needed, session.circles_filled + gain)

    if session.circles_filled >= session.circles_needed:
        save_hunt_session(storage, telegram_id, session)  # на случай сбоя до clear
        return _finish_success(storage, telegram_id, session)

    if session.moves >= session.max_moves:
        clear_hunt_session(storage, telegram_id)
        return ActionResult(
            False,
            f"Время вылазки вышло на «{session.location}».\n"
            f"Сигнал {session.circles_filled}/{session.circles_needed}, арт не взят.\n"
            f"Рад за вылазку +{session.rad_gained}.",
            payload={"hunt_active": False, "hunt_done": True},
        )

    save_hunt_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = render_hunt_frame(session, player)
    note = f"Сигнал +{gain}." if gain else "Тишина в эфире."
    if rad_add:
        note += f" Рад +{rad_add}."
    return ActionResult(
        True,
        note,
        payload={
            "hunt_image": image,
            "hunt_active": True,
            "caption": hunt_status_caption(session, player),
            "move_note": note,
        },
    )


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


_LOCATION_THUMB_DIR = PROJECT_ROOT / "assets" / "locations"

_LOCATION_THUMB_MAP: dict[str, str] = {
    "Кордон": "kordon.png",
    "Свалка": "svalka.png",
    "Росток": "rostok.png",
    "Армейские склады": "army_warehouses.png",
    "НИИ Агропром": "agroprom.png",
    "Янтарь": "yantar.png",
    "Болото": "boloto.png",
    "Темная долина": "dark_valley.png",
    "Рыжий лес": "red_forest.png",
    "Радар": "radar.png",
}


def _load_location_thumb(location: str) -> Image.Image | None:
    filename = _LOCATION_THUMB_MAP.get(location)
    if filename is None:
        return None
    path = _LOCATION_THUMB_DIR / filename
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        return img.resize((target_w, target_h))
    scale = max(target_w / src_w, target_h / src_h)
    new_w = max(target_w, int(src_w * scale))
    new_h = max(target_h, int(src_h * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _paste_circle(
    canvas: Image.Image,
    token: Image.Image,
    cx: int,
    cy: int,
    diameter: int,
    *,
    ring_color: tuple[int, int, int] | None = None,
    ring_width: int = 3,
) -> None:
    token = token.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, diameter - 2, diameter - 2), fill=255)
    ox = cx - diameter // 2
    oy = cy - diameter // 2
    canvas.paste(token, (ox, oy), mask)
    if ring_color is not None:
        ImageDraw.Draw(canvas).ellipse(
            (ox, oy, ox + diameter - 1, oy + diameter - 1),
            outline=ring_color,
            width=ring_width,
        )


def _paste_rounded(
    canvas: Image.Image,
    img: Image.Image,
    box: tuple[int, int, int, int],
    *,
    radius: int = 10,
) -> None:
    x0, y0, x1, y1 = box
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    img = img.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    canvas.paste(img, (x0, y0), mask)


def render_hunt_for_player(
    storage: Storage,
    telegram_id: int,
    session: HuntSession,
    player: Character,
) -> bytes:
    return render_hunt_frame(session, player)


def shoot_artifact_hunt(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_hunt_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Сначала начни поиск артефактов.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        clear_hunt_session(storage, telegram_id)
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        clear_hunt_session(storage, telegram_id)
        return ActionResult(False, _dead_block_text())
    image = render_hunt_frame(session, player)
    return ActionResult(
        False,
        "На поле нет целей для стрельбы — только аномалии и арт.",
        payload={
            "hunt_image": image,
            "hunt_active": True,
            "caption": hunt_status_caption(session, player),
            "move_note": "Стрелять некого.",
        },
    )


def _draw_cell(base: Image.Image, left: int, top: int, size: int, tone: int = 70) -> None:
    pix = base.load()
    for yy in range(size):
        for xx in range(size):
            n = ((left + xx) * 17 + (top + yy) * 31) % 28
            shade = max(40, min(120, tone + n - 10))
            pix[left + xx, top + yy] = (shade, shade - 2, max(30, shade - 8), 255)
    draw = ImageDraw.Draw(base)
    draw.rectangle((left, top, left + size - 1, top + size - 1), outline=(30, 30, 32), width=2)


def _glow(img: Image.Image, cx: int, cy: int, color: tuple[int, int, int], radius: int = 22) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    r, g, b = color
    for i, a in ((radius + 14, 35), (radius + 6, 90), (radius, 200), (max(4, radius // 2), 240)):
        d.ellipse((cx - i, cy - i, cx + i, cy + i), fill=(r, g, b, a))
    img.alpha_composite(overlay)


def render_hunt_frame(session: HuntSession, character: Character | None = None) -> bytes:
    """Кадр вылазки за артом: поле 6×6 со спрайтами + панель детектора."""
    cell = 108
    grid = session.grid
    grid_px = grid * cell
    margin = 24
    panel_w = 320
    width = margin + grid_px + 20 + panel_w + margin
    height = max(margin + grid_px + margin, 760)
    canvas = Image.new("RGBA", (width, height), (16, 18, 20, 255))
    draw = ImageDraw.Draw(canvas)

    field = (margin - 8, margin - 8, margin + grid_px + 8, margin + grid_px + 8)
    draw.rounded_rectangle(field, radius=14, fill=(34, 36, 40, 255), outline=(70, 74, 80), width=2)

    loc_bg = _load_location_thumb(session.location)
    if loc_bg is not None:
        field_img = _cover_crop(loc_bg, grid_px, grid_px).convert("RGBA")
        field_img.putalpha(160)
        canvas.paste(field_img, (margin, margin), field_img)

    for gy in range(grid):
        for gx in range(grid):
            left = margin + gx * cell
            top = margin + gy * cell
            if loc_bg is None:
                _draw_cell(canvas, left, top, cell)
            else:
                overlay = Image.new("RGBA", (cell, cell), (12, 14, 16, 55))
                canvas.alpha_composite(overlay, (left, top))
                ImageDraw.Draw(canvas).rectangle(
                    (left, top, left + cell - 1, top + cell - 1),
                    outline=(28, 30, 32),
                    width=1,
                )

    anomaly_set = set(session.anomalies)
    for ax, ay in session.anomalies:
        cx = margin + ax * cell + cell // 2
        cy = margin + ay * cell + cell // 2
        sprite = mission_icon_image(ANOMALY_ICON_KEY)
        if sprite is not None:
            _paste_circle(canvas, sprite, cx, cy, MISSION_ICON_GRID_DIAMETER)
        else:
            _glow(canvas, cx, cy, (255, 120, 40), 24)

    px, py = session.player
    pcx = margin + px * cell + cell // 2
    pcy = margin + py * cell + cell // 2
    token = None
    if character is not None:
        try:
            from app.avatar_render import render_avatar

            token = render_avatar(character, width=160, height=160)
        except Exception:
            token = None
    if token is None:
        token = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        td = ImageDraw.Draw(token)
        td.ellipse((20, 10, 140, 130), fill=(75, 85, 65), outline=(30, 35, 28), width=3)
        td.ellipse((45, 35, 115, 85), fill=(40, 48, 40))
        td.rectangle((45, 120, 115, 155), fill=(95, 75, 50))
    _paste_circle(canvas, token, pcx, pcy, 72, ring_color=(72, 220, 90), ring_width=5)

    pl = margin + grid_px + 20
    pr = width - margin
    pt = margin - 8
    pb = height - margin + 8
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((pl, pt, pr, pb), radius=16, fill=(48, 50, 54, 255), outline=(100, 104, 110), width=2)

    thumb = (pl + 16, pt + 14, pr - 16, pt + 120)
    loc_img = _load_location_thumb(session.location)
    if loc_img is not None:
        _paste_rounded(canvas, loc_img, thumb, radius=10)
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=10, outline=(110, 120, 100), width=2)
    else:
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=10, fill=(30, 34, 28), outline=(90, 100, 80), width=2)

    title_font = _load_font(22)
    body = _load_font(17)
    small = _load_font(14)
    loc_font = title_font if len(session.location) <= 14 else _load_font(18)
    draw.text((pl + 18, pt + 128), session.location, fill=(245, 245, 245), font=loc_font)
    draw.text((pl + 18, pt + 158), "Поиск артефакта", fill=(180, 200, 150), font=body)

    det_y = pt + 190
    draw.text((pl + 18, det_y), f"«{session.detector_name}»", fill=(220, 220, 220), font=body)
    filled = min(session.circles_filled, session.circles_needed)
    circle_y = det_y + 28
    for i in range(session.circles_needed):
        cx = pl + 22 + i * 28
        if i < filled:
            draw.ellipse((cx - 9, circle_y - 9, cx + 9, circle_y + 9), fill=(70, 220, 90), outline=(40, 120, 50))
        else:
            draw.ellipse((cx - 9, circle_y - 9, cx + 9, circle_y + 9), fill=(55, 58, 60), outline=(90, 90, 90))

    info_y = det_y + 56
    draw.text((pl + 18, info_y), f"Сигнал: {filled}/{session.circles_needed}", fill=(180, 220, 255), font=body)
    draw.text((pl + 18, info_y + 24), f"Ход {session.moves}/{session.max_moves}", fill=(200, 200, 200), font=small)
    draw.text((pl + 18, info_y + 44), f"Аномалий: {len(session.anomalies)}", fill=(200, 160, 120), font=small)
    draw.text((pl + 18, info_y + 64), "Аномалия = смерть", fill=(200, 100, 80), font=small)

    hp = int(character.health) if character else 0
    max_hp = int(effective_max_health(character)) if character else 100
    energy = int(character.energy) if character else 0
    max_energy = int(character.max_energy) if character else 100
    rad = int(character.radiation) if character else 0

    bar_top = info_y + 90
    draw.rounded_rectangle((pl + 18, bar_top, pr - 18, bar_top + 28), radius=8, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 44) * (hp / max(1, max_hp)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 20, bar_top + 2, pl + 20 + fill_w, bar_top + 26), radius=6, fill=(200, 60, 50))
    draw.text((pl + 24, bar_top + 5), f"HP {hp}/{max_hp}", fill=(255, 255, 255), font=small)

    draw.rounded_rectangle((pl + 18, bar_top + 40, pr - 18, bar_top + 68), radius=8, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 44) * min(1.0, rad / 100))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 20, bar_top + 42, pl + 20 + fill_w, bar_top + 66), radius=6, fill=(180, 200, 40))
    draw.text((pl + 24, bar_top + 45), f"RAD {rad}", fill=(255, 255, 255), font=small)

    draw.rounded_rectangle((pl + 18, bar_top + 80, pr - 18, bar_top + 108), radius=8, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 44) * (energy / max(1, max_energy)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 20, bar_top + 82, pl + 20 + fill_w, bar_top + 106), radius=6, fill=(50, 120, 210))
    draw.text((pl + 24, bar_top + 85), f"EN {energy}/{max_energy}", fill=(255, 255, 255), font=small)

    draw.text((pl + 18, pb - 50), "Дойди до сигнала детектора", fill=(210, 210, 210), font=small)
    draw.text((pl + 18, pb - 28), "Стрелки - ход, кнопка - бросить", fill=(190, 190, 190), font=small)

    out = canvas.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
