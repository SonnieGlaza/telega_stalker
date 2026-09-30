"""Открытая локация: прогулка по карте вместо списка кнопок-зон.

Это «осмотр локации», а не вылазка: шаг по сетке бесплатный (без энергии),
busy-сессий не создаётся и в player_busy_reason прогулка не участвует.
Игрок ходит по сетке 15×15; когда заходит в зону (круг по Чебышёву),
в клавиатуре появляется действие этой зоны (торговец/база, обыск,
поиск артов, лаборатория, тайный торговец).
"""

from __future__ import annotations

import json
import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from app.artifact_hunt import (
    _character_rating_points,
    _cover_crop,
    _draw_cell,
    _glow,
    _load_font,
    _load_hunt_field_background,
    _load_location_thumb,
    _paste_circle,
    _paste_rounded,
    _player_grid_token,
)
from app.image_text import render_emoji_glyph
from app.location_zones import location_zones_for
from app.storage import Character, Storage

WALK_META_PREFIX = "locwalk:"
WALK_GRID = 15

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

WALK_DIRECTION_KEYS = frozenset(MOVE_DELTAS)

# Цвета зон на поле: base/торговец — «радужная» база (заливка голубая, кольцо дугами),
# search — жёлтая, anomaly — сине-бирюзовая, lab — фиолетовая, тайный торговец — янтарная.
ZONE_COLORS: dict[str, tuple[int, int, int]] = {
    "base": (220, 60, 60),
    "search": (245, 210, 70),
    "anomaly": (240, 240, 240),
    "lab": (70, 200, 90),
    "secrettrader": (255, 170, 90),
    "bazaar": (255, 190, 80),
    "trade": (80, 170, 255),
}

ZONE_LEGEND_LABELS: dict[str, str] = {
    "base": "База",
    "search": "Обыск",
    "anomaly": "Аномалия",
    "lab": "Лаборатория",
    "secrettrader": "Бунс",
    "bazaar": "Барахолка",
    "trade": "Торговец",
}

_BASE_ZONE: dict[str, str] = {"id": "base", "kind": "base", "label": "База группировки"}
_SECRET_ZONE: dict[str, str] = {"id": "secrettrader", "kind": "secrettrader", "label": "Бунс"}

_DEFAULT_ZONE_RADIUS = 2
_BASE_SPOT: tuple[int, int, int] = (11, 11, _DEFAULT_ZONE_RADIUS)

# Разметка зон на сетке локации (новый формат): location -> {zone_id: точки}.
# Каждая точка — (x1, y1, x2, y2) в координатах игрока: (1,1) — левая верхняя
# клетка поля. «X1-X2, Y1-Y2» = прямоугольник клеток; одна клетка = X1==X2, Y1==Y2.
# Точки перечисляются через «;» — мест одной зоны (аномалий/обыска) может быть несколько.
LOCATION_WALK_RECTS: dict[str, dict[str, tuple[tuple[int, int, int, int], ...]]] = {
    "Кордон": {
        "anomaly": (
            (2, 10, 3, 10),
            (4, 8, 4, 8),
            (9, 4, 9, 4),
            (10, 8, 10, 8),
        ),
        "search_1": (
            (7, 5, 7, 5),
            (14, 5, 14, 5),
            (7, 8, 7, 8),
            (9, 9, 10, 10),
        ),
        "base": (
            (3, 12, 4, 13),
        ),
    },
}

