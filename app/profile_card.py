from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.avatar_render import render_avatar
from app.game_logic import ITEM_LABELS
from app.skins import resolve_skin
from app.storage import Character


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans.ttf"
LOCAL_NOTO_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"
FONT_CANDIDATES = (
    str(LOCAL_NOTO_FONT_PATH),
    str(LOCAL_FONT_PATH),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
)


def _font_supports_cyrillic(font: ImageFont.ImageFont) -> bool:
    test_text = "Карточка персонажа"
    try:
        bbox = font.getbbox(test_text)
    except Exception:
        return False
    # Invalid or empty bbox often indicates missing glyphs.
    if bbox is None:
        return False
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width <= 0 or height <= 0:
        return False
    # Exclude fallback "tofu" glyphs that appear as repeated squares.
    missing_patterns = set()
    for probe in ("□", "\u25a1", "?", "\ufffd"):
        try:
            missing_patterns.add(bytes(font.getmask(probe)))
        except Exception:
            continue
    samples = []
    for probe in ("К", "Я", "Ж", "Ы", "Ч"):
        try:
            samples.append(bytes(font.getmask(probe)))
        except Exception:
            return False
    if not samples:
        return False
    if any(sample in missing_patterns for sample in samples):
        return False
    # Cyrillic glyphs should not all be identical.
    return len(set(samples)) > 1


@lru_cache(maxsize=1)
def _read_local_font_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


@lru_cache(maxsize=8)
def _resolve_font_path() -> tuple[str | None, str]:
    for local_path in (LOCAL_NOTO_FONT_PATH, LOCAL_FONT_PATH):
        local_font = _read_local_font_bytes(local_path)
        if local_font is not None:
            try:
                font = ImageFont.truetype(BytesIO(local_font), size=22)
                if _font_supports_cyrillic(font):
                    return (str(local_path), "локальный файл")
            except OSError:
                pass
    for path in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            font = ImageFont.truetype(path, size=22)
        except OSError:
            continue
        if _font_supports_cyrillic(font):
            return (path, "системный файл")
    return (None, "встроенный PIL (ограниченный)")


def _load_font(size: int) -> ImageFont.ImageFont:
    resolved_path, _ = _resolve_font_path()
    for local_path in (LOCAL_NOTO_FONT_PATH, LOCAL_FONT_PATH):
        local_font = _read_local_font_bytes(local_path)
        if local_font is not None:
            try:
                font = ImageFont.truetype(BytesIO(local_font), size=size)
                if _font_supports_cyrillic(font):
                    return font
            except OSError:
                continue
    if resolved_path is not None:
        try:
            return ImageFont.truetype(resolved_path, size=size)
        except OSError:
            pass
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


def _equipment_lines(character: Character) -> list[str]:
    key_map = {
        "weapon": "Оружие",
        "armor": "Броня",
    }
    if not character.equipment:
        return ["Нет данных"]
    lines = []
    for key, value in sorted(character.equipment.items()):
        lines.append(f"{key_map.get(key, key)}: {value}")
    return lines


def _inventory_lines(character: Character) -> list[str]:
    if not character.inventory:
        return ["Пусто"]
    lines = []
    for key, amount in sorted(character.inventory.items()):
        title = ITEM_LABELS.get(key, key)
        lines.append(f"{title}: {amount}")
    return lines


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    header: str,
    lines: list[str],
    header_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
    max_lines: int,
) -> None:
    draw.text((x, y), header, fill=(218, 218, 218), font=header_font)
    draw.line((x, y + 30, x + 400, y + 30), fill=(90, 92, 108), width=1)
    visible = lines[:max_lines]
    hidden = len(lines) - len(visible)
    for i, line in enumerate(visible):
        draw.text((x, y + 38 + i * 26), line, fill=(230, 230, 230), font=body_font)
    if hidden > 0:
        draw.text((x, y + 38 + len(visible) * 26), f"Еще записей: {hidden}", fill=(180, 180, 180), font=body_font)


