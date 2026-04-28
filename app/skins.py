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
        min_gear_power=4,
        coat_color=(82, 98, 86),
        visor_color=(128, 170, 120),
        accent_color=(105, 130, 85),
    ),
    SkinTheme(
        key="heavy",
        title="Тяжелый штурмовик",
        min_gear_power=8,
        coat_color=(78, 84, 95),
        visor_color=(120, 160, 185),
        accent_color=(95, 110, 145),
    ),
    SkinTheme(
        key="legend",
        title="Легенда Зоны",
        min_gear_power=13,
        coat_color=(75, 76, 92),
        visor_color=(185, 165, 88),
        accent_color=(150, 130, 75),
    ),
)


def resolve_skin(character: Character) -> SkinTheme:
    selected = SKINS[0]
    for skin in SKINS:
        if character.gear_power >= skin.min_gear_power:
            selected = skin
    return selected
