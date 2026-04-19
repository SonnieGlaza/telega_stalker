from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENERGY_REGEN_PER_MINUTE = 2


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
    equipment: dict[str, str]
    truck_owned: bool
    fuel: int
    energy_updated_at: datetime


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
                topup_payments = [dict(row) for row in conn.execute("SELECT * FROM topup_payments").fetchall()]
            payload = {
                "version": 1,
                "characters": characters,
                "factions": factions,
                "locations": locations,
                "topup_payments": topup_payments,
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
        topup_payments = payload.get("topup_payments") or []
        if not characters:
            return

        for row in factions:
            conn.execute(
                """
                INSERT OR REPLACE INTO factions(name, treasury)
                VALUES(?, ?)
                """,
                (row.get("name"), int(row.get("treasury", 0))),
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
                    int(row.get("npc_power", 30)),
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
                    equipment_json TEXT NOT NULL DEFAULT '{"weapon":"Нож","armor":"Куртка новичка"}',
                    truck_owned INTEGER NOT NULL DEFAULT 0,
                    fuel INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._ensure_characters_schema(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS factions (
                    name TEXT PRIMARY KEY,
                    treasury INTEGER NOT NULL DEFAULT 20000
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS locations (
                    name TEXT PRIMARY KEY,
                    point_type TEXT NOT NULL,
                    controlled_by TEXT,
                    npc_power INTEGER NOT NULL DEFAULT 30
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
            conn.executemany(
                "INSERT OR IGNORE INTO factions(name, treasury) VALUES(?, ?)",
                [("Долг", 20000), ("Свобода", 20000)],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO locations(name, point_type, controlled_by, npc_power) VALUES(?, ?, ?, ?)",
                [
                    ("Росток", "база", "Долг", 20),
                    ("Армейские склады", "база", "Свобода", 20),
                    ("Янтарь", "точка ресурсов", None, 30),
                    ("Темная долина", "точка интереса", None, 30),
                    ("Радар", "точка интереса", None, 35),
                ],
            )
            self._restore_from_snapshot_if_needed(conn)

    def create_character(self, telegram_id: int, nickname: str, gender: str) -> None:
        player_uid = build_player_uid(telegram_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO characters(
                    telegram_id, player_uid, nickname, gender, energy_updated_at
                ) VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    nickname = excluded.nickname,
                    gender = excluded.gender
                """,
                (telegram_id, player_uid, nickname, gender, utc_now().isoformat()),
            )
        self.save_snapshot()

    def get_character(self, telegram_id: int, refresh_energy: bool = True) -> Character | None:
        if refresh_energy:
            self.recover_energy(telegram_id)
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

    def recover_energy(self, telegram_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT energy, max_energy, energy_updated_at
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

            gained = minutes_passed * ENERGY_REGEN_PER_MINUTE
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

    def set_equipment_item(self, telegram_id: int, slot: str, value: str) -> None:
        character = self.get_character(telegram_id, refresh_energy=False)
        if character is None:
            return
        equipment = dict(character.equipment)
        equipment[slot] = value
        self._set_equipment(telegram_id, equipment)
        self.save_snapshot()

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

    def change_faction_treasury(self, faction: str, delta: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE factions SET treasury = treasury + ? WHERE name = ?",
                (delta, faction),
            )
        self.save_snapshot()

    def get_factions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name, treasury FROM factions ORDER BY name").fetchall()
        return [{"name": row["name"], "treasury": row["treasury"]} for row in rows]

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

    def set_location_control(self, location_name: str, faction: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE locations SET controlled_by = ? WHERE name = ?",
                (faction, location_name),
            )
        self.save_snapshot()

    def run_periodic_sync(self) -> None:
        self.save_snapshot()

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

    def _set_equipment(self, telegram_id: int, equipment: dict[str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE characters SET equipment_json = ? WHERE telegram_id = ?",
                (json.dumps(equipment, ensure_ascii=False), telegram_id),
            )

    def _ensure_characters_schema(self, conn: sqlite3.Connection) -> None:
        columns = conn.execute("PRAGMA table_info(characters)").fetchall()
        column_names = {row["name"] for row in columns}
        if "player_uid" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN player_uid TEXT")
        if "avatar_style" not in column_names:
            conn.execute("ALTER TABLE characters ADD COLUMN avatar_style TEXT")

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

    @staticmethod
    def _row_to_character(row: sqlite3.Row) -> Character:
        inventory = json.loads(row["inventory_json"])
        equipment = json.loads(row["equipment_json"])
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
            fuel=row["fuel"],
            energy_updated_at=datetime.fromisoformat(row["energy_updated_at"]),
        )
