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


def render_hunt_frame(session: HuntSession, character: Character | None = None) -> bytes:
    """Кадр: слева поле 6×6, справа панель детектора (в духе мокапа)."""
    width, height = 900, 720
    img = Image.new("RGB", (width, height), color=(28, 30, 34))
    draw = ImageDraw.Draw(img)

    # Левая зона — сетка.
    grid_origin = (24, 24)
    cell = 100
    grid_px = session.grid * cell
    anomaly_set = set(session.anomalies)

    # Фон поля.
    draw.rounded_rectangle(
        (grid_origin[0] - 8, grid_origin[1] - 8, grid_origin[0] + grid_px + 8, grid_origin[1] + grid_px + 8),
        radius=12,
        fill=(42, 44, 48),
        outline=(70, 74, 80),
        width=2,
    )

    for y in range(session.grid):
        for x in range(session.grid):
            left = grid_origin[0] + x * cell
            top = grid_origin[1] + y * cell
            right = left + cell - 2
            bottom = top + cell - 2
            # Камень/земля.
            base = (58 + (x * 7 + y * 3) % 18, 56 + (x * 5 + y * 11) % 14, 52 + (x + y) % 10)
            draw.rectangle((left, top, right, bottom), fill=base, outline=(40, 40, 42))
            # Трещины.
            draw.line((left + 12, top + 20, left + 40, top + 55), fill=(45, 44, 42), width=1)
            draw.line((left + 55, top + 15, left + 80, top + 70), fill=(48, 46, 44), width=1)

            pos = (x, y)
            cx = (left + right) // 2
            cy = (top + bottom) // 2

            if pos in anomaly_set:
                color = _anomaly_color(pos, session.artifact)
                _draw_glow_orb(draw, cx, cy, 22, color)

            if pos == session.player:
                # Зелёная обводка активной клетки + игрок.
                draw.ellipse((cx - 32, cy - 32, cx + 32, cy + 32), outline=(80, 220, 90), width=4)
                _draw_player_token(draw, cx, cy, character)

    # Правая панель.
    panel_left = grid_origin[0] + grid_px + 28
    panel_right = width - 20
    draw.rounded_rectangle(
        (panel_left, 24, panel_right, height - 24),
        radius=14,
        fill=(48, 50, 54),
        outline=(90, 92, 96),
        width=2,
    )

    title_font = _load_font(28)
    body_font = _load_font(20)
    small_font = _load_font(16)

    # Превью локации.
    thumb = (panel_left + 18, 40, panel_right - 18, 150)
    draw.rounded_rectangle(thumb, radius=10, fill=(34, 38, 32), outline=(70, 80, 60), width=2)
    # Простая «зона».
    draw.rectangle((thumb[0] + 10, thumb[1] + 40, thumb[2] - 10, thumb[3] - 10), fill=(55, 62, 48))
    draw.ellipse((thumb[0] + 30, thumb[1] + 20, thumb[0] + 70, thumb[1] + 55), fill=(70, 78, 55))
    draw.text((panel_left + 22, 158), session.location, fill=(230, 230, 230), font=title_font)

    # Детектор + кружки.
    det_y = 210
    draw.rounded_rectangle(
        (panel_left + 18, det_y, panel_left + 78, det_y + 60),
        radius=8,
        fill=(30, 32, 36),
        outline=(120, 160, 90),
        width=2,
    )
    draw.rectangle((panel_left + 28, det_y + 12, panel_left + 68, det_y + 28), fill=(60, 90, 50))
    draw.text(
        (panel_left + 90, det_y + 8),
        f"«{session.detector_name}»",
        fill=(220, 220, 220),
        font=body_font,
    )
    # Кружки-индикаторы.
    filled = min(session.circles_filled, session.circles_needed)
    circle_y = det_y + 42
    start_x = panel_left + 90
    for i in range(session.circles_needed):
        cx = start_x + i * 28
        if i < filled:
            draw.ellipse((cx - 9, circle_y - 9, cx + 9, circle_y + 9), fill=(70, 220, 90), outline=(40, 120, 50))
        else:
            draw.ellipse((cx - 9, circle_y - 9, cx + 9, circle_y + 9), fill=(55, 58, 60), outline=(90, 90, 90))

    # «Радар» / экран.
    screen = (panel_left + 18, 300, panel_right - 18, 480)
    draw.rounded_rectangle(screen, radius=12, fill=(28, 30, 34), outline=(70, 72, 76), width=2)
    # Овал сигнала — ярче, если ближе.
    dist = _chebyshev(session.player, session.artifact)
    glow = max(40, 160 - dist * 25)
    oval = (screen[0] + 40, screen[1] + 30, screen[2] - 40, screen[3] - 30)
    draw.ellipse(oval, fill=(30, 40, glow // 3 + 30), outline=(100, 180, 220), width=3)
    draw.text(
        (panel_left + 28, 490),
        f"Сигнал: {filled}/{session.circles_needed}",
        fill=(180, 220, 255),
        font=body_font,
    )
    draw.text(
        (panel_left + 28, 520),
        f"Ход {session.moves}/{session.max_moves}",
        fill=(200, 200, 200),
        font=small_font,
    )
    draw.text(
        (panel_left + 28, 545),
        f"Аномалий: {len(session.anomalies)}",
        fill=(200, 160, 120),
        font=small_font,
    )

    # Полоски HP / рад / энергия.
    bar_top = 590
    bar_w = 28
    bar_h = 90
    gap = 36
    bx = panel_left + 40
    hp = character.health if character else 60
    max_hp = effective_max_health(character) if character else 100
    rad = character.radiation if character else 0
    energy = character.energy if character else 50
    max_energy = character.max_energy if character else 100
    _draw_vbar(draw, bx, bar_top, bar_w, bar_h, hp / max(1, max_hp), (180, 40, 40), "HP")
    _draw_vbar(draw, bx + gap, bar_top, bar_w, bar_h, min(1.0, rad / 100), (40, 40, 40), "RAD")
    _draw_vbar(draw, bx + gap * 2, bar_top, bar_w, bar_h, energy / max(1, max_energy), (40, 90, 180), "EN")

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _anomaly_color(pos: tuple[int, int], artifact: tuple[int, int]) -> tuple[int, int, int]:
    # Разноцветные орбы как на мокапе.
    palette = [
        (255, 140, 40),
        (255, 90, 30),
        (80, 220, 90),
        (220, 220, 230),
        (255, 180, 60),
    ]
    return palette[(pos[0] * 3 + pos[1] * 5) % len(palette)]


def _draw_glow_orb(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    r, g, b = color
    for i, alpha_scale in ((radius + 10, 0.25), (radius + 4, 0.45), (radius, 1.0)):
        rr = int(r * alpha_scale + 30 * (1 - alpha_scale))
        gg = int(g * alpha_scale + 30 * (1 - alpha_scale))
        bb = int(b * alpha_scale + 30 * (1 - alpha_scale))
        draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=(rr, gg, bb))


def _draw_player_token(draw: ImageDraw.ImageDraw, cx: int, cy: int, character: Character | None) -> None:
    # Упрощённый сталкер: шлем + тело.
    draw.ellipse((cx - 18, cy - 22, cx + 18, cy + 14), fill=(70, 78, 60), outline=(30, 35, 28), width=2)
    draw.ellipse((cx - 12, cy - 18, cx + 12, cy - 2), fill=(45, 50, 42))  # визор
    draw.rectangle((cx - 14, cy + 8, cx + 14, cy + 26), fill=(90, 70, 45), outline=(40, 30, 20))
    if character and character.faction == "Долг":
        draw.rectangle((cx - 6, cy + 10, cx + 6, cy + 16), fill=(180, 40, 40))
    elif character and character.faction == "Свобода":
        draw.rectangle((cx - 6, cy + 10, cx + 6, cy + 16), fill=(40, 140, 60))


def _draw_vbar(
    draw: ImageDraw.ImageDraw,
    x: int,
    top: int,
    w: int,
    h: int,
    ratio: float,
    color: tuple[int, int, int],
    label: str,
) -> None:
    ratio = max(0.0, min(1.0, float(ratio)))
    draw.rectangle((x, top, x + w, top + h), fill=(25, 25, 28), outline=(80, 80, 80))
    fill_h = int(h * ratio)
    if fill_h > 0:
        draw.rectangle((x + 2, top + h - fill_h, x + w - 2, top + h - 2), fill=color)
    font = _load_font(12)
    draw.text((x - 2, top + h + 4), label, fill=(180, 180, 180), font=font)
