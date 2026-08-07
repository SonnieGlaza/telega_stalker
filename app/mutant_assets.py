from __future__ import annotations

import random
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MUTANTS_DIR = PROJECT_ROOT / "assets" / "mutants"
MUTANTS_GRID_DIR = MUTANTS_DIR / "grid"
MUTANTS_CARD_DIR = MUTANTS_DIR / "card"
MUTANTS_SOURCE_DIR = MUTANTS_DIR / "source"

# Размер спрайта на клетке миссии (клетка 108px, игрок ~144px).
MISSION_MUTANT_GRID_DIAMETER = 80
MISSION_MUTANT_GRID_SIZE = 88
MISSION_MUTANT_CARD_SIZE = 256

MUTANT_SPRITES: dict[str, str] = {
    "blind_dog": "Слепой пёс",
    "tushkano": "Тушкан",
    "pseudodog": "Псевдособака",
    "bloodsucker": "Кровосос",
    "flesh": "Плоть",
}

MUTANT_SPRITE_KEYS: tuple[str, ...] = tuple(MUTANT_SPRITES.keys())


def pick_mutant_kind() -> str:
    return random.choice(MUTANT_SPRITE_KEYS)


@lru_cache(maxsize=32)
def load_mutant_grid_sprite(kind: str) -> bytes | None:
    """PNG 88×88 для отрисовки на поле миссии."""
    path = MUTANTS_GRID_DIR / f"{kind}.png"
    if not path.is_file():
        return None
    return path.read_bytes()


@lru_cache(maxsize=32)
def load_mutant_card_sprite(kind: str) -> bytes | None:
    """PNG 256×256 для карточек/PDA (будущие задания)."""
    path = MUTANTS_CARD_DIR / f"{kind}.png"
    if not path.is_file():
        return None
    return path.read_bytes()


def mutant_sprite_image(kind: str, *, card: bool = False) -> Image.Image | None:
    raw = load_mutant_card_sprite(kind) if card else load_mutant_grid_sprite(kind)
    if raw is None:
        return None
    try:
        return Image.open(BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