# Старый формат (центр + радиус «квадрата», 0-индексный) для локаций, координаты
# которых ещё не переведены в LOCATION_WALK_RECTS. Переводим по мере поступления.
_WALK_LEGACY_CENTER_SPOTS: dict[str, dict[str, tuple[int, int] | tuple[int, int, int]]] = {
    "Свалка": {
        "anomaly": (4, 4),
        "search_1": (11, 11),
        "base": (4, 11),
    },
    "Росток": {
        "anomaly": (4, 4),
        "search_1": (7, 5, 0),
        "base": (4, 11),
    },
    "Армейские склады": {
        "anomaly": (11, 4),
        "search_1": (4, 4),
        "base": (7, 11),
    },
    "НИИ Агропром": {
        "anomaly": (4, 4),
        "search_1": (11, 11),
    },
    "Янтарь": {
        "anomaly": (4, 4),
        "search_1": (11, 4),
        "lab_limit2": (11, 11),
    },
    "Болото": {
        "anomaly": (4, 11),
        "search_1": (11, 4),
    },
    "Темная долина": {
        "anomaly": (4, 4),
        "search_1": (11, 11),
        "lab_limit1": (4, 11),
    },
    "Рыжий лес": {
        "anomaly": (11, 11),
        "search_1": (4, 4),
    },
    "Радар": {
        "anomaly": (4, 4),
        "search_1": (11, 11),
        "lab_limit3": (11, 4),
    },
    "Припять": {
        "anomaly": (4, 4),
        "search_1": (11, 4),
        "secrettrader": (7, 10, 1),
    },
    "ЧАЭС": {
        "base": (7, 7, 4),
    },
    "Тунель": {
        "bazaar": (8, 6, 1),
        "trade": (11, 7, 1),
    },
}


def _normalize_spot(spot: tuple[int, int] | tuple[int, int, int]) -> tuple[int, int, int]:
    """(x, y) -> (x, y, _DEFAULT_ZONE_RADIUS); (x, y, radius) — как есть.

    Радиус — размер «квадрата» зоны вокруг центра (круг по Чебышёву);
    0 — одна клетка.
    """
    if len(spot) == 2:
        return int(spot[0]), int(spot[1]), _DEFAULT_ZONE_RADIUS
    return int(spot[0]), int(spot[1]), max(0, int(spot[2]))


def _walk_meta_key(telegram_id: int) -> str:
    return f"{WALK_META_PREFIX}{int(telegram_id)}"


def _clamp_coord(value: Any) -> int:
    return max(0, min(WALK_GRID - 1, int(value)))


def _save_walk_position(storage: Storage, telegram_id: int, location: str, x: int, y: int) -> None:
    storage.set_meta(
        _walk_meta_key(telegram_id),
        json.dumps({"location": str(location), "x": int(x), "y": int(y)}, ensure_ascii=False),
    )


def clear_walk_position(storage: Storage, telegram_id: int) -> None:
    """Явный сброс прогулки (респавн, смена локации и т.п.)."""
    storage.delete_meta(_walk_meta_key(telegram_id))


def get_walk_position(storage: Storage, telegram_id: int) -> tuple[int, int]:
    """Позиция игрока на сетке локации.

    Если записи нет или она относится к другой локации — сброс на центр
    сетки (с записью). Неизвестный игрок — центр без записи.
    """
    player = storage.get_character(telegram_id, refresh_energy=False)
    center = WALK_GRID // 2
    if player is None:
        return center, center
    location = str(player.location)
    x = y = center
    raw = storage.get_meta(_walk_meta_key(telegram_id))
    valid = False
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and str(data.get("location") or "") == location:
            try:
                x = _clamp_coord(data.get("x"))
                y = _clamp_coord(data.get("y"))
                valid = True
            except (TypeError, ValueError):
                valid = False
    if not valid:
        _save_walk_position(storage, telegram_id, location, x, y)
    return x, y


def move_walk_position(storage: Storage, telegram_id: int, direction: str) -> tuple[int, int]:
    """Шаг по сетке с клампом в границы. Ход бесплатный, busy-режимов нет."""
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return get_walk_position(storage, telegram_id)
    x, y = get_walk_position(storage, telegram_id)
    delta = MOVE_DELTAS.get(str(direction or "").strip().lower())
    if delta is None:
        return x, y
    new_x = _clamp_coord(x + delta[0])
    new_y = _clamp_coord(y + delta[1])
    _save_walk_position(storage, telegram_id, str(player.location), new_x, new_y)
    return new_x, new_y


