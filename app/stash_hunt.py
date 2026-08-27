from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.artifact_hunt import (
    FONT_CANDIDATES,
    PROJECT_ROOT,
    _cover_crop,
    _load_font,
    _load_location_thumb,
    _paste_circle,
    _paste_rounded,
)
from app.game_logic import (
    ActionResult,
    ITEM_LABELS,
    STASH_CONSUMABLE_KEYS,
    STASH_GEAR_TIER_CHANCES,
    STASH_ARMOR_BY_TIER,
    STASH_WEAPON_BY_TIER,
    STASH_CONSUMABLE_DROP_CHANCE,
    STASH_CONSUMABLE_DROP_CHANCE_BY_KEY,
    _is_dead,
    _dead_block_text,
    effective_max_health,
    is_traveling,
    travel_block_text,
)
from app.storage import Storage


STASH_META_PREFIX = "stash_hunt:"
STASH_MAX_MOVES = 30
STASH_RAD_EVERY_STEPS = 3
STASH_RAD_PER_TICK = 1
STASH_MINUTE_MOVES = 10
STASH_RAD_PER_MINUTE = 5
STASH_COORDINATE_PRICE = 3500
STASH_COORDINATE_KEY = "stash_coordinates"

AMBUSH_TYPES: tuple[tuple[str, str, int], ...] = (
    ("Слепые псы", "слепые псы", 8),
    ("Псевдособаки", "псевдособаки", 10),
    ("Кабаны", "кабаны", 7),
    ("Бандиты", "бандиты", 12),
    ("Снорк", "снорк", 15),
    ("Кровосос", "кровосос", 18),
)

# Сложность локации → шанс встречи (в %).
LOCATION_DIFFICULTY: dict[str, str] = {
    "Кордон": "easy",
    "Свалка": "easy",
    "Болото": "easy",
    "Темная долина": "easy",
    "НИИ Агропром": "hard",
    "Янтарь": "hard",
    "Росток": "hard",
    "Армейские склады": "hard",
    "Рыжий лес": "hardcore",
    "Радар": "hardcore",
    "Припять": "hardcore",
    "ЧАЭС": "hardcore",
}

AMBUSH_CHANCE_BY_DIFFICULTY: dict[str, int] = {
    "easy": 5,
    "hard": 7,
    "hardcore": 10,
}


@dataclass
class RoomNode:
    name: str
    desc: str
    doors: tuple[int, ...]


