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
    try_auto_turn_in_contract,
    use_medkit_item,
)
from app.mutant_assets import (
    MISSION_MUTANT_GRID_DIAMETER,
    MUTANT_SPRITE_KEYS,
    MUTANT_SPRITES,
    mutant_sprite_image,
    pick_mutant_kind,
)
from app.mission_icons import (
    ANOMALY_ICON_KEY,
    MISSION_ICON_GRID_DIAMETER,
    OBJECTIVE_ICON_KEY,
    mission_icon_image,
)
from app.npc_assets import (
    MISSION_NPC_GRID_DIAMETER,
    NPC_SPRITE_KEYS,
    NPC_SPRITES,
    npc_sprite_image,
    pick_npc_kind,
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

# Сложность → состав угроз на поле: аномалии / мутанты / НПС.
DIFFICULTY_THREATS: dict[str, tuple[bool, bool, bool]] = {
    "easy": (True, False, False),
    "hard": (True, True, False),
    "heavy": (True, False, True),
    "impossible": (True, True, True),
}

KIND_LABELS: dict[str, str] = {
    "collect": "Сбор",
    "scout": "Разведка",
    "loot": "Поиск хабара",
    "clear_mutant": "Зачистка мутантов",
    "clear_marauder": "Зачистка мародёров",
    "anomaly": "Аномалии",
}

HOSTILE_MOVE_CHANCE = 0.5


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
    hazards: list[tuple[int, int]] = field(default_factory=list)  # аномалии
    enemies: list[tuple[int, int]] = field(default_factory=list)  # мутанты
    enemy_kinds: list[str] = field(default_factory=list)  # blind_dog, tushkano, …
    npcs: list[tuple[int, int]] = field(default_factory=list)  # мародёры / НПС
    npc_kinds: list[str] = field(default_factory=list)  # maloy, …
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
            "enemy_kinds": list(self.enemy_kinds),
            "npcs": [list(p) for p in self.npcs],
            "npc_kinds": list(self.npc_kinds),
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
            enemy_kinds=_parse_enemy_kinds(raw.get("enemies") or [], raw.get("enemy_kinds")),
            npcs=[(int(p[0]), int(p[1])) for p in (raw.get("npcs") or [])],
            npc_kinds=_parse_npc_kinds(raw.get("npcs") or [], raw.get("npc_kinds")),
            moves=int(raw.get("moves") or 0),
            max_moves=int(raw.get("max_moves") or MAX_MOVES),
            grid=int(raw.get("grid") or GRID_SIZE),
            objectives_done=bool(raw.get("objectives_done")),
            resources_spent=bool(raw.get("resources_spent")),
        )


def _parse_enemy_kinds(enemies_raw: list, kinds_raw: Any) -> list[str]:
    n = len(enemies_raw)
    if not n:
        return []
    if isinstance(kinds_raw, list) and len(kinds_raw) == n:
        parsed: list[str] = []
        for i, k in enumerate(kinds_raw):
            key = str(k)
            parsed.append(
                key if key in MUTANT_SPRITES else MUTANT_SPRITE_KEYS[i % len(MUTANT_SPRITE_KEYS)]
            )
        return parsed
    return [MUTANT_SPRITE_KEYS[i % len(MUTANT_SPRITE_KEYS)] for i in range(n)]


def _parse_npc_kinds(npcs_raw: list, kinds_raw: Any) -> list[str]:
    n = len(npcs_raw)
    if not n:
        return []
    if isinstance(kinds_raw, list) and len(kinds_raw) == n:
        parsed: list[str] = []
        for i, k in enumerate(kinds_raw):
            key = str(k)
            parsed.append(key if key in NPC_SPRITES else NPC_SPRITE_KEYS[i % len(NPC_SPRITE_KEYS)])
        return parsed
    return [NPC_SPRITE_KEYS[i % len(NPC_SPRITE_KEYS)] for i in range(n)]


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


