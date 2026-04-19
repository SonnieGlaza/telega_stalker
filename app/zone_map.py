from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"

MAP_POINTS: dict[str, tuple[int, int]] = {
    "Росток": (360, 430),
    "Армейские склады": (190, 280),
    "Янтарь": (560, 240),
    "Темная долина": (500, 520),
    "Радар": (700, 140),
}

FACTION_COLORS = {
    "Долг": (230, 70, 70),
    "Свобода": (70, 200, 110),
}

POINT_TYPE_COLORS = {
    "база": (80, 170, 255),
    "точка ресурсов": (245, 210, 70),
    "точка интереса": (186, 130, 255),
}


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        if LOCAL_FONT_PATH.exists():
            return ImageFont.truetype(str(LOCAL_FONT_PATH), size=size)
    except OSError:
        pass
    return ImageFont.load_default()


def build_zone_map_image(
    locations: list[dict[str, str | int | None]],
    current_location: str | None = None,
    player_faction: str | None = None,
) -> bytes:
    width, height = 960, 640
    canvas = Image.new("RGB", (width, height), (22, 28, 26))
    draw = ImageDraw.Draw(canvas)

    title_font = _load_font(36)
    body_font = _load_font(22)
    small_font = _load_font(18)

    # Stylized "Zone" background mesh.
    draw.rectangle((24, 24, width - 24, height - 24), outline=(70, 90, 82), width=2)
    for x in range(80, width - 40, 80):
        draw.line((x, 80, x, height - 50), fill=(34, 46, 42), width=1)
    for y in range(80, height - 40, 70):
        draw.line((48, y, width - 48, y), fill=(34, 46, 42), width=1)

    draw.text((40, 30), "Карта Зоны", fill=(230, 240, 230), font=title_font)
    draw.text(
        (40, 72),
        "Текущие точки войны и контроля",
        fill=(168, 186, 173),
        font=small_font,
    )

    for location in locations:
        name = str(location.get("name") or "")
        if name not in MAP_POINTS:
            continue
        x, y = MAP_POINTS[name]
        point_type = str(location.get("point_type") or "")
        controlled_by = location.get("controlled_by")
        npc_power = int(location.get("npc_power") or 0)

        type_color = POINT_TYPE_COLORS.get(point_type, (210, 210, 210))
        owner_color = FACTION_COLORS.get(str(controlled_by), (170, 170, 170))

        # Outer type ring.
        draw.ellipse((x - 15, y - 15, x + 15, y + 15), fill=(26, 31, 30), outline=type_color, width=3)
        # Inner owner marker.
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=owner_color, outline=(15, 15, 15), width=1)

        label_color = (232, 232, 232)
        if current_location and name == current_location:
            label_color = (255, 245, 170)
            draw.ellipse((x - 22, y - 22, x + 22, y + 22), outline=(255, 240, 120), width=2)
        draw.text((x + 20, y - 16), name, fill=label_color, font=body_font)
        owner_text = str(controlled_by) if controlled_by else "нейтрал"
        owner_marker = ""
        if player_faction and controlled_by == player_faction:
            owner_marker = " (союз)"
        draw.text(
            (x + 20, y + 12),
            f"{point_type}; {owner_text}{owner_marker}; NPC {npc_power}",
            fill=(185, 196, 190),
            font=small_font,
        )

    legend_x, legend_y = 40, height - 155
    draw.rectangle((legend_x, legend_y, legend_x + 420, legend_y + 105), fill=(18, 23, 22), outline=(70, 90, 82), width=1)
    draw.text((legend_x + 12, legend_y + 8), "Легенда", fill=(225, 236, 228), font=body_font)

    draw.ellipse((legend_x + 14, legend_y + 42, legend_x + 34, legend_y + 62), fill=FACTION_COLORS["Долг"])
    draw.text((legend_x + 42, legend_y + 40), "Красный — контроль Долг", fill=(210, 220, 214), font=small_font)
    draw.ellipse((legend_x + 14, legend_y + 72, legend_x + 34, legend_y + 92), fill=FACTION_COLORS["Свобода"])
    draw.text((legend_x + 42, legend_y + 70), "Зеленый — контроль Свобода", fill=(210, 220, 214), font=small_font)

    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def build_zone_map(
    locations: list[dict[str, str | int | None]],
    current_location: str | None = None,
    player_faction: str | None = None,
) -> bytes:
    """Backward-compatible alias for older call sites."""
    return build_zone_map_image(
        locations,
        current_location=current_location,
        player_faction=player_faction,
    )