def build_character_card(character: Character) -> bytes:
    width, height = 1180, 700
    img = Image.new("RGB", (width, height), color=(21, 21, 26))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(34)
    subtitle_font = _load_font(24)
    body_font = _load_font(20)
    small_font = _load_font(18)

    faction_color = _faction_color(character.faction)
    location_color = _location_color(character.location)
    skin = resolve_skin(character)

    draw.rectangle((0, 0, width, 90), fill=(28, 31, 40))
    draw.text((24, 16), "Карточка персонажа", fill=(235, 235, 235), font=title_font)
    draw.text(
        (24, 56),
        f"ID-адрес: {character.player_uid}    Telegram ID: {character.telegram_id}",
        fill=(208, 208, 208),
        font=small_font,
    )

    draw.rounded_rectangle((24, 108, 430, 676), radius=16, fill=(34, 36, 48), outline=(66, 68, 82), width=2)
    draw.text((46, 132), "Местоположение", fill=(220, 220, 220), font=subtitle_font)
    draw.rounded_rectangle((46, 176, 408, 346), radius=12, fill=location_color, outline=(210, 210, 210), width=2)
    draw.text((62, 228), f"Локация: {character.location}", fill=(248, 248, 248), font=small_font)
    draw.text((62, 258), f"Группировка: {character.faction or 'не выбрана'}", fill=(248, 248, 248), font=small_font)
    draw.text((62, 288), f"Скин персонажа: {skin.title}", fill=(248, 248, 248), font=small_font)

    avatar = render_avatar(character)
    img.paste(avatar, (88, 354))
    draw.text((94, 580), f"Сила снаряжения: {character.gear_power}", fill=(232, 232, 232), font=small_font)

    draw.rounded_rectangle((454, 108, 1156, 676), radius=16, fill=(33, 35, 44), outline=(66, 68, 82), width=2)
    draw.text((480, 132), f"Игрок: {character.nickname}", fill=(240, 240, 240), font=subtitle_font)
    draw.text((480, 166), f"Пол: {character.gender}", fill=(220, 220, 220), font=body_font)
    draw.text((480, 194), f"Группировка: {character.faction or 'не выбрана'}", fill=faction_color, font=body_font)
    draw.text((480, 222), f"Баланс: {character.money} рублей", fill=(225, 225, 225), font=body_font)
    draw.text((480, 250), f"Здоровье: {character.health} из 100", fill=(225, 225, 225), font=body_font)
    draw.text((480, 278), f"Энергия: {character.energy} из {character.max_energy}", fill=(225, 225, 225), font=body_font)
    draw.text((480, 306), f"Транспорт: {'Грузовик' if character.truck_owned else 'Отсутствует'}", fill=(225, 225, 225), font=body_font)
    draw.text((480, 334), f"Топливо: {character.fuel}", fill=(225, 225, 225), font=body_font)
    draw.text((480, 362), f"Текущий скин: {skin.title}", fill=skin.accent_color, font=body_font)

    draw.text((480, 394), "Индикаторы состояния", fill=(210, 210, 210), font=body_font)
    _draw_power_bar(draw, 480, 428, character.health, 100, (190, 70, 70))
    _draw_power_bar(draw, 480, 454, character.energy, max(1, character.max_energy), (70, 150, 220))
    _draw_power_bar(draw, 480, 480, character.gear_power, 20, (170, 170, 95))
    draw.text((730, 424), "Здоровье", fill=(220, 220, 220), font=small_font)
    draw.text((730, 450), "Энергия", fill=(220, 220, 220), font=small_font)
    draw.text((730, 476), "Снаряжение", fill=(220, 220, 220), font=small_font)

    _draw_text_block(
        draw=draw,
        x=480,
        y=522,
        header="Снаряжение",
        lines=_equipment_lines(character),
        header_font=small_font,
        body_font=small_font,
        max_lines=3,
    )
    _draw_text_block(
        draw=draw,
        x=810,
        y=522,
        header="Инвентарь",
        lines=_inventory_lines(character),
        header_font=small_font,
        body_font=small_font,
        max_lines=3,
    )

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
