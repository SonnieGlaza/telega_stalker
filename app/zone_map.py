from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"
LOCAL_FONT_FALLBACK_PATH = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
ZONE_BACKGROUND_PATH = PROJECT_ROOT / "assets" / "zone_map" / "zone_background.jpg"

# Нормализованные координаты (x%, y%) — разметка на zone_background.jpg.
MAP_POINTS_NORM: dict[str, tuple[float, float]] = {
    "Болото": (0.145, 0.875),
    "Кордон": (0.450, 0.875),
    "Свалка": (0.495, 0.750),
    "НИИ Агропром": (0.220, 0.720),
    "Темная долина": (0.775, 0.725),
    "Янтарь": (0.180, 0.635),
    "Росток": (0.375, 0.620),
    "Армейские склады": (0.505, 0.530),
    "Рыжий лес": (0.325, 0.355),
    "Радар": (0.670, 0.415),
}

LOCATION_DISPLAY_NAMES: dict[str, str] = {
    "Болото": "Болото",
    "Кордон": "Кордон",
    "Свалка": "Свалка",
    "НИИ Агропром": "Агропром",
    "Темная долина": "Темная долина",
    "Янтарь": "Янтарь",
    "Росток": "Росток",
    "Армейские склады": "Арм. склады",
    "Рыжий лес": "Рыжий лес",
    "Радар": "Радар",
}

# Смещения подписи относительно точки (в долях ширины / высоты карты).
LABEL_OFFSETS_NORM: dict[str, tuple[float, float]] = {
    "Болото": (-0.34, 0.022),
    "Кордон": (0.06, 0.022),
    "Свалка": (0.05, -0.055),
    "НИИ Агропром": (-0.28, -0.01),
    "Темная долина": (-0.02, 0.022),
    "Янтарь": (0.04, 0.02),
    "Росток": (-0.28, -0.055),
    "Армейские склады": (0.04, 0.02),
    "Рыжий лес": (0.04, 0.022),
    "Радар": (0.04, -0.055),
}

# Кандидаты смещения, если preferred пересекается с уже занятой плашкой.
LABEL_FALLBACK_OFFSETS_NORM: tuple[tuple[float, float], ...] = (
    (0.04, 0.022),
    (-0.34, 0.022),
    (0.04, -0.055),
    (-0.34, -0.055),
    (0.04, 0.05),
    (-0.34, 0.05),
    (0.12, -0.08),
    (-0.42, -0.08),
)

MAP_LABEL_MARKER_COLOR = (0, 210, 255)
MAP_LABEL_TEXT_COLOR = (255, 255, 255)

# Для расчёта времени перехода (legacy-сетка; синхрон с game_logic.MAP_TRAVEL_POINTS).
MAP_POINTS: dict[str, tuple[int, int]] = {
    "Кордон": (324, 1204),
    "Свалка": (387, 980),
    "Росток": (360, 700),
    "Армейские склады": (450, 532),
    "НИИ Агропром": (558, 672),
    "Янтарь": (162, 784),
    "Болото": (108, 1176),
    "Темная долина": (666, 1064),
    "Рыжий лес": (378, 336),
    "Радар": (522, 168),
}

LOCATION_MARKER_COLORS: dict[str, tuple[int, int, int]] = {
    "Болото": (35, 110, 255),
    "Кордон": (255, 150, 45),
    "Свалка": (25, 25, 25),
    "Темная долина": (80, 210, 255),
    "Янтарь": (150, 95, 55),
    "Росток": (230, 55, 55),
    "Армейские склады": (55, 180, 85),
    "НИИ Агропром": (200, 160, 255),
    "Рыжий лес": (245, 245, 245),
    "Радар": (170, 95, 230),
}

FACTION_COLORS = {
    "Долг": (230, 70, 70),
    "Свобода": (70, 200, 110),
    "Нейтралы": (245, 150, 55),
    "Бандиты": (18, 18, 18),
}

POINT_TYPE_COLORS = {
    "база": (80, 170, 255),
    "точка ресурсов": (245, 210, 70),
    "точка интереса": (186, 130, 255),
}