# Помещения для каждой локации: связанные комнаты с дверями.
# Индексы в doors ссылаются на позиции в этом же списке.
LOCATION_ROOMS: dict[str, list[RoomNode]] = {
    "Кордон": [
        RoomNode("Блокпост", "Военный блокпост на границе Зоны. Ржавая КПП и мешки с песком.", (1, 2)),
        RoomNode("Деревня новичков", "Заброшенные хаты. Пахнет костром и дешёвым табаком.", (0, 3, 4)),
        RoomNode("Тропа", "Заросшая тропа вглубь Зоны. Стволы деревьев склонились над дорогой.", (0, 4)),
        RoomNode("Склад", "Старый склад с проржавевшей дверью. Пахнет мазутом.", (1, 5)),
        RoomNode("Подвал", "Сырой подвал под разрушенным домом. На стенах плесень.", (1, 2, 5)),
        RoomNode("Чердак", "Чердак с видом на Зону. Доски скрипят под ногами.", (3, 4)),
    ],
    "Свалка": [
        RoomNode("Проход", "Узкий проход между гор мусора. Вонь жжёного пластика.", (1, 2)),
        RoomNode("Кладбище машин", "Ряды ржавых остовов. Кое-где блестят целые детали.", (0, 3, 4)),
        RoomNode("Зона отчуждения", "Огороженная территория. Знаки радиации на заборе.", (0, 4, 5)),
        RoomNode("Бункер", "Бетонный бункер с тяжёлой дверью. Внутри темно и сухо.", (1, 5)),
        RoomNode("Схрон контрабандиста", "Старый фургон без колёс. Внутри — нары и пустые ящики.", (1, 2, 6)),
        RoomNode("Тоннель", "Дренажный тоннель. Вода по щиколотку, эхо гулкое.", (2, 3, 6)),
        RoomNode("Штаб бандитов", "Разрушенное здание. На стенах — граффити и следы от пуль.", (4, 5)),
    ],
    "Болото": [
        RoomNode("Причал", "Гнилой деревянный причал. Туман над водой.", (1, 2)),
        RoomNode("Хижина", "Покосившаяся хижина на сваях. Внутри — старые сети и весло.", (0, 3, 4)),
        RoomNode("Топь", "Трясина. Деревянные настилы-мостики уходят в туман.", (0, 4, 5)),
        RoomNode("Сторожка", "Каменная сторожка с провалившейся крышей.", (1, 5)),
        RoomNode("Затопленный подвал", "Подвал по колено в мутной воде. На поверхности плавает мусор.", (1, 2, 6)),
        RoomNode("Мост", "Разбитый мост через болото. Доски гниют под ногами.", (2, 3, 6)),
        RoomNode("Остров", "Крошечный островок сухой земли посреди трясины.", (4, 5)),
    ],
    "Темная долина": [
        RoomNode("Въезд", "Разбитый асфальт. Покосившийся указатель «Темная долина».", (1, 2)),
        RoomNode("Завод", "Старый химический завод. Запах аммиака и гнили.", (0, 3, 4)),
        RoomNode("Тоннель", "Автодорожный тоннель. Свет из фонарей не достигает стен.", (0, 4, 5)),
        RoomNode("Цех", "Заводской цех с разбитыми окнами. Под ногами — осколки.", (1, 5, 6)),
        RoomNode("Склад химии", "Склад с бочками. Знаки «Опасно» на стенах.", (1, 2, 6)),
        RoomNode("Подземный гараж", "Подземный гараж. Стоят два сгоревших УАЗа.", (2, 3)),
        RoomNode("Лаборатория", "Разрушенная лаборатория в подвале завода. Битые колбы.", (3, 4)),
    ],
    "НИИ Агропром": [
        RoomNode("Проходная", "КПП института. Вертушка на воротах, будка охраны.", (1, 2)),
        RoomNode("Административный корпус", "Разрушенный офис. Листы бумаги по всему полу.", (0, 3, 4)),
        RoomNode("Подземный ход", "Технический тоннель под территорией. Трубы и кабели.", (0, 4, 5)),
        RoomNode("Лаборатория", "Лаборатория с разбитым оборудованием. Запах формалина.", (1, 5, 6)),
        RoomNode("Серверная", "Серверная комната. Серверы мертвы, но экраны ещё светятся.", (1, 2, 6)),
        RoomNode("Вентиляционная", "Вентиляционная шахта. Лестница уходит вниз.", (2, 3)),
        RoomNode("Архив", "Архив с полками до потолка. Папки осыпались.", (3, 4)),
    ],
    "Янтарь": [
        RoomNode("Озеро", "Берег мёртвого озера. Вода мутная, поверхность — как стекло.", (1, 2)),
        RoomNode("Научный лагерь", "Палатки и генераторы. Учёные давно ушли.", (0, 3, 4)),
        RoomNode("Дамба", "Бетонная плотина. Трещины во всю ширину.", (0, 4, 5)),
        RoomNode("Бункер учёных", "Подземный бункер. На стенах — схемы и графики.", (1, 5, 6)),
        RoomNode("Здание станции", "Насосная станция. Ржавые трубы и гул турбин.", (1, 2, 6)),
        RoomNode("Тоннель", "Служебный тоннель под дамбой. Вода капает с потолка.", (2, 3)),
        RoomNode("Котельная", "Старая котельная. Запах мазута и гари.", (3, 4)),
    ],
    "Росток": [
        RoomNode("Ворота", "КПП базы «Росток». Стены из бетонных блоков.", (1, 2)),
        RoomNode("Бар «100 рентген»", "Заведение Сидоровича. Столики, стойка, прокуренный воздух.", (0, 3, 4)),
        RoomNode("Общежитие", "Здание общежития. На стенах — следы от пуль и копоти.", (0, 4, 5)),
        RoomNode("Подвал Сидоровича", "Торговая лавка в подвале. Полки с барахлом.", (1, 5, 6)),
        RoomNode("Чердачный ход", "Лестница на чердак. Окна выбиты, ветер гуляет.", (1, 2, 6)),
        RoomNode("Трансформаторная", "Трансформаторная будка во дворе. Гул высоковольтных линий.", (2, 3)),
        RoomNode("Склад артефактов", "Запертый склад. Контейнер с артефактами — если найдёшь.", (3, 4)),
    ],
    "Армейские склады": [
        RoomNode("КПП", "Военный контрольно-пропускной пункт. Колючая проволока.", (1, 2)),
        RoomNode("Казарма", "Длинная казарма с двухъярусными койками. Запах сырости.", (0, 3, 4)),
        RoomNode("Склад боеприпасов", "Бетонный склад. Ящики с патронами — пустые.", (0, 4, 5)),
        RoomNode("Ангар", "Ангар с техникой. Остов БТР и два сгоревших УАЗа.", (1, 5, 6)),
        RoomNode("Штаб", "Здание штаба. Карта Зоны на стене, стулья опрокинуты.", (1, 2, 6)),
        RoomNode("Подземный ход", "Подземный переход между складами. Темно и сыро.", (2, 3)),
        RoomNode("Арсенал", "Запертый арсенал. Тяжёлая дверь, замок сорван.", (3, 4)),
    ],
    "Рыжий лес": [
        RoomNode("Опушка", "Край мёртвого леса. Деревья — как скелеты без коры.", (1, 2)),
        RoomNode("Поляна", "Выгоревшая поляна. Пепел по щиколотку.", (0, 3, 4)),
        RoomNode("Засада", "Старый окоп. На бруствере — гильзы.", (0, 4, 5)),
        RoomNode("Развалины", "Фундамент сгоревшего дома. Заросли бурьяна.", (1, 5, 6)),
        RoomNode("Тропа на Радар", "Крутая тропа в гору. Виден купол радара.", (1, 2, 6)),
        RoomNode("Землянка", "Землянка под корнями упавшего дерева. Тесно и темно.", (2, 3)),
        RoomNode("Схрон лесника", "Старый домик лесника. Дверь сорвана с петель.", (3, 4)),
    ],
    "Радар": [
        RoomNode("Подножие", "Подножие холма с радаром. Колючая проволока по склону.", (1, 2)),
        RoomNode("Бункер ПВО", "Железобетонный бункер. Тяжёлая гермодверь приоткрыта.", (0, 3, 4)),
        RoomNode("Купол", "Основание радарного купола. Кабели обвивают конструкцию.", (0, 4, 5)),
        RoomNode("Командный пункт", "Подземный командный пункт. Экраны погасли, стулья опрокинуты.", (1, 5, 6)),
        RoomNode("Технический отсек", "Серверный отсек под куполом. Гул вентиляции.", (1, 2, 6)),
        RoomNode("Антенная", "Помещение с аппаратурой. Проводка оплавлена.", (2, 3)),
        RoomNode("Схрон", "Секретная комната за фальшстеной. Тут прятали ценное.", (3, 4)),
    ],
    "Припять": [
        RoomNode("Улица", "Заросшая улица спального района. Трава по пояс.", (1, 2)),
        RoomNode("Подъезд", "Разбитый подъезд девятиэтажки. Лифт застрял между этажами.", (0, 3, 4)),
        RoomNode("Школа", "Школа №1. Парты, доска, глобус. На стенах — плесень.", (0, 4, 5)),
        RoomNode("Подвал", "Подвал жилого дома. Трубы лопнули, вода на полу.", (1, 5, 6)),
        RoomNode("Больница", "Городская больница. Стоматологическое кресло и разбитые шкафы.", (1, 2, 6)),
        RoomNode("Чердак", "Чердак дома. Кровля провалилась, видны звёзды.", (2, 3)),
        RoomNode("Универмаг", "Разграбленный универмаг. Витрины выбиты, полки пусты.", (3, 4)),
    ],
    "ЧАЭС": [
        RoomNode("КПП станции", "Контрольно-пропускной пункт АЭС. Знаки радиации везде.", (1, 2)),
        RoomNode("Машинный зал", "Гигантский турбинный зал. Эхо шагов гремит под куполом.", (0, 3, 4)),
        RoomNode("Реакторная", "Центральный зал реактора. Саркофаг нависает над всем.", (0, 4, 5)),
        RoomNode("Управление", "Помещение управления реактором. Пульты с мёртвыми лампами.", (1, 5, 6)),
        RoomNode("Дезактивация", "Камера дезактивации. Следы химикатов на стенах.", (1, 2, 6)),
        RoomNode("Подсобка", "Маленькая подсобка. Тут прятались ликвидаторы.", (2, 3)),
        RoomNode("Схрон Призрака", "Тайник в глубине станции. Говорят, тут хранят лучшее.", (3, 4)),
    ],
}


