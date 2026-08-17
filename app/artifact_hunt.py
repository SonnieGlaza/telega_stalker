from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from app.mission_icons import ANOMALY_ICON_KEY, MISSION_ICON_GRID_DIAMETER, mission_icon_image

# Тот же спрайт аномалии (mission_icon_image/ANOMALY_ICON_KEY), что и в quest_mission.py/coop_mission.py —
# единый арт для угроз на всех сетках. Клетка охоты крупнее (118px против 108px в quest_mission),
# поэтому масштабируем от общего MISSION_ICON_GRID_DIAMETER, сохраняя ту же пропорцию иконка/клетка,
# чтобы аномалии выглядели одинаково узнаваемо во всех режимах (квесты/кооп/охота).
HUNT_GRID_CELL_PX = 118
_QUEST_GRID_CELL_PX = 108
HUNT_ANOMALY_ICON_DIAMETER = round(MISSION_ICON_GRID_DIAMETER * HUNT_GRID_CELL_PX / _QUEST_GRID_CELL_PX)


HUNT_META_PREFIX = "artifact_hunt:"
HUNT_ACTIVE_IDS_META = "artifact_hunt:active_ids"
HUNT_IDLE_HOURS = 4
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

LOCATIONS_ASSET_DIR = PROJECT_ROOT / "assets" / "locations"
HUNT_ASSET_DIR = PROJECT_ROOT / "assets" / "hunt"
LOCATION_THUMB_SLUGS: dict[str, str] = {
    "Кордон": "kordon",
    "Свалка": "svalka",
    "Росток": "rostok",
    "Армейские склады": "army_warehouses",
    "НИИ Агропром": "agroprom",
    "Янтарь": "yantar",
    "Болото": "boloto",
    "Темная долина": "dark_valley",
    "Рыжий лес": "red_forest",
    "Радар": "radar",
}
DETECTOR_SIGNAL_ASSET = HUNT_ASSET_DIR / "detector_signal.png"

_location_thumb_cache: dict[str, Image.Image | None] = {}
_signal_asset_cache: Image.Image | None | bool = False


def _load_location_thumb(location: str) -> Image.Image | None:
    slug = LOCATION_THUMB_SLUGS.get(location)
    if not slug:
        return None
    if slug in _location_thumb_cache:
        return _location_thumb_cache[slug]
    path = LOCATIONS_ASSET_DIR / f"{slug}.png"
    img: Image.Image | None = None
    if path.is_file():
        try:
            img = Image.open(path).convert("RGBA")
        except Exception:
            img = None
    _location_thumb_cache[slug] = img
    return img


def _load_signal_asset() -> Image.Image | None:
    global _signal_asset_cache
    if _signal_asset_cache is not False:
        return _signal_asset_cache  # type: ignore[return-value]
    img: Image.Image | None = None
    if DETECTOR_SIGNAL_ASSET.is_file():
        try:
            img = Image.open(DETECTOR_SIGNAL_ASSET).convert("RGBA")
        except Exception:
            img = None
    _signal_asset_cache = img
    return img


def _cover_crop(src: Image.Image, tw: int, th: int) -> Image.Image:
    """Масштаб cover + center crop."""
    sw, sh = src.size
    scale = max(tw / max(1, sw), th / max(1, sh))
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    return resized.crop((left, top, left + tw, top + th))


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _paste_rounded(
    canvas: Image.Image,
    src: Image.Image,
    box: tuple[int, int, int, int],
    *,
    radius: int = 10,
) -> None:
    x0, y0, x1, y1 = box
    tw, th = max(1, x1 - x0), max(1, y1 - y0)
    fitted = _cover_crop(src.convert("RGBA"), tw, th)
    mask = _rounded_mask((tw, th), radius)
    canvas.paste(fitted, (x0, y0), mask)


