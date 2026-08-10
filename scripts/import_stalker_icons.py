#!/usr/bin/env python3
"""Импорт иконок НПС и транспорта (game-icons.net, CC BY 3.0) в assets/."""

from __future__ import annotations

import re
import sys
from io import BytesIO
from pathlib import Path

import cairosvg
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.npc_assets import (  # noqa: E402
    MISSION_NPC_CARD_SIZE,
    MISSION_NPC_GRID_SIZE,
    NPCS_CARD_DIR,
    NPCS_GRID_DIR,
    NPCS_SOURCE_DIR,
)

SMUGGLE_DIR = ROOT / "assets" / "smuggle"
GAME_ICONS_BASE = "https://game-icons.net/icons/ffffff/transparent/1x1"

# author/path, цвет под сталкер
NPC_ICON_SPECS: dict[str, tuple[str, tuple[int, int, int]]] = {
    "bandit": ("delapouite/bandit", (210, 165, 110)),       # бандит — ржаво-коричневый
    "mercenary": ("delapouite/spy", (150, 175, 215)),        # наёмник — синеватый плащ
    "soldier": ("delapouite/flamethrower-soldier", (135, 165, 95)),  # военный — олива
}

SMUGGLE_ICON_SPECS: dict[str, tuple[str, tuple[int, int, int]]] = {
    "bicycle": ("delapouite/cycling", (230, 210, 150)),
    "niva": ("delapouite/jeep", (125, 155, 90)),
    "truck": ("delapouite/truck", (175, 185, 170)),
}


def _fetch_svg(path: str) -> str:
    import urllib.request

    url = f"{GAME_ICONS_BASE}/{path}.svg"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _svg_with_color(svg_text: str, rgb: tuple[int, int, int]) -> str:
    color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    text = svg_text.replace('fill="#fff"', f'fill="{color}"')
    text = text.replace('fill="#ffffff"', f'fill="{color}"')
    text = text.replace('fill="#FFFFFF"', f'fill="{color}"')
    text = re.sub(r'stroke="#fff(?:fff)?"', f'stroke="{color}"', text, flags=re.I)
    if 'fill="' not in text and "<path" in text:
        text = text.replace("<path ", f'<path fill="{color}" ', 1)
    return text


def _render_png(svg_text: str, size: int) -> Image.Image:
    raw = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=size, output_height=size)
    return Image.open(BytesIO(raw)).convert("RGBA")


def _fit_icon(img: Image.Image, size: int, *, pad: float = 0.12) -> Image.Image:
    """Вписать иконку с полями — без квадратной заливки фона."""
    img = img.convert("RGBA")
    bbox = img.getbbox()
    if bbox is None:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cropped = img.crop(bbox)
    inner = max(1, int(size * (1 - pad * 2)))
    fitted = ImageOps.contain(cropped, (inner, inner), method=Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ox = (size - fitted.width) // 2
    oy = (size - fitted.height) // 2
    out.paste(fitted, (ox, oy), fitted)
    return out


def _write_png(path: Path, img: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)


def import_npc_icons() -> None:
    NPCS_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for key, (icon_path, rgb) in NPC_ICON_SPECS.items():
        svg_raw = _fetch_svg(icon_path)
        svg_colored = _svg_with_color(svg_raw, rgb)
        (NPCS_SOURCE_DIR / f"{key}.svg").write_text(svg_colored, encoding="utf-8")
        base = _render_png(svg_colored, 512)
        grid = _fit_icon(base, MISSION_NPC_GRID_SIZE)
        card = _fit_icon(base, MISSION_NPC_CARD_SIZE)
        _write_png(NPCS_GRID_DIR / f"{key}.png", grid)
        _write_png(NPCS_CARD_DIR / f"{key}.png", card)
        print(f"  npc {key}: {icon_path} -> grid+card")


def import_smuggle_icons() -> None:
    SMUGGLE_DIR.mkdir(parents=True, exist_ok=True)
    for key, (icon_path, rgb) in SMUGGLE_ICON_SPECS.items():
        svg_raw = _fetch_svg(icon_path)
        svg_colored = _svg_with_color(svg_raw, rgb)
        (SMUGGLE_DIR / f"{key}.svg").write_text(svg_colored, encoding="utf-8")
        base = _render_png(svg_colored, 512)
        png = _fit_icon(base, 256)
        _write_png(SMUGGLE_DIR / f"{key}.png", png)
        print(f"  smuggle {key}: {icon_path} -> png")


def main() -> None:
    print("NPC icons:")
    import_npc_icons()
    print("Smuggle transport icons:")
    import_smuggle_icons()
    # Сброс кэша иконок в рантайме (если процесс уже импортировал модуль).
    from app.smuggle_mission import _cached_smuggle_icon

    _cached_smuggle_icon.cache_clear()
    print("Done.")


if __name__ == "__main__":
    main()
