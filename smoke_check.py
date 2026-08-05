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
    repair_truck,
    search_artifacts,
    travel_to,
    use_medkit,
    accept_quest_contract,
    run_contract_work,
    can_travel_by_truck,
)
from app.storage import Storage

PROJECT_ROOT = Path(__file__).resolve().parent


def _all_callback_data() -> set[str]:
    keyboards_source = (PROJECT_ROOT / "app" / "keyboards.py").read_text(encoding="utf-8")
    return set(re.findall(r'callback_data="([^"]+)"', keyboards_source))


def _callback_handler_coverage() -> tuple[set[str], set[str], list[str]]:
    bot_source = (PROJECT_ROOT / "app" / "bot.py").read_text(encoding="utf-8")
    exact_handlers = set(re.findall(r'@router\.callback_query\(F\.data == "([^"]+)"\)', bot_source))
    prefix_handlers = set(re.findall(r'@router\.callback_query\(F\.data\.startswith\("([^"]+)"\)\)', bot_source))
    # Exact multi-value filters: F.data.in_({...})
    for block in re.findall(r"@router\.callback_query\(\s*F\.data\.in_\(\s*\{([^}]+)\}\s*\)", bot_source, flags=re.S):
        exact_handlers.update(re.findall(r'"([^"]+)"', block))

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

        # Faction ranks assigned by leader.
        from app.game_logic import assign_faction_rank, character_rank_title

        assert character_rank_title(storage, storage.get_character(111)) == "Полковник"
        assert character_rank_title(storage, storage.get_character(222)) == "Рядовой"
        promote = assign_faction_rank(storage, 111, 222, "r3")
        assert promote.ok, promote.text
        assert character_rank_title(storage, storage.get_character(222)) == "Прапорщик"
        denied = assign_faction_rank(storage, 222, 111, "r2")
        assert not denied.ok
        bandit_rank = assign_faction_rank(storage, 333, 333, "r1")
        assert not bandit_rank.ok

        # Faction base fortification (+1 defense per 10000 RU from treasury).
        from app.game_logic import upgrade_faction_base, faction_home_base, BASE_FORTIFY_COST_RU

        duty_base = faction_home_base("Долг")
        assert int(storage.get_location(duty_base).get("defense_bonus") or 0) == 0
        denied_fortify = upgrade_faction_base(storage, 222)
        assert not denied_fortify.ok
        before_treasury = next(f for f in storage.get_factions() if f["name"] == "Долг")["treasury"]
        fortify = upgrade_faction_base(storage, 111)
        assert fortify.ok, fortify.text
        after_treasury = next(f for f in storage.get_factions() if f["name"] == "Долг")["treasury"]
        assert before_treasury - after_treasury == BASE_FORTIFY_COST_RU
        assert int(storage.get_location(duty_base)["defense_bonus"]) == 1
        fortify2 = upgrade_faction_base(storage, 111)
        assert fortify2.ok, fortify2.text
        assert int(storage.get_location(duty_base)["defense_bonus"]) == 2

        # Referral rewards.
        from app.game_logic import (
            apply_referral_rewards,
            build_referral_link,
            parse_referral_payload,
            REFERRAL_INVITER_BONUS_RU,
        )

        assert parse_referral_payload("ref_111") == 111
        assert parse_referral_payload("ref111") == 111
        assert parse_referral_payload("hello") is None
        assert build_referral_link("my_bot", 111) == "https://t.me/my_bot?start=ref_111"
        storage.create_character(444, "NewbieRef", "Мужской")
        before_money = storage.get_character(111, refresh_energy=False).money
        referral = apply_referral_rewards(storage, 444, 111)
        assert referral.ok, referral.text
        newbie = storage.get_character(444, refresh_energy=False)
        assert newbie.inventory.get("stew") == 2
        assert newbie.inventory.get("antirad") == 1
        assert newbie.inventory.get("water_bottle") == 1
        assert newbie.inventory.get("weapon_pm") == 1
        assert newbie.inventory.get("medkit") == 1
        after_money = storage.get_character(111, refresh_energy=False).money
        assert after_money == before_money + REFERRAL_INVITER_BONUS_RU
        again = apply_referral_rewards(storage, 444, 111)
        assert not again.ok

        # Economy / trader items.
        assert buy_item(storage, 111, "detector_otklik").ok
        storage.change_money(111, 100000)
        assert buy_item(storage, 111, "truck").ok
        storage.change_money(222, 20000)
        assert buy_item(storage, 222, "niva").ok
        storage.change_diesel(111, 3)
        storage.change_gasoline(222, 5)
        assert buy_item(storage, 222, "gasoline_can").ok
        before_travel = storage.get_character(111, refresh_energy=False)
        assert before_travel is not None
        before_truck_durability = before_travel.truck_durability
        assert buy_item(storage, 111, "sleeping_bag").ok
        assert buy_item(storage, 111, "medkit").ok
        storage.change_money(111, 100000)
        bulk = buy_item(storage, 111, "medkit", amount=10)
        assert bulk.ok, bulk.text
        assert "×10" in bulk.text
        assert not buy_item(storage, 111, "detector_otklik", amount=5).ok
        assert use_medkit(storage, 111).ok is False  # hp full
        assert search_artifacts(storage, 111).text
        travel_result = travel_to(storage, 111, "Янтарь")
        assert travel_result.ok, travel_result.text
        in_transit = storage.get_character(111, refresh_energy=False)
        assert in_transit is not None
        from app.game_logic import is_traveling, accept_quest_contract, run_contract_work

        assert is_traveling(in_transit)
        from datetime import datetime, timedelta, timezone

        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE characters SET travel_arrives_at = ? WHERE telegram_id = ?",
                (past, 111),
            )
        storage.resolve_travel_if_due(111)
        after_travel = storage.get_character(111, refresh_energy=False)
        assert after_travel is not None
        assert after_travel.location == "Янтарь"
        assert not is_traveling(after_travel)
        assert after_travel.truck_durability < before_truck_durability
        no_fuel_player = storage.get_character(111, refresh_energy=False)
        assert no_fuel_player is not None
        if no_fuel_player.diesel > 0:
            storage.change_diesel(111, -no_fuel_player.diesel)
        if no_fuel_player.gasoline > 0:
            storage.change_gasoline(111, -no_fuel_player.gasoline)
        foot_travel = travel_to(storage, 111, "Болото")
        assert foot_travel.ok, foot_travel.text
        assert "пешком" in foot_travel.text.lower()
        assert can_travel_by_truck(storage.get_character(111, refresh_energy=False)) is False
        past2 = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE characters SET travel_arrives_at = ? WHERE telegram_id = ?",
                (past2, 111),
            )
        storage.resolve_travel_if_due(111)
        repaired = repair_truck(storage, 111)
        assert repaired.ok, repaired.text
        after_repair = storage.get_character(111, refresh_energy=False)
        assert after_repair is not None
        assert after_repair.truck_durability == 100

        storage.set_location(111, "Росток")
        contract = accept_quest_contract(storage, 111, "easy_boloto")
        assert contract.ok, contract.text
        storage.set_location(111, "Болото")
        work = run_contract_work(storage, 111)
        assert work.text

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
        assert "Создал:" in build_war_lobby_overview(storage, 111)
        from app.game_logic import dissolve_war_lobby, can_dissolve_war_lobby
        assert can_dissolve_war_lobby(storage, 111)
        dissolved = dissolve_war_lobby(storage, 111)
        assert dissolved.ok, dissolved.text
        assert "Открытых военных лобби нет" in build_war_lobby_overview(storage, 111)
        solo_assault = attack_location(storage, 111, "Свалка")
        assert not solo_assault.ok, solo_assault.text
        assert attempt_smuggling(storage, 111).text

        # Character career stats.
        from app.game_logic import build_character_stats_overview

        storage.add_player_stat(111, "quests_completed", 3)
        storage.add_player_stat(111, "artifacts_found", 2)
        storage.add_player_stat(111, "wars_won", 1)
        storage.add_player_stat(111, "money_earned", 500)
        storage.change_health(111, -10_000)
        stats = storage.get_player_stats(111)
        assert stats["quests_completed"] >= 3
        assert stats["artifacts_found"] >= 2
        assert stats["wars_won"] >= 1
        assert stats["money_earned"] >= 500
        assert stats["deaths"] >= 1
        assert stats["raids_completed"] >= 0
        stats_text = build_character_stats_overview(storage, 111)
        assert "Заданий выполнено" in stats_text
        assert "Артефактов найдено" in stats_text
        assert "Смертей" in stats_text
        storage.change_health(111, 100)

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
        assert "contract:refresh" in callbacks
        assert "travel:status" in callbacks
        assert "rank:menu" in callbacks
        assert "war:section:scenario" in callbacks
        assert "war:section:lobby" in callbacks
        assert "war:section:assault" not in callbacks
        _, _, missing_callbacks = _callback_handler_coverage()
        assert not missing_callbacks, f"Missing callback handlers: {', '.join(missing_callbacks)}"

        # Label map sanity (no missing key for new items).
        assert "detector_otklik" in ITEM_LABELS
        assert "sleeping_bag" in ITEM_LABELS


if __name__ == "__main__":
    run_smoke_check()
    print("Smoke check passed.")