TELEGRAM_PHOTO_MAX_BYTES = 10 * 1024 * 1024
TELEGRAM_PHOTO_MAX_SUM_DIMENSION = 10_000
FALLBACK_SIZE = (3133, 8456)
# Лёгкое затемнение спутникового фона, чтобы плашки и маркеры читались лучше.
MAP_BACKGROUND_DARKEN_ALPHA = 125
MAP_CONNECTOR_COLOR = (180, 200, 185, 255)


def _load_font(size: int) -> ImageFont.ImageFont:
    for font_path in (LOCAL_FONT_PATH, LOCAL_FONT_FALLBACK_PATH):
        try:
            if font_path.exists():
                return ImageFont.truetype(str(font_path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_for_telegram_photo(image: Image.Image) -> Image.Image:
    """sendPhoto принимает только если width + height <= 10000."""
    width, height = image.size
    total = width + height
    if total <= TELEGRAM_PHOTO_MAX_SUM_DIMENSION:
        return image
    scale = (TELEGRAM_PHOTO_MAX_SUM_DIMENSION - 10) / total
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    logger.info("Scaling zone map for Telegram: %sx%s -> %sx%s", width, height, *new_size)
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _load_background() -> Image.Image:
    if ZONE_BACKGROUND_PATH.exists():
        try:
            bg = Image.open(ZONE_BACKGROUND_PATH).convert("RGBA")
            w, h = bg.size
            if w <= 0 or h <= 0:
                raise ValueError("invalid background dimensions")
            shade = Image.new("RGBA", (w, h), (0, 0, 0, MAP_BACKGROUND_DARKEN_ALPHA))
            return Image.alpha_composite(bg, shade)
        except Exception:
            logger.exception("Failed to load zone background from %s", ZONE_BACKGROUND_PATH)

    w, h = FALLBACK_SIZE
    bg = Image.new("RGBA", (w, h), (48, 52, 46, 255))
    draw = ImageDraw.Draw(bg)
    for y in range(0, h, 4):
        shade = 40 + (y * 30 // h)
        draw.line((0, y, w, y), fill=(shade, shade + 8, shade - 4, 255))
    title_font = _load_font(22)
    draw.rounded_rectangle((16, 16, w - 16, 72), radius=8, fill=(0, 0, 0, 170))
    draw.text(
        (28, 26),
        "Карта Зоны (фон не найден — положите zone_background.jpg)",
        fill=(220, 220, 210),
        font=title_font,
    )
    return bg


def _label_anchor(x: int, y: int, box: tuple[int, int, int, int]) -> tuple[int, int]:
    """Ближайшая точка на краю плашки к маркеру — якорь для соединительной линии."""
    box_x1, box_y1, box_x2, box_y2 = box
    if x < box_x1:
        anchor_x = box_x1
    elif x > box_x2:
        anchor_x = box_x2
    else:
        anchor_x = x
    if y < box_y1:
        anchor_y = box_y1
    elif y > box_y2:
        anchor_y = box_y2
    else:
        anchor_y = y
    return anchor_x, anchor_y


def _point_xy(name: str, width: int, height: int) -> tuple[int, int] | None:
    norm = MAP_POINTS_NORM.get(name)
    if norm is None:
        return None
    return int(norm[0] * width), int(norm[1] * height)


def _marker_outline(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return (240, 240, 240) if sum(color) < 280 else (35, 35, 35)


def _short_point_type(point_type: str) -> str:
    mapping = {
        "база": "база",
        "точка ресурсов": "ресурсы",
        "точка интереса": "интерес",
    }
    return mapping.get(point_type, point_type or "точка")


def _rects_intersect(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _clamp_label_box(
    *,
    label_x: int,
    label_y: int,
    box: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[int, int, tuple[int, int, int, int]]:
    box_x1, box_y1, box_x2, box_y2 = box
    shift_x = 0
    shift_y = 0
    if box_x1 < 8:
        shift_x = 8 - box_x1
    elif box_x2 > width - 8:
        shift_x = (width - 8) - box_x2
    if box_y1 < 8:
        shift_y = 8 - box_y1
    elif box_y2 > height - 8:
        shift_y = (height - 8) - box_y2
    if shift_x or shift_y:
        label_x += shift_x
        label_y += shift_y
        box_x1 += shift_x
        box_y1 += shift_y
        box_x2 += shift_x
        box_y2 += shift_y
    return label_x, label_y, (box_x1, box_y1, box_x2, box_y2)


def _draw_control_overlays(
    canvas: Image.Image,
    locations: list[dict[str, str | int | None]],
    *,
    current_location: str | None = None,
    player_faction: str | None = None,
) -> None:
    """Маркеры контроля + подписи: тип территории, владелец, сила NPC."""
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    name_font = _load_font(max(22, width // 28))
    details_font = _load_font(max(17, width // 38))
    r_outer = max(12, width // 48)
    r_inner = max(7, width // 78)
    pad = max(6, width // 110)
    gap = max(4, pad // 2)

    by_name = {str(loc.get("name") or ""): loc for loc in locations}
    ordered = sorted(
        (name for name in MAP_POINTS_NORM if name in by_name),
        key=lambda key: MAP_POINTS_NORM[key][1],
    )
    reserved_rects: list[tuple[int, int, int, int]] = []

    for name in ordered:
        location = by_name[name]
        xy = _point_xy(name, width, height)
        if xy is None:
            continue
        x, y = xy
        point_type = str(location.get("point_type") or "")
        controlled_by = location.get("controlled_by")
        npc_power = int(location.get("npc_power") or 0)

        type_color = POINT_TYPE_COLORS.get(point_type, (210, 210, 210))
        owner_color = FACTION_COLORS.get(str(controlled_by), (170, 170, 170))
        owner_outline = _marker_outline(owner_color)

        # Внешнее кольцо — тип точки, заливка — фракция-контролёр.
        draw.ellipse(
            (x - r_outer, y - r_outer, x + r_outer, y + r_outer),
            fill=(20, 24, 22, 230),
            outline=type_color + (255,),
            width=max(3, r_outer // 5),
        )
        draw.ellipse(
            (x - r_inner, y - r_inner, x + r_inner, y + r_inner),
            fill=owner_color + (255,),
            outline=owner_outline + (255,),
            width=max(2, r_inner // 4),
        )
        if current_location and name == current_location:
            draw.ellipse(
                (x - r_outer - 8, y - r_outer - 8, x + r_outer + 8, y + r_outer + 8),
                outline=(255, 240, 120, 255),
                width=max(3, r_outer // 4),
            )

        owner_text = str(controlled_by) if controlled_by else "нейтрал"
        owner_marker = ""
        if player_faction and controlled_by == player_faction:
            owner_marker = " (союз)"
        display_name = LOCATION_DISPLAY_NAMES.get(name, name)
        details_text = f"{point_type or 'точка'}; {owner_text}{owner_marker}; NPC {npc_power}"

        preferred = LABEL_OFFSETS_NORM.get(name, (0.02, 0.016))
        candidates: list[tuple[float, float]] = [preferred]
        for offset in LABEL_FALLBACK_OFFSETS_NORM:
            if offset not in candidates:
                candidates.append(offset)

        selected: tuple[int, int, tuple[int, int, int, int], int] | None = None
        for ox, oy in candidates:
            label_x = int(x + ox * width)
            label_y = int(y + oy * height)
            name_bbox = draw.textbbox((label_x, label_y), display_name, font=name_font)
            line_gap = (name_bbox[3] - name_bbox[1]) + 6
            details_bbox = draw.textbbox(
                (label_x, label_y + line_gap),
                details_text,
                font=details_font,
            )
            box = (
                min(name_bbox[0], details_bbox[0]) - pad,
                min(name_bbox[1], details_bbox[1]) - pad,
                max(name_bbox[2], details_bbox[2]) + pad,
                max(name_bbox[3], details_bbox[3]) + pad,
            )
            label_x, label_y, box = _clamp_label_box(
                label_x=label_x,
                label_y=label_y,
                box=box,
                width=width,
                height=height,
            )
            padded = (box[0] - gap, box[1] - gap, box[2] + gap, box[3] + gap)
            if any(_rects_intersect(padded, reserved) for reserved in reserved_rects):
                continue
            selected = (label_x, label_y, box, line_gap)
            break

        if selected is None:
            ox, oy = preferred
            label_x = int(x + ox * width)
            label_y = int(y + oy * height)
            name_bbox = draw.textbbox((label_x, label_y), display_name, font=name_font)
            line_gap = (name_bbox[3] - name_bbox[1]) + 6
            details_bbox = draw.textbbox(
                (label_x, label_y + line_gap),
                details_text,
                font=details_font,
            )
            box = (
                min(name_bbox[0], details_bbox[0]) - pad,
                min(name_bbox[1], details_bbox[1]) - pad,
                max(name_bbox[2], details_bbox[2]) + pad,
                max(name_bbox[3], details_bbox[3]) + pad,
            )
            label_x, label_y, box = _clamp_label_box(
                label_x=label_x,
                label_y=label_y,
                box=box,
                width=width,
                height=height,
            )
            selected = (label_x, label_y, box, line_gap)

        label_x, label_y, box, line_gap = selected
        box_x1, box_y1, box_x2, box_y2 = box
        reserved_rects.append((box_x1 - gap, box_y1 - gap, box_x2 + gap, box_y2 + gap))

        # Полоска от маркера к плашке — видно, какая подпись к какой точке.
        anchor_x, anchor_y = _label_anchor(x, y, box)
        line_w = max(3, width // 160)
        draw.line((x, y, anchor_x, anchor_y), fill=MAP_CONNECTOR_COLOR, width=line_w)
        dot = max(2, line_w)
        draw.ellipse(
            (anchor_x - dot, anchor_y - dot, anchor_x + dot, anchor_y + dot),
            fill=MAP_CONNECTOR_COLOR,
            outline=(20, 26, 22, 255),
            width=1,
        )

        draw.rounded_rectangle(
            (box_x1, box_y1, box_x2, box_y2),
            radius=max(6, pad),
            fill=(10, 14, 12, 220),
            outline=(70, 90, 80, 255),
            width=max(2, pad // 4),
        )
        name_fill = (255, 245, 170) if current_location and name == current_location else MAP_LABEL_TEXT_COLOR
        draw.text((label_x, label_y), display_name, fill=name_fill, font=name_font)
        draw.text(
            (label_x, label_y + line_gap),
            details_text,
            fill=(190, 205, 195),
            font=details_font,
        )


def _draw_location_labels(
    canvas: Image.Image,
    *,
    current_location: str | None = None,
) -> None:
    """Простые подписи имён (без динамики контроля) — legacy/fallback."""
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    label_font = _load_font(max(48, width // 42))
    r = max(14, width // 55)

    for name in sorted(MAP_POINTS_NORM, key=lambda key: MAP_POINTS_NORM[key][1]):
        xy = _point_xy(name, width, height)
        if xy is None:
            continue
        x, y = xy
        marker_color = MAP_LABEL_MARKER_COLOR
        outline = (15, 35, 45)
        display_name = LOCATION_DISPLAY_NAMES.get(name, name)

        draw.ellipse((x - r, y - r, x + r, y + r), fill=marker_color + (255,), outline=outline, width=max(2, r // 6))
        if current_location and name == current_location:
            draw.ellipse((x - r - 6, y - r - 6, x + r + 6, y + r + 6), outline=(255, 240, 120, 255), width=max(2, r // 5))

        tb = draw.textbbox((0, 0), display_name, font=label_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        lx = min(max(8, x - tw // 2), width - tw - 8)
        ly = max(8, min(height - th - 8, y - r - th - 10))
        pad = 10
        draw.rounded_rectangle((lx - pad, ly - pad, lx + tw + pad, ly + th + pad), radius=8, fill=(0, 0, 0, 210))
        draw.text((lx, ly), display_name, fill=MAP_LABEL_TEXT_COLOR, font=label_font)


def build_zone_map_image(
    locations: list[dict[str, str | int | None]],
    current_location: str | None = None,
    player_faction: str | None = None,
    *,
    show_markers: bool = True,
) -> bytes:
    canvas = _load_background()

    if show_markers:
        if locations:
            _draw_control_overlays(
                canvas,
                locations,
                current_location=current_location,
                player_faction=player_faction,
            )
        else:
            _draw_location_labels(canvas, current_location=current_location)

    canvas = _fit_for_telegram_photo(canvas)
    output = BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=88, optimize=True, progressive=True)
    data = output.getvalue()
    if not data:
        raise RuntimeError("zone map image is empty")
    return data
