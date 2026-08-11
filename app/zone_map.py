from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"
ZONE_BACKGROUND_PATH = PROJECT_ROOT / "assets" / "zone_map" / "zone_background.png"

# Нормализованные координаты (x%, y%) на спутниковой карте Зоны (Chernobyl Exclusion Zone).
MAP_POINTS_NORM: dict[str, tuple[float, float]] = {
    "Болото": (0.11, 0.88),
    "Кордон": (0.26, 0.95),
    "Свалка": (0.29, 0.60),
    "Темная долина": (0.82, 0.67),
    "Янтарь": (0.08, 0.47),
    "Росток": (0.35, 0.53),
    "Армейские склады": (0.12, 0.42),
    "НИИ Агропром": (0.54, 0.49),
    "Рыжий лес": (0.26, 0.39),
    "Радар": (0.34, 0.12),
}

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

TELEGRAM_MAX_DIMENSION = 2048
FALLBACK_SIZE = (900, 1263)


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        if LOCAL_FONT_PATH.exists():
            return ImageFont.truetype(str(LOCAL_FONT_PATH), size=size)
    except OSError:
        pass
    return ImageFont.load_default()


def _load_background() -> Image.Image:
    if ZONE_BACKGROUND_PATH.exists():
        try:
            bg = Image.open(ZONE_BACKGROUND_PATH).convert("RGBA")
            w, h = bg.size
            if w <= 0 or h <= 0:
                raise ValueError("invalid background dimensions")
            scale = min(1.0, TELEGRAM_MAX_DIMENSION / max(w, h))
            if scale < 1.0:
                bg = bg.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            return bg
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
        "Карта Зоны (фон не найден — положите zone_background.png)",
        fill=(220, 220, 210),
        font=title_font,
    )
    return bg


def _point_xy(name: str, width: int, height: int) -> tuple[int, int] | None:
    norm = MAP_POINTS_NORM.get(name)
    if norm is None:
        return None
    return int(norm[0] * width), int(norm[1] * height)


def _marker_outline(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return (240, 240, 240) if sum(color) < 280 else (35, 35, 35)


def build_zone_map_image(
    locations: list[dict[str, str | int | None]],
    current_location: str | None = None,
    player_faction: str | None = None,
) -> bytes:
    bg = _load_background()
    width, height = bg.size
    canvas = bg.copy()
    draw = ImageDraw.Draw(canvas)

    title_font = _load_font(max(20, width // 28))
    body_font = _load_font(max(16, width // 40))
    tiny_font = _load_font(max(13, width // 52))

    draw.rounded_rectangle((12, 12, min(width - 12, 360), 58), radius=8, fill=(0, 0, 0, 175))
    draw.text((24, 20), "Карта Зоны", fill=(235, 240, 230), font=title_font)

    visible = [
        loc
        for loc in locations
        if str(loc.get("name") or "") in MAP_POINTS_NORM
    ]
    visible.sort(key=lambda loc: MAP_POINTS_NORM[str(loc["name"])][1])

    for location in visible:
        name = str(location.get("name") or "")
        xy = _point_xy(name, width, height)
        if xy is None:
            continue
        x, y = xy
        point_type = str(location.get("point_type") or "")
        controlled_by = location.get("controlled_by")
        npc_power = int(location.get("npc_power") or 0)
        defense_bonus = int(location.get("defense_bonus") or 0)

        marker_color = LOCATION_MARKER_COLORS.get(name, (210, 210, 210))
        owner_color = FACTION_COLORS.get(str(controlled_by), (170, 170, 170))
        type_color = POINT_TYPE_COLORS.get(point_type, (210, 210, 210))

        r = max(12, width // 55)
        outline = _marker_outline(marker_color)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=marker_color + (255,), outline=outline, width=3)
        draw.ellipse(
            (x - r // 2, y - r // 2, x + r // 2, y + r // 2),
            fill=owner_color + (255,),
            outline=(15, 15, 15, 255),
            width=1,
        )
        if current_location and name == current_location:
            draw.ellipse((x - r - 8, y - r - 8, x + r + 8, y + r + 8), outline=(255, 240, 120, 255), width=3)

        owner_text = str(controlled_by) if controlled_by else "нейтрал"
        owner_marker = " (союз)" if player_faction and controlled_by == player_faction else ""
        defense_part = f"; +{defense_bonus} укр." if defense_bonus > 0 else ""
        details_text = f"{point_type}; {owner_text}{owner_marker}; NPC {npc_power}{defense_part}"

        short_name = name.replace("Армейские склады", "Арм. склады")
        tb = draw.textbbox((0, 0), short_name, font=body_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        lx = min(max(8, x - tw // 2), width - tw - 8)
        ly = max(64, min(height - 120, y - r - th - 12))
        pad = 4
        db = draw.textbbox((lx, ly + th + 2), details_text, font=tiny_font)
        box = (
            min(lx, db[0]) - pad,
            ly - pad,
            max(lx + tw, db[2]) + pad,
            max(ly + th, db[3]) + pad + 2,
        )
        draw.rounded_rectangle(box, radius=5, fill=(0, 0, 0, 190))
        text_fill = (235, 235, 235) if name == "Свалка" else marker_color
        draw.text((lx, ly), short_name, fill=text_fill, font=body_font)
        draw.text((lx, ly + th + 2), details_text, fill=(200, 205, 200), font=tiny_font)

        # Маленькое кольцо типа точки.
        draw.ellipse(
            (x + r + 2, y - r - 2, x + r + 10, y - r + 6),
            fill=type_color + (255,),
            outline=(20, 20, 20, 255),
            width=1,
        )

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    data = output.getvalue()
    if not data:
        raise RuntimeError("zone map PNG is empty")
    return data
