"""Проверка: игрок уже в другом активном режиме."""

from __future__ import annotations

from app.storage import Storage


def _unlink_from_shared_sessions(storage: Storage, telegram_id: int) -> None:
    """Снять привязку мёртвого игрока к групповому бою, не уничтожая сессию для остальных."""
    from app.coop_mission import _player_key as coop_player_key
    from app.coop_mission import get_coop_session_by_player
    from app.neutral_capture import _player_key as ncap_player_key
    from app.neutral_capture import get_ncap_session
    from app.clan_war_grid import _player_key as cwar_player_key
    from app.clan_war_grid import get_cwar_session_by_player
    from app.raid_grid import _player_key as rgrid_player_key
    from app.raid_grid import get_raid_grid_session_by_player

    if get_coop_session_by_player(storage, telegram_id) is not None:
        storage.delete_meta(coop_player_key(telegram_id))
    if get_ncap_session(storage, telegram_id) is not None:
        storage.delete_meta(ncap_player_key(telegram_id))
    if get_cwar_session_by_player(storage, telegram_id) is not None:
        storage.delete_meta(cwar_player_key(telegram_id))
    if get_raid_grid_session_by_player(storage, telegram_id) is not None:
        storage.delete_meta(rgrid_player_key(telegram_id))


def clear_all_activity_sessions(storage: Storage, telegram_id: int) -> None:
    """Снять все активные режимы — после смерти или респавна."""
    from app.quest_mission import clear_mission_session, get_mission_session
    from app.artifact_hunt import clear_hunt_session, get_hunt_session
    from app.coop_mission import clear_coop_session, get_coop_session_by_player
    from app.neutral_capture import clear_ncap_session, get_ncap_session
    from app.clan_war_grid import clear_cwar_session, get_cwar_session_by_player
    from app.duel_grid import clear_duel_session, get_duel_session_by_player
    from app.raid_grid import clear_raid_grid_session, get_raid_grid_session_by_player
    from app.arena_grid import clear_arena_session, get_arena_session

    if get_mission_session(storage, telegram_id):
        clear_mission_session(storage, telegram_id)
        storage.set_active_contract(telegram_id, None)

    if get_hunt_session(storage, telegram_id):
        clear_hunt_session(storage, telegram_id)

    coop = get_coop_session_by_player(storage, telegram_id)
    if coop is not None:
        clear_coop_session(storage, coop)

    ncap = get_ncap_session(storage, telegram_id)
    if ncap is not None:
        clear_ncap_session(storage, ncap)

    cwar = get_cwar_session_by_player(storage, telegram_id)
    if cwar is not None:
        clear_cwar_session(storage, cwar)

    duel = get_duel_session_by_player(storage, telegram_id)
    if duel is not None:
        clear_duel_session(storage, duel)

    rgrid = get_raid_grid_session_by_player(storage, telegram_id)
    if rgrid is not None:
        clear_raid_grid_session(storage, rgrid)

    arena = get_arena_session(storage, telegram_id)
    if arena is not None:
        clear_arena_session(storage, arena)


def clear_stale_activity_for_dead_player(storage: Storage, telegram_id: int) -> None:
    """Мёртвый игрок не должен оставаться «занятым» вылазкой или боем."""
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.health > 0:
        return

    from app.quest_mission import clear_mission_session, get_mission_session
    from app.artifact_hunt import clear_hunt_session, get_hunt_session
    from app.duel_grid import clear_duel_session, get_duel_session_by_player
    from app.arena_grid import clear_arena_session, get_arena_session

    if get_mission_session(storage, telegram_id):
        clear_mission_session(storage, telegram_id)
        storage.set_active_contract(telegram_id, None)

    if get_hunt_session(storage, telegram_id):
        clear_hunt_session(storage, telegram_id)

    duel = get_duel_session_by_player(storage, telegram_id)
    if duel is not None:
        clear_duel_session(storage, duel)

    arena = get_arena_session(storage, telegram_id)
    if arena is not None:
        clear_arena_session(storage, arena)

    _unlink_from_shared_sessions(storage, telegram_id)


def recover_stuck_player(storage: Storage, telegram_id: int, *, force_clear: bool = False) -> tuple[bool, int]:
    """Сбросить зависшие режимы. Возвращает (is_dead, health)."""
    if force_clear:
        clear_all_activity_sessions(storage, telegram_id)
    else:
        clear_stale_activity_for_dead_player(storage, telegram_id)
    player = storage.get_character(telegram_id, refresh_energy=True)
    if player is None:
        return False, 0
    return player.health <= 0, int(player.health)


def player_busy_reason(storage: Storage, telegram_id: int, *, skip: str | None = None) -> str | None:
    """Вернёт текст блокировки или None если свободен. skip: duel|coop|quest|hunt|cwar|ncap|rgrid|arena|travel|smuggle."""
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is not None and player.health <= 0:
        clear_stale_activity_for_dead_player(storage, telegram_id)
        return None

    from app.duel_grid import get_duel_session_by_player
    from app.coop_mission import get_coop_session_by_player, get_coop_lobby_by_player
    from app.quest_mission import get_mission_session
    from app.artifact_hunt import get_hunt_session
    from app.clan_war_grid import get_cwar_session_by_player
    from app.neutral_capture import get_ncap_session, get_ncap_lobby_by_player
    from app.game_logic import is_traveling

    if skip != "duel" and get_duel_session_by_player(storage, telegram_id):
        return "Ты в тактической дуэли — сначала закончи бой."
    if skip != "cwar" and get_cwar_session_by_player(storage, telegram_id):
        return "Ты в тактическом штурме — сначала закончи бой."
    if skip != "rgrid":
        from app.raid_grid import get_raid_grid_session_by_player

        if get_raid_grid_session_by_player(storage, telegram_id):
            return "Ты в тактическом рейде — сначала закончи бой."
    if skip != "ncap" and get_ncap_session(storage, telegram_id):
        return "Ты захватываешь нейтральную точку — сначала закончи."
    if skip != "ncap" and get_ncap_lobby_by_player(storage, telegram_id):
        return "Ты в группе захвата нейтральной точки — сначала выйди или начни вылазку."
    if skip != "arena":
        from app.arena_grid import get_arena_session

        if get_arena_session(storage, telegram_id):
            return "Ты на арене — сначала закончи бой."
    if skip != "coop":
        if get_coop_session_by_player(storage, telegram_id):
            return "Ты на кооп-вылазке — сначала закончи миссию."
        if get_coop_lobby_by_player(storage, telegram_id):
            return "Ты в кооп-группе — выйди или начни вылазку."
    if skip != "quest" and get_mission_session(storage, telegram_id):
        return "Ты на вылазке по контракту — сначала закончи или сваливай."
    if skip != "hunt" and get_hunt_session(storage, telegram_id):
        return "Ты на охоте за артефактами — сначала закончи или сваливай."
    if skip != "smuggle":
        from app.game_logic import get_active_smuggling
        from app.smuggle_mission import get_smuggle_session

        if get_smuggle_session(storage, telegram_id):
            return "Ты на тактическом рейсе контрабанды — пройди маршрут или сбрось груз."
        if get_active_smuggling(storage, telegram_id):
            return "Ты на рейсе контрабанды — сначала заверши доставку."
    if skip != "travel":
        if player is not None and is_traveling(player):
            return "Ты в пути — дождись прибытия."
    return None