def _draw_fallback_location_thumb(draw: ImageDraw.ImageDraw, thumb: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(thumb, radius=10, fill=(30, 34, 28, 255), outline=(90, 100, 80, 255), width=2)
    draw.rectangle((thumb[0] + 8, thumb[1] + 48, thumb[2] - 8, thumb[3] - 8), fill=(48, 56, 40, 255))
    draw.polygon(
        [
            (thumb[0] + 20, thumb[3] - 8),
            (thumb[0] + 70, thumb[1] + 55),
            (thumb[0] + 120, thumb[3] - 8),
        ],
        fill=(62, 70, 50, 255),
    )
    draw.rectangle((thumb[0] + 140, thumb[1] + 70, thumb[0] + 175, thumb[3] - 8), fill=(70, 55, 40, 255))
    draw.ellipse((thumb[0] + 40, thumb[1] + 18, thumb[0] + 95, thumb[1] + 55), fill=(95, 105, 70, 255))


def _draw_signal_screen(
    canvas: Image.Image,
    screen: tuple[int, int, int, int],
    *,
    strength: float,
) -> None:
    """HD-экран детектора: фото-ассет + кольца/сканлайны по силе сигнала."""
    x0, y0, x1, y1 = screen
    tw, th = max(1, x1 - x0), max(1, y1 - y0)
    strength = max(0.0, min(1.0, float(strength)))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(screen, radius=14, fill=(18, 20, 24, 255), outline=(80, 82, 86, 255), width=2)

    asset = _load_signal_asset()
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    if asset is not None:
        fitted = _cover_crop(asset, tw, th)
        # Затемнение при слабом сигнале, ярче при сильном.
        dim = Image.new("RGBA", (tw, th), (0, 0, 0, int(160 * (1.0 - strength))))
        fitted = Image.alpha_composite(fitted, dim)
        # Лёгкий cyan tint по силе.
        tint_a = int(40 + 70 * strength)
        tint = Image.new("RGBA", (tw, th), (40, 120, 180, tint_a))
        fitted = Image.blend(fitted, Image.alpha_composite(fitted, tint), 0.35)
        layer.alpha_composite(fitted)
    else:
        # Fallback: процедурный овал.
        ld = ImageDraw.Draw(layer)
        blue = (70, 150, int(150 + 80 * strength))
        pad = int(22 + (1.0 - strength) * 16)
        oval = (pad, 18, tw - pad, th - 18)
        for expand, alpha in ((16, 30), (8, 70), (0, 140)):
            ld.ellipse(
                (oval[0] - expand, oval[1] - expand, oval[2] + expand, oval[3] + expand),
                fill=(*blue, alpha),
            )
        ld.ellipse(oval, outline=(160, 220, 255, 220), width=3)

    # Концентрические кольца радара.
    fx = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fx)
    cx, cy = tw // 2, th // 2
    ring_alpha = int(35 + 90 * strength)
    for r in (28, 48, 70, 96):
        fd.ellipse((cx - r, cy - int(r * 1.15), cx + r, cy + int(r * 1.15)), outline=(120, 200, 230, ring_alpha))
    # Сканлайны.
    for yy in range(0, th, 3):
        fd.line((0, yy, tw, yy), fill=(0, 0, 0, 28))
    # Центральный блик-артефакт.
    core_r = int(10 + 18 * strength)
    for i, a in ((core_r + 14, int(40 * strength + 20)), (core_r, int(120 * strength + 40)), (max(4, core_r // 2), 220)):
        fd.ellipse((cx - i, cy - int(i * 1.3), cx + i, cy + int(i * 1.3)), fill=(160, 220, 255, a))
    # Угловой блик стекла.
    fd.ellipse((12, 10, 70, 48), fill=(220, 240, 255, 35))
    layer.alpha_composite(fx)

    mask = _rounded_mask((tw, th), 12)
    canvas.paste(layer, (x0, y0), mask)
    ImageDraw.Draw(canvas).rounded_rectangle(screen, radius=14, outline=(100, 120, 140, 255), width=2)


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
    turn_seq: int = 0
    started_at: str | None = None

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
            "turn_seq": self.turn_seq,
            "started_at": self.started_at,
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
            turn_seq=int(raw.get("turn_seq") or 0),
            started_at=raw.get("started_at"),
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        storage.delete_meta(_hunt_meta_key(telegram_id))
        return None


def save_hunt_session(storage: Storage, telegram_id: int, session: HuntSession) -> None:
    storage.set_meta(_hunt_meta_key(telegram_id), json.dumps(session.to_dict(), ensure_ascii=False))
    _register_active_hunt(storage, telegram_id)


def clear_hunt_session(storage: Storage, telegram_id: int) -> None:
    storage.delete_meta(_hunt_meta_key(telegram_id))
    _unregister_active_hunt(storage, telegram_id)


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


def _save_hunt_if_turn_ok(
    storage: Storage,
    telegram_id: int,
    session: HuntSession,
    expected_seq: int,
) -> bool:
    from app.tactical_turn import save_turn_if_seq_ok

    tid = int(telegram_id)
    return save_turn_if_seq_ok(
        storage,
        meta_key=_hunt_meta_key(tid),
        session=session,
        from_dict=HuntSession.from_dict,
        save_fn=lambda st, sess: save_hunt_session(st, tid, sess),
        expected_seq=expected_seq,
    )


def check_hunt_session_timeout(storage: Storage, telegram_id: int) -> ActionResult | None:
    session = get_hunt_session(storage, telegram_id)
    if session is None:
        _unregister_active_hunt(storage, telegram_id)
        return None
    if session.moves >= session.max_moves:
        clear_hunt_session(storage, telegram_id)
        return ActionResult(
            False,
            f"Время вылазки вышло на «{session.location}».\n"
            f"Сигнал {session.circles_filled}/{session.circles_needed}, арт не взят.\n"
            f"Рад за вылазку +{session.rad_gained}.",
            payload={"hunt_active": False, "hunt_done": True, "hunt_timeout": True},
        )
    if session.started_at:
        try:
            started = datetime.fromisoformat(str(session.started_at))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
        except ValueError:
            started = _utc_now()
        if _utc_now() > started + timedelta(hours=HUNT_IDLE_HOURS):
            clear_hunt_session(storage, telegram_id)
            return ActionResult(
                False,
                f"Поиск артефактов на «{session.location}» заброшен — слишком долго без движения.",
                payload={"hunt_active": False, "hunt_done": True, "hunt_timeout": True},
            )
    return None


def process_hunt_timeouts(storage: Storage) -> list[tuple[int, ActionResult]]:
    outcomes: list[tuple[int, ActionResult]] = []
    for telegram_id in list_active_hunt_player_ids(storage):
        result = check_hunt_session_timeout(storage, telegram_id)
        if result is not None:
            outcomes.append((telegram_id, result))
    return outcomes


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


def _grid_neighbors(cell: tuple[int, int], grid: int) -> list[tuple[int, int]]:
    """Соседние клетки (8 направлений, включая диагонали)."""
    x, y = cell
    neighbors: list[tuple[int, int]] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid and 0 <= ny < grid:
                neighbors.append((nx, ny))
    return neighbors


def _cells_adjacent_to_any(
    cells: list[tuple[int, int]],
    grid: int,
    *,
    forbidden: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Свободные клетки рядом хотя бы с одной из переданных (для арта у аномалий)."""
    candidates: set[tuple[int, int]] = set()
    for cell in cells:
        for neighbor in _grid_neighbors(cell, grid):
            if neighbor not in forbidden:
                candidates.add(neighbor)
    return list(candidates)


def artifact_beside_anomaly(session: HuntSession) -> bool:
    """Артефакт на соседней с аномалией клетке (для тестов и отладки)."""
    anomaly_set = set(session.anomalies)
    for neighbor in _grid_neighbors(session.artifact, session.grid):
        if neighbor in anomaly_set:
            return True
    return False


def _build_session(character: Character, detector_key: str, detector_name: str) -> HuntSession:
    grid = HUNT_GRID_SIZE
    anomaly_n = location_anomaly_count(character.location)
    player = (random.randrange(grid), random.randrange(grid))
    forbidden: set[tuple[int, int]] = {player}
    anomalies: list[tuple[int, int]] = []
    for _ in range(anomaly_n):
        cell = _random_free_cell(grid, forbidden)
        anomalies.append(cell)
        forbidden.add(cell)
    adjacent_to_anomalies = _cells_adjacent_to_any(anomalies, grid, forbidden=forbidden)
    if adjacent_to_anomalies:
        artifact = random.choice(adjacent_to_anomalies)
    else:
        artifact = _random_free_cell(grid, forbidden)
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
        started_at=_utc_now().isoformat(),
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
        f"📡 Вылазка за артом · «{session.location}»",
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
    from app.player_busy import player_busy_reason

    busy = player_busy_reason(storage, telegram_id, skip="hunt")
    if busy:
        return ActionResult(False, busy)
    if get_hunt_session(storage, telegram_id) is not None:
        session = get_hunt_session(storage, telegram_id)
        assert session is not None
        image = _render_for_player(storage, telegram_id, session, player)
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
    image = _render_for_player(storage, telegram_id, session, player)
    caption = hunt_status_caption(session, player)
    anomaly_n = len(session.anomalies)
    return ActionResult(
        True,
        f"Вылазка на «{session.location}».\n"
        f"Детектор «{detector_name}»: нужно {session.circles_needed} кружка(ов).\n"
        f"Аномалий на поле: {anomaly_n}. Энергия −{energy_cost}.",
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
        image = _render_for_player(storage, telegram_id, session, player)
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

    rad_add = 0
    if session.steps % HUNT_RAD_EVERY_STEPS == 0:
        rad_add += HUNT_RAD_PER_TICK
    if session.moves % HUNT_MINUTE_MOVES == 0:
        rad_add += HUNT_RAD_PER_MINUTE

    gain = _signal_gain(session.player, session.artifact)
    if gain > 0:
        session.circles_filled = min(session.circles_needed, session.circles_filled + gain)

    expected_seq = session.turn_seq
    session.turn_seq = expected_seq + 1
    if not _save_hunt_if_turn_ok(storage, telegram_id, session, expected_seq):
        from app.tactical_combat import STALE_TURN_MESSAGE

        return ActionResult(False, STALE_TURN_MESSAGE, payload={"hunt_active": True})

    if rad_add > 0:
        storage.adjust_survival(telegram_id, radiation_delta=rad_add)
        session.rad_gained += rad_add
        save_hunt_session(storage, telegram_id, session)

    if session.player in set(session.anomalies):
        clear_hunt_session(storage, telegram_id)
        storage.change_health(telegram_id, -10_000)
        from app.game_logic import remember_death_cause

        remember_death_cause(storage, telegram_id, "anomaly")
        return ActionResult(
            False,
            f"Ты влетел в аномалию на «{session.location}».\n"
            "Сознание гаснет… Респавн из инвентаря (мутанты обшарят рюкзак).",
            payload={
                "hunt_active": False,
                "hunt_dead": True,
                "death_location": session.location,
                "death_cause": "anomaly",
            },
        )

    if session.circles_filled >= session.circles_needed:
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

    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = _render_for_player(storage, telegram_id, session, player)
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


def _hunt_rating(storage: Storage, telegram_id: int) -> int:
    try:
        return int(storage.get_player_stats(telegram_id).get("rating_points", 0))
    except Exception:
        return 0


def render_hunt_for_player(
    storage: Storage,
    telegram_id: int,
    session: HuntSession,
    player: Character,
) -> bytes:
    return render_hunt_frame(session, player, rating_points=_hunt_rating(storage, telegram_id))


def _render_for_player(storage: Storage, telegram_id: int, session: HuntSession, player: Character) -> bytes:
    return render_hunt_for_player(storage, telegram_id, session, player)


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _hash_noise(x: int, y: int, salt: int = 0) -> float:
    n = (x * 374761393 + y * 668265263 + salt * 1274126177) & 0x7FFFFFFF
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _mix_rgb(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
    )


def _draw_rock_cell(
    base: Image.Image,
    left: int,
    top: int,
    size: int,
    gx: int,
    gy: int,
) -> None:
    """Плитка земли/бетона с сеткой — ближе к мокапу."""
    pix = base.load()
    for yy in range(size):
        for xx in range(size):
            n1 = _hash_noise(gx * size + xx, gy * size + yy, 1)
            n2 = _hash_noise(gx * size + xx, gy * size + yy, 7)
            shade = 72 + int(n1 * 38) - int(n2 * 12)
            # Лёгкий градиент «освещения».
            shade = int(shade + (xx + yy) * 0.04)
            shade = max(48, min(130, shade))
            # Серо-коричневый камень.
            r = shade
            g = max(40, shade - 4)
            b = max(36, shade - 10)
            # Мелкие трещины.
            if n2 > 0.92:
                r = g = b = max(30, shade - 25)
            pix[left + xx, top + yy] = (r, g, b, 255)

    draw = ImageDraw.Draw(base)
    # Рамка клетки как на референсе.
    draw.rectangle(
        (left, top, left + size - 1, top + size - 1),
        outline=(28, 28, 30),
        width=2,
    )
    # Внутренний скос.
    draw.line((left + 1, top + 1, left + size - 2, top + 1), fill=(95, 95, 92))
    draw.line((left + 1, top + 1, left + 1, top + size - 2), fill=(90, 90, 88))


def _paste_anomaly_icon(canvas: Image.Image, cx: int, cy: int, *, diameter: int = HUNT_ANOMALY_ICON_DIAMETER) -> None:
    sprite = mission_icon_image(ANOMALY_ICON_KEY)
    if sprite is not None:
        token = sprite.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
        mask = Image.new("L", (diameter, diameter), 0)
        ImageDraw.Draw(mask).ellipse((1, 1, diameter - 2, diameter - 2), fill=255)
        canvas.paste(token, (cx - diameter // 2, cy - diameter // 2), mask)
        return
    _draw_glow_orb_layer(canvas, cx, cy, 28, (255, 120, 40))


def _paste_circle(
    canvas: Image.Image,
    token: Image.Image,
    cx: int,
    cy: int,
    diameter: int,
    *,
    ring_color: tuple[int, int, int] = (70, 210, 85),
    ring_width: int = 5,
) -> None:
    token = token.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, diameter - 2, diameter - 2), fill=255)
    ring = Image.new("RGBA", (diameter + ring_width * 2, diameter + ring_width * 2), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    outer = diameter + ring_width * 2 - 1
    rd.ellipse((0, 0, outer, outer), outline=(*ring_color, 255), width=ring_width)
    # Мягкое свечение кольца.
    glow = Image.new("RGBA", ring.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((2, 2, outer - 2, outer - 2), outline=(*ring_color, 70), width=ring_width + 4)
    ox = cx - ring.size[0] // 2
    oy = cy - ring.size[1] // 2
    canvas.alpha_composite(glow, (ox, oy))
    canvas.alpha_composite(ring, (ox, oy))
    canvas.paste(token, (cx - diameter // 2, cy - diameter // 2), mask)


def _draw_glow_orb_layer(
    layer: Image.Image,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    overlay = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    r, g, b = color
    for i, alpha in (
        (radius + 22, 22),
        (radius + 14, 48),
        (radius + 6, 110),
        (radius, 200),
    ):
        draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=(r, g, b, alpha))
    # Яркое ядро как на мокапе.
    core = max(6, radius // 2)
    draw.ellipse((cx - core, cy - core, cx + core, cy + core), fill=(255, 250, 230, 235))
    draw.ellipse(
        (cx - core // 2, cy - core // 2, cx + core // 3, cy + core // 3),
        fill=(255, 255, 255, 200),
    )
    layer.alpha_composite(overlay)


def _draw_detector_icon(draw: ImageDraw.ImageDraw, x: int, y: int, w: int = 70, h: int = 54) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=8, fill=(32, 34, 36), outline=(110, 150, 80), width=2)
    draw.rounded_rectangle((x + 10, y + 10, x + w - 10, y + 26), radius=4, fill=(55, 85, 45))
    draw.rectangle((x + 16, y + 30, x + 28, y + 42), fill=(70, 75, 70))
    draw.rectangle((x + 32, y + 30, x + 44, y + 42), fill=(50, 120, 60))
    draw.ellipse((x + w - 22, y + 30, x + w - 10, y + 42), fill=(40, 200, 70))


def _draw_status_tube(
    draw: ImageDraw.ImageDraw,
    x: int,
    top: int,
    w: int,
    h: int,
    ratio: float,
    color: tuple[int, int, int],
    label: str,
    value_text: str,
    font: ImageFont.ImageFont,
    small: ImageFont.ImageFont,
) -> None:
    ratio = max(0.0, min(1.0, float(ratio)))
    # Корпус колбы.
    draw.rounded_rectangle((x, top, x + w, top + h), radius=8, fill=(22, 22, 26), outline=(95, 95, 100), width=2)
    inner_top = top + 6
    inner_bottom = top + h - 6
    inner_h = inner_bottom - inner_top
    fill_h = int(inner_h * ratio)
    if fill_h > 0:
        fy0 = inner_bottom - fill_h
        # Градиент заливки.
        for i in range(fill_h):
            t = i / max(1, fill_h - 1)
            c = _mix_rgb(_mix_rgb((20, 20, 20), color, 0.55), color, t)
            y = fy0 + i
            draw.line((x + 4, y, x + w - 4, y), fill=c)
        # Блик слева.
        draw.rectangle((x + 5, fy0, x + 8, inner_bottom - 1), fill=(210, 210, 215, 255))
    draw.text((x + w // 2, top + h + 6), label, fill=(210, 210, 210), font=small, anchor="ma")
    draw.text((x + w // 2, top + h + 24), value_text, fill=(235, 235, 235), font=font, anchor="ma")


def render_hunt_frame(
    session: HuntSession,
    character: Character | None = None,
    *,
    rating_points: int = 0,
) -> bytes:
    """HD-кадр: поле слева, PDA-панель справа (референс-мокап)."""
    cell = HUNT_GRID_CELL_PX
    grid = session.grid
    grid_px = grid * cell
    margin = 28
    panel_w = 340
    width = margin + grid_px + 24 + panel_w + margin
    # Панель чуть выше сетки, чтобы колбы HP/RAD/EN не обрезались.
    height = max(margin + grid_px + margin, 820)
    canvas = Image.new("RGBA", (width, height), (18, 20, 22, 255))

    # Атмосферный фон (не плоский).
    bg = ImageDraw.Draw(canvas)
    for y in range(height):
        t = y / max(1, height - 1)
        shade = int(18 + t * 8)
        n = int((_hash_noise(0, y, 3) - 0.5) * 6)
        c = max(10, min(36, shade + n))
        bg.line((0, y, width, y), fill=(c, c + 1, c + 2, 255))

    draw = ImageDraw.Draw(canvas)
    field_bg = (margin - 10, margin - 10, margin + grid_px + 10, margin + grid_px + 10)
    draw.rounded_rectangle(field_bg, radius=16, fill=(36, 38, 42, 255), outline=(75, 78, 84, 255), width=3)

    for gy in range(grid):
        for gx in range(grid):
            left = margin + gx * cell
            top = margin + gy * cell
            _draw_rock_cell(canvas, left, top, cell, gx, gy)

    for ax, ay in session.anomalies:
        cx = margin + ax * cell + cell // 2
        cy = margin + ay * cell + cell // 2
        _paste_anomaly_icon(canvas, cx, cy)

    # Близкий арт — бледный пинг на поле.
    if session.circles_filled >= max(1, session.circles_needed - 1):
        acx = margin + session.artifact[0] * cell + cell // 2
        acy = margin + session.artifact[1] * cell + cell // 2
        _draw_glow_orb_layer(canvas, acx, acy, 22, (150, 210, 255))

    px, py = session.player
    pcx = margin + px * cell + cell // 2
    pcy = margin + py * cell + cell // 2
    token = None
    if character is not None:
        try:
            from app.avatar_render import render_avatar

            token = render_avatar(character, rating_points=rating_points, width=160, height=160)
        except Exception:
            token = None
    if token is None:
        token = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        td = ImageDraw.Draw(token)
        td.ellipse((20, 10, 140, 130), fill=(75, 85, 65), outline=(30, 35, 28), width=3)
        td.ellipse((45, 35, 115, 85), fill=(40, 48, 40))
        td.rectangle((45, 120, 115, 155), fill=(95, 75, 50))
    _paste_circle(canvas, token, pcx, pcy, 78, ring_color=(72, 220, 90), ring_width=5)

    panel_left = margin + grid_px + 24
    panel_right = width - margin
    panel_top = margin - 10
    panel_bottom = height - margin + 10
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (panel_left, panel_top, panel_right, panel_bottom),
        radius=18,
        fill=(52, 54, 58, 255),
        outline=(110, 112, 116, 255),
        width=2,
    )
    draw.rounded_rectangle(
        (panel_left + 8, panel_top + 10, panel_right - 8, panel_bottom - 10),
        radius=14,
        fill=(44, 46, 50, 255),
        outline=(70, 72, 76, 255),
        width=1,
    )

    title_font = _load_font(32)
    body_font = _load_font(20)
    small_font = _load_font(16)
    tiny_font = _load_font(14)

    # Фото локации — слот справа сверху над названием.
    thumb = (panel_left + 18, panel_top + 16, panel_right - 18, panel_top + 152)
    loc_img = _load_location_thumb(session.location)
    if loc_img is not None:
        _paste_rounded(canvas, loc_img, thumb, radius=12)
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=12, outline=(120, 130, 110, 255), width=2)
    else:
        _draw_fallback_location_thumb(draw, thumb)

    loc = session.location
    draw = ImageDraw.Draw(canvas)
    loc_font = title_font if len(loc) <= 14 else _load_font(24)
    draw.text((panel_left + 24, panel_top + 160), loc, fill=(245, 245, 245, 255), font=loc_font)

    det_y = panel_top + 202
    _draw_detector_icon(draw, panel_left + 24, det_y, 72, 52)
    draw.text(
        (panel_left + 110, det_y),
        f"«{session.detector_name}»",
        fill=(230, 230, 230, 255),
        font=body_font,
    )
    filled = min(session.circles_filled, session.circles_needed)
    led_y = det_y + 34
    led_x0 = panel_left + 110
    for i in range(session.circles_needed):
        cx = led_x0 + i * 32
        if i < filled:
            draw.ellipse((cx - 14, led_y - 14, cx + 14, led_y + 14), fill=(40, 120, 50, 80))
            draw.ellipse((cx - 9, led_y - 9, cx + 9, led_y + 9), fill=(90, 230, 100, 255), outline=(40, 140, 55, 255))
            draw.ellipse((cx - 4, led_y - 5, cx + 1, led_y - 1), fill=(220, 255, 220, 200))
        else:
            draw.ellipse((cx - 9, led_y - 9, cx + 9, led_y + 9), fill=(48, 50, 52, 255), outline=(85, 85, 88, 255))

    # HD-экран сигнала детектора.
    screen = (panel_left + 22, panel_top + 275, panel_right - 22, panel_top + 440)
    dist = _chebyshev(session.player, session.artifact)
    strength = max(0.12, min(1.0, 1.0 - dist / 6.0))
    strength = max(strength, 0.18 + 0.16 * (filled / max(1, session.circles_needed)))
    _draw_signal_screen(canvas, screen, strength=strength)
    draw = ImageDraw.Draw(canvas)

    info_y = panel_top + 452
    draw.text(
        (panel_left + 28, info_y),
        f"Сигнал  {filled}/{session.circles_needed}",
        fill=(170, 220, 255, 255),
        font=body_font,
    )
    draw.text(
        (panel_left + 28, info_y + 26),
        f"Ход  {session.moves}/{session.max_moves}   ·   Аномалий  {len(session.anomalies)}",
        fill=(195, 195, 195, 255),
        font=small_font,
    )
    draw.text(
        (panel_left + 28, info_y + 48),
        f"Рад за вылазку  +{session.rad_gained}",
        fill=(210, 180, 140, 255),
        font=small_font,
    )

    hp = int(character.health) if character else 0
    max_hp = int(effective_max_health(character)) if character else 100
    rad = int(character.radiation) if character else 0
    energy = int(character.energy) if character else 0
    max_energy = int(character.max_energy) if character else 100
    hunger = int(character.hunger) if character else 0
    thirst = int(character.thirst) if character else 0

    bar_top = panel_top + 530
    bar_w = 44
    bar_h = 115
    gap = 62
    bx = panel_left + 40
    _draw_status_tube(
        draw, bx, bar_top, bar_w, bar_h, hp / max(1, max_hp),
        (220, 70, 45), "HP", f"{hp}/{max_hp}", tiny_font, tiny_font,
    )
    _draw_status_tube(
        draw, bx + gap, bar_top, bar_w, bar_h, min(1.0, rad / 100.0),
        (120, 200, 70), "RAD", f"{rad}", tiny_font, tiny_font,
    )
    _draw_status_tube(
        draw, bx + gap * 2, bar_top, bar_w, bar_h, energy / max(1, max_energy),
        (55, 130, 220), "EN", f"{energy}/{max_energy}", tiny_font, tiny_font,
    )
    draw.text(
        (panel_left + 28, panel_bottom - 42),
        f"Голод {hunger} · Жажда {thirst}",
        fill=(160, 160, 160, 255),
        font=tiny_font,
    )

    out = canvas.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
