from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.artifact_hunt import (
    FONT_CANDIDATES,
    _load_location_thumb,
    _paste_circle,
    _paste_rounded,
)
from app.game_logic import (
    CONTRACT_TURN_IN_BONUS_PERCENT,
    QUESTS,
    QUEST_CONTRACTS,
    ActionResult,
    QuestContractTemplate,
    QuestType,
    _dead_block_text,
    _is_dead,
    _spend_quest_resources,
    apply_contract_mission_fail,
    apply_contract_mission_success,
    apply_incoming_damage,
    effective_max_health,
    equipment_power,
    faction_home_base,
    use_medkit_item,
)
from app.storage import Character, Storage


MISSION_META_PREFIX = "quest_mission:"
GRID_SIZE = 6
MAX_MOVES = 28

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

# Опасность локации → урон/число врагов.
LOCATION_DANGER: dict[str, int] = {
    "Кордон": 1,
    "Свалка": 1,
    "Болото": 2,
    "НИИ Агропром": 2,
    "Росток": 2,
    "Армейские склады": 2,
    "Янтарь": 3,
    "Темная долина": 3,
    "Рыжий лес": 3,
    "Радар": 4,
}

DIFFICULTY_DANGER_BONUS: dict[str, int] = {
    "easy": 0,
    "hard": 1,
    "heavy": 2,
    "impossible": 3,
}

KIND_LABELS: dict[str, str] = {
    "collect": "Сбор",
    "scout": "Разведка",
    "loot": "Поиск хабара",
    "clear_mutant": "Зачистка мутантов",
    "clear_marauder": "Зачистка мародёров",
    "anomaly": "Аномалии",
}


@dataclass
class QuestMissionSession:
    contract_key: str
    title: str
    location: str
    kind: str
    difficulty: str
    player: tuple[int, int]
    start: tuple[int, int]
    objectives: list[tuple[int, int]]
    collected: list[tuple[int, int]] = field(default_factory=list)
    hazards: list[tuple[int, int]] = field(default_factory=list)  # аномалии / препятствия
    enemies: list[tuple[int, int]] = field(default_factory=list)  # мутанты / мародёры
    moves: int = 0
    max_moves: int = MAX_MOVES
    grid: int = GRID_SIZE
    objectives_done: bool = False
    resources_spent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_key": self.contract_key,
            "title": self.title,
            "location": self.location,
            "kind": self.kind,
            "difficulty": self.difficulty,
            "player": list(self.player),
            "start": list(self.start),
            "objectives": [list(p) for p in self.objectives],
            "collected": [list(p) for p in self.collected],
            "hazards": [list(p) for p in self.hazards],
            "enemies": [list(p) for p in self.enemies],
            "moves": self.moves,
            "max_moves": self.max_moves,
            "grid": self.grid,
            "objectives_done": self.objectives_done,
            "resources_spent": self.resources_spent,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> QuestMissionSession:
        return cls(
            contract_key=str(raw.get("contract_key") or ""),
            title=str(raw.get("title") or ""),
            location=str(raw.get("location") or ""),
            kind=str(raw.get("kind") or "collect"),
            difficulty=str(raw.get("difficulty") or "easy"),
            player=(int(raw["player"][0]), int(raw["player"][1])),
            start=(int(raw["start"][0]), int(raw["start"][1])),
            objectives=[(int(p[0]), int(p[1])) for p in (raw.get("objectives") or [])],
            collected=[(int(p[0]), int(p[1])) for p in (raw.get("collected") or [])],
            hazards=[(int(p[0]), int(p[1])) for p in (raw.get("hazards") or [])],
            enemies=[(int(p[0]), int(p[1])) for p in (raw.get("enemies") or [])],
            moves=int(raw.get("moves") or 0),
            max_moves=int(raw.get("max_moves") or MAX_MOVES),
            grid=int(raw.get("grid") or GRID_SIZE),
            objectives_done=bool(raw.get("objectives_done")),
            resources_spent=bool(raw.get("resources_spent")),
        )


