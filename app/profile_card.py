from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.storage import Character


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _faction_color(faction: str | None) -> tuple[int, int, int]:
    if faction == "Долг":
        return (190, 70, 65)
    if faction == "Свобода":
        return (70, 165, 90)
    return (110, 110, 130)


def _location_color(location: str) -> tuple[int, int, int]:
    mapping = {
        "Росток": (90, 110, 150),
        "Армейские склады": (80, 120, 85),
        "Янтарь": (130, 125, 75),
        "Темная долина": (120, 90, 90),
        "Радар": (105, 85, 125),
        "База новичков": (100, 105, 120),
    }
    return mapping.get(location, (95, 95, 95))


def _draw_power_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    value: int,
    max_value: int,
    color: tuple[int, int, int],
) -> None:
    bar_w = 240
    bar_h = 14
    draw.rounded_rectangle((x, y, x + bar_w, y + bar_h), radius=6, fill=(40, 40, 45))
    fill_w = int(bar_w * max(0.0, min(1.0, value / max_value)))
    draw.rounded_rectangle((x, y, x + fill_w, y + bar_h), radius=6, fill=color)


def build_character_card(character: Character) -> bytes:
    width, height = 960, 540
    img = Image.new("RGB", (width, height), color=(21, 21, 26))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(36)
    subtitle_font = _load_font(24)
    body_font = _load_font(21)
    small_font = _load_font(18)

    faction_color = _faction_color(character.faction)
    location_color = _location_color(character.location)

    draw.rectangle((0, 0, width, 74), fill=(28, 31, 40))
    draw.text((24, 18), f"STALKER PROFILE • {character.player_uid}", fill=(235, 235, 235), font=title_font)

    draw.rounded_rectangle((24, 98, 390, 510), radius=16, fill=(34, 36, 48), outline=(66, 68, 82), width=2)
    draw.text((46, 120), "Текущая позиция", fill=(220, 220, 220), font=subtitle_font)
    draw.rounded_rectangle((46, 164, 368, 334), radius=12, fill=location_color, outline=(210, 210, 210), width=2)
    draw.text((62, 228), character.location, fill=(248, 248, 248), font=subtitle_font)

    # Схематичная фигура сталкера.
    armor_tint = min(200, 80 + character.gear_power * 8)
    suit_color = (armor_tint, armor_tint, armor_tint - 20)
    draw.ellipse((140, 350, 220, 430), fill=(145, 145, 145), outline=(225, 225, 225))
    draw.rounded_rectangle((126, 420, 234, 494), radius=12, fill=suit_color, outline=(225, 225, 225), width=2)
    draw.rectangle((230, 442, 315, 455), fill=(95, 95, 95))
    draw.text((92, 458), f"Сила снаряги: {character.gear_power}", fill=(232, 232, 232), font=small_font)

    draw.rounded_rectangle((420, 98, 936, 510), radius=16, fill=(33, 35, 44), outline=(66, 68, 82), width=2)
    draw.text((446, 122), f"{character.nickname} ({character.gender})", fill=(240, 240, 240), font=subtitle_font)
    draw.text((446, 160), f"Фракция: {character.faction or 'не выбрана'}", fill=faction_color, font=body_font)
    draw.text((446, 192), f"Баланс: {character.money} RU", fill=(225, 225, 225), font=body_font)
    draw.text((446, 224), f"Здоровье: {character.health}/100", fill=(225, 225, 225), font=body_font)
    draw.text((446, 256), f"Энергия: {character.energy}/{character.max_energy}", fill=(225, 225, 225), font=body_font)
    draw.text((446, 288), f"Топливо: {character.fuel}", fill=(225, 225, 225), font=body_font)
    draw.text((446, 320), f"Транспорт: {'Грузовик' if character.truck_owned else 'Нет'}", fill=(225, 225, 225), font=body_font)

    draw.text((446, 364), "Индикаторы", fill=(210, 210, 210), font=body_font)
    _draw_power_bar(draw, 446, 396, character.health, 100, (190, 70, 70))
    _draw_power_bar(draw, 446, 422, character.energy, max(1, character.max_energy), (70, 150, 220))
    _draw_power_bar(draw, 446, 448, character.gear_power, 20, (170, 170, 95))
    draw.text((694, 392), "Здоровье", fill=(220, 220, 220), font=small_font)
    draw.text((694, 418), "Энергия", fill=(220, 220, 220), font=small_font)
    draw.text((694, 444), "Снаряга", fill=(220, 220, 220), font=small_font)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
