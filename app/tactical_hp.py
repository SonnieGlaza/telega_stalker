"""HP и аптечки в тактических режимах (дуэль, кооп) — отдельно от БД до конца боя."""

from __future__ import annotations

from app.game_logic import (
    ITEM_LABELS,
    ActionResult,
    MEDKIT_EFFECTS,
    effective_max_health,
)
from app.storage import Storage


def use_tactical_medkit(storage: Storage, telegram_id: int, current_hp: int) -> tuple[ActionResult, int]:
    """Потратить аптечку и вернуть новое HP на поле (не трогая БД до конца боя)."""
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return ActionResult(False, "Персонаж не найден."), current_hp
    max_hp = effective_max_health(player)
    if current_hp >= max_hp:
        return ActionResult(False, "Здоровье на поле уже полное."), current_hp
    for key in ("medkit_science", "medkit_army", "medkit"):
        if int(player.inventory.get(key, 0)) <= 0:
            continue
        effect = MEDKIT_EFFECTS.get(key)
        if effect is None:
            continue
        label = ITEM_LABELS.get(key, key)
        heal_cap = int(effect["heal"])
        heal_amount = min(heal_cap, max_hp - current_hp)
        if heal_amount <= 0:
            return ActionResult(False, "Здоровье на поле уже полное."), current_hp
        if not storage.remove_item(telegram_id, key, 1):
            continue
        new_hp = min(max_hp, current_hp + heal_amount)
        rad_delta = int(effect.get("radiation", 0))
        if rad_delta < 0 and player.radiation > 0:
            storage.adjust_survival(telegram_id, radiation_delta=rad_delta)
            rad_note = f", {rad_delta} рад"
        else:
            rad_note = ""
        return ActionResult(True, f"Ты использовал {label}: +{heal_amount} HP{rad_note}."), new_hp
    return ActionResult(False, "Нет аптечки в инвентаре."), current_hp


def sync_session_hp_to_db(
    storage: Storage,
    telegram_id: int,
    session_hp: int,
    *,
    force: bool = False,
) -> None:
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        return
    session_hp = int(session_hp)
    # Респавн / отвязка: не затирать живого игрока старым HP=0 из JSON сессии.
    if not force and session_hp <= 0 and player.health > 0:
        return
    max_hp = effective_max_health(player)
    delta = session_hp - int(player.health)
    if delta != 0:
        storage.change_health(telegram_id, delta, max_health=max_hp)


def commit_tactical_death(
    storage: Storage,
    telegram_id: int,
    session_hp: int = 0,
    *,
    cause: str | None = None,
    killer_name: str | None = None,
) -> None:
    """Записать тактическое падение (HP=0) в БД — для экрана смерти и респавна."""
    from app.game_logic import remember_death_cause, remember_death_killer

    sync_session_hp_to_db(storage, telegram_id, int(session_hp), force=True)
    if int(session_hp) > 0:
        return
    if cause:
        remember_death_cause(storage, telegram_id, cause)
    if killer_name:
        remember_death_killer(storage, telegram_id, killer_name)
