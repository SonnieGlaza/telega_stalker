from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is not set. Put it in .env or environment variables.")
    db_path = os.getenv("DB_PATH", "stalker_game.db")
    return Settings(bot_token=token, db_path=db_path)
