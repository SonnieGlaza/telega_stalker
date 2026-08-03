from __future__ import annotations

from dataclasses import dataclass

from app.storage import Character


@dataclass(frozen=True)
class SkinTheme:
    key: str
    title: str
    min_gear_power: int
    coat_color: tuple[int, int, int]
    visor_color: tuple[int, int, int]
    accent_color: tuple[int, int, int]


SKINS: tuple[SkinTheme, ...] = (
    SkinTheme(
        key="novice",
        title="Новичок",
        min_gear_power=0,
        coat_color=(95, 95, 102),
        visor_color=(125, 130, 145),
        accent_color=(130, 115, 85),
    ),
    SkinTheme(
        key="veteran",
        title="Ветеран",
        # Было 4: понижено, чтобы прогресс скина ощущался раньше.
        min_gear_power=2,
        coat_color=(82, 98, 86),
        visor_color=(128, 170, 120),
        accent_color=(105, 130, 85),
    ),
    SkinTheme(
        key="heavy",
        title="Тяжелый штурмовик",
        min_gear_power=5,
        coat_color=(78, 84, 95),
        visor_color=(120, 160, 185),
        accent_color=(95, 110, 145),
    ),
    SkinTheme(
        key="legend",
        title="Легенда Зоны",
        min_gear_power=9,
        coat_color=(75, 76, 92),
        visor_color=(185, 165, 88),
        accent_color=(150, 130, 75),
    ),
)

FACTION_SKIN_ACCENTS: dict[str, tuple[int, int, int]] = {
    "Долг": (180, 70, 70),
    "Свобода": (70, 150, 90),
    "Нейтралы": (150, 140, 110),
    "Бандиты": (120, 90, 150),
}


def resolve_skin(character: Character, gear_power: int | None = None) -> SkinTheme:
    power = character.gear_power if gear_power is None else gear_power
    selected = SKINS[0]
    for skin in SKINS:
        if power >= skin.min_gear_power:
            selected = skin
    return selected


def resolve_faction_accent(faction: str | None) -> tuple[int, int, int] | None:
    if not faction:
        return None
    return FACTION_SKIN_ACCENTS.get(faction)
