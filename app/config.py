from __future__ import annotations

import os
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
    # Use a single canonical DB path to avoid split progress.
    canonical_path = Path("/data/stalker_game.db")
    if _is_writable_dir(canonical_path.parent):
        return str(canonical_path)
    return "stalker_game.db"


def _resolve_default_snapshot_path(db_path: str) -> str:
    return str(Path(db_path).with_suffix(".backup.json"))


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
