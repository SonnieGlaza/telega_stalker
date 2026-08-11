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
    "Темная долина": (0.775, 0.725),
    "Янтарь": (0.180, 0.635),
    "Росток": (0.375, 0.620),
    "Армейские склады": (0.505, 0.530),
    "Рыжий лес": (0.325, 0.430),
    "Радар": (0.670, 0.415),
}

LOCATION_DISPLAY_NAMES: dict[str, str] = {
    "Болото": "Болото",
    "Кордон": "Кордон",
    "Свалка": "Свалка",
    "Темная долина": "Темная долина",
    "Янтарь": "Янтарь",
    "Росток": "Росток",
    "Армейские склады": "Арм. склады",
    "Рыжий лес": "Рыжий лес",
    "Радар": "Радар",
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

TELEGRAM_PHOTO_MAX_BYTES = 10 * 1024 * 1024
TELEGRAM_PHOTO_MAX_SUM_DIMENSION = 10_000
FALLBACK_SIZE = (3133, 8456)


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
        "Карта Зоны (фон не найден — положите zone_background.jpg)",
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


def _label_text_fill(name: str, marker_color: tuple[int, int, int]) -> tuple[int, int, int]:
    if name in {"Свалка", "Рыжий лес"}:
        return (245, 245, 245)
    return marker_color


def _draw_location_labels(
    canvas: Image.Image,
    *,
    current_location: str | None = None,
) -> None:
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    label_font = _load_font(max(48, width // 42))
    r = max(14, width // 55)

    for name in sorted(MAP_POINTS_NORM, key=lambda key: MAP_POINTS_NORM[key][1]):
        xy = _point_xy(name, width, height)
        if xy is None:
            continue
        x, y = xy
        marker_color = LOCATION_MARKER_COLORS.get(name, (210, 210, 210))
        outline = _marker_outline(marker_color)
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
        draw.text((lx, ly), display_name, fill=_label_text_fill(name, marker_color), font=label_font)


def build_zone_map_image(
    locations: list[dict[str, str | int | None]],
    current_location: str | None = None,
    player_faction: str | None = None,
    *,
    show_markers: bool = False,
) -> bytes:
    if not show_markers and ZONE_BACKGROUND_PATH.exists():
        data = ZONE_BACKGROUND_PATH.read_bytes()
        if data:
            return data

    canvas = _load_background()

    if show_markers:
        _draw_location_labels(canvas, current_location=current_location)

    canvas = _fit_for_telegram_photo(canvas)
    output = BytesIO()
    canvas.convert("RGB").save(output, format="JPEG", quality=88, optimize=True, progressive=True)
    data = output.getvalue()
    if not data:
        raise RuntimeError("zone map image is empty")
    return data