def _rooms_for(location: str) -> list[RoomNode]:
    return LOCATION_ROOMS.get(location) or LOCATION_ROOMS["Кордон"]


def _ambush_chance(location: str) -> int:
    diff = LOCATION_DIFFICULTY.get(location, "easy")
    return AMBUSH_CHANCE_BY_DIFFICULTY.get(diff, 5)


@dataclass
class StashSession:
    location: str
    current_room: int
    target_room: int
    visited_rooms: list[int]
    moves: int
    steps: int
    rad_gained: int
    max_moves: int = STASH_MAX_MOVES
    found: bool = False
    source: str = "found"

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "current_room": self.current_room,
            "target_room": self.target_room,
            "visited_rooms": list(self.visited_rooms),
            "moves": self.moves,
            "steps": self.steps,
            "rad_gained": self.rad_gained,
            "max_moves": self.max_moves,
            "found": self.found,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StashSession:
        return cls(
            location=str(raw.get("location") or ""),
            current_room=int(raw.get("current_room") or 0),
            target_room=int(raw.get("target_room") or 1),
            visited_rooms=[int(x) for x in (raw.get("visited_rooms") or [0])],
            moves=int(raw.get("moves") or 0),
            steps=int(raw.get("steps") or 0),
            rad_gained=int(raw.get("rad_gained") or 0),
            max_moves=int(raw.get("max_moves") or STASH_MAX_MOVES),
            found=bool(raw.get("found")),
            source=str(raw.get("source") or "found"),
        )


