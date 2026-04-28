from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"

MAP_POINTS: dict[str, tuple[int, int]] = {
    "Кордон": (120, 520),
    "Свалка": (250, 460),
    "Росток": (360, 430),
    "Армейские склады": (190, 280),
    "НИИ Агропром": (320, 340),
    "Янтарь": (560, 240),
    "Болото": (120, 360),
    "Темная долина": (500, 520),
    "Рыжий лес": (700, 240),
    "Радар": (700, 140),
}

LABEL_OFFSETS: dict[str, tuple[int, int]] = {
    "Кордон": (22, -12),
    "Свалка": (22, -18),
    "Росток": (22, -18),
    "Армейские склады": (22, -16),
    "Болото": (22, -14),
    "НИИ Агропром": (22, -16),
    "Янтарь": (22, -16),
    "Темная долина": (22, -14),
    "Рыжий лес": (22, -16),
    "Радар": (22, -16),
}

FACTION_COLORS = {
    "Долг": (230, 70, 70),
    "Свобода": (70, 200, 110),
    "Нейтралы": (210, 210, 210),
    "Бандиты": (205, 130, 60),
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

    title_font = _load_font(34)
    body_font = _load_font(16)
    small_font = _load_font(14)
    tiny_font = _load_font(13)

    # Stylized "Zone" background mesh.
    draw.rectangle((24, 24, width - 24, height - 24), outline=(70, 90, 82), width=2)
    for x in range(80, width - 40, 80):
        draw.line((x, 80, x, height - 50), fill=(34, 46, 42), width=1)
    for y in range(80, height - 40, 70):
        draw.line((48, y, width - 48, y), fill=(34, 46, 42), width=1)

    draw.text((40, 30), "Карта Зоны", fill=(230, 240, 230), font=title_font)
    draw.text(
        (40, 70),
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
        owner_text = str(controlled_by) if controlled_by else "нейтрал"
        owner_marker = ""
        if player_faction and controlled_by == player_faction:
            owner_marker = " (союз)"
        offset_x, offset_y = LABEL_OFFSETS.get(name, (22, -14))
        label_x = x + offset_x
        label_y = y + offset_y
        details_text = f"{point_type}; {owner_text}{owner_marker}; NPC {npc_power}"
        name_bbox = draw.textbbox((label_x, label_y), name, font=body_font)
        details_bbox = draw.textbbox((label_x, label_y + 20), details_text, font=tiny_font)
        box_x1 = min(name_bbox[0], details_bbox[0]) - 6
        box_y1 = min(name_bbox[1], details_bbox[1]) - 4
        box_x2 = max(name_bbox[2], details_bbox[2]) + 6
        box_y2 = max(name_bbox[3], details_bbox[3]) + 4
        draw.rounded_rectangle(
            (box_x1, box_y1, box_x2, box_y2),
            radius=6,
            fill=(18, 23, 22),
            outline=(58, 74, 67),
            width=1,
        )
        draw.text((label_x, label_y), name, fill=label_color, font=body_font)
        draw.text((label_x, label_y + 20), details_text, fill=(185, 196, 190), font=tiny_font)

    legend_x, legend_y = 40, height - 162
    legend_w, legend_h = 530, 116
    draw.rounded_rectangle(
        (legend_x, legend_y, legend_x + legend_w, legend_y + legend_h),
        radius=10,
        fill=(16, 21, 20),
        outline=(76, 97, 88),
        width=2,
    )
    draw.text((legend_x + 14, legend_y + 10), "Легенда", fill=(230, 238, 232), font=body_font)

    chips = [
        ("Долг", "Контроль Долг"),
        ("Свобода", "Контроль Свобода"),
        ("Нейтралы", "Контроль Нейтралы"),
        ("Бандиты", "Контроль Бандиты"),
    ]
    chip_x = legend_x + 14
    chip_y = legend_y + 42
    for idx, (faction, text) in enumerate(chips):
        row = idx // 2
        col = idx % 2
        x = chip_x + col * 255
        y = chip_y + row * 34
        draw.rounded_rectangle((x, y, x + 236, y + 26), radius=8, fill=(24, 30, 29), outline=(60, 74, 68), width=1)
        draw.ellipse((x + 8, y + 5, x + 24, y + 21), fill=FACTION_COLORS[faction], outline=(14, 14, 14), width=1)
        draw.text((x + 30, y + 5), text, fill=(208, 220, 213), font=small_font)

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
