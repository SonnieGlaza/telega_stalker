from __future__ import annotations

import random
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NPCS_DIR = PROJECT_ROOT / "assets" / "npcs"
NPCS_GRID_DIR = NPCS_DIR / "grid"
NPCS_CARD_DIR = NPCS_DIR / "card"
NPCS_SOURCE_DIR = NPCS_DIR / "source"

# Те же размеры, что у мутантов (клетка миссии 108px).
MISSION_NPC_GRID_DIAMETER = 80
MISSION_NPC_GRID_SIZE = 88
MISSION_NPC_CARD_SIZE = 256

NPC_SPRITES: dict[str, str] = {
    "maloy": "Малой",
    "bandit": "Бандит",
    "mercenary": "Наёмник",
    "soldier": "Военный",
}

NPC_SPRITE_KEYS: tuple[str, ...] = tuple(NPC_SPRITES.keys())


def pick_npc_kind(*, marauder: bool = False) -> str:
    if marauder:
        return random.choice(("bandit", "maloy", "mercenary"))
    return random.choice(NPC_SPRITE_KEYS)


@lru_cache(maxsize=32)
def load_npc_grid_sprite(kind: str) -> bytes | None:
    """PNG 88×88 для отрисовки на поле миссии."""
    path = NPCS_GRID_DIR / f"{kind}.png"
    if not path.is_file():
        return None
    return path.read_bytes()


@lru_cache(maxsize=32)
def load_npc_card_sprite(kind: str) -> bytes | None:
    """PNG 256×256 для карточек/PDA (будущие задания)."""
    path = NPCS_CARD_DIR / f"{kind}.png"
    if not path.is_file():
        return None
    return path.read_bytes()


def npc_sprite_image(kind: str, *, card: bool = False) -> Image.Image | None:
    raw = load_npc_card_sprite(kind) if card else load_npc_grid_sprite(kind)
    if raw is None:
        return None
    try:
        return Image.open(BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