def _stash_meta_key(telegram_id: int) -> str:
    return f"{STASH_META_PREFIX}{int(telegram_id)}"


def get_stash_session(storage: Storage, telegram_id: int) -> StashSession | None:
    raw = storage.get_meta(_stash_meta_key(telegram_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return StashSession.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_stash_session(storage: Storage, telegram_id: int, session: StashSession) -> None:
    storage.set_meta(_stash_meta_key(telegram_id), json.dumps(session.to_dict(), ensure_ascii=False))


def clear_stash_session(storage: Storage, telegram_id: int) -> None:
    storage.delete_meta(_stash_meta_key(telegram_id))


def _build_stash_session(character: Any, source: str) -> StashSession:
    rooms = _rooms_for(character.location)
    start = 0
    target = random.randrange(1, len(rooms))
    return StashSession(
        location=character.location,
        current_room=start,
        target_room=target,
        visited_rooms=[start],
        moves=0,
        steps=0,
        rad_gained=0,
        source=source,
    )


def stash_status_caption(session: StashSession, character: Any | None = None) -> str:
    rooms = _rooms_for(session.location)
    room = rooms[session.current_room] if session.current_room < len(rooms) else rooms[0]
    lines = [
        f"Поиск хабара — {session.location}",
        f"📍 {room.name}",
        f"Ход {session.moves}/{session.max_moves} · рад +{session.rad_gained}",
    ]
    if character is not None:
        lines.append(
            f"HP {character.health}/{effective_max_health(character)} · "
            f"☢ {character.radiation} · ⚡ {character.energy}"
        )
    lines.append("Ищи хабар в комнатах. Берегись мутантов и бандитов.")
    return "\n".join(lines)


def start_stash_hunt(storage: Storage, telegram_id: int, *, source: str = "found") -> ActionResult:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Сначала создай персонажа через /start.")
    if _is_dead(player):
        return ActionResult(False, _dead_block_text())
    blocked = travel_block_text(player)
    if blocked:
        return ActionResult(False, blocked)
    if is_traveling(player):
        return ActionResult(False, "Нельзя искать хабар в пути.")

    existing = get_stash_session(storage, telegram_id)
    if existing is not None and not existing.found:
        image = render_stash_frame(existing, player)
        return ActionResult(
            False,
            "У тебя уже идёт поиск хабара. Продолжай с карты.",
            payload={"stash_image": image, "stash_active": True, "caption": stash_status_caption(existing, player)},
        )

    session = _build_stash_session(player, source)
    save_stash_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = render_stash_frame(session, player)
    caption = stash_status_caption(session, player)
    if source == "buy":
        note = f"Координаты хабара куплены за {STASH_COORDINATE_PRICE} RU."
    else:
        note = "Ты нашёл координаты хабара! Ищи в комнатах."
    return ActionResult(
        True,
        note,
        payload={"stash_image": image, "stash_active": True, "caption": caption, "stash_started": True},
    )


def abandon_stash_hunt(storage: Storage, telegram_id: int) -> ActionResult:
    session = get_stash_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Активного поиска хабара нет.")
    clear_stash_session(storage, telegram_id)
    return ActionResult(
        True,
        f"Ты бросил поиск хабара на «{session.location}».\n"
        f"Ходов потрачено: {session.moves}, рад +{session.rad_gained}.",
        payload={"stash_active": False},
    )


def _roll_stash_loot(storage: Storage, telegram_id: int, location: str) -> list[str]:
    loot: list[str] = []
    if random.random() * 100 < STASH_CONSUMABLE_DROP_CHANCE:
        consumable = random.choice(STASH_CONSUMABLE_KEYS)
        if random.random() * 100 < STASH_CONSUMABLE_DROP_CHANCE_BY_KEY.get(consumable, 100):
            loot.append(consumable)
    gear_roll = random.random() * 100
    cumulative = 0.0
    for tier, chance in STASH_GEAR_TIER_CHANCES:
        cumulative += chance
        if gear_roll < cumulative:
            if random.random() < 0.5:
                pool = STASH_WEAPON_BY_TIER.get(tier, ())
            else:
                pool = STASH_ARMOR_BY_TIER.get(tier, ())
            if pool:
                loot.append(random.choice(pool))
            break
    if not loot:
        loot.append(random.choice(STASH_CONSUMABLE_KEYS))
    return loot


def _finish_stash_success(storage: Storage, telegram_id: int, session: StashSession) -> ActionResult:
    clear_stash_session(storage, telegram_id)
    loot_keys = _roll_stash_loot(storage, telegram_id, session.location)
    labels: list[str] = []
    for key in loot_keys:
        storage.add_item(telegram_id, key, 1)
        label = ITEM_LABELS.get(key, key)
        labels.append(f"{label} x1")
    storage.add_player_stat(telegram_id, "quests_completed", 1)
    loot_text = ", ".join(labels)
    return ActionResult(
        True,
        f"Хабар найден на «{session.location}»!\n"
        f"Содержимое: {loot_text}.\n"
        f"Ходов: {session.moves}, рад +{session.rad_gained}.",
        payload={"stash_active": False, "stash_done": True, "loot": loot_keys},
    )


def _try_ambush(storage: Storage, telegram_id: int, location: str) -> dict[str, Any] | None:
    chance = _ambush_chance(location)
    if random.random() * 100 >= chance:
        return None
    name, short, enemy_power = random.choice(AMBUSH_TYPES)
    character = storage.get_character(telegram_id, refresh_energy=False)
    if character is None:
        return None
    player_power = max(1, int(character.gear_power))
    if player_power >= enemy_power * 2:
        damage = random.randint(3, 8)
    elif player_power >= enemy_power:
        damage = random.randint(8, 18)
    else:
        damage = random.randint(15, 30)
    storage.change_health(telegram_id, -damage)
    survived = True
    updated = storage.get_character(telegram_id, refresh_energy=False)
    if updated is not None and updated.health <= 0:
        survived = False
    return {
        "name": name,
        "short": short,
        "damage": damage,
        "survived": survived,
    }


def _room_distance(rooms: list[RoomNode], start: int, goal: int) -> int:
    """BFS по графу комнат → кратчайшее количество переходов."""
    if start == goal:
        return 0
    visited: set[int] = {start}
    queue: list[int] = [start]
    dist = 0
    while queue:
        dist += 1
        nxt: list[int] = []
        for room_idx in queue:
            for door in rooms[room_idx].doors:
                if door == goal:
                    return dist
                if door not in visited:
                    visited.add(door)
                    nxt.append(door)
        queue = nxt
    return 99


def move_stash_hunt(storage: Storage, telegram_id: int, door_index: int) -> ActionResult:
    session = get_stash_session(storage, telegram_id)
    if session is None:
        return ActionResult(False, "Сначала начни поиск хабара.")
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        clear_stash_session(storage, telegram_id)
        return ActionResult(False, "Сначала создай персонажа.")
    if _is_dead(player):
        clear_stash_session(storage, telegram_id)
        return ActionResult(False, _dead_block_text())

    rooms = _rooms_for(session.location)
    room = rooms[session.current_room] if session.current_room < len(rooms) else rooms[0]
    if door_index < 0 or door_index >= len(room.doors):
        image = render_stash_frame(session, player)
        return ActionResult(
            False,
            "Такой двери нет.",
            payload={"stash_image": image, "stash_active": True, "caption": stash_status_caption(session, player)},
        )

    new_room = room.doors[door_index]
    session.current_room = new_room
    session.moves += 1
    session.steps += 1
    if new_room not in session.visited_rooms:
        session.visited_rooms.append(new_room)

    rad_add = 0
    if session.steps % STASH_RAD_EVERY_STEPS == 0:
        rad_add += STASH_RAD_PER_TICK
    if session.moves % STASH_MINUTE_MOVES == 0:
        rad_add += STASH_RAD_PER_MINUTE
    if rad_add > 0:
        storage.adjust_survival(telegram_id, radiation_delta=rad_add)
        session.rad_gained += rad_add

    ambush = _try_ambush(storage, telegram_id, session.location)
    if ambush is not None and not ambush["survived"]:
        clear_stash_session(storage, telegram_id)
        return ActionResult(
            False,
            f"На тебя напали — {ambush['name']}!\n"
            f"Урон: {ambush['damage']} HP. Ты погиб в Зоне.\n"
            "Респавн из инвентаря (мутанты обшарят рюкзак).",
            payload={"stash_active": False, "stash_dead": True},
        )

    if new_room == session.target_room:
        return _finish_stash_success(storage, telegram_id, session)

    if session.moves >= session.max_moves:
        clear_stash_session(storage, telegram_id)
        return ActionResult(
            False,
            f"Время поиска вышло на «{session.location}».\n"
            f"Хабар не найден. Рад +{session.rad_gained}.",
            payload={"stash_active": False, "stash_done": True},
        )

    save_stash_session(storage, telegram_id, session)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    image = render_stash_frame(session, player)

    dist = _room_distance(rooms, new_room, session.target_room)
    if dist <= 1:
        note = "Рядом! Хабар где-то совсем близко."
    elif dist <= 2:
        note = "Тёплый след… продолжай искать."
    elif dist <= 4:
        note = "Холодно. Хабар ещё далеко."
    else:
        note = "Очень далеко от хабара."
    if rad_add:
        note += f" Рад +{rad_add}."
    if ambush is not None:
        note += f" ⚠ Нападение: {ambush['name']}! Урон −{ambush['damage']} HP."

    return ActionResult(
        True,
        note,
        payload={
            "stash_image": image,
            "stash_active": True,
            "caption": stash_status_caption(session, player),
            "move_note": note,
        },
    )


# --- Rendering ---

_ROOM_VIEW_W = 660
_ROOM_VIEW_H = 660
_PANEL_W = 280
_MARGIN = 20


def _draw_minimap(
    canvas: Image.Image,
    rooms: list[RoomNode],
    session: StashSession,
    x0: int,
    y0: int,
    size: int,
) -> None:
    """Рисует мини-карту комнат: точки — комнаты, линии — двери с номерами."""
    import math

    n = len(rooms)
    if n == 0:
        return
    cx = x0 + size // 2
    cy = y0 + size // 2
    radius = size // 2 - 24

    positions: list[tuple[float, float]] = []
    for i in range(n):
        angle = 2 * math.pi * i / n - math.pi / 2
        px = cx + radius * math.cos(angle)
        py = cy + radius * math.sin(angle)
        positions.append((px, py))

    draw = ImageDraw.Draw(canvas)

    # Затемнённый фон мини-карты
    draw.rounded_rectangle(
        (x0, y0, x0 + size, y0 + size),
        radius=10,
        fill=(20, 22, 26, 220),
        outline=(60, 64, 70),
        width=1,
    )

    mm_font = _load_font(10)

    # Линии дверей с номерами
    for i, room in enumerate(rooms):
        for di, door in enumerate(room.doors):
            if door <= i:
                continue
            x1, y1 = positions[i]
            x2, y2 = positions[door]
            visited = i in session.visited_rooms and door in session.visited_rooms
            is_current_edge = i == session.current_room or door == session.current_room
            if is_current_edge:
                color = (120, 200, 100, 230)
                width = 3
            elif visited:
                color = (90, 110, 80, 200)
                width = 2
            else:
                color = (50, 52, 56, 150)
                width = 1
            draw.line((x1, y1, x2, y2), fill=color, width=width)

            # Номер двери на середине линии (только для дверей текущей комнаты)
            if is_current_edge:
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2
                badge_r = 9
                draw.ellipse(
                    (mid_x - badge_r, mid_y - badge_r, mid_x + badge_r, mid_y + badge_r),
                    fill=(60, 90, 50, 240),
                    outline=(120, 200, 100),
                    width=1,
                )
                num_text = str(di + 1)
                num_w = draw.textlength(num_text, font=mm_font)
                draw.text(
                    (mid_x - num_w / 2, mid_y - 5),
                    num_text,
                    fill=(220, 255, 200),
                    font=mm_font,
                )

    # Точки комнат
    for i, (px, py) in enumerate(positions):
        is_current = i == session.current_room
        is_target = i == session.target_room
        is_visited = i in session.visited_rooms
        if is_current:
            r = 10
            draw.ellipse((px - r, py - r, px + r, py + r), fill=(72, 220, 90), outline=(40, 120, 50), width=2)
        elif is_target and is_visited:
            r = 8
            draw.ellipse((px - r, py - r, px + r, py + r), fill=(255, 200, 50), outline=(200, 150, 30), width=2)
        elif is_visited:
            r = 7
            draw.ellipse((px - r, py - r, px + r, py + r), fill=(120, 130, 100), outline=(80, 85, 70), width=1)
        else:
            r = 5
            draw.ellipse((px - r, py - r, px + r, py + r), fill=(60, 62, 66), outline=(90, 92, 96), width=1)

    # Заголовок мини-карты
    title_font = _load_font(11)
    draw.text((x0 + 8, y0 + 4), "Карта", fill=(180, 180, 180), font=title_font)


def render_stash_frame(session: StashSession, character: Any | None = None) -> bytes:
    """Кадр поиска хабара: вид комнаты + мини-карта + панель."""
    rooms = _rooms_for(session.location)
    room = rooms[session.current_room] if session.current_room < len(rooms) else rooms[0]

    view_w = _ROOM_VIEW_W
    view_h = _ROOM_VIEW_H
    panel_w = _PANEL_W
    margin = _MARGIN
    width = margin + view_w + 16 + panel_w + margin
    height = max(margin + view_h + margin, 720)
    canvas = Image.new("RGBA", (width, height), (16, 18, 20, 255))
    draw = ImageDraw.Draw(canvas)

    # Рамка вокруг вида комнаты
    field = (margin - 6, margin - 6, margin + view_w + 6, margin + view_h + 6)
    draw.rounded_rectangle(field, radius=10, fill=(34, 36, 40, 255), outline=(70, 74, 80), width=2)

    # Фон локации
    loc_bg = _load_location_thumb(session.location)
    if loc_bg is not None:
        field_img = _cover_crop(loc_bg, view_w, view_h).convert("RGBA")
        field_img.putalpha(210)
        canvas.paste(field_img, (margin, margin), field_img)
    else:
        draw.rectangle((margin, margin, margin + view_w - 1, margin + view_h - 1), fill=(28, 30, 34))

    # Затемнение
    overlay = Image.new("RGBA", (view_w, view_h), (0, 0, 0, 80))
    canvas.alpha_composite(overlay, (margin, margin))

    draw = ImageDraw.Draw(canvas)

    # Название комнаты
    title_font = _load_font(26)
    body_font = _load_font(17)
    small_font = _load_font(14)
    loc_font = title_font if len(session.location) <= 14 else _load_font(20)

    # Плашка с названием комнаты
    name_box = (margin + 16, margin + 16, margin + view_w - 16, margin + 60)
    draw.rounded_rectangle(name_box, radius=8, fill=(0, 0, 0, 180), outline=(80, 84, 90), width=1)
    draw.text((margin + 24, margin + 22), f"📍 {room.name}", fill=(245, 245, 245), font=title_font)

    # Описание комнаты
    desc_box = (margin + 16, margin + 72, margin + view_w - 16, margin + 120)
    draw.rounded_rectangle(desc_box, radius=8, fill=(0, 0, 0, 160), outline=(60, 64, 70), width=1)
    # Перенос описания
    words = room.desc.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=body_font) > view_w - 48:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    for li, line in enumerate(lines[:3]):
        draw.text((margin + 24, margin + 80 + li * 18), line, fill=(200, 200, 200), font=body_font)

    # Двери — метки на стенах комнаты с номерами
    door_count = len(room.doors)
    door_font = _load_font(20)
    door_label_font = _load_font(13)

    # Раскладываем двери по четырём стенкам: top, right, bottom, left
    wall_positions = [
        ("top", view_w // 2, 0),
        ("right", view_w, view_h // 2),
        ("bottom", view_w // 2, view_h),
        ("left", 0, view_h // 2),
    ]

    for di, target_idx in enumerate(room.doors):
        target_room = rooms[target_idx] if target_idx < len(rooms) else None
        target_name = target_room.name if target_room else f"Дверь {di + 1}"
        visited = target_idx in session.visited_rooms

        wall, wx, wy = wall_positions[di % 4]
        badge_d = 46
        badge_r = badge_d // 2

        if wall == "top":
            bx = margin + wx - badge_r
            by = margin + 6
        elif wall == "right":
            bx = margin + view_w - badge_d - 6
            by = margin + wy - badge_r
        elif wall == "bottom":
            bx = margin + wx - badge_r
            by = margin + view_h - badge_d - 6
        else:  # left
            bx = margin + 6
            by = margin + wy - badge_r

        bg_color = (50, 70, 45, 235) if not visited else (35, 50, 35, 235)
        border_color = (120, 200, 100) if not visited else (80, 120, 70)

        # Тень/контур дверного проёма
        draw.rounded_rectangle(
            (bx, by, bx + badge_d, by + badge_d),
            radius=10,
            fill=bg_color,
            outline=border_color,
            width=3,
        )

        # Иконка двери
        door_icon_y = by + 6
        draw.text(
            (bx + badge_d / 2 - 10, door_icon_y),
            "🚪",
            fill=(255, 255, 255),
            font=_load_font(16),
        )

        # Номер двери крупно
        num_text = str(di + 1)
        num_w = draw.textlength(num_text, font=door_font)
        draw.text(
            (bx + (badge_d - num_w) / 2, by + 20),
            num_text,
            fill=(220, 255, 200),
            font=door_font,
        )

        # Подсказка о посещении
        if visited:
            tag = "✓ осмотр."
            tag_w = draw.textlength(tag, font=door_label_font)
            draw.text(
                (bx + (badge_d - tag_w) / 2, by + badge_d - 14),
                tag,
                fill=(160, 180, 140),
                font=door_label_font,
            )

    # Мини-карта в правом нижнем углу
    mm_size = 150
    _draw_minimap(
        canvas,
        rooms,
        session,
        margin + view_w - mm_size - 16,
        margin + view_h - mm_size - 16,
        mm_size,
    )

    # Легенда дверей в левом нижнем углу
    legend_x = margin + 16
    legend_y = margin + view_h - 16 - max(door_count * 18, 36)
    legend_box = (legend_x, legend_y, legend_x + 230, margin + view_h - 16)
    draw.rounded_rectangle(legend_box, radius=8, fill=(0, 0, 0, 180), outline=(60, 64, 70), width=1)
    draw.text((legend_x + 10, legend_y + 6), "Двери:", fill=(200, 200, 200), font=small_font)
    for di, target_idx in enumerate(room.doors):
        target_room = rooms[target_idx] if target_idx < len(rooms) else None
        target_name = target_room.name if target_room else f"Дверь {di + 1}"
        visited = target_idx in session.visited_rooms
        line_y = legend_y + 22 + di * 18
        draw.text((legend_x + 10, line_y), f"{di + 1}.", fill=(120, 200, 100), font=small_font)
        color = (160, 180, 140) if visited else (200, 220, 180)
        draw.text((legend_x + 32, line_y), target_name, fill=color, font=small_font)

    # --- Боковая панель ---
    pl = margin + view_w + 16
    pr = width - margin
    pt = margin - 6
    pb = height - margin + 6
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((pl, pt, pr, pb), radius=14, fill=(48, 50, 54, 255), outline=(100, 104, 110), width=2)

    # Миниатюра локации
    thumb = (pl + 12, pt + 10, pr - 12, pt + 100)
    loc_img = _load_location_thumb(session.location)
    if loc_img is not None:
        _paste_rounded(canvas, loc_img, thumb, radius=8)
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=8, outline=(110, 120, 100), width=2)
    else:
        ImageDraw.Draw(canvas).rounded_rectangle(thumb, radius=8, fill=(30, 34, 28), outline=(90, 100, 80), width=2)

    draw.text((pl + 14, pt + 106), session.location, fill=(245, 245, 245), font=loc_font)
    draw.text((pl + 14, pt + 132), "Поиск хабара", fill=(200, 180, 120), font=body_font)

    info_y = pt + 162
    draw.text((pl + 14, info_y), f"Ход {session.moves}/{session.max_moves}", fill=(200, 200, 200), font=body_font)
    draw.text((pl + 14, info_y + 24), f"Рад +{session.rad_gained}", fill=(200, 160, 120), font=small_font)

    dist = _room_distance(rooms, session.current_room, session.target_room)
    if dist <= 1:
        hint = "🔥 Хабар очень близко!"
    elif dist <= 2:
        hint = "🌡 Тёплый след"
    elif dist <= 4:
        hint = "❄ Холодно"
    else:
        hint = "🧊 Очень далеко"
    draw.text((pl + 14, info_y + 48), hint, fill=(220, 220, 200), font=small_font)

    # Сложность локации
    diff = LOCATION_DIFFICULTY.get(session.location, "easy")
    diff_labels = {"easy": "🟢 Лёгкая", "hard": "🟡 Опасная", "hardcore": "🔴 Смертельная"}
    draw.text((pl + 14, info_y + 70), diff_labels.get(diff, diff), fill=(220, 220, 200), font=small_font)

    hp = int(character.health) if character else 0
    max_hp = int(effective_max_health(character)) if character else 100
    energy = int(character.energy) if character else 0
    max_energy = int(character.max_energy) if character else 100
    rad = int(character.radiation) if character else 0

    bar_top = info_y + 100
    draw.rounded_rectangle((pl + 12, bar_top, pr - 12, bar_top + 24), radius=6, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 36) * (hp / max(1, max_hp)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 14, bar_top + 2, pl + 14 + fill_w, bar_top + 22), radius=4, fill=(200, 60, 50))
    draw.text((pl + 16, bar_top + 4), f"HP {hp}/{max_hp}", fill=(255, 255, 255), font=small_font)

    draw.rounded_rectangle((pl + 12, bar_top + 34, pr - 12, bar_top + 58), radius=6, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 36) * min(1.0, rad / 100))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 14, bar_top + 36, pl + 14 + fill_w, bar_top + 56), radius=4, fill=(180, 200, 40))
    draw.text((pl + 16, bar_top + 38), f"RAD {rad}", fill=(255, 255, 255), font=small_font)

    draw.rounded_rectangle((pl + 12, bar_top + 68, pr - 12, bar_top + 92), radius=6, fill=(30, 30, 34), outline=(90, 90, 95))
    fill_w = int((pr - pl - 36) * (energy / max(1, max_energy)))
    if fill_w > 0:
        draw.rounded_rectangle((pl + 14, bar_top + 70, pl + 14 + fill_w, bar_top + 90), radius=4, fill=(50, 120, 210))
    draw.text((pl + 16, bar_top + 72), f"EN {energy}/{max_energy}", fill=(255, 255, 255), font=small_font)

    draw.text((pl + 14, pb - 42), "Выбирай дверь для перехода", fill=(210, 210, 210), font=small_font)
    draw.text((pl + 14, pb - 24), "Кнопка — уйти, обновить — перекадр", fill=(190, 190, 190), font=small_font)

    out = canvas.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def try_random_stash_coordinates(storage: Storage, telegram_id: int) -> bool:
    """Small chance to find stash coordinates during normal play (called from hunt)."""
    if random.random() * 100 < 3:
        existing = get_stash_session(storage, telegram_id)
        if existing is None or existing.found:
            session = _build_stash_session(
                storage.get_character(telegram_id, refresh_energy=False),
                "found",
            )
            save_stash_session(storage, telegram_id, session)
            return True
    return False