def _meta_key(telegram_id: int) -> str:
    return f"{MISSION_META_PREFIX}{int(telegram_id)}"


def get_mission_session(storage: Storage, telegram_id: int) -> QuestMissionSession | None:
    raw = storage.get_meta(_meta_key(telegram_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return QuestMissionSession.from_dict(data)
    except Exception:
        return None


def save_mission_session(storage: Storage, telegram_id: int, session: QuestMissionSession) -> None:
    storage.set_meta(_meta_key(telegram_id), json.dumps(session.to_dict(), ensure_ascii=False))


def clear_mission_session(storage: Storage, telegram_id: int) -> None:
    storage.delete_meta(_meta_key(telegram_id))


def _location_danger(location: str, difficulty: str) -> int:
    return LOCATION_DANGER.get(location, 2) + DIFFICULTY_DANGER_BONUS.get(difficulty, 0)


def _free_cell(grid: int, forbidden: set[tuple[int, int]]) -> tuple[int, int]:
    free = [(x, y) for x in range(grid) for y in range(grid) if (x, y) not in forbidden]
    if not free:
        return 0, 0
    return random.choice(free)


def _build_session(template: QuestContractTemplate, quest: QuestType) -> QuestMissionSession:
    kind = template.mission_kind
    danger = _location_danger(template.work_location, template.difficulty)
    grid = GRID_SIZE
    start = (random.randrange(grid), random.randrange(grid))
    forbidden: set[tuple[int, int]] = {start}

    objectives: list[tuple[int, int]] = []
    hazards: list[tuple[int, int]] = []
    enemies: list[tuple[int, int]] = []

    if kind in {"collect", "anomaly"}:
        obj_n = 2 if kind == "collect" and template.difficulty == "easy" else 3
        if kind == "anomaly":
            obj_n = 3
        haz_n = 3 + danger if kind == "anomaly" else 2 + danger // 2
        for _ in range(obj_n):
            cell = _free_cell(grid, forbidden)
            objectives.append(cell)
            forbidden.add(cell)
        for _ in range(haz_n):
            cell = _free_cell(grid, forbidden)
            hazards.append(cell)
            forbidden.add(cell)
    elif kind == "scout":
        objectives.append(_free_cell(grid, forbidden))
        forbidden.add(objectives[0])
        for _ in range(2 + danger):
            cell = _free_cell(grid, forbidden)
            # Смесь аномалий и «мутантов» как hazards (урон, не смерть).
            hazards.append(cell)
            forbidden.add(cell)
    elif kind == "loot":
        obj_n = 2 + (1 if danger >= 3 else 0)
        for _ in range(obj_n):
            cell = _free_cell(grid, forbidden)
            objectives.append(cell)
            forbidden.add(cell)
        for _ in range(3 + danger):
            cell = _free_cell(grid, forbidden)
            hazards.append(cell)
            forbidden.add(cell)
    elif kind in {"clear_mutant", "clear_marauder"}:
        enemy_n = 2 + danger
        for _ in range(enemy_n):
            cell = _free_cell(grid, forbidden)
            enemies.append(cell)
            forbidden.add(cell)
    else:
        # fallback collect
        for _ in range(2):
            cell = _free_cell(grid, forbidden)
            objectives.append(cell)
            forbidden.add(cell)
        for _ in range(3):
            cell = _free_cell(grid, forbidden)
            hazards.append(cell)
            forbidden.add(cell)

    return QuestMissionSession(
        contract_key=template.key,
        title=template.title,
        location=template.work_location,
        kind=kind,
        difficulty=template.difficulty,
        player=start,
        start=start,
        objectives=objectives,
        hazards=hazards,
        enemies=enemies,
        max_moves=MAX_MOVES + danger,
        resources_spent=False,
    )


def _objectives_complete(session: QuestMissionSession) -> bool:
    if session.kind in {"clear_mutant", "clear_marauder"}:
        return len(session.enemies) == 0
    remaining = [p for p in session.objectives if p not in session.collected]
    return len(remaining) == 0


def _combat_damage(location: str, difficulty: str, character: Character) -> int:
    danger = _location_danger(location, difficulty)
    base_lo = 6 + danger * 4
    base_hi = 12 + danger * 7
    raw = random.randint(base_lo, base_hi)
    # Снаряга слегка режет урон.
    soak = min(12, equipment_power(character))
    pre_defense = max(4, raw - soak)
    return apply_incoming_damage(pre_defense, character, min_damage=1)


def _hazard_damage(kind: str, character: Character) -> int:
    if kind == "scout":
        raw = 20
    elif kind == "loot":
        raw = 15
    else:
        raw = 25
    return apply_incoming_damage(raw, character, min_damage=1)


def _mission_rating(storage: Storage, telegram_id: int) -> int:
    try:
        return int(storage.get_player_stats(telegram_id).get("rating_points", 0))
    except Exception:
        return 0


def render_mission_for_player(
    storage: Storage,
    telegram_id: int,
    session: QuestMissionSession,
    player: Character,
) -> bytes:
    return render_mission_frame(session, player, rating_points=_mission_rating(storage, telegram_id))


def _render_for_player(storage: Storage, telegram_id: int, session: QuestMissionSession, player: Character) -> bytes:
    return render_mission_for_player(storage, telegram_id, session, player)


def mission_status_caption(session: QuestMissionSession, character: Character | None = None) -> str:
    kind_label = KIND_LABELS.get(session.kind, session.kind)
    lines = [
        f"📋 {session.title}",
        f"{kind_label} · «{session.location}»",
        f"Ход {session.moves}/{session.max_moves}",
    ]
    if session.kind in {"clear_mutant", "clear_marauder"}:
        label = "Мутанты" if session.kind == "clear_mutant" else "Мародёры"
        lines.append(f"{label}: осталось {len(session.enemies)}")
    else:
        left = len([p for p in session.objectives if p not in session.collected])
        lines.append(f"Цели: {len(session.collected)}/{len(session.objectives)} (осталось {left})")
    if session.objectives_done:
        lines.append("Цель взята — вернись на стартовую клетку (зелёная рамка).")
    else:
        lines.append("Собери цели / зачисти поле, затем вернись на старт.")
    if character is not None:
        lines.append(
            f"HP {character.health}/{effective_max_health(character)} · "
            f"☢ {character.radiation} · ⚡ {character.energy}"
        )
    return "\n".join(lines)


def _finish_success(storage: Storage, telegram_id: int, session: QuestMissionSession) -> ActionResult:
    clear_mission_session(storage, telegram_id)
    template = QUEST_CONTRACTS.get(session.contract_key)
    quest = QUESTS.get(session.difficulty)
    if template is None or quest is None:
        storage.set_active_contract(telegram_id, None)
        return ActionResult(False, "Контракт повреждён после миссии.")

    result = apply_contract_mission_success(
        storage,
        telegram_id,
        quest=quest,
        work_location=session.location,
        title=session.title,
    )
    reward = int((result.payload or {}).get("reward", 0))
    character = storage.get_character(telegram_id, refresh_energy=False)
    if template.return_home:
        storage.set_active_contract(
            telegram_id,
            {
                "template_key": template.key,
                "stage": "return",
                "pending_reward": reward,
            },
        )
        home = faction_home_base(character.faction if character else None)
        return ActionResult(
            True,
            result.text
            + f"\n\nВернись на «{home}» и сдай отчёт (+{CONTRACT_TURN_IN_BONUS_PERCENT}% RU).",
            payload={"mission_active": False, "mission_done": True, "reward": reward},
        )
    storage.set_active_contract(telegram_id, None)
    return ActionResult(
        True,
        result.text,
        payload={"mission_active": False, "mission_done": True, "reward": reward},
    )


def start_or_resume_quest_mission(
    storage: Storage,
    telegram_id: int,
    template: QuestContractTemplate,
    quest: QuestType,
) -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())

    existing = get_mission_session(storage, telegram_id)
    if existing is not None and existing.contract_key == template.key:
        image = _render_for_player(storage, telegram_id, existing, player)
        return ActionResult(
            True,
            "Продолжай вылазку по контракту.",
            payload={
                "mission_image": image,
                "mission_active": True,
                "caption": mission_status_caption(existing, player),
            },
        )

    # Новая миссия — списываем ресурсы один раз.
    spend_err = _spend_quest_resources(storage, telegram_id, quest)
    if spend_err is not None:
        return spend_err

    session = _build_session(template, quest)
    session.resources_spent = True
    save_mission_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = _render_for_player(storage, telegram_id, session, player)
    return ActionResult(
        True,
        f"Вылазка: «{template.title}» на «{template.work_location}».\n"
        f"{KIND_LABELS.get(template.mission_kind, template.mission_kind)}. "
        f"Энергия −{quest.energy_cost}.\n"
        "Зелёные точки — цели. Дойди до них и вернись на старт.\n"
        "Опасности наносят урон; аномалии на сборе могут убить.",
        payload={
            "mission_image": image,
            "mission_active": True,
            "mission_started": True,
            "caption": mission_status_caption(session, player),
        },
    )


def abandon_quest_mission(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_mission_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активной вылазки по контракту нет.")
    clear_mission_session(storage, telegram_id)
    quest = QUESTS.get(session.difficulty) or QUESTS["easy"]
    result = apply_contract_mission_fail(
        storage,
        telegram_id,
        quest=quest,
        work_location=session.location,
        title=session.title,
        reason="Ты свалил с поля.",
    )
    storage.set_active_contract(telegram_id, None)
    return ActionResult(
        False,
        result.text,
        payload={"mission_active": False, "mission_done": True},
    )


def use_mission_medkit(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_mission_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Сначала начни вылазку по контракту.")
    # В миссии берём лучшую доступную аптечку (наука → армия → обычная).
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа.")
    preferred = ("medkit_science", "medkit_army", "medkit")
    chosen = next((key for key in preferred if int(player.inventory.get(key, 0)) > 0), None)
    if chosen is None:
        return ActionResult(
            False,
            "Нет аптечек в инвентаре (обычная / армейская / научная).",
            payload={"mission_active": True},
        )
    result = use_medkit_item(storage, telegram_id, chosen)
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return result
    image = _render_for_player(storage, telegram_id, session, player)
    return ActionResult(
        result.ok,
        result.text,
        payload={
            "mission_image": image,
            "mission_active": True,
            "caption": mission_status_caption(session, player),
            "move_note": result.text,
        },
    )


def move_quest_mission(storage: Storage, telegram_id: int, direction: str) -> ActionResult:
    session = get_mission_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Сначала начни работу по контракту.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        clear_mission_session(storage, telegram_id)
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        clear_mission_session(storage, telegram_id)
        storage.set_active_contract(telegram_id, None)
        return ActionResult(False, _dead_block_text())

    delta = MOVE_DELTAS.get(direction)
    if delta is None:
        return ActionResult(False, "Некорректное направление.")
    nx = session.player[0] + delta[0]
    ny = session.player[1] + delta[1]
    if not (0 <= nx < session.grid and 0 <= ny < session.grid):
        image = _render_for_player(storage, telegram_id, session, player)
        return ActionResult(
            False,
            "Край поля — туда не пройти.",
            payload={
                "mission_image": image,
                "mission_active": True,
                "caption": mission_status_caption(session, player),
            },
        )

    session.player = (nx, ny)
    session.moves += 1
    notes: list[str] = []

    # Цель.
    if session.player in session.objectives and session.player not in session.collected:
        session.collected.append(session.player)
        notes.append("Цель отмечена.")

    # Враг.
    if session.player in session.enemies:
        dmg = _combat_damage(session.location, session.difficulty, player)
        storage.change_health(telegram_id, -dmg)
        session.enemies = [e for e in session.enemies if e != session.player]
        label = "мутанта" if session.kind == "clear_mutant" else "мародёра"
        notes.append(f"Бой с {label}: −{dmg} HP.")
        player = storage.get_character(telegram_id, refresh_energy=False) or player
        if player.health <= 0:
            clear_mission_session(storage, telegram_id)
            storage.set_active_contract(telegram_id, None)
            return ActionResult(
                False,
                f"Ты пал в бою на «{session.location}».\nКонтракт сорван.",
                payload={"mission_active": False, "mission_dead": True},
            )

    # Опасность / аномалия.
    if session.player in session.hazards:
        if session.kind in {"collect", "anomaly"}:
            clear_mission_session(storage, telegram_id)
            storage.set_active_contract(telegram_id, None)
            storage.change_health(telegram_id, -10_000)
            return ActionResult(
                False,
                f"Аномалия на «{session.location}». Сознание гаснет…\nКонтракт сорван.",
                payload={"mission_active": False, "mission_dead": True},
            )
        dmg = _hazard_damage(session.kind, player)
        storage.change_health(telegram_id, -dmg)
        # Препятствие/мутант-хазард снимается после контакта.
        session.hazards = [h for h in session.hazards if h != session.player]
        notes.append(f"Опасность: −{dmg} HP.")
        player = storage.get_character(telegram_id, refresh_energy=False) or player
        if player.health <= 0:
            clear_mission_session(storage, telegram_id)
            storage.set_active_contract(telegram_id, None)
            return ActionResult(
                False,
                f"Раны оказались смертельными на «{session.location}».\nКонтракт сорван.",
                payload={"mission_active": False, "mission_dead": True},
            )

    if _objectives_complete(session):
        session.objectives_done = True

    # Победа: цели/враги закрыты и игрок на старте.
    if session.objectives_done and session.player == session.start:
        save_mission_session(storage, telegram_id, session)
        return _finish_success(storage, telegram_id, session)

    if session.moves >= session.max_moves:
        clear_mission_session(storage, telegram_id)
        quest = QUESTS.get(session.difficulty) or QUESTS["easy"]
        result = apply_contract_mission_fail(
            storage,
            telegram_id,
            quest=quest,
            work_location=session.location,
            title=session.title,
            reason="Время вылазки вышло.",
        )
        storage.set_active_contract(telegram_id, None)
        return ActionResult(
            False,
            result.text,
            payload={"mission_active": False, "mission_done": True},
        )

    save_mission_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = _render_for_player(storage, telegram_id, session, player)
    note = " ".join(notes) if notes else "Тихо."
    if session.objectives_done:
        note += " Цель есть — на старт!"
    return ActionResult(
        True,
        note,
        payload={
            "mission_image": image,
            "mission_active": True,
            "caption": mission_status_caption(session, player),
            "move_note": note,
        },
    )


# --- Render -----------------------------------------------------------------

def _load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_cell(base: Image.Image, left: int, top: int, size: int, tone: int = 70) -> None:
    pix = base.load()
    for yy in range(size):
        for xx in range(size):
            n = ((left + xx) * 17 + (top + yy) * 31) % 28
            shade = max(40, min(120, tone + n - 10))
            pix[left + xx, top + yy] = (shade, shade - 2, max(30, shade - 8), 255)
    draw = ImageDraw.Draw(base)
    draw.rectangle((left, top, left + size - 1, top + size - 1), outline=(30, 30, 32), width=2)


def _glow(img: Image.Image, cx: int, cy: int, color: tuple[int, int, int], radius: int = 22) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    r, g, b = color
    for i, a in ((radius + 14, 35), (radius + 6, 90), (radius, 200), (max(4, radius // 2), 240)):
        d.ellipse((cx - i, cy - i, cx + i, cy + i), fill=(r, g, b, a))
    img.alpha_composite(overlay)


def _draw_enemy_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, *, marauder: bool) -> None:
    if marauder:
        # Мародёр — тёмная фигура + красный акцент.
        draw.ellipse((cx - 16, cy - 22, cx + 16, cy + 10), fill=(55, 45, 40), outline=(180, 60, 50), width=2)
        draw.rectangle((cx - 12, cy + 8, cx + 12, cy + 22), fill=(70, 50, 40))
        draw.ellipse((cx - 6, cy - 14, cx + 6, cy - 2), fill=(200, 80, 60))
    else:
        # Мутант — зеленоватый.
        draw.ellipse((cx - 18, cy - 16, cx + 18, cy + 16), fill=(50, 90, 45), outline=(120, 200, 80), width=2)
        draw.ellipse((cx - 8, cy - 8, cx - 2, cy - 2), fill=(220, 230, 100))
        draw.ellipse((cx + 2, cy - 8, cx + 8, cy - 2), fill=(220, 230, 100))
        draw.polygon([(cx - 10, cy + 6), (cx, cy + 16), (cx + 10, cy + 6)], fill=(40, 70, 35))


def render_mission_frame(
    session: QuestMissionSession,
    character: Character | None = None,
    *,
    rating_points: int = 0,
) -> bytes:
    cell = 108
    grid = session.grid
    grid_px = grid * cell
    margin = 24
    panel_w = 320
    width = margin + grid_px + 20 + panel_w + margin
    height = max(margin + grid_px + margin, 760)
    canvas = Image.new("RGBA", (width, height), (16, 18, 20, 255))
    draw = ImageDraw.Draw(canvas)

    field = (margin - 8, margin - 8, margin + grid_px + 8, margin + grid_px + 8)
    draw.rounded_rectangle(field, radius=14, fill=(34, 36, 40, 255), outline=(70, 74, 80), width=2)

    for gy in range(grid):
        for gx in range(grid):
            _draw_cell(canvas, margin + gx * cell, margin + gy * cell, cell)

    # Старт — зелёная рамка.
    sx, sy = session.start
    sl = margin + sx * cell
    st = margin + sy * cell
    draw.rectangle((sl + 3, st + 3, sl + cell - 4, st + cell - 4), outline=(80, 200, 90), width=3)

    for hx, hy in session.hazards:
        cx = margin + hx * cell + cell // 2
        cy = margin + hy * cell + cell // 2
        if session.kind in {"collect", "anomaly"}:
            _glow(canvas, cx, cy, (255, 120, 40), 24)
        elif session.kind == "scout":
            # Аномалия/мутант-пинг.
            _glow(canvas, cx, cy, (255, 90, 50), 20)
            _draw_enemy_icon(ImageDraw.Draw(canvas), cx, cy, marauder=False)
        else:
            # Препятствие — серый шип.
            d = ImageDraw.Draw(canvas)
            d.polygon(
                [(cx, cy - 18), (cx + 16, cy + 14), (cx - 16, cy + 14)],
                fill=(90, 90, 95),
                outline=(40, 40, 45),
            )

    for ex, ey in session.enemies:
        cx = margin + ex * cell + cell // 2
        cy = margin + ey * cell + cell // 2
        marauder = session.kind == "clear_marauder"
        _glow(canvas, cx, cy, (200, 60, 50) if marauder else (90, 200, 70), 18)
        _draw_enemy_icon(ImageDraw.Draw(canvas), cx, cy, marauder=marauder)

    for ox, oy in session.objectives:
        if (ox, oy) in session.collected:
            continue
        cx = margin + ox * cell + cell // 2
        cy = margin + oy * cell + cell // 2
        _glow(canvas, cx, cy, (70, 230, 110), 22)

    # Игрок — аватар персонажа в зелёном кольце.
    px, py = session.player
    pcx = margin + px * cell + cell // 2
    pcy = margin + py * cell + cell // 2
    token = None
    if character is not None:
        try:
            from app.avatar_render import render_avatar

            token = render_avatar(character, rating_points=rating_points, width=160, height=160)
        except Exception:
            token = None
    if token is None:
        token = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        td = ImageDraw.Draw(token)
        td.ellipse((20, 10, 140, 130), fill=(75, 85, 65), outline=(30, 35, 28), width=3)
        td.ellipse((45, 35, 115, 85), fill=(40, 48, 40))
        td.rectangle((45, 120, 115, 155), fill=(95, 75, 50))
    _paste_circle(canvas, token, pcx, pcy, 72, ring_color=(72, 220, 90), ring_width=5)
    # Панель.
    pl = margin + grid_px + 20
    pr = width - margin
    pt = margin - 8
    pb = height - margin + 8
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((pl, pt, pr, pb), radius=16, fill=(48, 50, 54, 255), outline=(100, 104, 110), width=2)

    thumb = (pl + 16, pt + 14, pr - 16, pt + 120)
    loc_img = _load_location_thumb(session.location)
    if loc_img is not None:
        _paste_rounded(canvas, loc_img, thumb, radius=10)
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=10, outline=(110, 120, 100), width=2)
    else:
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=10, fill=(30, 34, 28), outline=(90, 100, 80), width=2)

    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(22)
    body = _load_font(17)
    small = _load_font(14)
    loc_font = title_font if len(session.location) <= 14 else _load_font(18)
    draw.text((pl + 18, pt + 128), session.location, fill=(245, 245, 245), font=loc_font)
    draw.text((pl + 18, pt + 158), KIND_LABELS.get(session.kind, session.kind), fill=(180, 200, 150), font=body)

    y = pt + 190
    if session.kind in {"clear_mutant", "clear_marauder"}:
        label = "Мутанты" if session.kind == "clear_mutant" else "Мародёры"
        draw.text((pl + 18, y), f"{label}: {len(session.enemies)}", fill=(230, 180, 160), font=body)
    else:
        done = len(session.collected)
        total = len(session.objectives)
        draw.text((pl + 18, y), f"Цели: {done}/{total}", fill=(150, 230, 170), font=body)
    draw.text((pl + 18, y + 28), f"Ход {session.moves}/{session.max_moves}", fill=(200, 200, 200), font=small)
    if session.objectives_done:
        draw.text((pl + 18, y + 52), ">> Вернись на старт!", fill=(120, 255, 140), font=body)
    else:
        draw.text((pl + 18, y + 52), "Собери / зачисти поле", fill=(170, 170, 170), font=small)

    hp = int(character.health) if character else 0
    max_hp = int(effective_max_health(character)) if character else 100
    energy = int(character.energy) if character else 0
    max_energy = int(character.max_energy) if character else 100
    meds = 0
    if character is not None:
        meds = sum(int(character.inventory.get(k, 0)) for k in ("medkit", "medkit_army", "medkit_science"))

    bar_top = y + 100
    # HP bar
    draw.rounded_rectangle((pl + 18, bar_top, pr - 18, bar_top + 28), radius=8, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 44) * (hp / max(1, max_hp)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 20, bar_top + 2, pl + 20 + fill_w, bar_top + 26), radius=6, fill=(200, 60, 50))
    draw.text((pl + 24, bar_top + 5), f"HP {hp}/{max_hp}", fill=(255, 255, 255), font=small)

    draw.rounded_rectangle((pl + 18, bar_top + 40, pr - 18, bar_top + 68), radius=8, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 44) * (energy / max(1, max_energy)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 20, bar_top + 42, pl + 20 + fill_w, bar_top + 66), radius=6, fill=(50, 120, 210))
    draw.text((pl + 24, bar_top + 45), f"EN {energy}/{max_energy}", fill=(255, 255, 255), font=small)

    draw.text((pl + 18, bar_top + 84), f"Аптечки: {meds}", fill=(180, 200, 180), font=small)
    draw.text((pl + 18, pb - 50), session.title[:28], fill=(160, 160, 160), font=small)
    draw.text((pl + 18, pb - 28), "Стрелки - ход, кнопка - аптечка", fill=(130, 130, 130), font=small)

    out = canvas.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
