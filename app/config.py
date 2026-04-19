from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str
    snapshot_path: str
    admin_ids: tuple[int, ...]


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _resolve_default_db_path() -> str:
    canonical_path = Path("/data/stalker_game.db")
    legacy_candidates = (
        Path("stalker_game.db"),
        Path("/workspace/stalker_game.db"),
        Path("/app/stalker_game.db"),
    )

    def has_character_data(path: Path) -> bool:
        if not path.exists():
            return False
        try:
            with sqlite3.connect(path) as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'characters'
                    """
                ).fetchone()
                if row is None or int(row[0]) == 0:
                    return False
                count_row = conn.execute("SELECT COUNT(*) FROM characters").fetchone()
                return bool(count_row and int(count_row[0]) > 0)
        except sqlite3.Error:
            return False

    canonical_has_data = has_character_data(canonical_path)
    if canonical_has_data:
        return str(canonical_path)

    seen: set[Path] = set()
    for legacy_path in legacy_candidates:
        if legacy_path in seen:
            continue
        seen.add(legacy_path)
        legacy_has_data = has_character_data(legacy_path)
        if not legacy_has_data:
            continue
        if _is_writable_dir(canonical_path.parent):
            try:
                shutil.copy2(legacy_path, canonical_path)
                return str(canonical_path)
            except OSError:
                return str(legacy_path)
        return str(legacy_path)

    if _is_writable_dir(canonical_path.parent):
        return str(canonical_path)
    return str(legacy_candidates[0])


def _resolve_default_snapshot_path(db_path: str) -> str:
    primary = Path(db_path).with_suffix(".backup.json")
    if primary.exists():
        return str(primary)

    legacy_candidates = (
        Path("stalker_game.backup.json"),
        Path("/workspace/stalker_game.backup.json"),
        Path("/app/stalker_game.backup.json"),
    )
    seen: set[Path] = set()
    for legacy in legacy_candidates:
        if legacy in seen:
            continue
        seen.add(legacy)
        if not legacy.exists() or primary == legacy:
            continue
        try:
            primary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, primary)
            return str(primary)
        except OSError:
            return str(legacy)
    return str(primary)


def _parse_admin_ids(raw_value: str) -> tuple[int, ...]:
    if not raw_value.strip():
        return ()
    admin_ids: list[int] = []
    for token in raw_value.split(","):
        value = token.strip()
        if not value:
            continue
        try:
            admin_ids.append(int(value))
        except ValueError as exc:
            raise ValueError(f"ADMIN_IDS содержит некорректный ID: {value}") from exc
    return tuple(admin_ids)


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is not set. Put it in .env or environment variables.")
    db_path = os.getenv("DB_PATH", "").strip() or _resolve_default_db_path()
    snapshot_path = os.getenv("SNAPSHOT_PATH", "").strip() or _resolve_default_snapshot_path(db_path)
    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    return Settings(
        bot_token=token,
        db_path=db_path,
        snapshot_path=snapshot_path,
        admin_ids=admin_ids,
    )