def _fallback_spots(location: str) -> dict[str, tuple[int, int, int]]:
    """Авто-разметка для локаций без ручной: зоны по кругу вокруг центра, радиус 2."""
    spots: dict[str, tuple[int, int, int]] = {}
    zones = location_zones_for(location)
    total = max(1, len(zones))
    center = WALK_GRID // 2
    orbit = 4
    for index, zone in enumerate(zones):
        angle = 2 * math.pi * index / total - math.pi / 2
        cx = _clamp_coord(center + round(orbit * math.cos(angle)))
        cy = _clamp_coord(center + round(orbit * math.sin(angle)))
        zone_id = str(zone.get("id") or f"zone_{index}")
        spots[zone_id] = (cx, cy, _DEFAULT_ZONE_RADIUS)
    return spots


def _zone_dict_for(zone_id: str, location: str) -> dict[str, str]:
    """Словарь зоны {id, kind, label} по id (base/secrettrader — особые)."""
    if zone_id == "base":
        return dict(_BASE_ZONE)
    if zone_id == "secrettrader":
        return dict(_SECRET_ZONE)
    zone_by_id = {str(z.get("id") or ""): z for z in location_zones_for(location)}
    source = zone_by_id.get(zone_id)
    return {
        "id": zone_id,
        "kind": str((source or {}).get("kind") or ""),
        "label": str((source or {}).get("label") or zone_id),
    }


def walk_zone_rects(
    location: str,
    faction: str | None,
) -> list[tuple[dict[str, str], tuple[int, int, int, int]]]:
    """Зоны локации как прямоугольники клеток (0-индексные, включительно).

    Новый формат (LOCATION_WALK_RECTS) — точные квадраты (x1, y1, x2, y2)
    в координатах игрока, где (1,1) — левая верхняя клетка. Старый формат
    (центр + радиус) переводится в «квадрат» для ещё не переведённых локаций.
    «base» показывается только фракции-владельцу локации.
    """
    from app.game_logic import faction_home_base

    is_own_base = bool(faction) and location == faction_home_base(faction)
    rects = LOCATION_WALK_RECTS.get(location)
    if rects is not None:
        result: list[tuple[dict[str, str], tuple[int, int, int, int]]] = []
        for zone_id, spots in rects.items():
            if zone_id == "base" and not is_own_base:
                continue
            zone = _zone_dict_for(zone_id, location)
            for x1, y1, x2, y2 in spots:
                result.append((zone, (x1 - 1, y1 - 1, x2 - 1, y2 - 1)))
        return result

    raw_spots = _WALK_LEGACY_CENTER_SPOTS.get(location) or _fallback_spots(location)
    if is_own_base:
        raw_spots = dict(raw_spots)
        raw_spots.setdefault("base", _BASE_SPOT)
    result = []
    for zone_id, spot in raw_spots.items():
        if zone_id == "base" and not is_own_base:
            # «base» в разметке показываем только своей фракции, чужим — нет.
            continue
        cx, cy, radius = _normalize_spot(spot)
        result.append(
            (_zone_dict_for(zone_id, location), (cx - radius, cy - radius, cx + radius, cy + radius))
        )
    return result


def zone_at(location: str, x: int, y: int, faction: str | None = None) -> dict[str, str] | None:
    """Зона под клеткой (прямоугольник) или None."""
    for zone, (x0, y0, x1, y1) in walk_zone_rects(location, faction):
        if x0 <= int(x) <= x1 and y0 <= int(y) <= y1:
            return zone
    return None


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> str:
    text = str(text)
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return f"{text}…" if text else text