def _difficulty_threat_flags(difficulty: str, kind: str) -> tuple[bool, bool, bool]:
    """Аномалии / мутанты / НПС по сложности (+ принудительно для зачисток)."""
    anom, mutants, npcs = DIFFICULTY_THREATS.get(difficulty, (True, False, False))
    if kind == "clear_mutant":
        mutants = True
    if kind == "clear_marauder":
        npcs = True
    return anom, mutants, npcs


def _free_cell(grid: int, forbidden: set[tuple[int, int]]) -> tuple[int, int]:
    free = [(x, y) for x in range(grid) for y in range(grid) if (x, y) not in forbidden]
    if not free:
        return 0, 0
    return random.choice(free)


def _adjacent_cells(pos: tuple[int, int], grid: int) -> list[tuple[int, int]]:
    x, y = pos
    cells: list[tuple[int, int]] = []
    for dx, dy in MOVE_DELTAS.values():
        nx, ny = x + dx, y + dy
        if 0 <= nx < grid and 0 <= ny < grid:
            cells.append((nx, ny))
    return cells


def _spawn_n(
    n: int,
    grid: int,
    forbidden: set[tuple[int, int]],
    into: list[tuple[int, int]],
) -> None:
    for _ in range(max(0, n)):
        cell = _free_cell(grid, forbidden)
        into.append(cell)
        forbidden.add(cell)


def _spawn_mutants(
    n: int,
    grid: int,
    forbidden: set[tuple[int, int]],
    enemies: list[tuple[int, int]],
    kinds: list[str],
) -> None:
    for _ in range(max(0, n)):
        cell = _free_cell(grid, forbidden)
        enemies.append(cell)
        kinds.append(pick_mutant_kind())
        forbidden.add(cell)


def _spawn_npcs(
    n: int,
    grid: int,
    forbidden: set[tuple[int, int]],
    npcs: list[tuple[int, int]],
    kinds: list[str],
) -> None:
    for _ in range(max(0, n)):
        cell = _free_cell(grid, forbidden)
        npcs.append(cell)
        kinds.append(pick_npc_kind())
        forbidden.add(cell)


