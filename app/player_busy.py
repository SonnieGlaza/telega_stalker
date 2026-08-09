"""Проверка: игрок уже в другом активном режиме."""

from __future__ import annotations

from app.storage import Storage


def player_busy_reason(storage: Storage, telegram_id: int, *, skip: str | None = None) -> str | None:
    """Вернёт текст блокировки или None если свободен. skip: duel|coop|quest|hunt|cwar|ncap|rgrid|arena|travel|smuggle."""
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

        if get_active_smuggling(storage, telegram_id):
            return "Ты на рейсе контрабанды — сначала заверши доставку."
    if skip != "travel":
        player = storage.get_character(telegram_id, refresh_energy=False)
        if player is not None and is_traveling(player):
            return "Ты в пути — дождись прибытия."
    return None
