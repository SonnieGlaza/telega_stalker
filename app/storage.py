from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENERGY_REGEN_PER_MINUTE = 2
BASE_LOCATION_NPC_POWER = 100
REGULAR_LOCATION_NPC_POWER = 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_player_uid(telegram_id: int) -> str:
    return f"STK-{telegram_id}"


@dataclass
class Character:
    telegram_id: int
    player_uid: str
    avatar_style: str
    nickname: str
    gender: str
    faction: str | None
    money: int
    energy: int
    max_energy: int
    health: int
    gear_power: int
    location: str
    inventory: dict[str, int]
    equipment: dict[str, Any]
    truck_owned: bool
    sleeping_bag_owned: bool
    fuel: int
    energy_updated_at: datetime
    radiation: int
    hunger: int
    thirst: int
    needs_updated_at: datetime
    survival_damage_at: datetime


SURVIVAL_HOURLY_GAIN = 1
SURVIVAL_DAMAGE_PER_TICK = 10
SURVIVAL_DAMAGE_TICK_MINUTES = 30


class Storage:
    def __init__(self, db_path: str, snapshot_path: str | None = None) -> None:
        self.db_path = db_path
        db_parent = Path(db_path).parent
        db_parent.mkdir(parents=True, exist_ok=True)
        if snapshot_path:
            self.snapshot_path = Path(snapshot_path)
        else:
            self.snapshot_path = Path(db_path).with_suffix(".backup.json")
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _write_snapshot(self) -> None:
        try:
            with self._connect() as conn:
                characters = [dict(row) for row in conn.execute("SELECT * FROM characters").fetchall()]
                factions = [dict(row) for row in conn.execute("SELECT * FROM factions").fetchall()]
                locations = [dict(row) for row in conn.execute("SELECT * FROM locations").fetchall()]
                alliances = [dict(row) for row in conn.execute("SELECT * FROM alliances").fetchall()]
                alliance_requests = [dict(row) for row in conn.execute("SELECT * FROM alliance_requests").fetchall()]
                topup_payments = [dict(row) for row in conn.execute("SELECT * FROM topup_payments").fetchall()]
                faction_warehouse = [dict(row) for row in conn.execute("SELECT * FROM faction_warehouse").fetchall()]
                auctions = [dict(row) for row in conn.execute("SELECT * FROM auctions").fetchall()]
                raids = [dict(row) for row in conn.execute("SELECT * FROM raids").fetchall()]
                raid_members = [dict(row) for row in conn.execute("SELECT * FROM raid_members").fetchall()]
                war_lobbies = [dict(row) for row in conn.execute("SELECT * FROM war_lobbies").fetchall()]
                war_lobby_members = [
                    dict(row) for row in conn.execute("SELECT * FROM war_lobby_members").fetchall()
                ]
                map_events = [dict(row) for row in conn.execute("SELECT * FROM map_events").fetchall()]
                player_stats = [dict(row) for row in conn.execute("SELECT * FROM player_stats").fetchall()]
                player_achievements = [
                    dict(row) for row in conn.execute("SELECT * FROM player_achievements").fetchall()
                ]
            payload = {
                "version": 2,
                "characters": characters,
                "factions": factions,
                "locations": locations,
                "alliances": alliances,
                "alliance_requests": alliance_requests,
                "topup_payments": topup_payments,
                "faction_warehouse": faction_warehouse,
                "auctions": auctions,
                "raids": raids,
                "raid_members": raid_members,
                "war_lobbies": war_lobbies,
                "war_lobby_members": war_lobby_members,
                "map_events": map_events,
                "player_stats": player_stats,
                "player_achievements": player_achievements,
            }
            self.snapshot_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # Не ломаем игру, если в окружении временно нет прав на запись backup-файла.
            return

    def _restore_from_snapshot_if_needed(self, conn: sqlite3.Connection) -> None:
        count_row = conn.execute("SELECT COUNT(*) AS cnt FROM characters").fetchone()
        existing_count = int(count_row["cnt"]) if count_row else 0
        if existing_count > 0:
            return
        if not self.snapshot_path.exists():
            return
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        characters = payload.get("characters") or []
        factions = payload.get("factions") or []
        locations = payload.get("locations") or []
        alliances = payload.get("alliances") or []
        alliance_requests = payload.get("alliance_requests") or []
        topup_payments = payload.get("topup_payments") or []
        faction_warehouse = payload.get("faction_warehouse") or []
        auctions = payload.get("auctions") or []
        raids = payload.get("raids") or []
        raid_members = payload.get("raid_members") or []
        war_lobbies = payload.get("war_lobbies") or []
        war_lobby_members = payload.get("war_lobby_members") or []
        map_events = payload.get("map_events") or []
        player_stats = payload.get("player_stats") or []
        player_achievements = payload.get("player_achievements") or []
        if not characters:
            return

        for row in factions:
            conn.execute(
                """
                INSERT OR REPLACE INTO factions(name, treasury, leader_id)
                VALUES(?, ?, ?)
                """,
                (
                    row.get("name"),
                    int(row.get("treasury", 0)),
                    row.get("leader_id"),
                ),
            )
        for row in locations:
            conn.execute(
                """
                INSERT OR REPLACE INTO locations(name, point_type, controlled_by, npc_power)
                VALUES(?, ?, ?, ?)
                """,
                (
                    row.get("name"),
                    row.get("point_type"),
                    row.get("controlled_by"),
                    int(row.get("npc_power", REGULAR_LOCATION_NPC_POWER)),
                ),
            )
        for row in alliances:
            conn.execute(
                """
                INSERT OR IGNORE INTO alliances(faction_a, faction_b, created_at)
                VALUES(?, ?, ?)
                """,
                (
                    row.get("faction_a"),
                    row.get("faction_b"),
                    row.get("created_at") or utc_now().isoformat(),
                ),
            )
        for row in alliance_requests:
            conn.execute(
                """
                INSERT OR IGNORE INTO alliance_requests(requester_faction, target_faction, proposed_by, created_at)
                VALUES(?, ?, ?, ?)
                """,
                (
                    row.get("requester_faction"),
                    row.get("target_faction"),
                    row.get("proposed_by"),
                    row.get("created_at") or utc_now().isoformat(),
                ),
            )
        for row in characters:
            conn.execute(
                """
                INSERT OR REPLACE INTO characters(
                    telegram_id, player_uid, avatar_style, nickname, gender, faction, money,
                    energy, max_energy, energy_updated_at, health, gear_power, location,
                    inventory_json, equipment_json, truck_owned, fuel
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row.get("telegram_id")),
                    row.get("player_uid") or build_player_uid(int(row.get("telegram_id"))),
                    row.get("avatar_style") or "classic",
                    row.get("nickname") or "Сталкер",
                    row.get("gender") or "Мужской",
                    row.get("faction"),
                    int(row.get("money", 1000)),
                    int(row.get("energy", 100)),
                    int(row.get("max_energy", 100)),
                    row.get("energy_updated_at") or utc_now().isoformat(),
                    int(row.get("health", 100)),
                    int(row.get("gear_power", 2)),
                    row.get("location") or "База новичков",
                    row.get("inventory_json") or "{}",
                    row.get("equipment_json") or '{"weapon":"Нож","armor":"Куртка новичка"}',
                    int(row.get("truck_owned", 0)),
                    int(row.get("fuel", 0)),
                ),
            )
        for row in topup_payments:
            conn.execute(
                """
                INSERT OR REPLACE INTO topup_payments(
                    payment_charge_id, telegram_id, stars_amount, ru_amount, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row.get("payment_charge_id"),
                    int(row.get("telegram_id")),
                    int(row.get("stars_amount", 0)),
                    int(row.get("ru_amount", 0)),
                    row.get("created_at") or utc_now().isoformat(),
                ),
            )
        for row in faction_warehouse:
            conn.execute(
                """
                INSERT OR REPLACE INTO faction_warehouse(faction, item_key, amount)
                VALUES(?, ?, ?)
                """,
                (
                    row.get("faction"),
                    row.get("item_key"),
                    int(row.get("amount", 0)),
                ),
            )
        for row in auctions:
            conn.execute(
                """
                INSERT OR REPLACE INTO auctions(
                    id, seller_id, faction, item_key, amount, price, status, buyer_id, created_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row.get("id")),
                    int(row.get("seller_id")),
                    row.get("faction"),
                    row.get("item_key"),
                    int(row.get("amount", 1)),
                    int(row.get("price", 0)),
                    row.get("status") or "open",
                    row.get("buyer_id"),
                    row.get("created_at") or utc_now().isoformat(),
                    row.get("closed_at"),
                ),
            )
        for row in raids:
            conn.execute(
                """
                INSERT OR REPLACE INTO raids(
                    id, faction, location, leader_id, status, created_at, started_at, finished_at, result_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row.get("id")),
                    row.get("faction"),
                    row.get("location"),
                    int(row.get("leader_id")),
                    row.get("status") or "open",
                    row.get("created_at") or utc_now().isoformat(),
                    row.get("started_at"),
                    row.get("finished_at"),
                    row.get("result_text"),
                ),
            )
        for row in raid_members:
            conn.execute(
                """
                INSERT OR REPLACE INTO raid_members(raid_id, telegram_id, joined_at)
                VALUES(?, ?, ?)
                """,
                (
                    int(row.get("raid_id")),
                    int(row.get("telegram_id")),
                    row.get("joined_at") or utc_now().isoformat(),
                ),
            )
        for row in war_lobbies:
            conn.execute(
                """
                INSERT OR REPLACE INTO war_lobbies(
                    id, host_faction, location, leader_id, status, created_at, started_at, finished_at, result_text
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row.get("id")),
                    row.get("host_faction"),
                    row.get("location"),
                    int(row.get("leader_id")),
                    row.get("status") or "open",
                    row.get("created_at") or utc_now().isoformat(),
                    row.get("started_at"),
                    row.get("finished_at"),
                    row.get("result_text"),
                ),
            )
        for row in war_lobby_members:
            conn.execute(
                """
                INSERT OR REPLACE INTO war_lobby_members(war_id, telegram_id, joined_at)
                VALUES(?, ?, ?)
                """,
                (
                    int(row.get("war_id")),
                    int(row.get("telegram_id")),
                    row.get("joined_at") or utc_now().isoformat(),
                ),
            )
        for row in map_events:
            conn.execute(
                """
                INSERT OR REPLACE INTO map_events(
                    location, event_type, modifier, description, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("location"),
                    row.get("event_type"),
                    int(row.get("modifier", 0)),
                    row.get("description") or "",
                    row.get("expires_at") or utc_now().isoformat(),
                    row.get("updated_at") or utc_now().isoformat(),
                ),
            )
        for row in player_stats:
            conn.execute(
                """
                INSERT OR REPLACE INTO player_stats(
                    telegram_id, quests_completed, quests_failed, raids_completed, raids_failed,
                    wars_won, smuggling_success, trades_done, money_earned, rating_points,
                    achievements_unlocked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row.get("telegram_id")),
                    int(row.get("quests_completed", 0)),
                    int(row.get("quests_failed", 0)),
                    int(row.get("raids_completed", 0)),
                    int(row.get("raids_failed", 0)),
                    int(row.get("wars_won", 0)),
                    int(row.get("smuggling_success", 0)),
                    int(row.get("trades_done", 0)),
                    int(row.get("money_earned", 0)),
                    int(row.get("rating_points", 0)),
                    int(row.get("achievements_unlocked", 0)),
                ),
            )
        for row in player_achievements:
            conn.execute(
                """
                INSERT OR REPLACE INTO player_achievements(
                    telegram_id, achievement_key, unlocked_at
                ) VALUES (?, ?, ?)
                """,
                (
                    int(row.get("telegram_id")),
                    row.get("achievement_key"),
                    row.get("unlocked_at") or utc_now().isoformat(),
                ),
            )

    def save_snapshot(self) -> None:
        self._write_snapshot()

    def restore_from_snapshot(self) -> None:
        with self._connect() as conn:
            self._restore_from_snapshot_if_needed(conn)

    # Backward-compatible alias for older bot startup code.
    def restore_from_snapshot_if_empty(self) -> None:
        self.restore_from_snapshot()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    telegram_id INTEGER PRIMARY KEY,
                    player_uid TEXT UNIQUE,
                    avatar_style TEXT NOT NULL DEFAULT 'classic',
                    nickname TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    faction TEXT,
                    money INTEGER NOT NULL DEFAULT 1000,
                    energy INTEGER NOT NULL DEFAULT 100,
                    max_energy INTEGER NOT NULL DEFAULT 100,
                    energy_updated_at TEXT NOT NULL,
                    health INTEGER NOT NULL DEFAULT 100,
                    gear_power INTEGER NOT NULL DEFAULT 2,
                    location TEXT NOT NULL DEFAULT 'База новичков',
                    inventory_json TEXT NOT NULL DEFAULT '{}',
                    equipment_json TEXT NOT NULL DEFAULT '{"weapon":"Нож","armor":"Куртка новичка","weapon_durability":100,"armor_durability":100}',
                    truck_owned INTEGER NOT NULL DEFAULT 0,
                    sleeping_bag_owned INTEGER NOT NULL DEFAULT 0,
                    fuel INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._ensure_characters_schema(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS factions (
                    name TEXT PRIMARY KEY,
                    treasury INTEGER NOT NULL DEFAULT 20000,
                    leader_id INTEGER
                )
                """
            )
            columns = conn.execute("PRAGMA table_info(factions)").fetchall()
            column_names = {str(row["name"]) for row in columns}
            if "leader_id" not in column_names:
                conn.execute("ALTER TABLE factions ADD COLUMN leader_id INTEGER")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS locations (
                    name TEXT PRIMARY KEY,
                    point_type TEXT NOT NULL,
                    controlled_by TEXT,
                    npc_power INTEGER NOT NULL DEFAULT 60
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alliance_requests (
                    requester_faction TEXT NOT NULL,
                    target_faction TEXT NOT NULL,
                    proposed_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(requester_faction, target_faction)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alliances (
                    faction_a TEXT NOT NULL,
                    faction_b TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(faction_a, faction_b)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topup_payments (
                    payment_charge_id TEXT PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    stars_amount INTEGER NOT NULL,
                    ru_amount INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faction_warehouse (
                    faction TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(faction, item_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auctions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL,
                    faction TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    buyer_id INTEGER,
                    created_at TEXT NOT NULL,
                    closed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raids (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    faction TEXT NOT NULL,
                    location TEXT NOT NULL,
                    leader_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_text TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raid_members (
                    raid_id INTEGER NOT NULL,
                    telegram_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY(raid_id, telegram_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS war_lobbies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host_faction TEXT NOT NULL,
                    location TEXT NOT NULL,
                    leader_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_text TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS war_lobby_members (
                    war_id INTEGER NOT NULL,
                    telegram_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY(war_id, telegram_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS map_events (
                    location TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    modifier INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_stats (
                    telegram_id INTEGER PRIMARY KEY,
                    quests_completed INTEGER NOT NULL DEFAULT 0,
                    quests_failed INTEGER NOT NULL DEFAULT 0,
                    raids_completed INTEGER NOT NULL DEFAULT 0,
                    raids_failed INTEGER NOT NULL DEFAULT 0,
                    wars_won INTEGER NOT NULL DEFAULT 0,
                    smuggling_success INTEGER NOT NULL DEFAULT 0,
                    trades_done INTEGER NOT NULL DEFAULT 0,
                    money_earned INTEGER NOT NULL DEFAULT 0,
                    rating_points INTEGER NOT NULL DEFAULT 0,
                    achievements_unlocked INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_achievements (
                    telegram_id INTEGER NOT NULL,
                    achievement_key TEXT NOT NULL,
                    unlocked_at TEXT NOT NULL,
                    PRIMARY KEY(telegram_id, achievement_key)
                )
                """
            )
            conn.executemany(
                "INSERT OR IGNORE INTO factions(name, treasury, leader_id) VALUES(?, ?, NULL)",
                [
                    ("Долг", 20000),
                    ("Свобода", 20000),
                    ("Нейтралы", 20000),
                    ("Бандиты", 20000),
                ],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO locations(name, point_type, controlled_by, npc_power) VALUES(?, ?, ?, ?)",
                [
                    ("Росток", "база", "Долг", BASE_LOCATION_NPC_POWER),
                    ("Кордон", "база", "Нейтралы", BASE_LOCATION_NPC_POWER),
                    ("Армейские склады", "база", "Свобода", BASE_LOCATION_NPC_POWER),
                    ("Янтарь", "точка ресурсов", None, REGULAR_LOCATION_NPC_POWER),
                    ("Свалка", "база", "Бандиты", BASE_LOCATION_NPC_POWER),
                    ("Болото", "точка ресурсов", None, REGULAR_LOCATION_NPC_POWER),
                    ("НИИ Агропром", "точка интереса", None, REGULAR_LOCATION_NPC_POWER),
                    ("Темная долина", "точка интереса", None, REGULAR_LOCATION_NPC_POWER),
                    ("Рыжий лес", "точка интереса", None, REGULAR_LOCATION_NPC_POWER),
                    ("Радар", "точка интереса", None, REGULAR_LOCATION_NPC_POWER),
                ],
            )
            # Для существующих БД фиксируем базовые владельцы и типы ключевых точек.
            conn.execute(
                "UPDATE locations SET point_type = 'база', controlled_by = 'Нейтралы' WHERE name = 'Кордон'"
            )
            conn.execute(
                "UPDATE locations SET point_type = 'база', controlled_by = 'Бандиты' WHERE name = 'Свалка'"
            )
            self._restore_from_snapshot_if_needed(conn)
            self._enforce_location_power_baseline(conn)
            self._ensure_player_stats_rows(conn)

    def create_character(self, telegram_id: int, nickname: str, gender: str) -> None:
        player_uid = build_player_uid(telegram_id)
        now_iso = utc_now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO characters(
                    telegram_id, player_uid, nickname, gender, energy_updated_at, needs_updated_at, survival_damage_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    nickname = excluded.nickname,
                    gender = excluded.gender
                """,
                (telegram_id, player_uid, nickname, gender, now_iso, now_iso, now_iso),
            )
            self._ensure_player_stats_row(conn, telegram_id)
        self.save_snapshot()

    def get_character(self, telegram_id: int, refresh_energy: bool = True) -> Character | None:
        if refresh_energy:
            self.recover_energy(telegram_id)
            self.refresh_survival(telegram_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM characters WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_character(row)

    def character_exists(self, telegram_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM characters WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        return row is not None

    def set_faction(self, telegram_id: int, faction: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET faction = ? WHERE telegram_id = ?",
                (faction, telegram_id),
            )
        self.save_snapshot()

    def set_location(self, telegram_id: int, location: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET location = ? WHERE telegram_id = ?",
                (location, telegram_id),
            )
        self.save_snapshot()

    def spend_energy(self, telegram_id: int, amount: int) -> bool:
        character = self.get_character(telegram_id, refresh_energy=True)
        if character is None or character.energy < amount:
            return False
        new_energy = character.energy - amount
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE characters
                SET energy = ?, energy_updated_at = ?
                WHERE telegram_id = ?
                """,
                (new_energy, utc_now().isoformat(), telegram_id),
            )
        self.save_snapshot()
        return True

    def restore_energy(self, telegram_id: int, amount: int) -> None:
        character = self.get_character(telegram_id, refresh_energy=True)
        if character is None:
            return
        new_energy = min(character.max_energy, character.energy + amount)
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET energy = ?, energy_updated_at = ? WHERE telegram_id = ?",
                (new_energy, utc_now().isoformat(), telegram_id),
            )
        self.save_snapshot()

    def refresh_survival(self, telegram_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT radiation, hunger, thirst, health, needs_updated_at, survival_damage_at
                FROM characters
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            if row is None:
                return
            now = utc_now()
            needs_updated_at = datetime.fromisoformat(row["needs_updated_at"])
            survival_damage_at = datetime.fromisoformat(row["survival_damage_at"])
            radiation = int(row["radiation"])
            hunger = int(row["hunger"])
            thirst = int(row["thirst"])
            health = int(row["health"])

            hours_passed = int((now - needs_updated_at).total_seconds() // 3600)
            if hours_passed > 0:
                hunger = min(200, hunger + hours_passed * SURVIVAL_HOURLY_GAIN)
                thirst = min(200, thirst + hours_passed * SURVIVAL_HOURLY_GAIN)
                needs_updated_at = now

            if hunger >= 100 or thirst >= 100:
                ticks = int((now - survival_damage_at).total_seconds() // (SURVIVAL_DAMAGE_TICK_MINUTES * 60))
                if ticks > 0:
                    health = max(0, health - ticks * SURVIVAL_DAMAGE_PER_TICK)
                    survival_damage_at = now
            else:
                survival_damage_at = now

            conn.execute(
                """
                UPDATE characters
                SET radiation = ?, hunger = ?, thirst = ?, health = ?, needs_updated_at = ?, survival_damage_at = ?
                WHERE telegram_id = ?
                """,
                (
                    max(0, min(200, radiation)),
                    max(0, min(200, hunger)),
                    max(0, min(200, thirst)),
                    max(0, min(100, health)),
                    needs_updated_at.isoformat(),
                    survival_damage_at.isoformat(),
                    telegram_id,
                ),
            )

    def adjust_survival(
        self,
        telegram_id: int,
        radiation_delta: int = 0,
        hunger_delta: int = 0,
        thirst_delta: int = 0,
        health_delta: int = 0,
    ) -> bool:
        self.refresh_survival(telegram_id)
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return False
        new_radiation = max(0, min(200, character.radiation + radiation_delta))
        new_hunger = max(0, min(200, character.hunger + hunger_delta))
        new_thirst = max(0, min(200, character.thirst + thirst_delta))
        new_health = max(0, min(100, character.health + health_delta))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE characters
                SET radiation = ?, hunger = ?, thirst = ?, health = ?, needs_updated_at = ?, survival_damage_at = ?
                WHERE telegram_id = ?
                """,
                (
                    new_radiation,
                    new_hunger,
                    new_thirst,
                    new_health,
                    utc_now().isoformat(),
                    utc_now().isoformat(),
                    telegram_id,
                ),
            )
        self.save_snapshot()
        return True

    def recover_energy(self, telegram_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT energy, max_energy, energy_updated_at, sleeping_bag_owned
                FROM characters
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            if row is None:
                return

            energy = int(row["energy"])
            max_energy = int(row["max_energy"])
            last_update = datetime.fromisoformat(row["energy_updated_at"])
            minutes_passed = int((utc_now() - last_update).total_seconds() // 60)
            if minutes_passed <= 0:
                return

            regen_per_minute = ENERGY_REGEN_PER_MINUTE * (2 if int(row["sleeping_bag_owned"]) == 1 else 1)
            gained = minutes_passed * regen_per_minute
            new_energy = min(max_energy, energy + gained)
            conn.execute(
                """
                UPDATE characters
                SET energy = ?, energy_updated_at = ?
                WHERE telegram_id = ?
                """,
                (new_energy, utc_now().isoformat(), telegram_id),
            )

    def change_money(self, telegram_id: int, delta: int) -> bool:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return False
        new_money = character.money + delta
        if new_money < 0:
            return False
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET money = ? WHERE telegram_id = ?",
                (new_money, telegram_id),
            )
        self.save_snapshot()
        return True

    def change_gear_power(self, telegram_id: int, delta: int) -> None:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return
        new_power = max(1, character.gear_power + delta)
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET gear_power = ? WHERE telegram_id = ?",
                (new_power, telegram_id),
            )
        self.save_snapshot()

    def add_item(self, telegram_id: int, item_key: str, amount: int = 1) -> None:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return
        inventory = dict(character.inventory)
        inventory[item_key] = inventory.get(item_key, 0) + amount
        self._set_inventory(telegram_id, inventory)
        self.save_snapshot()

    def remove_item(self, telegram_id: int, item_key: str, amount: int = 1) -> bool:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return False
        inventory = dict(character.inventory)
        owned = inventory.get(item_key, 0)
        if owned < amount:
            return False
        new_amount = owned - amount
        if new_amount <= 0:
            inventory.pop(item_key, None)
        else:
            inventory[item_key] = new_amount
        self._set_inventory(telegram_id, inventory)
        self.save_snapshot()
        return True

    def set_equipment_item(self, telegram_id: int, slot: str, value: Any) -> None:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return
        equipment = dict(character.equipment)
        equipment[slot] = value
        self._set_equipment(telegram_id, equipment)
        self.save_snapshot()

    def update_equipment_fields(self, telegram_id: int, updates: dict[str, Any]) -> bool:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return False
        equipment = dict(character.equipment)
        equipment.update(updates)
        self._set_equipment(telegram_id, equipment)
        self.save_snapshot()
        return True

    def add_player_stat(self, telegram_id: int, stat_key: str, delta: int = 1) -> bool:
        allowed_columns = {
            "quests_completed": "quests_completed",
            "quests_failed": "quests_failed",
            "raids_completed": "raids_completed",
            "raids_failed": "raids_failed",
            "wars_won": "wars_won",
            "smuggling_success": "smuggling_success",
            "trades_done": "trades_done",
            "money_earned": "money_earned",
            "rating_points": "rating_points",
            "achievements_unlocked": "achievements_unlocked",
        }
        column = allowed_columns.get(stat_key)
        if column is None or delta == 0:
            return False
        with self._connect() as conn:
            self._ensure_player_stats_row(conn, telegram_id)
            conn.execute(
                f"UPDATE player_stats SET {column} = MAX(0, {column} + ?) WHERE telegram_id = ?",  # noqa: S608
                (delta, telegram_id),
            )
        self.save_snapshot()
        return True

    def get_player_stats(self, telegram_id: int) -> dict[str, int]:
        with self._connect() as conn:
            self._ensure_player_stats_row(conn, telegram_id)
            row = conn.execute(
                """
                SELECT quests_completed, quests_failed, raids_completed, raids_failed, wars_won,
                       smuggling_success, trades_done, money_earned, rating_points, achievements_unlocked
                FROM player_stats
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
        if row is None:
            return {
                "quests_completed": 0,
                "quests_failed": 0,
                "raids_completed": 0,
                "raids_failed": 0,
                "wars_won": 0,
                "smuggling_success": 0,
                "trades_done": 0,
                "money_earned": 0,
                "rating_points": 0,
                "achievements_unlocked": 0,
            }
        return {
            "quests_completed": int(row["quests_completed"]),
            "quests_failed": int(row["quests_failed"]),
            "raids_completed": int(row["raids_completed"]),
            "raids_failed": int(row["raids_failed"]),
            "wars_won": int(row["wars_won"]),
            "smuggling_success": int(row["smuggling_success"]),
            "trades_done": int(row["trades_done"]),
            "money_earned": int(row["money_earned"]),
            "rating_points": int(row["rating_points"]),
            "achievements_unlocked": int(row["achievements_unlocked"]),
        }

    def unlock_player_achievement(self, telegram_id: int, achievement_key: str) -> bool:
        if not achievement_key.strip():
            return False
        with self._connect() as conn:
            self._ensure_player_stats_row(conn, telegram_id)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO player_achievements(telegram_id, achievement_key, unlocked_at)
                VALUES (?, ?, ?)
                """,
                (telegram_id, achievement_key, utc_now().isoformat()),
            )
            inserted = cursor.rowcount > 0
        if inserted:
            self.save_snapshot()
        return inserted

    def get_player_achievement_keys(self, telegram_id: int) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT achievement_key
                FROM player_achievements
                WHERE telegram_id = ?
                ORDER BY unlocked_at
                """,
                (telegram_id,),
            ).fetchall()
        return {str(row["achievement_key"]) for row in rows}

    def list_player_achievements(self, telegram_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT achievement_key, unlocked_at
                FROM player_achievements
                WHERE telegram_id = ?
                ORDER BY unlocked_at
                """,
                (telegram_id,),
            ).fetchall()
        return [{"achievement_key": row["achievement_key"], "unlocked_at": row["unlocked_at"]} for row in rows]

    def get_rating_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        safe_limit = max(1, min(25, limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.telegram_id,
                    c.nickname,
                    c.faction,
                    c.gear_power,
                    c.money,
                    COALESCE(ps.rating_points, 0) AS rating_points,
                    COALESCE(ps.quests_completed, 0) AS quests_completed,
                    COALESCE(ps.raids_completed, 0) AS raids_completed,
                    COALESCE(ps.wars_won, 0) AS wars_won,
                    COALESCE(ps.achievements_unlocked, 0) AS achievements_unlocked
                FROM characters c
                LEFT JOIN player_stats ps ON ps.telegram_id = c.telegram_id
                ORDER BY rating_points DESC, c.money DESC, c.gear_power DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_avatar_style(self, telegram_id: int, style: str) -> None:
        if style not in {"classic", "realistic"}:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET avatar_style = ? WHERE telegram_id = ?",
                (style, telegram_id),
            )
        self.save_snapshot()

    def set_truck_owned(self, telegram_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET truck_owned = 1 WHERE telegram_id = ?",
                (telegram_id,),
            )
        self.save_snapshot()

    def set_sleeping_bag_owned(self, telegram_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET sleeping_bag_owned = 1 WHERE telegram_id = ?",
                (telegram_id,),
            )
        self.save_snapshot()

    def clear_sleeping_bag_owned(self, telegram_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET sleeping_bag_owned = 0 WHERE telegram_id = ?",
                (telegram_id,),
            )
        self.save_snapshot()

    def clear_truck_owned(self, telegram_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET truck_owned = 0 WHERE telegram_id = ?",
                (telegram_id,),
            )
        self.save_snapshot()

    def change_fuel(self, telegram_id: int, delta: int) -> bool:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return False
        new_fuel = character.fuel + delta
        if new_fuel < 0:
            return False
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET fuel = ? WHERE telegram_id = ?",
                (new_fuel, telegram_id),
            )
        self.save_snapshot()
        return True

    def change_health(self, telegram_id: int, delta: int) -> bool:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return False
        new_health = max(0, min(100, character.health + delta))
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET health = ? WHERE telegram_id = ?",
                (new_health, telegram_id),
            )
        self.save_snapshot()
        return True

    def get_faction_power(self, faction: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(gear_power), 0) AS total_power
                FROM characters
                WHERE faction = ?
                """,
                (faction,),
            ).fetchone()
        return int(row["total_power"]) if row else 0

    def get_faction_active_members_count(self, faction: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total_members
                FROM characters
                WHERE faction = ? AND health > 0
                """,
                (faction,),
            ).fetchone()
        return int(row["total_members"]) if row else 0

    def change_faction_treasury(self, faction: str, delta: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE factions SET treasury = treasury + ? WHERE name = ?",
                (delta, faction),
            )
        self.save_snapshot()

    def get_factions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name, treasury, leader_id FROM factions ORDER BY name").fetchall()
        return [
            {
                "name": row["name"],
                "treasury": row["treasury"],
                "leader_id": row["leader_id"],
            }
            for row in rows
        ]

    def set_faction_leader(self, faction: str, leader_id: int) -> bool:
        with self._connect() as conn:
            faction_row = conn.execute("SELECT 1 FROM factions WHERE name = ?", (faction,)).fetchone()
            if faction_row is None:
                return False
            character_row = conn.execute(
                "SELECT faction FROM characters WHERE telegram_id = ?",
                (leader_id,),
            ).fetchone()
            if character_row is None or str(character_row["faction"] or "") != faction:
                return False
            conn.execute(
                "UPDATE factions SET leader_id = ? WHERE name = ?",
                (leader_id, faction),
            )
        self.save_snapshot()
        return True

    def get_faction_leader_id(self, faction: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT leader_id FROM factions WHERE name = ?", (faction,)).fetchone()
        if row is None or row["leader_id"] is None:
            return None
        return int(row["leader_id"])

    def are_factions_allied(self, faction_a: str, faction_b: str) -> bool:
        if faction_a == faction_b:
            return True
        left, right = sorted((faction_a, faction_b))
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM alliances
                WHERE faction_a = ? AND faction_b = ?
                """,
                (left, right),
            ).fetchone()
        return row is not None

    def set_faction_alliance(self, faction_a: str, faction_b: str, allied: bool) -> bool:
        if faction_a == faction_b:
            return False
        left, right = sorted((faction_a, faction_b))
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM factions WHERE name IN (?, ?)",
                (left, right),
            ).fetchall()
            if len(exists) < 2:
                return False
            if allied:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO alliances(faction_a, faction_b, created_at)
                    VALUES(?, ?, ?)
                    """,
                    (left, right, utc_now().isoformat()),
                )
                conn.execute(
                    """
                    DELETE FROM alliance_requests
                    WHERE (requester_faction = ? AND target_faction = ?)
                       OR (requester_faction = ? AND target_faction = ?)
                    """,
                    (left, right, right, left),
                )
            else:
                conn.execute(
                    """
                    DELETE FROM alliances
                    WHERE faction_a = ? AND faction_b = ?
                    """,
                    (left, right),
                )
        self.save_snapshot()
        return True

    def create_alliance_request(self, requester_faction: str, target_faction: str, proposed_by: int) -> bool:
        if requester_faction == target_faction:
            return False
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT 1 FROM factions WHERE name IN (?, ?)",
                (requester_faction, target_faction),
            ).fetchall()
            if len(rows) < 2:
                return False
            conn.execute(
                """
                INSERT OR IGNORE INTO alliance_requests(requester_faction, target_faction, proposed_by, created_at)
                VALUES(?, ?, ?, ?)
                """,
                (requester_faction, target_faction, proposed_by, utc_now().isoformat()),
            )
            created = conn.total_changes > 0
        if created:
            self.save_snapshot()
        return created

    def list_incoming_alliance_requests(self, faction: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT requester_faction, target_faction, proposed_by, created_at
                FROM alliance_requests
                WHERE target_faction = ?
                ORDER BY created_at DESC
                """,
                (faction,),
            ).fetchall()
        return [dict(row) for row in rows]

    def remove_alliance_request(self, requester_faction: str, target_faction: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM alliance_requests
                WHERE requester_faction = ? AND target_faction = ?
                """,
                (requester_faction, target_faction),
            )
        self.save_snapshot()

    def list_faction_alliances(self, faction: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT faction_a, faction_b
                FROM alliances
                WHERE faction_a = ? OR faction_b = ?
                ORDER BY faction_a, faction_b
                """,
                (faction, faction),
            ).fetchall()
        allies: list[str] = []
        for row in rows:
            left = str(row["faction_a"])
            right = str(row["faction_b"])
            allies.append(right if left == faction else left)
        return allies

    def get_locations(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT name, point_type, controlled_by, npc_power
                FROM locations
                ORDER BY name
                """
            ).fetchall()
        return [
            {
                "name": row["name"],
                "point_type": row["point_type"],
                "controlled_by": row["controlled_by"],
                "npc_power": row["npc_power"],
            }
            for row in rows
        ]

    def get_location(self, location_name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT name, point_type, controlled_by, npc_power
                FROM locations
                WHERE name = ?
                """,
                (location_name,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def set_location_control(self, location_name: str, faction: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE locations SET controlled_by = ? WHERE name = ?",
                (faction, location_name),
            )
        self.save_snapshot()

    def set_location_npc_power(self, location_name: str, npc_power: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT point_type FROM locations WHERE name = ?",
                (location_name,),
            ).fetchone()
            min_power = (
                BASE_LOCATION_NPC_POWER
                if row is not None and row["point_type"] == "база"
                else REGULAR_LOCATION_NPC_POWER
            )
            safe_power = max(min_power, npc_power)
            conn.execute(
                "UPDATE locations SET npc_power = ? WHERE name = ?",
                (safe_power, location_name),
            )
        self.save_snapshot()

    def run_periodic_sync(self) -> None:
        self.save_snapshot()

    def get_characters_by_ids(self, telegram_ids: list[int]) -> list[Character]:
        if not telegram_ids:
            return []
        placeholders = ",".join("?" for _ in telegram_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM characters WHERE telegram_id IN ({placeholders})",  # noqa: S608
                tuple(telegram_ids),
            ).fetchall()
        return [self._row_to_character(row) for row in rows]

    def get_open_raid_for_faction(self, faction: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, faction, location, leader_id, status, created_at, started_at, finished_at, result_text
                FROM raids
                WHERE faction = ? AND status = 'open'
                ORDER BY id DESC
                LIMIT 1
                """,
                (faction,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def create_raid(self, faction: str, location: str, leader_id: int) -> int:
        now_iso = utc_now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO raids(faction, location, leader_id, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
                """,
                (faction, location, leader_id, now_iso),
            )
            raid_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT OR IGNORE INTO raid_members(raid_id, telegram_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (raid_id, leader_id, now_iso),
            )
        self.save_snapshot()
        return raid_id

    def add_raid_member(self, raid_id: int, telegram_id: int) -> bool:
        with self._connect() as conn:
            raid_row = conn.execute(
                "SELECT status, faction FROM raids WHERE id = ?",
                (raid_id,),
            ).fetchone()
            if raid_row is None or raid_row["status"] != "open":
                return False
            member_row = conn.execute(
                "SELECT faction FROM characters WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if member_row is None or not str(member_row["faction"] or ""):
                return False
            conn.execute(
                """
                INSERT OR IGNORE INTO raid_members(raid_id, telegram_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (raid_id, telegram_id, utc_now().isoformat()),
            )
        self.save_snapshot()
        return True

    def get_raid(self, raid_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, faction, location, leader_id, status, created_at, started_at, finished_at, result_text
                FROM raids
                WHERE id = ?
                """,
                (raid_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_open_war_lobby_for_faction(self, faction: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, host_faction, location, leader_id, status, created_at, started_at, finished_at, result_text
                FROM war_lobbies
                WHERE host_faction = ? AND status = 'open'
                ORDER BY id DESC
                LIMIT 1
                """,
                (faction,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def create_war_lobby(self, host_faction: str, location: str, leader_id: int) -> int:
        now_iso = utc_now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO war_lobbies(host_faction, location, leader_id, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
                """,
                (host_faction, location, leader_id, now_iso),
            )
            war_id = int(cursor.lastrowid)
            conn.execute(
                """
                INSERT OR IGNORE INTO war_lobby_members(war_id, telegram_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (war_id, leader_id, now_iso),
            )
        self.save_snapshot()
        return war_id

    def add_war_lobby_member(self, war_id: int, telegram_id: int) -> bool:
        with self._connect() as conn:
            lobby = conn.execute(
                "SELECT status FROM war_lobbies WHERE id = ?",
                (war_id,),
            ).fetchone()
            if lobby is None or str(lobby["status"]) != "open":
                return False
            if conn.execute("SELECT 1 FROM characters WHERE telegram_id = ?", (telegram_id,)).fetchone() is None:
                return False
            conn.execute(
                """
                INSERT OR IGNORE INTO war_lobby_members(war_id, telegram_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (war_id, telegram_id, utc_now().isoformat()),
            )
        self.save_snapshot()
        return True

    def get_war_lobby_member_ids(self, war_id: int) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT telegram_id FROM war_lobby_members WHERE war_id = ? ORDER BY joined_at",
                (war_id,),
            ).fetchall()
        return [int(row["telegram_id"]) for row in rows]

    def finish_war_lobby(self, war_id: int, status: str, result_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE war_lobbies
                SET status = ?, started_at = COALESCE(started_at, ?), finished_at = ?, result_text = ?
                WHERE id = ?
                """,
                (status, utc_now().isoformat(), utc_now().isoformat(), result_text, war_id),
            )
        self.save_snapshot()

    def get_raid_member_ids(self, raid_id: int) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT telegram_id FROM raid_members WHERE raid_id = ? ORDER BY joined_at",
                (raid_id,),
            ).fetchall()
        return [int(row["telegram_id"]) for row in rows]

    def finish_raid(self, raid_id: int, status: str, result_text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE raids
                SET status = ?, started_at = COALESCE(started_at, ?), finished_at = ?, result_text = ?
                WHERE id = ?
                """,
                (status, utc_now().isoformat(), utc_now().isoformat(), result_text, raid_id),
            )
        self.save_snapshot()

    def get_faction_warehouse(self, faction: str) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item_key, amount FROM faction_warehouse WHERE faction = ? ORDER BY item_key",
                (faction,),
            ).fetchall()
        return {str(row["item_key"]): int(row["amount"]) for row in rows}

    def change_faction_warehouse_item(self, faction: str, item_key: str, delta: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT amount FROM faction_warehouse
                WHERE faction = ? AND item_key = ?
                """,
                (faction, item_key),
            ).fetchone()
            current = int(row["amount"]) if row else 0
            new_amount = current + delta
            if new_amount < 0:
                return False
            conn.execute(
                """
                INSERT INTO faction_warehouse(faction, item_key, amount)
                VALUES (?, ?, ?)
                ON CONFLICT(faction, item_key) DO UPDATE SET amount = excluded.amount
                """,
                (faction, item_key, new_amount),
            )
        self.save_snapshot()
        return True

    def create_auction(
        self,
        seller_id: int,
        faction: str,
        item_key: str,
        amount: int,
        price: int,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO auctions(seller_id, faction, item_key, amount, price, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'open', ?)
                """,
                (seller_id, faction, item_key, amount, price, utc_now().isoformat()),
            )
            auction_id = int(cursor.lastrowid)
        self.save_snapshot()
        return auction_id

    def list_open_auctions(self, faction: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, seller_id, faction, item_key, amount, price, status, buyer_id, created_at, closed_at
                FROM auctions
                WHERE status = 'open' AND faction = ?
                ORDER BY id DESC
                """,
                (faction,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_open_equipment_market_lots(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, seller_id, faction, item_key, amount, price, status, buyer_id, created_at, closed_at
                FROM auctions
                WHERE status = 'open'
                ORDER BY id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_open_auction(self, auction_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, seller_id, faction, item_key, amount, price, status, buyer_id, created_at, closed_at
                FROM auctions
                WHERE id = ? AND status = 'open'
                """,
                (auction_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def close_auction(
        self,
        auction_id: int,
        buyer_id: int | None = None,
        status: str = "sold",
    ) -> bool:
        if status not in {"sold", "cancelled"}:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM auctions WHERE id = ?",
                (auction_id,),
            ).fetchone()
            if row is None or row["status"] != "open":
                return False
            conn.execute(
                """
                UPDATE auctions
                SET status = ?, buyer_id = ?, closed_at = ?
                WHERE id = ?
                """,
                (status, buyer_id, utc_now().isoformat(), auction_id),
            )
        self.save_snapshot()
        return True

    def upsert_map_event(
        self,
        location: str,
        event_type: str,
        modifier: int,
        description: str,
        expires_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO map_events(location, event_type, modifier, description, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(location) DO UPDATE SET
                    event_type = excluded.event_type,
                    modifier = excluded.modifier,
                    description = excluded.description,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (location, event_type, modifier, description, expires_at, utc_now().isoformat()),
            )
        self.save_snapshot()

    def delete_expired_map_events(self) -> None:
        now_iso = utc_now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM map_events WHERE expires_at <= ?",
                (now_iso,),
            )
        self.save_snapshot()

    def get_map_events(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT location, event_type, modifier, description, expires_at, updated_at
                FROM map_events
                ORDER BY location
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def apply_topup_payment(
        self,
        telegram_id: int,
        payment_charge_id: str,
        stars_amount: int,
        ru_amount: int,
    ) -> tuple[bool, bool]:
        if stars_amount <= 0 or ru_amount <= 0 or not payment_charge_id.strip():
            return False, False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT money FROM characters WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if row is None:
                return False, False
            new_money = int(row["money"]) + ru_amount
            try:
                conn.execute(
                    """
                    INSERT INTO topup_payments(
                        payment_charge_id, telegram_id, stars_amount, ru_amount, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        payment_charge_id,
                        telegram_id,
                        stars_amount,
                        ru_amount,
                        utc_now().isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                return False, True

            conn.execute(
                "UPDATE characters SET money = ? WHERE telegram_id = ?",
                (new_money, telegram_id),
            )
        self.save_snapshot()
        return True, False

    def _set_inventory(self, telegram_id: int, inventory: dict[str, int]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET inventory_json = ? WHERE telegram_id = ?",
                (json.dumps(inventory, ensure_ascii=False), telegram_id),
            )

    def _set_equipment(self, telegram_id: int, equipment: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET equipment_json = ? WHERE telegram_id = ?",
                (json.dumps(equipment, ensure_ascii=False), telegram_id),
            )

    def _ensure_player_stats_rows(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO player_stats(telegram_id)
            SELECT telegram_id FROM characters
            """
        )

    def _ensure_player_stats_row(self, conn: sqlite3.Connection, telegram_id: int) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO player_stats(telegram_id) VALUES (?)",
            (telegram_id,),
        )

    def _enforce_location_power_baseline(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            UPDATE locations
            SET npc_power = CASE
                WHEN point_type = 'база' AND npc_power < ? THEN ?
                WHEN point_type <> 'база' AND npc_power < ? THEN ?
                ELSE npc_power
            END
            """,
            (
                BASE_LOCATION_NPC_POWER,
                BASE_LOCATION_NPC_POWER,
                REGULAR_LOCATION_NPC_POWER,
                REGULAR_LOCATION_NPC_POWER,
            ),
        )

    def _ensure_characters_schema(self, conn: sqlite3.Connection) -> None:
        columns = conn.execute("PRAGMA table_info(characters)").fetchall()
        column_names = {row["name"] for row in columns}
        if "player_uid" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN player_uid TEXT")
        if "avatar_style" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN avatar_style TEXT")
        if "radiation" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN radiation INTEGER NOT NULL DEFAULT 0")
        if "hunger" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN hunger INTEGER NOT NULL DEFAULT 0")
        if "thirst" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN thirst INTEGER NOT NULL DEFAULT 0")
        if "needs_updated_at" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN needs_updated_at TEXT")
        if "survival_damage_at" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN survival_damage_at TEXT")
        if "sleeping_bag_owned" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN sleeping_bag_owned INTEGER NOT NULL DEFAULT 0")

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_characters_player_uid ON characters(player_uid)"
        )
        # Backfill ID-address for old rows created before this column existed.
        rows = conn.execute(
            "SELECT telegram_id FROM characters WHERE player_uid IS NULL OR TRIM(player_uid) = ''"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE characters SET player_uid = ? WHERE telegram_id = ?",
                (build_player_uid(int(row["telegram_id"])), int(row["telegram_id"])),
            )
        conn.execute(
            """
            UPDATE characters
            SET avatar_style = 'classic'
            WHERE avatar_style IS NULL OR TRIM(avatar_style) = ''
            """
        )
        now_iso = utc_now().isoformat()
        conn.execute(
            """
            UPDATE characters
            SET needs_updated_at = ?
            WHERE needs_updated_at IS NULL OR TRIM(needs_updated_at) = ''
            """,
            (now_iso,),
        )
        conn.execute(
            """
            UPDATE characters
            SET survival_damage_at = ?
            WHERE survival_damage_at IS NULL OR TRIM(survival_damage_at) = ''
            """,
            (now_iso,),
        )
        rows = conn.execute(
            "SELECT telegram_id, equipment_json FROM characters"
        ).fetchall()
        for row in rows:
            try:
                equipment = json.loads(row["equipment_json"] or "{}")
            except json.JSONDecodeError:
                equipment = {}
            if not isinstance(equipment, dict):
                equipment = {}
            changed = False
            if "weapon" not in equipment:
                equipment["weapon"] = "Нож"
                changed = True
            if "armor" not in equipment:
                equipment["armor"] = "Куртка новичка"
                changed = True
            if "weapon_durability" not in equipment:
                equipment["weapon_durability"] = 100
                changed = True
            if "armor_durability" not in equipment:
                equipment["armor_durability"] = 100
                changed = True
            if changed:
                conn.execute(
                    "UPDATE characters SET equipment_json = ? WHERE telegram_id = ?",
                    (json.dumps(equipment, ensure_ascii=False), int(row["telegram_id"])),
                )

    @staticmethod
    def _row_to_character(row: sqlite3.Row) -> Character:
        inventory = json.loads(row["inventory_json"])
        if not isinstance(inventory, dict):
            inventory = {}
        equipment = json.loads(row["equipment_json"])
        if not isinstance(equipment, dict):
            equipment = {"weapon": "Нож", "armor": "Куртка новичка"}
        if "weapon" not in equipment:
            equipment["weapon"] = "Нож"
        if "armor" not in equipment:
            equipment["armor"] = "Куртка новичка"
        try:
            weapon_durability = int(equipment.get("weapon_durability", 100))
        except (TypeError, ValueError):
            weapon_durability = 100
        try:
            armor_durability = int(equipment.get("armor_durability", 100))
        except (TypeError, ValueError):
            armor_durability = 100
        equipment["weapon_durability"] = max(0, min(100, weapon_durability))
        equipment["armor_durability"] = max(0, min(100, armor_durability))
        return Character(
            telegram_id=row["telegram_id"],
            player_uid=row["player_uid"] or build_player_uid(row["telegram_id"]),
            avatar_style=(row["avatar_style"] or "classic"),
            nickname=row["nickname"],
            gender=row["gender"],
            faction=row["faction"],
            money=row["money"],
            energy=row["energy"],
            max_energy=row["max_energy"],
            health=row["health"],
            gear_power=row["gear_power"],
            location=row["location"],
            inventory=inventory,
            equipment=equipment,
            truck_owned=bool(row["truck_owned"]),
            sleeping_bag_owned=bool(row["sleeping_bag_owned"]),
            fuel=row["fuel"],
            energy_updated_at=datetime.fromisoformat(row["energy_updated_at"]),
            radiation=max(0, min(200, int(row["radiation"]))),
            hunger=max(0, min(200, int(row["hunger"]))),
            thirst=max(0, min(200, int(row["thirst"]))),
            needs_updated_at=datetime.fromisoformat(row["needs_updated_at"]),
            survival_damage_at=datetime.fromisoformat(row["survival_damage_at"]),
        )