def _draw_zone(
    canvas: Image.Image,
    kind: str,
    color: tuple[int, int, int],
    box: tuple[int, int, int, int],
) -> None:
    """Прямоугольник-зона из клеток: полупрозрачная заливка + жирная обводка."""
    cell = 44
    left, top, right, bottom = box
    w = max(1, right - left)
    h = max(1, bottom - top)
    radius = max(4, min(cell // 3, min(w, h) // 2))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(
        (left, top, right, bottom),
        radius=radius,
        fill=(*color, 46),
    )
    canvas.alpha_composite(overlay)
    draw = ImageDraw.Draw(canvas)
    if kind == "base":
        rainbow = (
            (255, 80, 80),
            (255, 170, 50),
            (250, 220, 70),
            (90, 210, 90),
            (80, 170, 255),
            (180, 120, 240),
        )
        segments = 4 * len(rainbow)
        step = 1.0 / (len(rainbow) * 4)
        for idx, arc_color in enumerate(rainbow):
            for seg in range(4):
                start = idx * 4 + seg
                f0, f1 = start * step, (start + 1) * step
                if seg == 0:  # top
                    a, b, c, d = (left + f0 * w, top, left + f1 * w, top + 8)
                elif seg == 1:  # right
                    a, b, c, d = (right - 8, top + f0 * h, right, top + f1 * h)
                elif seg == 2:  # bottom
                    a, b, c, d = (right - f1 * w, bottom - 8, right - f0 * w, bottom)
                else:  # left
                    a, b, c, d = (left, bottom - f1 * h, left + 8, bottom - f0 * h)
                draw.rectangle((a, b, c, d), fill=arc_color)
    else:
        draw.rounded_rectangle(
            box,
            radius=radius,
            outline=color,
            width=5,
        )
    if kind == "anomaly":
        # «Пузырьки» аномалий — только на достаточно крупных зонах.
        if w >= cell * 2 and h >= cell * 2:
            offsets = (
                (-0.55, -0.45),
                (0.45, -0.6),
                (0.65, 0.3),
                (-0.3, 0.6),
                (-0.8, 0.1),
                (0.15, 0.8),
            )
            for fx, fy in offsets[: 3 + 3 * max(0, min(1, min(w, h) // cell - 1))]:
                br = max(4, cell // 2)
                bx = int(left + (fx + 1) / 2 * w)
                by = int(top + (fy + 1) / 2 * h)
                draw.ellipse((bx - br, by - br, bx + br, by + br), outline=(*color, 220), width=2)
    if kind == "lab":
        glyph = render_emoji_glyph("🧪", 26)
        if glyph is not None:
            canvas.paste(
                glyph,
                (
                    (left + right) // 2 - glyph.size[0] // 2,
                    (top + bottom) // 2 - glyph.size[1] // 2,
                ),
                glyph,
            )


def render_walk_frame(storage: Storage, player: Character) -> bytes:
    """Кадр «открытой локации»: поле 15×15 с зонами + панель осмотра."""
    cell = 44
    grid = WALK_GRID
    grid_px = grid * cell
    margin = 20
    panel_w = 280
    width = margin + grid_px + 16 + panel_w + margin
    height = max(margin + grid_px + margin, 720)

    location = str(player.location)
    faction = str(player.faction or "")
    zones_here = walk_zone_rects(location, faction)
    x, y = get_walk_position(storage, player.telegram_id)
    current_zone = zone_at(location, x, y, faction)

    canvas = Image.new("RGBA", (width, height), (16, 18, 20, 255))
    draw = ImageDraw.Draw(canvas)

    field = (margin - 6, margin - 6, margin + grid_px + 6, margin + grid_px + 6)
    draw.rounded_rectangle(field, radius=10, fill=(34, 36, 40, 255), outline=(70, 74, 80), width=2)

    loc_bg = _load_hunt_field_background(location)
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

    for zone, (rx0, ry0, rx1, ry1) in zones_here:
        kind = str(zone.get("kind") or "")
        color = ZONE_COLORS.get(kind, (200, 200, 200))
        box = (
            margin + rx0 * cell,
            margin + ry0 * cell,
            margin + (rx1 + 1) * cell - 1,
            margin + (ry1 + 1) * cell - 1,
        )
        _draw_zone(canvas, kind, color, box)

    pcx = margin + x * cell + cell // 2
    pcy = margin + y * cell + cell // 2
    if current_zone is not None:
        _glow(canvas, pcx, pcy, ZONE_COLORS.get(str(current_zone.get("kind") or ""), (200, 200, 200)), 16)
    token = _player_grid_token(
        player,
        size=160,
        rating_points=_character_rating_points(storage, player.telegram_id),
    )
    # На Тунеле маркер игрока рисуется без зелёного кольца (по просьбе).
    ring_color = None if location == "Тунель" else (72, 220, 90)
    _paste_circle(canvas, token, pcx, pcy, 40, ring_color=ring_color, ring_width=3)

    pl = margin + grid_px + 16
    pr = width - margin
    pt = margin - 6
    pb = height - margin + 6
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((pl, pt, pr, pb), radius=14, fill=(48, 50, 54, 255), outline=(100, 104, 110), width=2)

    thumb = (pl + 12, pt + 10, pr - 12, pt + 100)
    loc_img = _load_location_thumb(location)
    if loc_img is not None:
        _paste_rounded(canvas, loc_img, thumb, radius=8)
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=8, outline=(110, 120, 100), width=2)
    else:
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=8, fill=(30, 34, 28), outline=(90, 100, 80), width=2)

    title_font = _load_font(20)
    body = _load_font(16)
    small = _load_font(13)
    loc_font = title_font if len(location) <= 14 else _load_font(16)
    panel_text_width = pr - pl - 30
    draw.text((pl + 14, pt + 106), location, fill=(245, 245, 245), font=loc_font)
    draw.text((pl + 14, pt + 132), "Осмотр локации", fill=(180, 200, 150), font=body)
    draw.text((pl + 16, pt + 160), f"Координаты: X {x + 1} · Y {y + 1}", fill=(200, 200, 200), font=body)

    zone_y = pt + 190
    if current_zone is not None:
        zlabel = str(current_zone.get("label") or current_zone.get("id") or "")
        zcolor = ZONE_COLORS.get(str(current_zone.get("kind") or ""), (200, 200, 200))
        draw.text((pl + 16, zone_y), "Ты в зоне:", fill=zcolor, font=body)
        draw.text(
            (pl + 16, zone_y + 22),
            _fit_text(draw, zlabel, body, panel_text_width),
            fill=(240, 240, 240),
            font=body,
        )
        zone_y += 52
    else:
        draw.text((pl + 16, zone_y), "Рядом зон нет", fill=(170, 170, 170), font=body)
        zone_y += 30

    draw.text((pl + 16, zone_y + 6), "Легенда:", fill=(220, 220, 220), font=small)
    entry_y = zone_y + 30
    seen_kinds: set[str] = set()
    for zone, _spot in zones_here:
        kind = str(zone.get("kind") or "")
        if not kind or kind in seen_kinds:
            continue
        seen_kinds.add(kind)
        dot_y = entry_y + 9
        draw.ellipse((pl + 22, dot_y - 6, pl + 34, dot_y + 6), fill=ZONE_COLORS.get(kind, (200, 200, 200)))
        draw.text((pl + 44, entry_y), ZONE_LEGEND_LABELS.get(kind, kind), fill=(210, 210, 210), font=small)
        entry_y += 24
    # Постоянная легенда цветов зон (видна на любой локации).
    for kind, label in (
        ("lab", "Лаборатория"),
        ("search", "Обыск"),
        ("anomaly", "Аномалия"),
        ("base", "База"),
    ):
        if kind in seen_kinds:
            continue
        dot_y = entry_y + 9
        draw.ellipse((pl + 22, dot_y - 6, pl + 34, dot_y + 6), fill=ZONE_COLORS.get(kind, (200, 200, 200)))
        draw.text((pl + 44, entry_y), label, fill=(210, 210, 210), font=small)
        entry_y += 24

    draw.text((pl + 14, pb - 42), "Стрелки — шаг по локации (бесплатно)", fill=(210, 210, 210), font=small)
    draw.text((pl + 14, pb - 24), "Зайди в круг зоны — появится действие", fill=(190, 190, 190), font=small)

    out = canvas.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