def _build_session(template: QuestContractTemplate, quest: QuestType) -> QuestMissionSession:
    kind = template.mission_kind
    difficulty = template.difficulty
    danger = _location_danger(template.work_location, difficulty)
    grid = GRID_SIZE
    start = (random.randrange(grid), random.randrange(grid))
    forbidden: set[tuple[int, int]] = {start}

    objectives: list[tuple[int, int]] = []
    hazards: list[tuple[int, int]] = []
    enemies: list[tuple[int, int]] = []
    enemy_kinds: list[str] = []
    npcs: list[tuple[int, int]] = []
    npc_kinds: list[str] = []

    # Цели задания — по типу контракта.
    if kind in {"clear_mutant", "clear_marauder"}:
        pass  # цель = зачистить соответствующих врагов
    elif kind == "scout":
        objectives.append(_free_cell(grid, forbidden))
        forbidden.add(objectives[0])
    elif kind == "anomaly":
        _spawn_n(3, grid, forbidden, objectives)
    elif kind == "loot":
        _spawn_n(2 + (1 if danger >= 3 else 0), grid, forbidden, objectives)
    else:
        # collect / fallback
        obj_n = 2 if difficulty == "easy" else 3
        _spawn_n(obj_n, grid, forbidden, objectives)

    # Угрозы — строго по сложности (+ добор для зачисток).
    want_anom, want_mut, want_npc = _difficulty_threat_flags(difficulty, kind)
    base_n = 2 + max(0, danger // 2)
    if want_anom:
        anom_n = base_n + (1 if kind == "anomaly" else 0)
        _spawn_n(anom_n, grid, forbidden, hazards)
    if want_mut:
        mut_n = base_n + (1 if kind == "clear_mutant" else 0)
        _spawn_mutants(mut_n, grid, forbidden, enemies, enemy_kinds)
    if want_npc:
        npc_n = base_n + (1 if kind == "clear_marauder" else 0)
        _spawn_npcs(npc_n, grid, forbidden, npcs, npc_kinds)

    return QuestMissionSession(
        contract_key=template.key,
        title=template.title,
        location=template.work_location,
        kind=kind,
        difficulty=difficulty,
        player=start,
        start=start,
        objectives=objectives,
        hazards=hazards,
        enemies=enemies,
        enemy_kinds=enemy_kinds,
        npcs=npcs,
        npc_kinds=npc_kinds,
        max_moves=MAX_MOVES + danger,
        resources_spent=False,
    )


def _objectives_complete(session: QuestMissionSession) -> bool:
    if session.kind == "clear_mutant":
        return len(session.enemies) == 0
    if session.kind == "clear_marauder":
        return len(session.npcs) == 0
    remaining = [p for p in session.objectives if p not in session.collected]
    return len(remaining) == 0


def _occupied_for_hostile_move(session: QuestMissionSession) -> set[tuple[int, int]]:
    """Клетки, на которые врагам лучше не становиться (кроме клетки игрока)."""
    blocked: set[tuple[int, int]] = set(session.hazards)
    blocked.update(session.enemies)
    blocked.update(session.npcs)
    return blocked


def _move_hostile_units(
    units: list[tuple[int, int]],
    session: QuestMissionSession,
    kinds: list[str] | None = None,
) -> tuple[list[tuple[int, int]], list[str] | None, int]:
    """С шансом HOSTILE_MOVE_CHANCE сдвинуть юнит на соседнюю клетку."""
    moved = 0
    result: list[tuple[int, int]] = []
    result_kinds: list[str] = []
    occupied = _occupied_for_hostile_move(session)
    for i, pos in enumerate(units):
        kind = kinds[i] if kinds is not None and i < len(kinds) else None
        occupied.discard(pos)
        if random.random() >= HOSTILE_MOVE_CHANCE:
            result.append(pos)
            if kind is not None:
                result_kinds.append(kind)
            occupied.add(pos)
            continue
        candidates = [
            cell
            for cell in _adjacent_cells(pos, session.grid)
            if cell not in occupied or cell == session.player
        ]
        if not candidates:
            result.append(pos)
            if kind is not None:
                result_kinds.append(kind)
            occupied.add(pos)
            continue
        nxt = random.choice(candidates)
        result.append(nxt)
        if kind is not None:
            result_kinds.append(kind)
        occupied.add(nxt)
        if nxt != pos:
            moved += 1
    out_kinds = result_kinds if kinds is not None else None
    return result, out_kinds, moved


def _maybe_move_hostiles(session: QuestMissionSession) -> list[str]:
    notes: list[str] = []
    session.enemies, session.enemy_kinds, mut_moved = _move_hostile_units(
        list(session.enemies), session, list(session.enemy_kinds)
    )
    session.npcs, session.npc_kinds, npc_moved = _move_hostile_units(
        list(session.npcs), session, list(session.npc_kinds)
    )
    if mut_moved:
        notes.append(f"Мутанты сдвинулись ({mut_moved}).")
    if npc_moved:
        notes.append(f"НПС сдвинулись ({npc_moved}).")
    return notes


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
    threat_bits: list[str] = []
    if session.hazards:
        threat_bits.append(f"аномалии {len(session.hazards)}")
    if session.enemies:
        threat_bits.append(f"мутанты {len(session.enemies)}")
    if session.npcs:
        threat_bits.append(f"НПС {len(session.npcs)}")
    if threat_bits:
        lines.append("Угрозы: " + ", ".join(threat_bits))
    if session.kind == "clear_mutant":
        lines.append(f"Зачистка: мутанты осталось {len(session.enemies)}")
    elif session.kind == "clear_marauder":
        lines.append(f"Зачистка: НПС осталось {len(session.npcs)}")
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
        # Если уже на базе (редкий случай) — сразу закрываем отчёт.
        auto = try_auto_turn_in_contract(storage, telegram_id)
        if auto:
            return ActionResult(
                True,
                result.text + "\n\n" + auto,
                payload={"mission_active": False, "mission_done": True, "reward": reward, "turned_in": True},
            )
        return ActionResult(
            True,
            result.text
            + f"\n\nВернись на «{home}» — отчёт сдастся автоматически при прибытии "
            + f"(+{CONTRACT_TURN_IN_BONUS_PERCENT}% RU).",
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
    want_anom, want_mut, want_npc = _difficulty_threat_flags(template.difficulty, template.mission_kind)
    threat_parts: list[str] = []
    if want_anom:
        threat_parts.append("аномалии")
    if want_mut:
        threat_parts.append("мутанты")
    if want_npc:
        threat_parts.append("НПС")
    threat_txt = ", ".join(threat_parts) if threat_parts else "без угроз"
    return ActionResult(
        True,
        f"Вылазка: «{template.title}» на «{template.work_location}».\n"
        f"{KIND_LABELS.get(template.mission_kind, template.mission_kind)}. "
        f"Энергия −{quest.energy_cost}.\n"
        f"Угрозы ({template.difficulty}): {threat_txt}.\n"
        "Зелёная обводка — ты и цели (собери их). Красная — враги. Аномалии без обводки.\n"
        "Дойди до целей и вернись на старт (зелёная рамка клетки).\n"
        "Мутанты и НПС с шансом 50% сдвигаются на соседнюю клетку каждый ход.",
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

    def _fight_on_cell(
        label: str,
        unit_attr: str,
        *,
        kinds_attr: str | None = None,
    ) -> ActionResult | None:
        nonlocal player, notes
        units: list[tuple[int, int]] = getattr(session, unit_attr)
        if session.player not in units:
            return None
        dmg = _combat_damage(session.location, session.difficulty, player)
        storage.change_health(telegram_id, -dmg)
        kinds: list[str] | None = getattr(session, kinds_attr) if kinds_attr else None
        if kinds is not None and len(kinds) == len(units):
            new_units: list[tuple[int, int]] = []
            new_kinds: list[str] = []
            for pos, kind in zip(units, kinds):
                if pos != session.player:
                    new_units.append(pos)
                    new_kinds.append(kind)
            setattr(session, unit_attr, new_units)
            setattr(session, kinds_attr, new_kinds)
        else:
            setattr(session, unit_attr, [e for e in units if e != session.player])
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
        return None

    dead = _fight_on_cell("мутанта", "enemies", kinds_attr="enemy_kinds")
    if dead is not None:
        return dead
    dead = _fight_on_cell("НПС", "npcs", kinds_attr="npc_kinds")
    if dead is not None:
        return dead

    # Аномалия.
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
        session.hazards = [h for h in session.hazards if h != session.player]
        notes.append(f"Аномалия: −{dmg} HP.")
        player = storage.get_character(telegram_id, refresh_energy=False) or player
        if player.health <= 0:
            clear_mission_session(storage, telegram_id)
            storage.set_active_contract(telegram_id, None)
            return ActionResult(
                False,
                f"Раны оказались смертельными на «{session.location}».\nКонтракт сорван.",
                payload={"mission_active": False, "mission_dead": True},
            )

    # Мутанты и НПС: 50% сдвиг на соседнюю клетку.
    notes.extend(_maybe_move_hostiles(session))

    # Если враг зашёл на клетку игрока после хода — бой.
    dead = _fight_on_cell("мутанта", "enemies", kinds_attr="enemy_kinds")
    if dead is not None:
        return dead
    dead = _fight_on_cell("НПС", "npcs", kinds_attr="npc_kinds")
    if dead is not None:
        return dead

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


def _paste_token_circle(
    canvas: Image.Image,
    token: Image.Image,
    cx: int,
    cy: int,
    diameter: int,
) -> None:
    """Круглый спрайт без цветной обводки (аномалии)."""
    token = token.convert("RGBA").resize((diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, diameter - 2, diameter - 2), fill=255)
    canvas.paste(token, (cx - diameter // 2, cy - diameter // 2), mask)


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
        sprite = mission_icon_image(ANOMALY_ICON_KEY)
        if sprite is not None:
            # Аномалия — спрайт без цветной обводки (не цель и не враг).
            _paste_token_circle(canvas, sprite, cx, cy, MISSION_ICON_GRID_DIAMETER)
        else:
            _glow(canvas, cx, cy, (255, 120, 40), 24)

    enemy_ring = (210, 55, 45)
    for i, (ex, ey) in enumerate(session.enemies):
        cx = margin + ex * cell + cell // 2
        cy = margin + ey * cell + cell // 2
        kind = (
            session.enemy_kinds[i]
            if i < len(session.enemy_kinds)
            else MUTANT_SPRITE_KEYS[i % len(MUTANT_SPRITE_KEYS)]
        )
        sprite = mutant_sprite_image(kind)
        if sprite is not None:
            _paste_circle(
                canvas,
                sprite,
                cx,
                cy,
                MISSION_MUTANT_GRID_DIAMETER,
                ring_color=enemy_ring,
                ring_width=3,
            )
        else:
            _draw_enemy_icon(ImageDraw.Draw(canvas), cx, cy, marauder=False)

    for i, (nx_, ny_) in enumerate(session.npcs):
        cx = margin + nx_ * cell + cell // 2
        cy = margin + ny_ * cell + cell // 2
        kind = (
            session.npc_kinds[i]
            if i < len(session.npc_kinds)
            else NPC_SPRITE_KEYS[i % len(NPC_SPRITE_KEYS)]
        )
        sprite = npc_sprite_image(kind)
        if sprite is not None:
            _paste_circle(
                canvas,
                sprite,
                cx,
                cy,
                MISSION_NPC_GRID_DIAMETER,
                ring_color=enemy_ring,
                ring_width=3,
            )
        else:
            _draw_enemy_icon(ImageDraw.Draw(canvas), cx, cy, marauder=True)

    objective_ring = (72, 220, 90)
    for ox, oy in session.objectives:
        if (ox, oy) in session.collected:
            continue
        cx = margin + ox * cell + cell // 2
        cy = margin + oy * cell + cell // 2
        sprite = mission_icon_image(OBJECTIVE_ICON_KEY)
        if sprite is not None:
            _paste_circle(
                canvas,
                sprite,
                cx,
                cy,
                MISSION_ICON_GRID_DIAMETER,
                ring_color=objective_ring,
                ring_width=4,
            )
        else:
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
    if session.kind == "clear_mutant":
        draw.text((pl + 18, y), f"Мутанты: {len(session.enemies)}", fill=(230, 180, 160), font=body)
    elif session.kind == "clear_marauder":
        draw.text((pl + 18, y), f"НПС: {len(session.npcs)}", fill=(230, 180, 160), font=body)
    else:
        done = len(session.collected)
        total = len(session.objectives)
        draw.text((pl + 18, y), f"Цели: {done}/{total}", fill=(150, 230, 170), font=body)
    threat_y = y + 26
    bits: list[str] = []
    if session.hazards:
        bits.append(f"ан.{len(session.hazards)}")
    if session.enemies:
        bits.append(f"мут.{len(session.enemies)}")
    if session.npcs:
        bits.append(f"нпс.{len(session.npcs)}")
    if bits:
        draw.text((pl + 18, threat_y), " ".join(bits), fill=(200, 170, 140), font=small)
    draw.text((pl + 18, y + 48), f"Ход {session.moves}/{session.max_moves}", fill=(200, 200, 200), font=small)
    if session.objectives_done:
        draw.text((pl + 18, y + 72), ">> Вернись на старт!", fill=(120, 255, 140), font=body)
    else:
        draw.text((pl + 18, y + 72), "Зелёные — цели, красные — враги", fill=(170, 170, 170), font=small)

    hp = int(character.health) if character else 0
    max_hp = int(effective_max_health(character)) if character else 100
    energy = int(character.energy) if character else 0
    max_energy = int(character.max_energy) if character else 100
    meds = 0
    if character is not None:
        meds = sum(int(character.inventory.get(k, 0)) for k in ("medkit", "medkit_army", "medkit_science"))

    bar_top = y + 120
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
