from __future__ import annotations

import re
import tempfile
from pathlib import Path

from app.game_logic import (
    ITEM_LABELS,
    attack_location,
    attempt_smuggling,
    buy_item,
    build_alliance_overview,
    build_economy_overview,
    build_market_lots_overview,
    build_raids_overview,
    build_war_lobby_overview,
    create_market_lot,
    create_or_join_faction_raid,
    create_or_join_war_lobby,
    launch_open_raid,
    launch_war_lobby,
    search_artifacts,
    travel_to,
    use_medkit,
)
from app.storage import Storage


def _all_callback_data() -> set[str]:
    keyboards_source = Path("/workspace/app/keyboards.py").read_text(encoding="utf-8")
    return set(re.findall(r'callback_data="([^"]+)"', keyboards_source))


def _callback_handler_coverage() -> tuple[set[str], set[str], list[str]]:
    bot_source = Path("/workspace/app/bot.py").read_text(encoding="utf-8")
    exact_handlers = set(re.findall(r'@router\.callback_query\(F\.data == "([^"]+)"\)', bot_source))
    prefix_handlers = set(re.findall(r'@router\.callback_query\(F\.data\.startswith\("([^"]+)"\)\)', bot_source))

    missing: list[str] = []
    for callback_data in sorted(_all_callback_data()):
        if callback_data in exact_handlers:
            continue
        if any(callback_data.startswith(prefix) for prefix in prefix_handlers):
            continue
        # Registration-only callbacks are handled under FSM state filters.
        if callback_data.startswith("gender:"):
            continue
        missing.append(callback_data)
    return exact_handlers, prefix_handlers, missing


def run_smoke_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "smoke.sqlite3"
        snapshot_path = Path(tmp) / "smoke.backup.json"
        storage = Storage(str(db_path), snapshot_path=str(snapshot_path))
        storage.init_db()

        # Registration + factions.
        storage.create_character(111, "LeaderDuty", "Мужской")
        storage.create_character(222, "WingmanDuty", "Мужской")
        storage.create_character(333, "LeaderBandit", "Женский")
        storage.set_faction(111, "Долг")
        storage.set_faction(222, "Долг")
        storage.set_faction(333, "Бандиты")
        assert storage.character_exists(111)
        assert storage.character_exists(222)
        assert storage.character_exists(333)
        assert storage.set_faction_leader("Долг", 111)
        assert storage.set_faction_leader("Бандиты", 333)

        # Economy / trader items.
        assert buy_item(storage, 111, "detector_otklik").ok
        storage.change_money(111, 40000)
        assert buy_item(storage, 111, "sleeping_bag").ok
        assert buy_item(storage, 111, "medkit").ok
        assert use_medkit(storage, 111).ok is False  # hp full
        assert search_artifacts(storage, 111).text
        assert travel_to(storage, 111, "Янтарь").text
        assert build_alliance_overview(storage, 111)
        assert build_economy_overview(storage, 111)

        # Raids.
        raid_create = create_or_join_faction_raid(storage, 111, "Янтарь")
        assert raid_create.ok, raid_create.text
        raid_join = create_or_join_faction_raid(storage, 222, "Янтарь")
        assert raid_join.ok, raid_join.text
        raid_launch = launch_open_raid(storage, 111)
        assert raid_launch.text
        assert build_raids_overview(storage, 111)

        # War lobby.
        war_create = create_or_join_war_lobby(storage, 111, "Свалка")
        assert war_create.ok, war_create.text
        war_join = create_or_join_war_lobby(storage, 222, "Свалка")
        assert war_join.ok, war_join.text
        war_launch = launch_war_lobby(storage, 111)
        assert war_launch.text
        assert build_war_lobby_overview(storage, 111)
        assert attack_location(storage, 111, "Свалка").text
        assert attempt_smuggling(storage, 111).text

        # Market + lots.
        # ensure one equipment exists in inventory
        buy_weapon = buy_item(storage, 111, "weapon_pm")
        assert buy_weapon.ok, buy_weapon.text
        lot_result = create_market_lot(storage, 111, "weapon_pm", 1)
        assert lot_result.ok, lot_result.text
        lots_text, lots = build_market_lots_overview(storage, 222, limit=10)
        assert lots_text
        assert isinstance(lots, list)

        # Keyboard callback sanity (basic non-empty check).
        callbacks = _all_callback_data()
        assert "artifact:search" in callbacks
        assert "war:section:scenario" in callbacks
        assert "war:section:lobby" in callbacks
        assert "war:section:assault" in callbacks
        _, _, missing_callbacks = _callback_handler_coverage()
        assert not missing_callbacks, f"Missing callback handlers: {', '.join(missing_callbacks)}"

        # Label map sanity (no missing key for new items).
        assert "detector_otklik" in ITEM_LABELS
        assert "sleeping_bag" in ITEM_LABELS


if __name__ == "__main__":
    run_smoke_check()
    print("Smoke check passed.")
