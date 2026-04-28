from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.avatar_render import render_avatar
from app.game_logic import ITEM_LABELS, equipment_power
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
        "Кордон": (96, 124, 158),
        "Свалка": (128, 116, 74),
        "НИИ Агропром": (118, 94, 142),
        "Болото": (78, 122, 104),
        "Рыжий лес": (142, 98, 72),
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
        "weapon_durability": "Прочность оружия",
        "armor_durability": "Прочность брони",
        "artifact": "Артефакт",
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
    max_width: int = 300,
) -> None:
    draw.text((x, y), header, fill=(218, 218, 218), font=header_font)
    draw.line((x, y + 30, x + max_width, y + 30), fill=(90, 92, 108), width=1)
    visible = lines[:max_lines]
    for i, line in enumerate(visible):
        draw.text(
            (x, y + 38 + i * 26),
            _ellipsize_text(draw, line, body_font, max_width),
            fill=(230, 230, 230),
            font=body_font,
        )


def _ellipsize_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "..."
    current = text
    while current and draw.textlength(current + suffix, font=font) > max_width:
        current = current[:-1]
    return (current + suffix) if current else suffix


def build_character_card(character: Character) -> bytes:
    width, height = 1180, 700
    img = Image.new("RGB", (width, height), color=(21, 21, 26))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(34)
    subtitle_font = _load_font(22)
    body_font = _load_font(18)
    small_font = _load_font(16)

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
    draw.text(
        (46, 132),
        _ellipsize_text(draw, f"Игрок: {character.nickname}", subtitle_font, 350),
        fill=(240, 240, 240),
        font=subtitle_font,
    )
    draw.text((46, 164), "Местоположение", fill=(220, 220, 220), font=subtitle_font)
    draw.rounded_rectangle((46, 204, 408, 346), radius=12, fill=location_color, outline=(210, 210, 210), width=2)
    draw.text((62, 236), f"Локация: {character.location}", fill=(248, 248, 248), font=small_font)
    draw.text((62, 266), f"Группировка: {character.faction or 'не выбрана'}", fill=(248, 248, 248), font=small_font)
    draw.text((62, 296), f"Скин персонажа: {skin.title}", fill=(248, 248, 248), font=small_font)

    avatar = render_avatar(character, width=248, height=320)
    panel_left = 46
    panel_right = 408
    panel_bottom = 676
    avatar_top = 347

    available_w = max(1, panel_right - panel_left)
    available_h = max(1, panel_bottom - avatar_top - 2)
    if avatar.width > available_w or avatar.height > available_h:
        scale = min(available_w / avatar.width, available_h / avatar.height)
        resized_w = max(1, int(avatar.width * scale))
        resized_h = max(1, int(avatar.height * scale))
        avatar = avatar.resize((resized_w, resized_h), Image.Resampling.LANCZOS)

    avatar_x = panel_left + (available_w - avatar.width) // 2
    avatar_y = avatar_top + max(0, (available_h - avatar.height) // 2)
    if avatar.mode in {"RGBA", "LA"}:
        # Сохраняем прозрачность, чтобы не появлялся темный фон вокруг спрайта.
        img.paste(avatar, (avatar_x, avatar_y), avatar)
    else:
        img.paste(avatar, (avatar_x, avatar_y))

    # Если остаются пустые зоны сверху/снизу, подложка панели остается однотонной.

    draw.rounded_rectangle((454, 108, 1156, 676), radius=16, fill=(33, 35, 44), outline=(66, 68, 82), width=2)
    right_x = 480
    right_max_width = 650
    draw.text((right_x, 132), f"Пол: {character.gender}", fill=(220, 220, 220), font=body_font)
    draw.text(
        (right_x, 158),
        _ellipsize_text(draw, f"Группировка: {character.faction or 'не выбрана'}", body_font, right_max_width),
        fill=faction_color,
        font=body_font,
    )
    draw.text((right_x, 184), f"Баланс: {character.money} рублей", fill=(225, 225, 225), font=body_font)
    draw.text(
        (right_x, 210),
        f"Транспорт: {'Грузовик' if character.truck_owned else 'Отсутствует'}",
        fill=(225, 225, 225),
        font=body_font,
    )
    draw.text((right_x, 236), f"Топливо: {character.fuel}", fill=(225, 225, 225), font=body_font)
    draw.text(
        (right_x, 262),
        _ellipsize_text(draw, f"Текущий скин: {skin.title}", body_font, right_max_width),
        fill=skin.accent_color,
        font=body_font,
    )

    draw.text((right_x, 292), "Индикаторы состояния", fill=(210, 210, 210), font=body_font)
    _draw_power_bar(draw, right_x, 322, character.health, 100, (190, 70, 70))
    _draw_power_bar(draw, right_x, 348, character.energy, max(1, character.max_energy), (70, 150, 220))
    _draw_power_bar(draw, right_x, 374, character.gear_power, 20, (170, 170, 95))
    draw.text((730, 318), f"{character.health}/100", fill=(220, 220, 220), font=small_font)
    draw.text((730, 344), f"{character.energy}/{character.max_energy}", fill=(220, 220, 220), font=small_font)
    draw.text((730, 370), f"{character.gear_power}/20", fill=(220, 220, 220), font=small_font)

    equipment = character.equipment or {}
    weapon_name = str(equipment.get("weapon", "—"))
    armor_name = str(equipment.get("armor", "—"))
    try:
        weapon_durability = int(equipment.get("weapon_durability", 100))
    except (TypeError, ValueError):
        weapon_durability = 100
    try:
        armor_durability = int(equipment.get("armor_durability", 100))
    except (TypeError, ValueError):
        armor_durability = 100
    artifact_name = str(equipment.get("artifact", "Нет"))
    equipment_lines = [
        f"Сила снаряжения: {equipment_power(character)}",
        f"Оружие: {weapon_name} ({weapon_durability}%)",
        f"Броня: {armor_name} ({armor_durability}%)",
        f"Артефакт: {artifact_name}",
    ]
    _draw_text_block(
        draw=draw,
        x=480,
        y=410,
        header="Снаряжение",
        lines=equipment_lines,
        header_font=small_font,
        body_font=small_font,
        max_lines=4,
        max_width=300,
    )
    _draw_text_block(
        draw=draw,
        x=810,
        y=410,
        header="Инвентарь",
        lines=_inventory_lines(character),
        header_font=small_font,
        body_font=small_font,
        max_lines=4,
        max_width=320,
    )

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
