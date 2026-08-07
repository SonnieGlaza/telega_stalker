from __future__ import annotations

import re
import tempfile
from pathlib import Path

from app.game_logic import (
    ITEM_LABELS,
    SHOP_ITEMS,
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
    upgrade_armor,
    armor_defense,
    apply_incoming_damage,
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
        from app.game_logic import faction_home_base

        assert storage.get_character(111, refresh_energy=False).location == faction_home_base("Долг")
        assert storage.get_character(333, refresh_energy=False).location == faction_home_base("Бандиты")
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
        from app.game_logic import upgrade_faction_base, BASE_FORTIFY_COST_RU

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
        assert newbie.inventory.get("medkit") == 1
        assert newbie.inventory.get("weapon_pm", 0) == 0
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
        from datetime import datetime, timedelta, timezone

        storage.change_money(333, 10000)
        bike = buy_item(storage, 333, "bicycle")
        assert bike.ok, bike.text
        assert storage.get_character(333, refresh_energy=False).bicycle_owned
        bike_travel = travel_to(storage, 333, "Янтарь")
        assert bike_travel.ok, bike_travel.text
        assert "велосипед" in bike_travel.text.lower()
        past_bike = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE characters SET travel_arrives_at = ? WHERE telegram_id = ?",
                (past_bike, 333),
            )
        storage.resolve_travel_if_due(333)
        assert storage.get_character(333, refresh_energy=False).location == "Янтарь"
        assert storage.get_last_arrival_transport(333) == "bicycle"
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

        # Artifact hunt mini-game (visual field).
        from app.artifact_hunt import (
            start_artifact_hunt,
            move_artifact_hunt,
            get_hunt_session,
            abandon_artifact_hunt,
            location_anomaly_count,
        )

        storage.restore_energy(111, 100)
        storage.set_location(111, "Кордон")
        if int(storage.get_character(111, refresh_energy=False).inventory.get("detector_otklik", 0)) <= 0:
            assert buy_item(storage, 111, "detector_otklik").ok
        hunt = start_artifact_hunt(storage, 111)
        assert hunt.ok, hunt.text
        assert hunt.payload and hunt.payload.get("hunt_image")
        assert get_hunt_session(storage, 111) is not None
        assert location_anomaly_count("Кордон") == 3
        step = move_artifact_hunt(storage, 111, "right")
        assert step.payload is not None
        left = abandon_artifact_hunt(storage, 111)
        assert left.ok, left.text
        assert get_hunt_session(storage, 111) is None

        travel_result = travel_to(storage, 111, "Янтарь")
        assert travel_result.ok, travel_result.text
        in_transit = storage.get_character(111, refresh_energy=False)
        assert in_transit is not None
        from app.game_logic import (
            is_traveling,
            accept_quest_contract,
            run_contract_work,
            collect_travel_eta_notices,
            travel_status_text,
        )

        assert is_traveling(in_transit)
        status = travel_status_text(in_transit)
        assert status is not None and "Осталось ехать" in status
        eta_notices = collect_travel_eta_notices(storage)
        assert any(uid == 111 and "Осталось ехать" in text for uid, text in eta_notices)
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
        bound_foot = travel_to(storage, 111, "Болото")
        assert not bound_foot.ok
        assert "грузовик" in bound_foot.text.lower() or "пешком" in bound_foot.text.lower()
        from app.game_logic import garage_deposit_truck, garage_withdraw_truck

        repaired_before = repair_truck(storage, 111)
        assert repaired_before.ok, repaired_before.text
        deposited = garage_deposit_truck(storage, 111)
        assert deposited.ok, deposited.text
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
        storage.change_diesel(111, 10)
        storage.change_money(111, 5000)
        withdrawn = garage_withdraw_truck(storage, 111)
        assert withdrawn.ok, withdrawn.text
        after_repair = storage.get_character(111, refresh_energy=False)
        assert after_repair is not None
        assert after_repair.truck_durability == 100

        storage.change_money(111, 10_000)
        upgraded = upgrade_armor(storage, 111)
        assert upgraded.ok, upgraded.text
        assert int(storage.get_character(111, refresh_energy=False).inventory.get("armor_upgrade", 0)) == 1
        assert armor_defense(storage.get_character(111, refresh_energy=False)) == 0
        from app.game_logic import install_armor_upgrade, unequip_armor_upgrade, equip_armor

        installed = install_armor_upgrade(storage, 111)
        assert installed.ok, installed.text
        assert armor_defense(storage.get_character(111, refresh_energy=False)) == 1
        player_111 = storage.get_character(111, refresh_energy=False)
        assert apply_incoming_damage(10, player_111) == 9
        upgraded2 = upgrade_armor(storage, 111)
        assert upgraded2.ok, upgraded2.text
        installed2 = install_armor_upgrade(storage, 111)
        assert installed2.ok, installed2.text
        assert armor_defense(storage.get_character(111, refresh_energy=False)) == 2
        removed = unequip_armor_upgrade(storage, 111)
        assert removed.ok, removed.text
        assert armor_defense(storage.get_character(111, refresh_energy=False)) == 1
        assert int(storage.get_character(111, refresh_energy=False).inventory.get("armor_upgrade", 0)) == 1

        storage.set_location(111, "Росток")
        contract = accept_quest_contract(storage, 111, "easy_boloto")
        assert contract.ok, contract.text
        storage.set_location(111, "Болото")
        work = run_contract_work(storage, 111)
        assert work.ok, work.text
        assert (work.payload or {}).get("mission_active"), work.text
        assert (work.payload or {}).get("mission_image"), "mission png missing"

        from app.quest_mission import (
            get_mission_session,
            save_mission_session,
            clear_mission_session,
            _finish_success,
            move_quest_mission,
            render_mission_frame,
            use_mission_medkit,
        )

        # Army medkit must heal during mission (not only basic medkit).
        storage.add_item(111, "medkit_army", 1)
        # Remove basic medkits so only army is available.
        cur_inv = storage.get_character(111, refresh_energy=False)
        basic = int(cur_inv.inventory.get("medkit", 0))
        if basic > 0:
            storage.remove_item(111, "medkit", basic)
        storage.change_health(111, -40)
        med_result = use_mission_medkit(storage, 111)
        assert med_result.ok, med_result.text
        assert int(storage.get_character(111, refresh_energy=False).inventory.get("medkit_army", 0)) == 0

        session = get_mission_session(storage, 111)
        assert session is not None
        assert session.kind == "collect"
        assert len(session.objectives) >= 1
        # Easy: только аномалии, без мутантов/НПС.
        assert session.difficulty == "easy"
        assert len(session.hazards) >= 1
        assert len(session.enemies) == 0
        assert len(session.npcs) == 0
        png = render_mission_frame(session, storage.get_character(111, refresh_energy=False))
        assert len(png) > 1000

        # Hard: аномалии + мутанты.
        from app.quest_mission import _build_session, _difficulty_threat_flags, _maybe_move_hostiles
        from app.game_logic import QUEST_CONTRACTS, QUESTS

        hard_tpl = QUEST_CONTRACTS["hard_forest"]
        hard_sess = _build_session(hard_tpl, QUESTS["hard"])
        assert _difficulty_threat_flags("hard", hard_tpl.mission_kind) == (True, True, False)
        assert len(hard_sess.hazards) >= 1
        assert len(hard_sess.enemies) >= 1
        assert len(hard_sess.npcs) == 0

        # Heavy: аномалии + НПС.
        heavy_tpl = QUEST_CONTRACTS["heavy_valley"]
        heavy_sess = _build_session(heavy_tpl, QUESTS["heavy"])
        assert heavy_tpl.mission_kind == "clear_marauder"
        assert len(heavy_sess.hazards) >= 1
        assert len(heavy_sess.npcs) >= 1

        # Impossible: всё вместе.
        imp_tpl = QUEST_CONTRACTS["impossible_radar"]
        imp_sess = _build_session(imp_tpl, QUESTS["impossible"])
        assert len(imp_sess.hazards) >= 1
        assert len(imp_sess.enemies) >= 1
        assert len(imp_sess.npcs) >= 1

        # Hostile move: 50% chance path doesn't crash and keeps count.
        before = len(imp_sess.enemies) + len(imp_sess.npcs)
        _maybe_move_hostiles(imp_sess)
        assert len(imp_sess.enemies) + len(imp_sess.npcs) == before

        # Forced finish for smoke.
        session.collected = list(session.objectives)
        session.objectives_done = True
        session.player = session.start
        save_mission_session(storage, 111, session)
        done = _finish_success(storage, 111, session)
        assert done.ok, done.text
        active_after = storage.get_active_contract(111)
        assert active_after is not None  # stage return
        assert str(active_after.get("stage")) == "return"

        # Turn-in: return home → auto-complete report.
        from app.game_logic import turn_in_quest_contract, try_auto_turn_in_contract

        storage.set_location(111, faction_home_base("Долг"))
        auto = try_auto_turn_in_contract(storage, 111)
        assert auto is not None and "сдан" in auto.lower(), auto
        assert storage.get_active_contract(111) is None

        # Manual turn-in path still works if auto didn't run yet.
        storage.set_location(111, faction_home_base("Долг"))
        storage.set_active_contract(
            111,
            {"template_key": "easy_boloto", "stage": "return", "pending_reward": 1000},
        )
        manual = turn_in_quest_contract(storage, 111)
        assert manual.ok, manual.text
        assert "100" in manual.text or "+100" in manual.text  # 10% of 1000
        assert storage.get_active_contract(111) is None

        # Daily contract bonus: once per template per day, not per turn-in repeat.
        import json
        from datetime import datetime, timezone

        from app.game_logic import DAILY_CONTRACTS_META_KEY, _daily_key

        today = _daily_key(datetime.now(timezone.utc))
        storage.set_meta(
            DAILY_CONTRACTS_META_KEY,
            json.dumps({"date": today, "keys": ["easy_boloto", "easy_dump"]}, ensure_ascii=False),
        )
        home_dolg = faction_home_base("Долг")
        storage.set_location(111, home_dolg)
        before_money = storage.get_character(111, refresh_energy=False).money

        storage.set_active_contract(
            111,
            {"template_key": "easy_boloto", "stage": "return", "pending_reward": 1000},
        )
        first_daily = turn_in_quest_contract(storage, 111)
        assert first_daily.ok, first_daily.text
        assert "Бонус: +500 RU" in first_daily.text
        after_first = storage.get_character(111, refresh_energy=False).money
        assert after_first >= before_money + 100 + 500  # 10% turn-in + 50% daily

        storage.set_active_contract(
            111,
            {"template_key": "easy_boloto", "stage": "return", "pending_reward": 1000},
        )
        before_repeat = storage.get_character(111, refresh_energy=False).money
        repeat_daily = turn_in_quest_contract(storage, 111)
        assert repeat_daily.ok, repeat_daily.text
        assert "Бонус: +500 RU" not in repeat_daily.text
        after_repeat = storage.get_character(111, refresh_energy=False).money
        assert after_repeat == before_repeat + 100  # only 10% turn-in

        storage.set_active_contract(
            111,
            {"template_key": "easy_dump", "stage": "return", "pending_reward": 800},
        )
        before_second = storage.get_character(111, refresh_energy=False).money
        second_daily = turn_in_quest_contract(storage, 111)
        assert second_daily.ok, second_daily.text
        assert "Бонус: +400 RU" in second_daily.text
        after_second = storage.get_character(111, refresh_energy=False).money
        assert after_second >= before_second + 80 + 400  # 10% + 50% for other daily
        storage.set_active_contract(111, None)

        # Turn-in blocked off-base.
        storage.set_active_contract(
            111,
            {"template_key": "easy_boloto", "stage": "return", "pending_reward": 500},
        )
        storage.set_location(111, "Болото")
        blocked = turn_in_quest_contract(storage, 111)
        assert not blocked.ok
        assert storage.get_active_contract(111) is not None
        storage.set_active_contract(111, None)

        # Bicycle quest mult only after bike arrival (and then consumed).
        from app.game_logic import TRANSPORT_QUEST_REWARD_MULT, build_players_faction_page_text
        from app.keyboards import players_faction_page_keyboard

        bandit_home = faction_home_base("Бандиты")
        storage.set_location(333, bandit_home)
        storage.set_last_arrival_transport(333, "bicycle")
        storage.restore_energy(333, 100)
        storage.add_item(333, "ammo_pack", 5)
        storage.add_item(333, "medkit", 5)
        bike_contract = accept_quest_contract(storage, 333, "easy_boloto")
        assert bike_contract.ok, bike_contract.text
        storage.set_location(333, "Болото")
        bike_work = run_contract_work(storage, 333)
        assert bike_work.ok, bike_work.text
        assert (bike_work.payload or {}).get("mission_active")
        bike_session = get_mission_session(storage, 333)
        assert bike_session is not None
        bike_session.collected = list(bike_session.objectives)
        bike_session.objectives_done = True
        bike_session.player = bike_session.start
        save_mission_session(storage, 333, bike_session)
        bike_done = _finish_success(storage, 333, bike_session)
        assert bike_done.ok, bike_done.text
        assert f"×{TRANSPORT_QUEST_REWARD_MULT['bicycle']:g}" in bike_done.text or "велосипед" in bike_done.text.lower()
        assert storage.get_last_arrival_transport(333) is None
        storage.set_last_arrival_transport(333, "bicycle")
        assert storage.consume_last_arrival_transport(333) == "bicycle"
        assert storage.get_last_arrival_transport(333) is None
        clear_mission_session(storage, 111)
        clear_mission_session(storage, 333)
        page_text, key, page, pages, page_players = build_players_faction_page_text(
            storage, "Долг", 0
        )
        assert "/дуэль" in page_text.lower() or "дуэль" in page_text.lower()
        kb = players_faction_page_keyboard(
            key, page=page, total_pages=pages, players=page_players, self_id=111
        )
        duel_cbs = [
            btn.callback_data
            for row in kb.inline_keyboard
            for btn in row
            if (btn.callback_data or "").startswith("duel:challenge:")
        ]
        assert len(duel_cbs) == 1
        assert duel_cbs[0].endswith(":222")

        _page_text_b, _k_b, _p_b, _pg_b, bandit_players = build_players_faction_page_text(
            storage, "Бандиты", 0
        )
        kb_bandit = players_faction_page_keyboard(
            "Бандиты", page=0, total_pages=1, players=bandit_players, self_id=111
        )
        bandit_duel_cbs = [
            btn.callback_data
            for row in kb_bandit.inline_keyboard
            for btn in row
            if (btn.callback_data or "").startswith("duel:challenge:")
        ]
        assert len(bandit_duel_cbs) == 1
        assert bandit_duel_cbs[0].endswith(":333")

        # Bandits cannot take home-location easy dump contract.
        from app.game_logic import list_quest_contracts_for_character, list_available_travel_modes

        bandit = storage.get_character(333, refresh_energy=False)
        assert all(t.work_location != "Свалка" for t in list_quest_contracts_for_character(bandit))
        modes = {m for m, *_ in list_available_travel_modes(bandit)}
        assert "bicycle" in modes and "foot" in modes

        assert build_alliance_overview(storage, 111)
        assert build_economy_overview(storage, 111)

        # Raids.
        raid_create = create_or_join_faction_raid(storage, 111, "Янтарь")
        assert raid_create.ok, raid_create.text
        raid_join = create_or_join_faction_raid(storage, 222, "Янтарь")
        assert raid_join.ok, raid_join.text
        raid_launch = launch_open_raid(storage, 111)
        assert raid_launch.ok, raid_launch.text
        assert raid_launch.tactical_raid
        from app.raid_grid import clear_raid_grid_session, get_raid_grid_session_by_player

        rgrid_session = get_raid_grid_session_by_player(storage, 111)
        assert rgrid_session is not None
        assert rgrid_session.player_ids == [111, 222]
        assert rgrid_session.participant_ids() == [111, 222]
        clear_raid_grid_session(storage, rgrid_session)
        storage.finish_raid(int(rgrid_session.raid_id), status="cancelled", result_text="smoke cleanup")
        assert build_raids_overview(storage, 111)

        # Depot raids (warehouse/garage) — tactical map + legacy raid_kind fix.
        from app.game_logic import (
            create_or_join_depot_raid,
            get_faction_garage,
            _set_faction_garage,
            resolve_open_raid_kind,
        )

        bandit_garage = get_faction_garage(storage, "Бандиты")
        bandit_garage["gasoline"] = 4
        _set_faction_garage(storage, "Бандиты", bandit_garage)
        storage.change_faction_warehouse_item("Бандиты", "ammo_pack", 6)
        depot_create = create_or_join_depot_raid(storage, 111, "Бандиты", depot="warehouse")
        assert depot_create.ok, depot_create.text
        depot_join = create_or_join_depot_raid(storage, 222, "Бандиты", depot="warehouse")
        assert depot_join.ok, depot_join.text
        assert depot_join.payload and depot_join.payload.get("notify")
        join_notify = depot_join.payload["notify"]
        assert any(int(item[0]) == 222 for item in join_notify)
        assert any(int(item[0]) == 111 for item in join_notify)
        open_depot = storage.get_open_raid_for_faction("Долг")
        assert open_depot is not None
        with storage._connect() as conn:
            conn.execute("UPDATE raids SET raid_kind = 'lair' WHERE id = ?", (int(open_depot["id"]),))
        open_depot = storage.get_open_raid_for_faction("Долг")
        assert resolve_open_raid_kind(open_depot) == "warehouse"
        depot_launch = launch_open_raid(storage, 111)
        assert depot_launch.ok, depot_launch.text
        assert depot_launch.tactical_raid
        depot_session = get_raid_grid_session_by_player(storage, 111)
        assert depot_session is not None
        assert depot_session.raid_kind == "warehouse"
        clear_raid_grid_session(storage, depot_session)
        storage.finish_raid(int(depot_session.raid_id), status="cancelled", result_text="smoke depot cleanup")

        # Mutants must not occupy player cells (melee from adjacent, lunge and return).
        from app.raid_grid import RaidGridSession, _hostile_turn

        mutant_session = RaidGridSession(
            session_id="mutest",
            raid_id=9999,
            raid_kind="lair",
            location_label="test",
            attacker_faction="Долг",
            player_ids=[111, 222],
        )
        mutant_session.grid = 9
        mutant_session.set_pos(111, (4, 4))
        mutant_session.set_pos(222, (6, 6))
        mutant_session.hp = {"111": 100, "222": 100}
        mutant_session.hostiles = [(4, 5)]
        mutant_session.hostile_types = ["mutant"]
        mutant_session.hostile_kinds = ["boar"]
        mutant_session.hostile_weapons = [""]
        _hostile_turn(storage, mutant_session)
        player_cells = {mutant_session.pos(111), mutant_session.pos(222)}
        assert all(hpos not in player_cells for hpos in mutant_session.hostiles)
        assert mutant_session.hostiles == [(4, 5)]

        # Defensive bots may reposition toward players (25% chance), never onto player cells.
        from unittest.mock import patch
        from app.tactical_combat import NPC_MOVE_CHANCE

        bot_session = RaidGridSession(
            session_id="botest",
            raid_id=9998,
            raid_kind="lair",
            location_label="test",
            attacker_faction="Долг",
            player_ids=[111],
        )
        bot_session.grid = 9
        bot_session.set_pos(111, (0, 4))
        bot_session.hp = {"111": 100}
        bot_session.hostiles = [(8, 4)]
        bot_session.hostile_types = ["bot"]
        bot_session.hostile_kinds = ["maloy"]
        bot_session.hostile_weapons = ["ПМ"]
        with patch("app.raid_grid.random.random", return_value=0.0):
            _hostile_turn(storage, bot_session)
        assert bot_session.hostiles != [(8, 4)]
        assert bot_session.hostiles[0] not in {(0, 4)}
        assert 0.0 < NPC_MOVE_CHANCE < 1.0

        # Stale rgrid session must not block a new raid launch.
        from app.raid_grid import clear_stale_raid_grid_session, start_raid_grid

        depot_create2 = create_or_join_depot_raid(storage, 111, "Бандиты", depot="garage")
        assert depot_create2.ok, depot_create2.text
        create_or_join_depot_raid(storage, 222, "Бандиты", depot="garage")
        open_garage = storage.get_open_raid_for_faction("Долг")
        assert open_garage is not None
        raid_id = int(open_garage["id"])
        stale_result, stale_session = start_raid_grid(
            storage,
            raid_id=raid_id,
            raid_kind="garage",
            location_label="Гараж «Бандиты»",
            attacker_faction="Долг",
            player_ids=[111, 222],
            target_faction="Бандиты",
        )
        assert stale_result.ok and stale_session is not None
        storage.start_raid_assault(raid_id)
        storage.finish_raid(raid_id, status="success", result_text="stale setup")
        clear_raid_grid_session(storage, stale_session)
        clear_stale_raid_grid_session(storage, 111)
        assert get_raid_grid_session_by_player(storage, 111) is None

        # War lobby.
        war_create = create_or_join_war_lobby(storage, 111, "Свалка")
        assert war_create.ok, war_create.text
        war_join = create_or_join_war_lobby(storage, 222, "Свалка")
        assert war_join.ok, war_join.text
        too_few = launch_war_lobby(storage, 111)
        assert not too_few.ok, too_few.text
        assert "5" in too_few.text
        assert build_war_lobby_overview(storage, 111)
        assert "Создал:" in build_war_lobby_overview(storage, 111)
        from app.game_logic import dissolve_war_lobby, can_dissolve_war_lobby
        assert can_dissolve_war_lobby(storage, 111)
        dissolved = dissolve_war_lobby(storage, 111)
        assert dissolved.ok, dissolved.text
        assert "Открытых военных лобби нет" in build_war_lobby_overview(storage, 111)

        war_create2 = create_or_join_war_lobby(storage, 111, "Янтарь")
        assert war_create2.ok, war_create2.text
        storage.restore_energy(111, 100)
        storage.restore_energy(222, 100)
        create_or_join_war_lobby(storage, 222, "Янтарь")
        for extra_id, extra_name in ((501, "Duty3"), (502, "Duty4"), (503, "Duty5")):
            storage.create_character(extra_id, extra_name, "Мужской")
            storage.set_faction(extra_id, "Долг")
            storage.restore_energy(extra_id, 100)
            join_extra = create_or_join_war_lobby(storage, extra_id, "Янтарь")
            assert join_extra.ok, join_extra.text
        war_launch = launch_war_lobby(storage, 111)
        assert war_launch.text
        if war_launch.tactical_cwar:
            from app.clan_war_grid import (
                clear_cwar_session,
                cwar_status_caption,
                get_cwar_session_by_player,
                render_cwar_frame,
            )

            seen: set[str] = set()
            for pid in war_launch.notify_member_ids:
                sess = get_cwar_session_by_player(storage, pid)
                if sess and sess.session_id not in seen:
                    seen.add(sess.session_id)
                    assert len(render_cwar_frame(storage, sess, pid)) > 1000
                    assert "квадрат" not in cwar_status_caption(storage, sess, pid).lower()
                    clear_cwar_session(storage, sess)
            with storage._connect() as conn:
                conn.execute(
                    "UPDATE war_lobbies SET status = 'cancelled', finished_at = datetime('now') WHERE status = 'in_progress'"
                )
        solo_assault = attack_location(storage, 111, "Свалка")
        assert not solo_assault.ok, solo_assault.text

        # Smuggling as travel run with arrival resolve.
        from app.game_logic import (
            start_smuggling_run,
            resolve_smuggling_if_pending,
            get_active_smuggling,
            abandon_smuggling_run,
            build_smuggling_overview,
            SMUGGLING_REWARD_MIN,
            SMUGGLING_REWARD_MAX,
            roll_arrival_encounter,
        )

        overview = build_smuggling_overview(storage, 111)
        assert str(SMUGGLING_REWARD_MIN) in overview and str(SMUGGLING_REWARD_MAX) in overview
        assert "лут" in overview.lower() or "курьер" in overview.lower()

        # Arrival encounter is optional; just ensure it doesn't crash.
        storage.set_location(111, "Росток")
        _ = roll_arrival_encounter(storage, 111, "Росток")

        storage.set_active_contract(111, None)
        storage.restore_energy(111, 100)
        storage.set_location(111, "Росток")
        if storage.get_character(111, refresh_energy=False).truck_owned:
            garage_deposit_truck(storage, 111)
        smuggle_start = start_smuggling_run(storage, 111, "Болото", transport_mode="foot")
        assert smuggle_start.ok, smuggle_start.text
        assert get_active_smuggling(storage, 111)
        assert "ограб" in smuggle_start.text.lower() or "контрабанд" in smuggle_start.text.lower()
        past_smuggle = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE characters SET travel_arrives_at = ? WHERE telegram_id = ?",
                (past_smuggle, 111),
            )
        storage.resolve_travel_if_due(111)
        smuggle_result = resolve_smuggling_if_pending(storage, 111)
        assert smuggle_result
        assert get_active_smuggling(storage, 111) is None
        assert abandon_smuggling_run(storage, 111).ok is False

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
        from app.game_logic import (
            buy_first_market_lot,
            create_duel_challenge,
            accept_duel,
            propose_alliance,
            process_due_travels,
        )
        from app.html_utils import html_safe

        assert html_safe("<test>") == "&lt;test&gt;"
        assert html_safe(None) == ""

        # Travel arrival notice on next action.
        storage.set_location(111, "Росток")
        travel3 = travel_to(storage, 111, "Свалка")
        assert travel3.ok, travel3.text
        past3 = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE characters SET travel_arrives_at = ? WHERE telegram_id = ?",
                (past3, 111),
            )
        dest = storage.resolve_travel_if_due(111)
        assert dest == "Свалка"
        assert storage.pop_arrival_notice(111) == "Свалка"
        assert storage.pop_arrival_notice(111) is None

        # Periodic travel push for idle player.
        storage.set_location(222, "Росток")
        travel4 = travel_to(storage, 222, "Болото")
        assert travel4.ok, travel4.text
        past4 = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage._connect() as conn:
            conn.execute(
                "UPDATE characters SET travel_arrives_at = ? WHERE telegram_id = ?",
                (past4, 222),
            )
        due = process_due_travels(storage)
        assert (222, "Болото") in due
        assert storage.get_character(222, refresh_energy=False).location == "Болото"

        # Duels.
        storage.restore_energy(111, 100)
        storage.restore_energy(222, 100)
        duel, target_msg = create_duel_challenge(storage, 111, 222)
        assert duel.ok, duel.text
        assert target_msg and "дуэль" in target_msg.lower()
        duel_result, challenger_msg = accept_duel(storage, 222, 111)
        assert duel_result.ok, duel_result.text
        assert challenger_msg
        assert duel_result.payload and duel_result.payload.get("duel_started")
        from app.duel_grid import get_duel_session_by_player, duel_shoot

        session = get_duel_session_by_player(storage, 111)
        assert session is not None
        assert session.challenger_id == 111
        assert session.target_id == 222
        shoot = duel_shoot(storage, 111, "right")
        assert shoot.ok or shoot.payload, shoot.text

        # Alliance notify payload.
        alliance = propose_alliance(storage, 111, "Бандиты")
        assert alliance.ok, alliance.text
        assert alliance.payload and alliance.payload.get("notify")

        # ensure one equipment exists in inventory
        buy_weapon = buy_item(storage, 111, "weapon_pm")
        assert buy_weapon.ok, buy_weapon.text
        lot_result = create_market_lot(storage, 111, "weapon_pm", 1)
        assert lot_result.ok, lot_result.text
        storage.change_money(222, 50000)
        market_buy = buy_first_market_lot(storage, 222)
        assert market_buy.ok, market_buy.text
        assert market_buy.payload and market_buy.payload.get("notify")
        lots_text, lots = build_market_lots_overview(storage, 222, limit=10)
        assert lots_text
        assert isinstance(lots, list)

        # Personal stash + death inventory loot.
        from app.game_logic import (
            deposit_to_personal_stash,
            withdraw_from_personal_stash,
            respawn_character,
            RESPAWN_COST_RU,
        )

        storage.set_location(111, faction_home_base("Долг"))
        storage.change_money(111, 5000)
        # Reset medkit stack for predictable death loot math.
        cur = storage.get_character(111, refresh_energy=False)
        have = int(cur.inventory.get("medkit", 0))
        if have > 0:
            storage.remove_item(111, "medkit", have)
        storage.add_item(111, "medkit", 10)
        put = deposit_to_personal_stash(storage, 111, "medkit", 3)
        assert put.ok, put.text
        assert storage.get_personal_stash(111).get("medkit") == 3
        assert storage.get_character(111, refresh_energy=False).inventory.get("medkit") == 7
        storage.change_health(111, -10_000)
        money_before = storage.get_character(111, refresh_energy=False).money
        revive = respawn_character(storage, 111)
        assert revive.ok, revive.text
        assert "доставили" in revive.text.lower() or "спасен" in revive.text.lower()
        after = storage.get_character(111, refresh_energy=False)
        assert after.health > 0
        assert after.money == money_before - RESPAWN_COST_RU
        assert after.inventory.get("medkit", 0) == 1  # 7 → keep 20% = 1
        assert storage.get_personal_stash(111).get("medkit") == 3
        take = withdraw_from_personal_stash(storage, 111, "medkit", 1)
        assert take.ok, take.text

        # Rating top achievements: top-10 / top-3 / top-1.
        from app.game_logic import (
            ACHIEVEMENT_BY_KEY,
            _progress_and_unlock_achievements,
            _player_rating_rank,
        )

        assert "rating_top_10" in ACHIEVEMENT_BY_KEY
        assert "rating_top_3" in ACHIEVEMENT_BY_KEY
        assert "rating_top_1" in ACHIEVEMENT_BY_KEY
        # Reset ratings so 111 is clearly #1.
        for tid, pts in ((111, 9000), (222, 100), (333, 50)):
            with storage._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO player_stats(telegram_id, rating_points)
                    VALUES (?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET rating_points = excluded.rating_points
                    """,
                    (tid, pts),
                )
        assert _player_rating_rank(storage, 111, limit=10) == 1
        top_text = _progress_and_unlock_achievements(storage, 111)
        unlocked = storage.get_player_achievement_keys(111)
        assert "rating_top_10" in unlocked
        assert "rating_top_3" in unlocked
        assert "rating_top_1" in unlocked
        assert "Первый среди сталкеров" in top_text or "rating_top_1" in unlocked

        # Keyboard callback sanity (basic non-empty check).
        callbacks = _all_callback_data()
        assert "contract:refresh" in callbacks
        assert "stash:menu" in callbacks
        assert "hunt:up" in callbacks
        assert "upgrade:armor" in callbacks
        assert "equip:upgrade:install" in callbacks
        assert "equip:upgrade:remove" in callbacks

        # Top gear set achievement: Nosorog + Gauss.
        storage.change_money(111, 200_000)
        buy_n = buy_item(storage, 111, "armor_nosorog")
        assert buy_n.ok, buy_n.text
        buy_g = buy_item(storage, 111, "weapon_gauss")
        assert buy_g.ok, buy_g.text
        assert "Тяжёлая артиллерия" in buy_g.text or "Тяжёлая артиллерия" in buy_n.text or (
            "nosorog_gauss" in storage.get_player_achievement_keys(111)
        )
        assert "armor_nosorog" in SHOP_ITEMS
        assert int(SHOP_ITEMS["armor_nosorog"]["buy_price"]) == 90000
        assert int(SHOP_ITEMS["weapon_gauss"]["buy_price"]) == 90000
        assert int(SHOP_ITEMS["armor_upgrade"]["buy_price"]) == 5000
        assert "rank:menu" in callbacks
        assert "war:section:scenario" in callbacks
        assert "war:section:lobby" in callbacks
        assert "war:section:assault" not in callbacks

        # Garage vehicle rental: withdraw returns to faction garage after 30 minutes.
        import json
        import random
        from datetime import datetime, timedelta, timezone

        from app.game_logic import (
            GARAGE_VEHICLE_RENTALS_META,
            _set_faction_garage,
            _steal_faction_garage,
            garage_withdraw_niva,
            get_faction_garage,
            process_due_garage_vehicle_rentals,
        )

        dolg_garage = get_faction_garage(storage, "Долг")
        dolg_garage["niva"] = 1
        dolg_garage["niva_durs"] = [77]
        _set_faction_garage(storage, "Долг", dolg_garage)
        bandit_garage = get_faction_garage(storage, "Бандиты")
        bandit_garage["niva"] = 0
        bandit_garage["niva_durs"] = []
        _set_faction_garage(storage, "Бандиты", bandit_garage)

        old_randint = random.randint

        def _force_steal(a: int, b: int) -> int:
            if a == 1 and b == 100:
                return 1
            return old_randint(a, b)

        random.randint = _force_steal
        try:
            steal_lines = _steal_faction_garage(storage, "Долг", "Бандиты")
        finally:
            random.randint = old_randint
        assert any("угнан" in line.lower() for line in steal_lines)
        assert get_faction_garage(storage, "Долг")["niva"] == 0
        assert get_faction_garage(storage, "Бандиты")["niva"] == 1
        assert storage.get_meta(GARAGE_VEHICLE_RENTALS_META) in (None, "[]", "")

        dolg_garage["niva"] = 1
        dolg_garage["niva_durs"] = [55]
        _set_faction_garage(storage, "Долг", dolg_garage)
        withdraw = garage_withdraw_niva(storage, 111)
        assert withdraw.ok, withdraw.text
        assert storage.get_character(111, refresh_energy=False).niva_owned
        assert get_faction_garage(storage, "Долг")["niva"] == 0

        raw_rentals = storage.get_meta(GARAGE_VEHICLE_RENTALS_META)
        assert raw_rentals
        rentals = json.loads(raw_rentals)
        rentals[0]["return_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        storage.set_meta(GARAGE_VEHICLE_RENTALS_META, json.dumps(rentals))
        due_rentals = process_due_garage_vehicle_rentals(storage)
        assert len(due_rentals) == 1
        assert get_faction_garage(storage, "Долг")["niva"] == 1
        assert get_faction_garage(storage, "Долг")["niva_durs"] == [55]
        assert not storage.get_character(111, refresh_energy=False).niva_owned

        # Season rating leaderboard + exclusive rewards.
        from app.game_logic import (
            RATING_SEASON_META_KEY,
            SEASON_REWARD_ITEM_KEYS,
            build_season_rating_overview,
            get_rating_season,
            process_rating_season,
        )

        assert "weapon_season_champion" in SEASON_REWARD_ITEM_KEYS
        assert "armor_season_bronze" in SEASON_REWARD_ITEM_KEYS
        assert "weapon_season_champion" not in SHOP_ITEMS
        denied_season_buy = buy_item(storage, 111, "weapon_season_champion")
        assert not denied_season_buy.ok
        assert "торговца" in denied_season_buy.text.lower() or "эксклюзив" in denied_season_buy.text.lower()

        for tid, pts in ((111, 500), (222, 300), (333, 100)):
            with storage._connect() as conn:
                storage._ensure_player_stats_row(conn, tid)
                conn.execute(
                    "UPDATE player_stats SET season_rating = ? WHERE telegram_id = ?",
                    (pts, tid),
                )
        season_text, _pg, _pages = build_season_rating_overview(storage, 111, page=0)
        assert "Сезонный рейтинг" in season_text
        assert "Чемпион Зоны" in season_text
        assert "#1" in season_text or "1." in season_text

        season = get_rating_season(storage)
        past_season = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        storage.set_meta(
            RATING_SEASON_META_KEY,
            json.dumps({**season, "ends_at": past_season}, ensure_ascii=False),
        )
        end_message = process_rating_season(storage)
        assert end_message
        assert "Чемпион Зоны" in end_message
        inv111 = storage.get_character(111, refresh_energy=False).inventory
        assert inv111.get("weapon_season_champion", 0) >= 1
        assert inv111.get("armor_season_champion", 0) >= 1
        inv222 = storage.get_character(222, refresh_energy=False).inventory
        assert inv222.get("weapon_season_silver", 0) >= 1
        inv333 = storage.get_character(333, refresh_energy=False).inventory
        assert inv333.get("armor_season_bronze", 0) >= 1

        _, _, missing_callbacks = _callback_handler_coverage()
        assert not missing_callbacks, f"Missing callback handlers: {', '.join(missing_callbacks)}"

        # Label map sanity (no missing key for new items).
        assert "detector_otklik" in ITEM_LABELS
        assert "sleeping_bag" in ITEM_LABELS


if __name__ == "__main__":
    run_smoke_check()
    print("Smoke check passed.")
