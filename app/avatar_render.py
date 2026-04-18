from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.storage import Character


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AVATAR_DIR = PROJECT_ROOT / "assets" / "avatars"


def _tier(character: Character) -> int:
    if character.gear_power >= 13:
        return 4
    if character.gear_power >= 8:
        return 3
    if character.gear_power >= 4:
        return 2
    return 1


def _palette(tier: int) -> dict[str, tuple[int, int, int]]:
    palettes = {
        1: {
            "suit": (98, 105, 92),
            "armor": (110, 116, 106),
            "belt": (98, 70, 50),
            "mask": (112, 118, 110),
            "accent": (122, 126, 116),
        },
        2: {
            "suit": (85, 95, 78),
            "armor": (103, 112, 95),
            "belt": (92, 66, 46),
            "mask": (106, 112, 101),
            "accent": (122, 138, 112),
        },
        3: {
            "suit": (75, 82, 86),
            "armor": (93, 99, 112),
            "belt": (82, 60, 48),
            "mask": (98, 104, 117),
            "accent": (110, 128, 151),
        },
        4: {
            "suit": (70, 72, 78),
            "armor": (98, 92, 74),
            "belt": (102, 82, 52),
            "mask": (122, 116, 97),
            "accent": (171, 149, 88),
        },
    }
    return palettes[tier]


def _avatar_candidates(tier: int) -> tuple[Path, ...]:
    return (
        AVATAR_DIR / f"stalker_t{tier}.png",
        AVATAR_DIR / f"stalker_{tier}.png",
        AVATAR_DIR / f"tier_{tier}.png",
        AVATAR_DIR / "stalker_default.png",
    )


def _load_avatar_asset(tier: int, width: int, height: int) -> Image.Image | None:
    for candidate in _avatar_candidates(tier):
        if not candidate.exists():
            continue
        try:
            source = Image.open(candidate).convert("RGBA")
        except OSError:
            continue
        fitted = source.copy()
        fitted.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        offset_x = (width - fitted.width) // 2
        offset_y = height - fitted.height
        canvas.paste(fitted, (offset_x, offset_y), fitted)
        return canvas
    return None


def _render_stalker_avatar_fallback(character: Character, width: int = 260, height: int = 360) -> Image.Image:
    tier = _tier(character)
    p = _palette(tier)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    center_x = width // 2

    # Legs / pants
    draw.rounded_rectangle((center_x - 64, 218, center_x - 12, 350), radius=18, fill=p["suit"])
    draw.rounded_rectangle((center_x + 12, 218, center_x + 64, 350), radius=18, fill=p["suit"])
    # Boots
    draw.rounded_rectangle((center_x - 68, 336, center_x - 10, 358), radius=8, fill=(45, 45, 48))
    draw.rounded_rectangle((center_x + 10, 336, center_x + 68, 358), radius=8, fill=(45, 45, 48))

    # Torso suit
    draw.rounded_rectangle((center_x - 80, 120, center_x + 80, 242), radius=26, fill=p["suit"])
    # Tactical vest
    draw.rounded_rectangle((center_x - 72, 116, center_x + 72, 208), radius=16, fill=p["armor"], outline=(210, 210, 210), width=2)
    for i in range(4):
        y = 128 + i * 18
        draw.rounded_rectangle((center_x - 58, y, center_x + 58, y + 10), radius=4, fill=p["accent"])

    # Belt
    draw.rounded_rectangle((center_x - 84, 208, center_x + 84, 232), radius=8, fill=p["belt"])
    draw.rounded_rectangle((center_x - 10, 211, center_x + 10, 229), radius=4, fill=(140, 130, 116))

    # Arms
    draw.rounded_rectangle((center_x - 122, 138, center_x - 76, 260), radius=18, fill=p["suit"])
    draw.rounded_rectangle((center_x + 76, 138, center_x + 122, 260), radius=18, fill=p["suit"])
    draw.ellipse((center_x - 125, 246, center_x - 96, 274), fill=(175, 148, 130))
    draw.ellipse((center_x + 96, 246, center_x + 125, 274), fill=(175, 148, 130))

    # Gas mask / head
    draw.ellipse((center_x - 42, 42, center_x + 42, 126), fill=p["mask"], outline=(212, 212, 212), width=2)
    draw.ellipse((center_x - 32, 56, center_x - 8, 80), fill=(44, 44, 44))
    draw.ellipse((center_x + 8, 56, center_x + 32, 80), fill=(44, 44, 44))
    draw.ellipse((center_x - 18, 78, center_x + 18, 116), fill=(58, 58, 60), outline=(195, 195, 195), width=2)

    # Shoulder armor on high tiers
    if tier >= 3:
        draw.polygon(
            [(center_x - 94, 122), (center_x - 62, 122), (center_x - 74, 156), (center_x - 102, 150)],
            fill=p["armor"],
        )
        draw.polygon(
            [(center_x + 94, 122), (center_x + 62, 122), (center_x + 74, 156), (center_x + 102, 150)],
            fill=p["armor"],
        )
    if tier == 4:
        draw.ellipse((center_x - 8, 88, center_x + 8, 104), fill=(240, 220, 118))

    return image


def render_avatar(character: Character, width: int = 260, height: int = 360) -> Image.Image:
    tier = _tier(character)
    asset_avatar = _load_avatar_asset(tier, width=width, height=height)
    if asset_avatar is not None:
        return asset_avatar
    return _render_stalker_avatar_fallback(character, width=width, height=height)
