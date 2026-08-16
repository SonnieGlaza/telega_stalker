from __future__ import annotations

import asyncio
import json
import logging
import os
from html import unescape
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    TelegramObject,
)

from app.fsm_nav import abort_fsm_if_nav, is_reply_menu_button, nav_button
from app.artifact_hunt import (
    abandon_artifact_hunt,
    get_hunt_session,
    hunt_status_caption,
    move_artifact_hunt,
    process_hunt_timeouts,
    render_hunt_for_player,
    start_artifact_hunt,
)
from app.quest_mission import (
    abandon_quest_mission,
    get_mission_session,
    mission_shoot_available,
    mission_status_caption,
    move_quest_mission,
    process_quest_timeouts,
    render_mission_for_player,
    shoot_quest_mission,
    use_mission_medkit,
)
from app.smuggle_mission import (
    abandon_smuggle_mission,
    get_smuggle_session,
    move_smuggle_mission,
    process_smuggle_timeouts,
    render_smuggle_for_player,
    smuggle_status_caption,
)
from app.duel_grid import (
    duel_forfeit,
    duel_move,
    duel_shoot,
    duel_use_medkit,
    get_duel_session_by_player,
    process_duel_turn_timeouts,
    render_duel_frame,
    save_duel_session,
)
from app.clan_war_grid import (
    cwar_move,
    cwar_shoot,
    cwar_status_caption,
    cwar_use_medkit,
    get_cwar_session_by_player,
    process_cwar_turn_timeouts,
    render_cwar_frame,
    save_cwar_session,
)
from app.raid_grid import (
    clear_stale_raid_grid_session,
    find_raid_grid_session_for_faction,
    get_raid_grid_session_by_player,
    process_rgrid_turn_timeouts,
    render_rgrid_frame,
    rgrid_forfeit,
    rgrid_move,
    rgrid_revive_ally,
    rgrid_shoot,
    rgrid_status_caption,
    rgrid_use_medkit,
    save_raid_grid_session,
)
from app.neutral_capture import (
    NCAP_MIN_MEMBERS,
    get_ncap_lobby_by_player,
    get_ncap_session,
    join_ncap_lobby,
    leave_ncap_lobby,
    ncap_forfeit,
    ncap_lobby_menu_text,
    ncap_move,
    ncap_shoot,
    ncap_status_caption,
    ncap_use_medkit,
    process_ncap_turn_timeouts,
    render_ncap_frame,
    save_ncap_session,
    start_ncap_from_lobby,
)
from app.arena_grid import (
    arena_forfeit,
    arena_move,
    arena_shoot,
    arena_status_caption,
    arena_use_medkit,
    get_arena_session,
    process_arena_turn_timeouts,
    render_arena_frame,
    save_arena_session,
    start_arena,
)
from app.coop_mission import (
    can_evacuate,
    coop_evacuate,
    coop_forfeit,
    coop_menu_text,
    coop_move,
    coop_status_caption,
    coop_use_medkit,
    create_coop_lobby,
    get_coop_lobby_by_player,
    get_coop_session_by_player,
    join_coop_lobby,
    leave_coop_lobby,
    list_open_coop_lobbies,
    process_coop_turn_timeouts,
    render_coop_frame,
    save_coop_session,
    start_coop_mission,
)
from app.config import load_settings
from app.html_utils import html_safe as h, nickname_validation_error
from app.game_logic import (
    ActionResult,
    apply_referral_rewards,
    build_referral_link,
    parse_referral_payload,
    REFERRAL_INVITER_BONUS_RU,
    REFERRAL_STARTER_PACK,
    ITEM_LABELS,
    append_survival_craving_notice,
    attack_location,
    start_smuggling_run,
    abandon_smuggling_run,
    resolve_smuggling_if_pending,
    build_smuggling_overview,
    list_smuggling_destinations,
    get_active_smuggling,
    roll_arrival_encounter,
    faction_home_base,
    DUEL_LOSER_MONEY_PERCENT,
    DUEL_LOSER_MONEY_CAP,
    DUEL_LOSER_HP_REMAINING,
    TRANSFER_FEE_PERCENT,
    TRAVEL_SPEED_BICYCLE,
    TRAVEL_SPEED_NIVA,
    TRAVEL_SPEED_TRUCK,
    TRANSPORT_QUEST_REWARD_MULT,
    RESOURCE_POINT_INCOME_PER_HOUR,
    BASE_POINT_INCOME_PER_HOUR,
    build_achievements_overview,
    build_character_stats_overview,
    build_economy_overview,
    build_faction_group_overview,
    build_events_overview,
    build_raids_overview,
    build_rating_overview,
    build_season_rating_overview,
    build_rating_menu_text,
    BULK_BUY_ITEM_KEYS,
    SHOP_ITEMS,
    buy_item,
    buy_first_faction_auction,
    cancel_own_first_auction,
    build_exchange_lots_overview,
    buy_exchange_lot,
    EXCHANGE_SELL_FEE_PERCENT,
    cancel_own_auction,
    cancel_all_raids_by_leader,
    cancel_raid_by_leader,
    create_faction_auction,
    create_or_join_faction_raid,
    create_or_join_depot_raid,
    launch_open_raid,
    resolve_open_raid_kind,
    list_war_enemy_factions,
    DEPOT_RAID_KINDS,
    build_quest_overview,
    accept_quest_contract,
    cancel_quest_contract,
    try_auto_turn_in_contract,
    run_contract_work,
    is_traveling,
    travel_status_text,
    travel_status_with_smuggle,
    format_location_display,
    QUEST_CONTRACTS,
    apply_controlled_points_income,
    process_emission_cycle,
    process_rating_season,
    DAILY_CONTRACT_BONUS_PERCENT,
    WEEKLY_CONTRACT_BONUS_PERCENT,
    NCAP_SUCCESS_PAY_RU,
    WAR_SUCCESS_PAY_RU,
    WAR_ALLY_SUCCESS_PAY_RU,
    WAR_ALLY_SUCCESS_RATING,
    WAR_LOBBY_ENERGY_COST,
    RATING_REWARD,
    QUESTS,
    QUEST_RATING_BY_DIFFICULTY,
    ARTIFACT_SEARCH_ENERGY_COST,
    DEPOT_RAID_ENERGY_COST,
    TOPUP_RATE_RU_PER_STAR,
    process_due_travels,
    process_due_garage_vehicle_rentals,
    collect_travel_eta_notices,
    process_zone_event_cycle,
    build_players_root_text,
    build_players_faction_page_text,
    trader_screen_text,
    touch_player_activity,
    build_faction_broadcast_text,
    list_faction_broadcast_targets,
    deposit_to_faction_warehouse,
    garage_deposit_fuel,
    garage_withdraw_fuel,
    garage_deposit_niva,
    garage_withdraw_niva,
    garage_deposit_truck,
    garage_withdraw_truck,
    request_garage_vehicle_rental,
    approve_garage_rental_request,
    deny_garage_rental_request,
    build_garage_rental_requests_overview,
    list_garage_rental_requests_for_faction,
    can_request_garage_vehicle_rental,
    format_inventory,
    repair_gear,
    upgrade_armor,
    sell_item,
    list_owned_trader_sell_buttons,
    trader_sell_categories_with_stock,
    travel_to,
    list_available_travel_modes,
    describe_travel_fuel_status,
    can_travel_by_truck,
    use_energy_drink,
    use_medkit,
    use_medkit_army,
    use_medkit_science,
    repair_truck,
    repair_niva,
    use_vodka,
    use_antirad,
    use_bread,
    use_sausage,
    use_stew,
    use_water,
    use_mineralka,
    use_beard_tea,
    open_stash,
    transfer_money_with_fee,
    create_duel_challenge,
    accept_duel,
    decline_duel,
    create_or_join_war_lobby,
    launch_war_lobby,
    list_assaultable_locations,
    dissolve_war_lobby,
    can_dissolve_war_lobby,
    build_war_lobby_overview,
    transfer_location_to_ally,
    create_market_lot,
    buy_market_lot,
    build_market_lots_overview,
    list_sellable_market_equipment,
    cancel_own_first_market_lot,
    list_sellable_exchange_items,
    create_custom_exchange_lot,
    withdraw_from_faction_warehouse,
    withdraw_from_faction_treasury,
    deposit_to_faction_treasury,
    can_withdraw_faction_treasury,
    can_withdraw_faction_warehouse,
    upgrade_faction_base,
    assign_faction_rank,
    build_faction_ranks_overview,
    build_faction_member_rank_pick_text,
    character_rank_title,
    build_dead_character_text,
    build_battle_death_text,
    append_death_log_once,
    build_death_log_text,
    respawn_character,
    format_personal_stash,
    deposit_to_personal_stash,
    withdraw_from_personal_stash,
    list_stash_deposit_buttons,
    list_stash_withdraw_buttons,
    build_alliance_overview,
    propose_alliance,
    break_alliance,
    accept_alliance,
    declare_war,
    equip_artifact,
    equip_armor,
    equip_weapon,
    unequip_artifact,
    install_armor_upgrade,
    unequip_armor_upgrade,
    build_equip_root_text,
    build_equip_slot_page,
    claim_daily_login,
    get_notify_prefs,
    toggle_notify_pref,
    is_notify_enabled,
    build_notify_prefs_text,
    build_tutorial_page,
    claim_tutorial_completion,
    build_clan_quest_overview,
    claim_clan_quest,
    can_claim_clan_quest,
    maybe_daily_login_hint,
)
from app.keyboards import (
    economy_keyboard,
    smuggling_keyboard,
    faction_group_keyboard,
    garage_rental_requests_keyboard,
    faction_ranks_members_keyboard,
    faction_rank_pick_keyboard,
    inventory_equipment_keyboard,
    inventory_consumables_keyboard,
    personal_stash_menu_keyboard,
    personal_stash_items_keyboard,
    personal_stash_amount_keyboard,
    artifact_hunt_keyboard,
    quest_mission_keyboard,
    smuggle_mission_keyboard,
    dead_character_keyboard,
    faction_keyboard,
    gender_keyboard,
    locations_keyboard,
    main_menu_keyboard,
    pda_keyboard,
    sortie_keyboard,
    quests_keyboard,
    quests_info_keyboard,
    travel_keyboard,
    travel_transport_keyboard,
    smuggle_transport_keyboard,
    raid_keyboard,
    topup_keyboard,
    trader_buy_categories_keyboard,
    trader_buy_armor_keyboard,
    trader_buy_consumables_keyboard,
    buy_item_qty_keyboard,
    trader_buy_consumable_qty_keyboard,
    trader_buy_gear_keyboard,
    trader_buy_repair_keyboard,
    trader_buy_weapons_keyboard,
    trader_keyboard,
    barkeep_menu_keyboard,
    barkeep_food_keyboard,
    medic_menu_keyboard,
    medic_buy_keyboard,
    tech_menu_keyboard,
    vendor_upgrade_keyboard,
    trader_sell_categories_keyboard,
    trader_sell_armor_keyboard,
    trader_sell_consumables_keyboard,
    trader_sell_gear_keyboard,
    trader_sell_trophies_keyboard,
    trader_sell_weapons_keyboard,
    equip_root_keyboard,
    equip_slot_page_keyboard,
    alliance_keyboard,
    alliance_target_keyboard,
    alliance_pending_keyboard,
    duel_challenge_keyboard,
    duel_grid_keyboard,
    cwar_grid_keyboard,
    rgrid_keyboard,
    ncap_grid_keyboard,
    ncap_lobby_keyboard,
    arena_grid_keyboard,
    coop_menu_keyboard,
    coop_lobby_list_keyboard,
    coop_mission_keyboard,
    war_lobby_keyboard,
    war_transfer_keyboard,
    market_lots_keyboard,
    market_create_select_keyboard,
    exchange_lots_keyboard,
    exchange_custom_select_keyboard,
    war_sections_keyboard,
    players_factions_keyboard,
    players_faction_page_keyboard,
    ratings_keyboard,
    rating_page_keyboard,
    notify_prefs_keyboard,
    tutorial_keyboard,
    clan_quest_keyboard,
)
from app.export_players import (
    build_players_export_files,
    load_current_payload,
    load_legacy_payload,
    migrate_payload_to_storage,
)
from app.profile_card import build_character_card
from app.faction_ranks import ranks_for_faction
from app.storage import Character, Storage, NicknameTakenError
from app.zone_map import TELEGRAM_PHOTO_MAX_BYTES, build_zone_map_image

logger = logging.getLogger(__name__)

router = Router()
storage: Storage | None = None
admin_ids: tuple[int, ...] = ()
SNAPSHOT_SYNC_SECONDS = 300
POINTS_INCOME_TICK_SECONDS = 60
TRAVEL_ETA_TICK_SECONDS = 1
TRAVEL_ETA_MSG_META_PREFIX = "travel_eta_msg:"
_travel_eta_locks: dict[int, asyncio.Lock] = {}


def _travel_eta_lock(telegram_id: int) -> asyncio.Lock:
    lock = _travel_eta_locks.get(telegram_id)
    if lock is None:
        lock = asyncio.Lock()
        _travel_eta_locks[telegram_id] = lock
    return lock


def _release_travel_eta_lock(telegram_id: int) -> None:
    _travel_eta_locks.pop(int(telegram_id), None)

TOPUP_PAYLOAD_PREFIX = "topup_stars:"
TOPUP_ALLOWED_AMOUNTS = {1, 5, 10, 25}
TOPUP_MIN_STARS = 1
TOPUP_MAX_STARS = 500
# Telegram callback alerts are limited to 200 characters.
CALLBACK_ALERT_MAX_LEN = 200


def _travel_eta_msg_key(telegram_id: int) -> str:
    return f"{TRAVEL_ETA_MSG_META_PREFIX}{int(telegram_id)}"


def get_travel_eta_message_id(storage: Storage, telegram_id: int) -> int | None:
    raw = storage.get_meta(_travel_eta_msg_key(telegram_id))
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def set_travel_eta_message_id(storage: Storage, telegram_id: int, message_id: int) -> None:
    storage.set_meta(_travel_eta_msg_key(telegram_id), str(int(message_id)))


def clear_travel_eta_message_id(storage: Storage, telegram_id: int) -> None:
    storage.delete_meta(_travel_eta_msg_key(telegram_id))
    _release_travel_eta_lock(telegram_id)


async def upsert_travel_eta_message(bot: Bot, telegram_id: int, text: str) -> None:
    """Создать или отредактировать live-сообщение о времени в пути."""
    storage = get_storage()
    clean = (text or "").strip()
    if not clean:
        return
    async with _travel_eta_lock(telegram_id):
        message_id = get_travel_eta_message_id(storage, telegram_id)
        if message_id is not None:
            try:
                await bot.edit_message_text(chat_id=telegram_id, message_id=message_id, text=clean)
                return
            except TelegramBadRequest as exc:
                low = str(exc).lower()
                if "message is not modified" in low:
                    return
                logger.debug("Travel ETA edit failed for %s: %s", telegram_id, exc)
            except Exception:
                logger.debug("Travel ETA edit error for %s", telegram_id, exc_info=True)
            clear_travel_eta_message_id(storage, telegram_id)
        try:
            sent = await bot.send_message(telegram_id, clean)
            set_travel_eta_message_id(storage, telegram_id, sent.message_id)
        except Exception:
            logger.debug("Travel ETA send failed for %s", telegram_id, exc_info=True)


async def publish_travel_live_eta(bot: Bot, telegram_id: int) -> None:
    storage = get_storage()
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or not is_traveling(player):
        return
    status = travel_status_with_smuggle(storage, telegram_id) or travel_status_text(player)
    if status:
        await upsert_travel_eta_message(bot, telegram_id, status)


def _is_stale_callback_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return "query is too old" in message or "query id is invalid" in message


def _is_benign_callback_answer_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return _is_stale_callback_error(exc) or "query already answered" in message


async def safe_callback_answer(callback: CallbackQuery, *args: Any, **kwargs: Any) -> None:
    try:
        await callback.answer(*args, **kwargs)
    except TelegramBadRequest as exc:
        if _is_benign_callback_answer_error(exc):
            logger.debug("Ignored callback answer for user %s: %s", callback.from_user.id, exc)
            return
        raise


async def edit_menu_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Any = None,
    *,
    answer_callback: bool = True,
) -> None:
    """Обновляет меню на месте, чтобы не копить сообщения в чате."""
    message = callback.message
    if message is None:
        if answer_callback:
            await safe_callback_answer(callback)
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "message is not modified" in error_text:
            if answer_callback:
                await safe_callback_answer(callback)
            return
        # Нельзя отредактировать (например, это не текст) — шлём новое и пытаемся убрать старое.
        await message.answer(text, reply_markup=reply_markup)
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
    if answer_callback:
        await safe_callback_answer(callback)


def action_notify_pairs(result: Any) -> list[tuple[int, str]]:
    payload = getattr(result, "payload", None)
    if not payload:
        return []
    raw = payload.get("notify")
    if not raw:
        return []
    pairs: list[tuple[int, str]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            pairs.append((int(item[0]), str(item[1])))
    return pairs


async def notify_player(bot: Bot, user_id: int, text: str) -> None:
    clean = action_result_text(user_id, text)
    if not clean:
        return
    try:
        await bot.send_message(user_id, clean)
    except Exception:
        logger.exception("Failed to notify player %s", user_id)


async def apply_action_notifies(bot: Bot, result: Any) -> None:
    for user_id, text in action_notify_pairs(result):
        await notify_player(bot, user_id, text)


async def reply_action_result(
    callback: CallbackQuery,
    text: str,
    *,
    bot: Bot | None = None,
    short_ack: str = "Готово",
) -> None:
    """Короткий итог — popup; длинный — сообщение в чат."""
    clean = action_result_text(callback.from_user.id, text)
    if not clean:
        await safe_callback_answer(callback)
        return
    if len(clean) <= CALLBACK_ALERT_MAX_LEN:
        await safe_callback_answer(callback, clean, show_alert=True)
        return
    await safe_callback_answer(callback, short_ack)
    message = callback.message
    if message is not None:
        await message.answer(clean)
    elif bot is not None:
        await bot.send_message(callback.from_user.id, clean)


async def finish_callback_action(
    callback: CallbackQuery,
    result: Any,
    bot: Bot,
    *,
    short_ack: str = "Готово",
) -> None:
    await reply_action_result(callback, result.text, bot=bot, short_ack=short_ack)
    await apply_action_notifies(bot, result)


async def deliver_group_result(
    callback: CallbackQuery,
    bot: Bot,
    result: Any,
    *,
    prefix: str = "📣",
    short_ack: str = "Готово",
) -> None:
    initiator_id = callback.from_user.id
    member_ids = getattr(result, "notify_member_ids", ()) or ()
    for member_id in member_ids:
        if member_id == initiator_id:
            continue
        try:
            await bot.send_message(
                member_id,
                action_result_text(member_id, f"{prefix}\n{result.text}"),
            )
        except Exception:
            logger.exception("Failed to deliver group result to %s", member_id)
    await reply_action_result(callback, result.text, bot=bot, short_ack=short_ack)
    await apply_action_notifies(bot, result)


@router.error()
async def ignore_stale_callback_query_error(event: Any) -> bool:
    exc = getattr(event, "exception", None)
    if isinstance(exc, TelegramBadRequest) and _is_stale_callback_error(exc):
        logger.debug("Ignored stale callback query error: %s", exc)
        return True
    return False


class Registration(StatesGroup):
    nickname = State()
    gender = State()
    topup_custom_stars = State()
    market_lot_price = State()
    auction_lot_price = State()
    treasury_deposit_custom = State()
    treasury_withdraw_custom = State()
    warehouse_deposit_custom = State()
    warehouse_withdraw_custom = State()


TREASURY_CUSTOM_MIN_RU = 1
TREASURY_CUSTOM_MAX_RU = 1_000_000
WAREHOUSE_CUSTOM_MIN = 1
WAREHOUSE_CUSTOM_MAX = 10_000
WAREHOUSE_CUSTOM_ITEM_KEYS = frozenset({"ammo_pack", "medkit", "energy_drink", "artifact"})
FSM_CANCEL_HINT = "\nОтмена: /cancel или «⬅️ В меню»."


def get_storage() -> Storage:
    if storage is None:
        raise RuntimeError("Storage is not initialized")
    return storage


def is_admin_user(user_id: int) -> bool:
    return user_id in admin_ids


def player_ready(player: Character) -> bool:
    return player.faction is not None


def parse_topup_stars_amount(payload: str) -> int | None:
    if not payload.startswith(TOPUP_PAYLOAD_PREFIX):
        return None
    stars_part = payload.replace(TOPUP_PAYLOAD_PREFIX, "", 1)
    try:
        stars_amount = int(stars_part)
    except ValueError:
        return None
    if stars_amount < TOPUP_MIN_STARS or stars_amount > TOPUP_MAX_STARS:
        return None
    return stars_amount


async def send_topup_invoice(bot: Bot, chat_id: int, stars_amount: int) -> None:
    ru_amount = stars_amount * TOPUP_RATE_RU_PER_STAR
    payload = f"{TOPUP_PAYLOAD_PREFIX}{stars_amount}"
    prices = [LabeledPrice(label=f"{ru_amount} RU в игре", amount=stars_amount)]
    await bot.send_invoice(
        chat_id=chat_id,
        title="Пополнение игровой валюты",
        description=f"{stars_amount}⭐ = {ru_amount} RU",
        payload=payload,
        currency="XTR",
        prices=prices,
        provider_token="",
    )


async def _apply_and_announce_referral(
    *,
    message: Message,
    bot: Bot,
    invitee_id: int,
    referrer_id: int | None,
) -> str:
    """Применяет реферал-награду и возвращает текст для новичка (или пустую строку)."""
    if referrer_id is None:
        return ""
    storage = get_storage()
    result = apply_referral_rewards(storage, invitee_id, referrer_id)
    storage.clear_pending_referrer(invitee_id)
    if not result.ok:
        return ""
    try:
        referrer = storage.get_character(int(referrer_id), refresh_energy=False)
        invitee = storage.get_character(invitee_id, refresh_energy=False)
        invitee_name = invitee.nickname if invitee else str(invitee_id)
        await bot.send_message(
            int(referrer_id),
            f"👥 По твоей ссылке в Зону пришёл {h(invitee_name)}.\n"
            f"+{REFERRAL_INVITER_BONUS_RU} RU на баланс.",
        )
        if referrer is None:
            pass
    except Exception:
        logger.exception("Failed to notify referrer %s", referrer_id)
    return f"\n\n{result.text}"


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, command: CommandObject, bot: Bot) -> None:
    telegram_id = message.from_user.id
    db = get_storage()
    referrer_id = parse_referral_payload(command.args)
    if referrer_id is not None:
        db.set_pending_referrer(telegram_id, referrer_id)
        await state.update_data(referrer_id=referrer_id)

    player = db.get_character(telegram_id, refresh_energy=False)

    # Main guard: if ID already exists in DB, never restart registration flow.
    if player is not None:
        await state.clear()
        if not player_ready(player):
            await message.answer(
                "Персонаж найден по твоему ID. Выбери группировку:",
                reply_markup=faction_keyboard(),
            )
            return
        dead = resolve_dead_player(db, telegram_id)
        if dead is not None:
            await show_death_screen(message, dead, bot=bot)
            return
        hint = maybe_daily_login_hint(db, telegram_id)
        await message.answer(
            f"С возвращением, {h(player.nickname)}! Добро пожаловать в Зону.{hint}\n\n"
            f"📢 Новости и обновления: {UPDATE_CHANNEL}",
            reply_markup=main_menu_keyboard(),
        )
        return

    # No account for this Telegram ID yet -> normal registration flow.
    player = db.get_character(telegram_id)
    if player is None:
        pending = db.get_pending_registration(telegram_id)
        current_state = await state.get_state()
        if pending:
            nickname = pending["nickname"]
            gender = pending.get("gender")
            pending_ref = db.get_pending_referrer(telegram_id)
            await state.update_data(nickname=nickname, gender=gender, referrer_id=pending_ref)
            if gender:
                # Ник+пол уже сохранены — добиваем создание персонажа после редеплоя.
                try:
                    db.create_character(telegram_id, nickname=nickname, gender=gender)
                    saved = db.get_character(telegram_id, refresh_energy=False)
                    if saved is None:
                        raise RuntimeError("character missing after resume create")
                except NicknameTakenError:
                    await state.set_state(Registration.nickname)
                    await message.answer(
                        f"Черновик найден, но прозвище «{nickname}» уже занято.\n"
                        "Введи другое прозвище:"
                    )
                    return
                except Exception:
                    logger.exception("Failed to resume character create for user %s", telegram_id)
                    await state.set_state(Registration.gender)
                    await message.answer(
                        f"Нашёл черновик: {nickname} ({gender}).\n"
                        "Не удалось завершить создание автоматически. Нажми пол ещё раз:",
                        reply_markup=gender_keyboard(),
                    )
                    return
                referral_note = await _apply_and_announce_referral(
                    message=message,
                    bot=bot,
                    invitee_id=telegram_id,
                    referrer_id=pending_ref,
                )
                await state.clear()
                uid_line = f"\nТвой ID в Зоне: {saved.player_uid}"
                await message.answer(
                    f"Персонаж восстановлен: {nickname} ({gender}).{uid_line}"
                    f"{referral_note}\nВыбери сторону:",
                    reply_markup=faction_keyboard(),
                )
                return
            await state.set_state(Registration.gender)
            await message.answer(
                f"Нашёл сохранённое прозвище: {nickname}.\nВыбери пол персонажа:",
                reply_markup=gender_keyboard(),
            )
            return
        if current_state == Registration.nickname.state:
            await message.answer("Регистрация уже начата. Введи прозвище.")
            return
        if current_state == Registration.gender.state:
            await message.answer("Регистрация уже начата. Выбери пол персонажа:", reply_markup=gender_keyboard())
            return
        await state.set_state(Registration.nickname)
        referral_hello = ""
        if referrer_id is not None and db.character_exists(referrer_id):
            referral_hello = (
                "\n\nТы пришёл по приглашению сталкера. "
                "После регистрации получишь стартовый набор."
            )
        await message.answer(
            "Telegram-бот-игра в стиле S.T.A.L.K.E.R., где это не просто "
            "«нажал кнопку — получил ответ», а целый живой мир с прогрессом игрока.\n\n"
            "Что в нем есть:\n\n"
            "👥 Группировки: можно вступать, назначать лидеров, договариваться о союзе или объявлять войну.\n"
            "⚔️ Рейды и военные лобби: игроки собираются командой и вместе атакуют точки.\n"
            "🛒 Рынок между игроками: вещи можно выставлять лотами, а не только продавать боту.\n"
            "☢️ Выживание: радиация, голод и жажда влияют на персонажа, за этим нужно следить.\n"
            "🔫 Снаряжение с износом: оружие и броня теряют прочность, и это влияет на цену продажи.\n"
            "💎 Поиск артефактов: тактическая охота на сетке (нужен детектор в инвентаре).\n"
            "❤️ Смерть и респавн: если персонаж «падает», нужно восстанавливаться по правилам игры.\n\n"
            f"Если ты готов, то назови свое имя!{referral_hello}"
        )
        return
    # Defensive fallback (should be unreachable).
    await message.answer("Сбой проверки аккаунта. Попробуй /start еще раз.")


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    storage = get_storage()
    dead = resolve_dead_player(storage, message.from_user.id)
    if dead is not None:
        await show_death_screen(message, dead)
        return
    await message.answer("Главное меню открыто.", reply_markup=main_menu_keyboard())


@router.message(Command("respawn"))
@router.message(Command("респавн"))
async def cmd_respawn(message: Message) -> None:
    """Принудительный респавн / показ экрана смерти."""
    storage = get_storage()
    telegram_id = message.from_user.id
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    from app.player_busy import recover_stuck_player

    is_dead, _hp = recover_stuck_player(storage, telegram_id, force_clear=True)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    if not is_dead and player.health > 0:
        await message.answer(
            f"Ты жив ({player.health} HP). Респавн не нужен.",
            reply_markup=main_menu_keyboard(),
        )
        return
    result = respawn_character(storage, telegram_id)
    if result.ok:
        player = storage.get_character(telegram_id, refresh_energy=False)
        await message.answer(result.text, reply_markup=main_menu_keyboard())
        if player is not None:
            await send_profile_snapshot(message, player)
        return
    await show_death_screen(message, player)


@router.message(Command("fixme"))
@router.message(Command("починить"))
async def cmd_fixme(message: Message) -> None:
    """Сброс зависших сессий (вылазка, бой) без респавна."""
    storage = get_storage()
    telegram_id = message.from_user.id
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    from app.player_busy import recover_stuck_player

    is_dead, hp = recover_stuck_player(storage, telegram_id, force_clear=True)
    player = storage.get_character(telegram_id, refresh_energy=False) or player
    if is_dead or player.health <= 0:
        await show_death_screen(message, player)
        return
    await message.answer(
        f"Зависшие режимы сброшены. HP: {hp}. Можешь играть.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("deleteplayer"))
async def admin_delete_player(message: Message, bot: Bot, command: CommandObject) -> None:
    if not is_admin_user(message.from_user.id):
        await message.answer("Команда только для администратора.")
        return
    target = (command.args or "").strip()
    if not target:
        await message.answer(
            "Использование: /deleteplayer [telegram_id|прозвище]\n"
            "Пример: /deleteplayer 8053436007"
        )
        return
    storage = get_storage()
    if target.isdigit():
        telegram_id = int(target)
    else:
        telegram_id = storage.find_telegram_id_by_nickname(target)
        if telegram_id is None:
            await message.answer(f"Игрок «{h(target)}» не найден.")
            return
    from app.game_logic import admin_delete_player_account

    result = admin_delete_player_account(storage, telegram_id)
    if result.ok:
        try:
            await bot.send_message(
                telegram_id,
                "Твой аккаунт удалён администратором.\n"
                "Чтобы начать заново — /start и выбери новое прозвище.",
            )
        except Exception:
            logger.debug("Delete-player notify failed for %s", telegram_id, exc_info=True)
    await message.answer(result.text)


@router.message(Command("setfaction"))
async def admin_set_faction(message: Message, bot: Bot, command: CommandObject) -> None:
    if not is_admin_user(message.from_user.id):
        await message.answer("Команда только для администратора.")
        return
    raw = (command.args or "").strip()
    parts = raw.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "Использование: /setfaction [telegram_id|прозвище] [группировка]\n"
            "Пример: /setfaction Воробей Нейтралы\n"
            "Группировки: Долг, Свобода, Нейтралы, Бандиты"
        )
        return
    target, faction = parts[0].strip(), parts[1].strip()
    from app.game_logic import admin_set_player_faction

    storage = get_storage()
    result = admin_set_player_faction(storage, target=target, faction=faction)
    await message.answer(result.text)
    if not result.ok:
        return
    telegram_id = (
        int(target)
        if target.isdigit()
        else storage.find_telegram_id_by_nickname(target)
    )
    if telegram_id is None:
        return
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.faction is None:
        return
    try:
        await bot.send_message(
            telegram_id,
            f"🔄 Админ перевёл тебя в группировку «{h(player.faction)}».\n"
            f"Ты на базе: {h(player.location)}.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        logger.debug("Set-faction notify failed for %s", telegram_id, exc_info=True)


@router.message(Command("unstick"))
async def admin_unstick_player(message: Message, bot: Bot, command: CommandObject) -> None:
    if not is_admin_user(message.from_user.id):
        await message.answer("Команда только для администратора.")
        return
    nickname = (command.args or "").strip()
    if not nickname:
        await message.answer("Использование: /unstick прозвище\nПример: /unstick Сиплый")
        return
    storage = get_storage()
    telegram_id = storage.find_telegram_id_by_nickname(nickname)
    if telegram_id is None:
        await message.answer(f"Игрок «{h(nickname)}» не найден.")
        return
    from app.player_busy import recover_stuck_player

    is_dead, hp = recover_stuck_player(storage, telegram_id, force_clear=True)
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        await message.answer("Персонаж не найден после сброса.")
        return
    if is_dead or player.health <= 0:
        try:
            await bot.send_message(telegram_id, "🔧 Админ разблокировал аккаунт.")
            await _send_battle_death_notice(bot, telegram_id, player)
        except Exception:
            logger.exception("Failed unstick death notify to %s", telegram_id)
        await message.answer(
            f"«{h(player.nickname)}» (id {telegram_id}): мёртв (HP {hp}), сессии сброшены, отправлен экран смерти."
        )
        return
    try:
        await bot.send_message(
            telegram_id,
            "🔧 Админ сбросил зависшие режимы. Можешь продолжать игру.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        logger.exception("Failed unstick notify to %s", telegram_id)
    await message.answer(
        f"«{h(player.nickname)}» (id {telegram_id}): жив (HP {hp}), сессии сброшены."
    )


@router.message(F.text == "⭐ Пополнить")
async def show_topup(message: Message, state: FSMContext) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await state.clear()
    await message.answer(
        f"Выбери пакет пополнения.\nКурс: 1 звезда = {TOPUP_RATE_RU_PER_STAR} RU.",
        reply_markup=topup_keyboard(),
    )


def _normalize_info_trigger(value: str | None) -> str:
    normalized = (value or "").replace("\ufe0f", "").strip().lower()
    return " ".join(normalized.split())


FACTION_CHATS = {
    "Свобода": "https://t.me/+kAvQ4NyrKndlNmI6",
    "Долг": "https://t.me/+IbIz9zSoruY0OTMy",
    "Нейтралы": "https://t.me/+IHxjjCKSFJQwOTky",
    "Бандиты": "https://t.me/+cP-Eihx_QFo0MTAy",
}
COMMON_CHAT = "https://t.me/+R0mfqDJ_HCUyOTI6"
UPDATE_CHANNEL = "https://t.me/stalkerGreatWar"


def _build_pda_chats_text(player: Character) -> str:
    faction_chat = FACTION_CHATS.get(player.faction or "")
    lines = [
        "📟 КПК — связь",
        "",
        f"📢 Канал обновлений бота:\n{UPDATE_CHANNEL}",
        "",
        f"🌐 Общий чат Зоны:\n{COMMON_CHAT}",
    ]
    if faction_chat:
        lines.extend(
            [
                "",
                f"🛡️ Чат группировки «{player.faction}»:\n{faction_chat}",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "🛡️ Чат группировки появится после выбора группировки.",
            ]
        )
    return "\n".join(lines)


def _build_referral_system_text(*, referral_link: str | None = None) -> str:
    pack = ", ".join(
        f"{ITEM_LABELS.get(key, key)} x{amount}" for key, amount in REFERRAL_STARTER_PACK
    )
    if referral_link:
        link_line = f"• Твоя ссылка: {referral_link}"
    else:
        link_line = "• Ссылка появится после запуска бота с username."
    return (
        "🔗 Реферальная система\n\n"
        f"{link_line}\n"
        f"• За друга: +{REFERRAL_INVITER_BONUS_RU} RU тебе.\n"
        f"• Другу при вступлении: {pack}."
    )


def _build_info_text(player: Character) -> str:
    return (
        "ℹ️ Информация по игре\n\n"
        "Разделы меню:\n"
        "• 📟 КПК — профиль, чаты (канал обновлений + общий + фракция), рейтинг (общий + сезонный), карта, игроки, рефералка, "
        "☠️ журнал смертей (последние 5).\n"
        "• 🏕 Вылазка — война, переходы, ⚔️ арена (тренировка 8×8 на базе), рейды и 👥 кооп-вылазка.\n"
        "  В коопе: до 3 игроков, −14 энергии, 1 аптечка/боец, «🏃 Свалить» возвращает энергию; "
        "эвакуация раненого (рядом + тащить на старт). "
        "В рейде: «💊 Поднять» союзника "
        "на соседней клетке (аптечка из инвентаря, ≈40% HP).\n"
        "• 👥 Группировка — склад/казна/гараж: сдать может любой; забрать склад/гараж с 5 ранга, "
        "ранги 1–4 — запрос на аренду авто. В гараже канистры и сданные Нивы/грузовики; "
        "техника из гаража — аренда 30 мин, перед сдачей грузовика — полный ремонт.\n"
        "• 🏦 Экономика — биржа (свои лоты, фильтры по категориям: артефакты/расходники/топливо), "
        "рынок снаряжения, перевозка контрабанды.\n"
        "• 📋 Задания — контракты с переездом (есть 🗓 контракты дня и 📅 контракт недели "
        f"с бонусом +{DAILY_CONTRACT_BONUS_PERCENT}%/+{WEEKLY_CONTRACT_BONUS_PERCENT}% RU); "
        "контрабанда — рисковый курьерский рейс.\n\n"
        "Команды:\n"
        "• /start — создать персонажа или войти.\n"
        "• /menu — главное меню.\n"
        "• /cancel — отменить ввод суммы/количества.\n"
        "• /info — эта справка.\n"
        f"• /pay [id] [сумма] — перевод (комиссия {TRANSFER_FEE_PERCENT}%).\n"
        "• /дуэль [id] — вызвать на дуэль (ID в КПК → Игроки).\n"
        f"  Проигравший: HP опускается до {DUEL_LOSER_HP_REMAINING}, "
        f"−{DUEL_LOSER_MONEY_PERCENT}% денег (макс. {DUEL_LOSER_MONEY_CAP} RU).\n\n"
        "Механики:\n"
        "• 🗺 Переходы: 1 игровая минута ≈ 10 сек реально;\n"
        f"  пешком ×1, велосипед ×{TRAVEL_SPEED_BICYCLE:g}, "
        f"Нива ×{TRAVEL_SPEED_NIVA:g} + бензин, грузовик ×{TRAVEL_SPEED_TRUCK:g} + дизель. "
        "Награда за контракт (если доехал на этом транспорте): "
        f"пешком ×{TRANSPORT_QUEST_REWARD_MULT['foot']:g}, "
        f"велосипед ×{TRANSPORT_QUEST_REWARD_MULT['bicycle']:g}, "
        f"Нива ×{TRANSPORT_QUEST_REWARD_MULT['niva']:g}, "
        f"грузовик ×{TRANSPORT_QUEST_REWARD_MULT['truck']:g}. "
        "На арендованной технике нельзя слезть и идти пешком.\n"
        "• 📋 Контракты: тактическая вылазка 6×6 — обходишь или побеждаешь аномалии, "
        "мутантов и НПС; лимит ходов ~28+ (зависит от локации); "
        "ресурсы списываются при «Выполнить работу», не при принятии контракта.\n"
        "• 🗓 Контракты дня/недели: ротация в «Заданиях», бонус RU и рейтинга сверху, "
        "1 раз за период на игрока.\n"
        "• ☢️ Выброс: предупреждения за 60 и 30 мин, затем волны убийства по зонам — "
        "сначала самые опасные локации, потом остальные; на базе всегда безопасно.\n"
        "• 🚚 Контрабанда: перевозка, ограбление в пути = провал; лут важнее чистого RU.\n"
        "• 🏚 Рейды (тактика 9×9, 2–5 бойцов, 15 мин / ход 12 сек): логово, склад/гараж врага; "
        f"−18 энергии (логово) / −{DEPOT_RAID_ENERGY_COST} (склад/гараж); "
        "1 аптечка/боец; «🏳 Сдаться» = провал для всех; HP после боя сохраняется в БД.\n"
        "  Успех рейда на логово: 1400 + 180×выживших RU в казну фракции.\n"
        "  Провал логова: −110 RU, −8 рейтинга каждому (включая погибших); "
        "склад/гараж: −90 RU, −6 рейтинга.\n"
        f"• 💰 Пассив казны: ресурсы {RESOURCE_POINT_INCOME_PER_HOUR} RU/ч, "
        f"база {BASE_POINT_INCOME_PER_HOUR} RU/ч.\n"
        f"• 🔗 Реферал: пригласившему +{REFERRAL_INVITER_BONUS_RU} RU.\n"
        "• 🛏 Спальник — ×2 реген энергии.\n"
        f"• 💎 Артефакты — «📡 Поиск артефактов» в «📋 Задания»: тактическая охота "
        f"(−{ARTIFACT_SEARCH_ENERGY_COST} энергии, до 24 ходов, нужен детектор).\n"
        f"• ⚔️ Война: нейтральные — группа от {NCAP_MIN_MEMBERS} на 6×6 (+{NCAP_SUCCESS_PAY_RU} RU, +{RATING_REWARD['war_success']} рейт., "
        f"−18 энергии) или лобби от 5 на ту же точку (9×9, суммарно выгоднее команде); "
        f"занятые — только лобби (−{WAR_LOBBY_ENERGY_COST} энергии, 1 аптечка/боец, "
        f"хост +{WAR_SUCCESS_PAY_RU}/+{RATING_REWARD['war_success']} рейт., "
        f"союзники +{WAR_ALLY_SUCCESS_PAY_RU}/+{WAR_ALLY_SUCCESS_RATING} рейт.).\n"
        "• ⚔️ Арена: на домашней базе, поле 8×8, бесконечные волны; 3 аптечки арены (+45 HP); "
        "тренировка без штрафов смерти (HP/ресурсы как при входе); награда как лёгкое задание "
        f"({QUESTS['easy'].reward_min}–{QUESTS['easy'].reward_max} RU, +{QUEST_RATING_BY_DIFFICULTY['easy'][0]} рейтинга), "
        "если зачистил ≥1 волну — даже при падении.\n"
        "• 🎖 Скины по рейтингу: 0 / 500 / 2000 / 5000.\n"
        "• 📅 Сезон рейтинга: раз в 14 дней топ-3 получает эксклюзивную снарягу "
        "(🥇 пушка+броня, 🥈 пушка, 🥉 броня; у торговца не продаётся).\n\n"
        "Чаты и рефералка: 📟 КПК → 💬 Чаты.\n"
        f"Канал обновлений: {UPDATE_CHANNEL}"
    )


@router.message(F.text == "ℹ️ Информация")
async def show_info(message: Message, state: FSMContext, bot: Bot) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await state.clear()
    await message.answer(_build_info_text(player))


@router.callback_query(F.data.startswith("topup:"))
async def handle_topup(callback: CallbackQuery, bot: Bot, state: FSMContext) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return

    parts = (callback.data or "").split(":", maxsplit=1)
    if len(parts) != 2:
        await callback.answer("Некорректный пакет пополнения.", show_alert=True)
        return
    option = parts[1]
    if option == "custom":
        await state.set_state(Registration.topup_custom_stars)
        await callback.message.answer(
            f"Введи количество звёзд для пополнения (от {TOPUP_MIN_STARS} до {TOPUP_MAX_STARS}).\n"
            "Отмена: /cancel или «⬅️ В меню»."
        )
        await callback.answer()
        return

    try:
        stars_amount = int(option)
    except ValueError:
        await callback.answer("Некорректный пакет пополнения.", show_alert=True)
        return
    if stars_amount not in TOPUP_ALLOWED_AMOUNTS:
        await callback.answer("Пакет пополнения недоступен.", show_alert=True)
        return

    await state.clear()
    await send_topup_invoice(bot=bot, chat_id=callback.from_user.id, stars_amount=stars_amount)
    await callback.answer()


@router.message(Registration.topup_custom_stars)
async def process_custom_topup_stars(message: Message, state: FSMContext, bot: Bot) -> None:
    if await abort_fsm_if_nav(message, state):
        return
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return

    raw_value = (message.text or "").strip()
    try:
        stars_amount = int(raw_value)
    except ValueError:
        await message.answer("Нужно ввести целое число звёзд, например: 7")
        return
    if stars_amount < TOPUP_MIN_STARS or stars_amount > TOPUP_MAX_STARS:
        await message.answer(
            f"Некорректное количество. Допустимо от {TOPUP_MIN_STARS} до {TOPUP_MAX_STARS} звёзд."
        )
        return

    await state.clear()
    await send_topup_invoice(bot=bot, chat_id=message.from_user.id, stars_amount=stars_amount)


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    payload = pre_checkout_query.invoice_payload or ""
    stars_amount = parse_topup_stars_amount(payload)
    if stars_amount is None:
        await pre_checkout_query.answer(ok=False, error_message="Некорректный платеж.")
        return
    if pre_checkout_query.currency != "XTR":
        await pre_checkout_query.answer(ok=False, error_message="Поддерживается только оплата звездами.")
        return
    if pre_checkout_query.total_amount != stars_amount:
        await pre_checkout_query.answer(ok=False, error_message="Сумма платежа не совпадает с пакетом.")
        return
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message) -> None:
    payment = message.successful_payment
    if payment is None:
        return
    payload = payment.invoice_payload or ""
    stars_amount = parse_topup_stars_amount(payload)
    if stars_amount is None:
        return
    if payment.currency != "XTR":
        await message.answer("Платеж получен в неподдерживаемой валюте.")
        return
    if payment.total_amount != stars_amount:
        await message.answer("Платеж получен, но сумма не совпадает с пакетом пополнения.")
        return

    ru_amount = stars_amount * TOPUP_RATE_RU_PER_STAR
    db = get_storage()
    applied, already_applied = db.apply_topup_payment(
        telegram_id=message.from_user.id,
        payment_charge_id=payment.telegram_payment_charge_id,
        stars_amount=stars_amount,
        ru_amount=ru_amount,
    )
    if already_applied:
        await message.answer("Этот платеж уже был зачислен ранее.")
        return
    if not applied:
        await message.answer("Платеж успешен, но начисление не выполнено. Обратись к администратору.")
        return
    player = db.get_character(message.from_user.id, refresh_energy=False)
    balance = player.money if player is not None else "неизвестно"
    await message.answer(
        f"Оплата прошла успешно: {stars_amount}⭐.\n"
        f"Зачислено: {ru_amount} RU.\n"
        f"Баланс: {balance} RU."
    )


ADMIN_GIVE_MAX_RU = 500_000


@router.message(Command("give"))
async def cmd_give(message: Message) -> None:
    sender_id = message.from_user.id
    if not is_admin_user(sender_id):
        await message.answer("Команда доступна только администратору.")
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.answer("Использование: /give [telegram_id] [amount]")
        return

    try:
        target_telegram_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("Telegram ID и amount должны быть целыми числами.")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть положительным числом.")
        return
    if amount > ADMIN_GIVE_MAX_RU:
        await message.answer(f"Максимум за одну выдачу: {ADMIN_GIVE_MAX_RU} RU.")
        return

    db = get_storage()
    target = db.get_character(target_telegram_id, refresh_energy=False)
    if target is None:
        await message.answer("Игрок с таким Telegram ID не найден.")
        return

    if not db.change_money(target_telegram_id, amount):
        await message.answer("Не удалось зачислить валюту.")
        return

    updated_target = db.get_character(target_telegram_id, refresh_energy=False)
    updated_balance = updated_target.money if updated_target else target.money
    await message.answer(
        f"Выдано {amount} RU игроку {target.nickname} ({target_telegram_id}).\n"
        f"Новый баланс: {updated_balance} RU."
    )


@router.message(Command("settravel"))
async def admin_set_travel_eta(message: Message, bot: Bot) -> None:
    if not is_admin_user(message.from_user.id):
        await message.answer("Команда доступна только администратору.")
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.answer("Использование: /settravel [telegram_id] [seconds]")
        return

    try:
        target_telegram_id = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        await message.answer("Telegram ID и seconds должны быть целыми числами.")
        return

    if seconds < 0:
        await message.answer("Секунды не могут быть отрицательными.")
        return

    storage = get_storage()
    target = storage.get_character(target_telegram_id, refresh_energy=False)
    if target is None:
        await message.answer("Игрок с таким Telegram ID не найден.")
        return
    if not is_traveling(target):
        await message.answer(
            f"«{target.nickname}» сейчас не в пути "
            f"(локация: {target.location})."
        )
        return

    from datetime import timedelta

    from app.storage import utc_now

    arrives_at = utc_now() + timedelta(seconds=seconds)
    if not storage.set_travel_arrives_at(target_telegram_id, arrives_at):
        await message.answer("Не удалось обновить время в пути.")
        return

    await message.answer(
        f"Время в пути для {target.nickname} ({target_telegram_id}): {seconds} сек.\n"
        f"Маршрут → «{target.travel_destination}»."
    )
    await publish_travel_live_eta(bot, target_telegram_id)


@router.message(Command("leader"))
@router.message(Command("commander"))
async def cmd_set_leader(message: Message, bot: Bot) -> None:
    sender_id = message.from_user.id
    if not is_admin_user(sender_id):
        await message.answer("Команда доступна только администратору.")
        return

    parts = (message.text or "").strip().split(maxsplit=2)
    if len(parts) != 3:
        await message.answer(
            "Назначение командира группировки:\n"
            "• /commander [группировка] [telegram_id]\n"
            "• /leader [группировка] [telegram_id]\n"
            "Пример: /commander Долг 123456789"
        )
        return

    faction_name = parts[1]
    try:
        leader_id = int(parts[2])
    except ValueError:
        await message.answer("Telegram ID командира должен быть целым числом.")
        return

    db = get_storage()
    if not db.set_faction_leader(faction_name, leader_id):
        await message.answer(
            "Не удалось назначить командира. Проверь, что группировка существует, "
            "а игрок состоит в этой группировке."
        )
        return

    leader = db.get_character(leader_id, refresh_energy=False)
    leader_name = leader.nickname if leader is not None else str(leader_id)
    await message.answer(
        f"Командир группировки «{faction_name}» назначен: {leader_name} ({leader_id})."
    )
    try:
        await bot.send_message(
            leader_id,
            f"⭐ Тебя назначили командиром группировки «{faction_name}».\n"
            "Доступна кнопка «📣 Сбор» и команда /сбор для оповещения бойцов.",
        )
    except Exception:
        logger.exception("Failed to notify new faction commander %s", leader_id)


@router.message(Command("export_players"))
async def cmd_export_players(message: Message) -> None:
    sender_id = message.from_user.id
    if not is_admin_user(sender_id):
        await message.answer("Команда доступна только администратору.")
        return

    source = "unknown"
    try:
        payload, source = load_legacy_payload()
    except FileNotFoundError:
        payload, source = load_current_payload(get_storage())

    files, count = build_players_export_files(
        payload.get("characters") or [],
        payload.get("player_stats") or [],
        Path("/tmp/stalker_export"),
    )
    await message.answer(f"Выгрузка игроков: {count}\nИсточник: {source}")
    for key in ("txt", "csv", "json"):
        path = files[key]
        data = path.read_bytes()
        await message.answer_document(
            BufferedInputFile(data, filename=path.name),
            caption=f"{path.name} ({len(data)} bytes)",
        )


@router.message(Command("migrate_db"))
async def cmd_migrate_db(message: Message) -> None:
    sender_id = message.from_user.id
    if not is_admin_user(sender_id):
        await message.answer("Команда доступна только администратору.")
        return

    settings_url = (os.getenv("DATABASE_URL") or "").strip()
    if not settings_url:
        await message.answer("DATABASE_URL не задан в окружении Railway.")
        return

    try:
        payload, source = load_legacy_payload()
    except FileNotFoundError as exc:
        await message.answer(str(exc))
        return

    from app.db import normalize_database_url

    database_url = normalize_database_url(settings_url)
    export_dir = Path("/tmp/stalker_export")
    files, count = build_players_export_files(
        payload.get("characters") or [],
        payload.get("player_stats") or [],
        export_dir,
    )
    full_dump = export_dir / "full_source_dump.json"
    full_dump.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    target = Storage(
        db_path=database_url,
        snapshot_path=str(export_dir / "migration.backup.json"),
        database_url=database_url,
    )
    target.init_db()
    pg_count = migrate_payload_to_storage(target, payload)

    await message.answer(
        f"Миграция завершена.\nИсточник: {source}\n"
        f"Игроков в выгрузке: {count}\nИгроков в Postgres: {pg_count}"
    )
    await message.answer_document(
        BufferedInputFile(files["txt"].read_bytes(), filename="old_players.txt"),
        caption="Список старых игроков",
    )


@router.message(Command("dbstatus"))
async def cmd_dbstatus(message: Message) -> None:
    if not is_admin_user(message.from_user.id):
        await message.answer("Команда доступна только администратору.")
        return
    db = get_storage()
    status = db.get_db_status()
    me = db.get_character(message.from_user.id, refresh_energy=False)
    me_block = "Твой персонаж в БД: нет"
    if me is not None:
        me_block = (
            f"Твой персонаж в БД:\n"
            f"• {me.nickname} | {me.gender} | {me.faction or 'без гп'}\n"
            f"• Локация: {format_location_display(me)}\n"
            f"• HP {me.health} | энергия {me.energy}/{me.max_energy} | сила {me.gear_power}\n"
            f"• RU {me.money} | дизель {me.diesel} | бензин {me.gasoline}\n"
            f"• Нива: {'да' if me.niva_owned else 'нет'} | "
            f"Велосипед: {'да' if me.bicycle_owned else 'нет'} | "
            f"Грузовик: {'да' if me.truck_owned else 'нет'} ({me.truck_durability}%) | "
            f"Спальник: {'да' if me.sleeping_bag_owned else 'нет'}\n"
            f"• Оружие: {me.equipment.get('weapon')} ({me.equipment.get('weapon_durability')}%)\n"
            f"• Броня: {me.equipment.get('armor')} ({me.equipment.get('armor_durability')}%)\n"
            f"• Рад {me.radiation}/100 | голод {me.hunger}/100 | жажда {me.thirst}/100"
        )
    await message.answer(
        "Статус БД:\n"
        f"• backend: {status['backend']}\n"
        f"• source: {status['db_path']}\n"
        f"• telegram_id type: {status.get('telegram_id_type') or 'n/a (sqlite)'}\n"
        f"• персонажей: {status['characters']}\n"
        f"• черновиков регистрации: {status['pending_registrations']}\n"
        f"• snapshot: {status['snapshot_path']}\n\n"
        f"{me_block}"
    )


@router.message(Command("dbsave"))
async def cmd_dbsave(message: Message) -> None:
    if not is_admin_user(message.from_user.id):
        await message.answer("Команда доступна только администратору.")
        return
    db = get_storage()
    ok = db.persist_character_state(message.from_user.id)
    db.save_snapshot(force=True)
    synced = db.backfill_all_gear_power()
    if not ok:
        await message.answer(
            f"Твоего персонажа нет в БД.\nSnapshot сохранён. Синхронизировано gear_power: {synced}."
        )
        return
    player = db.get_character(message.from_user.id, refresh_energy=False)
    await message.answer(
        "Полное состояние записано в БД + snapshot.\n"
        f"Локация: {player.location if player else '?'}\n"
        f"Синхронизировано gear_power у игроков: {synced}."
    )


@router.message(Registration.nickname)
async def process_nickname(message: Message, state: FSMContext) -> None:
    existing = get_storage().get_character(message.from_user.id, refresh_energy=False)
    if existing is not None:
        await state.clear()
        if player_ready(existing):
            await message.answer(
                f"Персонаж уже зарегистрирован: {h(existing.nickname)}. Открываю меню.",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.answer(
                "Персонаж уже создан. Осталось выбрать группировку:",
                reply_markup=faction_keyboard(),
            )
        return

    nickname = (message.text or "").strip()
    nick_err = nickname_validation_error(nickname)
    if nick_err:
        await message.answer(nick_err)
        return

    db = get_storage()
    if db.is_nickname_taken(nickname, exclude_telegram_id=message.from_user.id):
        await message.answer("Это прозвище уже занято. Выбери другое.")
        return

    data = await state.get_data()
    referrer_id = data.get("referrer_id")
    if referrer_id is None:
        referrer_id = db.get_pending_referrer(message.from_user.id)
    try:
        referrer_id_int = int(referrer_id) if referrer_id is not None else None
    except (TypeError, ValueError):
        referrer_id_int = None

    try:
        db.save_pending_registration(
            message.from_user.id,
            nickname,
            step="gender",
            referrer_id=referrer_id_int,
        )
    except Exception:
        # Не блокируем регистрацию: ник всё равно в FSM, персонаж создастся на шаге пола.
        logger.exception(
            "Failed to persist pending nickname for user %s; continuing with FSM only",
            message.from_user.id,
        )

    await state.update_data(nickname=nickname, referrer_id=referrer_id_int)
    await state.set_state(Registration.gender)
    await message.answer("Отлично. Выбери пол персонажа:", reply_markup=gender_keyboard())


@router.callback_query(F.data.startswith("gender:"))
async def process_gender(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    payload = (callback.data or "").split(":", maxsplit=1)
    if len(payload) != 2:
        await safe_callback_answer(callback, "Некорректный выбор", show_alert=True)
        return

    gender_code = payload[1]
    if gender_code not in {"male", "female"}:
        await safe_callback_answer(callback, "Некорректный пол", show_alert=True)
        return
    gender = "Мужской" if gender_code == "male" else "Женский"

    # Ник/пол: FSM → черновик в БД (переживает редеплой).
    db = get_storage()
    data = await state.get_data()
    nickname = str(data.get("nickname") or "").strip()
    pending = db.get_pending_registration(callback.from_user.id)
    if not nickname and pending:
        nickname = pending.get("nickname", "")
    if not nickname:
        await state.set_state(Registration.nickname)
        await callback.message.answer(
            "Сессия регистрации сбросилась, и сохранённого прозвища нет.\n"
            "Введи прозвище заново:"
        )
        await safe_callback_answer(callback)
        return

    referrer_raw = data.get("referrer_id")
    if referrer_raw is None:
        referrer_raw = db.get_pending_referrer(callback.from_user.id)
    try:
        referrer_id = int(referrer_raw) if referrer_raw is not None else None
    except (TypeError, ValueError):
        referrer_id = None

    # Сразу пишем пол в черновик — даже если create_character упадёт, /start добьёт аккаунт.
    try:
        db.save_pending_registration(
            callback.from_user.id,
            nickname=nickname,
            gender=gender,
            step="faction",
            referrer_id=referrer_id,
        )
    except Exception:
        logger.exception(
            "Failed to persist pending gender for user %s; continuing",
            callback.from_user.id,
        )

    await state.update_data(nickname=nickname, gender=gender, referrer_id=referrer_id)

    if db.is_nickname_taken(nickname, exclude_telegram_id=callback.from_user.id):
        await state.set_state(Registration.nickname)
        await callback.message.answer(
            "Это прозвище уже занято. Введи другое прозвище:"
        )
        await safe_callback_answer(callback, "Прозвище занято", show_alert=True)
        return

    existing = db.get_character(callback.from_user.id, refresh_energy=False)
    if existing is not None:
        await state.clear()
        try:
            db.create_character(callback.from_user.id, nickname=nickname, gender=gender)
        except NicknameTakenError:
            await state.set_state(Registration.nickname)
            await callback.message.answer(
                "Это прозвище уже занято. Введи другое прозвище:"
            )
            await safe_callback_answer(callback, "Прозвище занято", show_alert=True)
            return
        except Exception:
            logger.exception("Failed to update existing character gender for %s", callback.from_user.id)
        db.clear_pending_registration(callback.from_user.id)
        if player_ready(existing):
            await callback.message.answer(
                f"Персонаж уже есть: {existing.nickname}.",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await callback.message.answer(
                "Персонаж уже создан. Выбери группировку:",
                reply_markup=faction_keyboard(),
            )
        await safe_callback_answer(callback)
        return

    try:
        db.create_character(callback.from_user.id, nickname=nickname, gender=gender)
        saved = db.get_character(callback.from_user.id, refresh_energy=False)
        if saved is None:
            raise RuntimeError("character row missing after create_character")
    except NicknameTakenError:
        await state.set_state(Registration.nickname)
        await callback.message.answer(
            "Это прозвище уже занято. Введи другое прозвище:"
        )
        await safe_callback_answer(callback, "Прозвище занято", show_alert=True)
        return
    except Exception as exc:
        logger.exception("Failed to create character for user %s", callback.from_user.id)
        await state.set_state(Registration.gender)
        await callback.message.answer(
            "Не удалось создать персонажа в базе (часто из‑за старого типа ID в Postgres).\n"
            "Черновик сохранён. После обновления бота нажми /start — аккаунт дособерётся сам.\n"
            f"Технически: {type(exc).__name__}"
        )
        await safe_callback_answer(callback, "Ошибка БД, черновик сохранён", show_alert=True)
        return

    referral_note = await _apply_and_announce_referral(
        message=callback.message,
        bot=bot,
        invitee_id=callback.from_user.id,
        referrer_id=referrer_id,
    )
    await state.clear()
    uid_line = f"\nТвой ID в Зоне: {saved.player_uid}" if saved else ""
    await callback.message.answer(
        f"Персонаж создан: {nickname} ({gender}).{uid_line}{referral_note}\nВыбери сторону:",
        reply_markup=faction_keyboard(),
    )
    await safe_callback_answer(callback)


@router.callback_query(
    F.data.in_(
        {
            "faction:Долг",
            "faction:Свобода",
            "faction:Нейтралы",
            "faction:Бандиты",
        }
    )
)
async def process_faction(callback: CallbackQuery, state: FSMContext) -> None:
    faction = (callback.data or "").split(":", maxsplit=1)[1]
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала введи /start", show_alert=True)
        return

    if player.faction is not None:
        await callback.answer(
            f"Ты уже в группировке «{player.faction}». Смена недоступна.",
            show_alert=True,
        )
        return

    db.set_faction(callback.from_user.id, faction)
    await state.clear()
    home = faction_home_base(faction)
    await callback.message.answer(
        f"Принято. Теперь ты в группировке «{faction}».\n"
        f"Тебя перебросили на домашнюю базу «{home}».\n\n"
        "С чего начать:\n"
        "1) 📋 Задания → 1–2 лёгких контракта на базе\n"
        "2) 🛒 Торговец → «Отклик» (1000) или еда/аптечки\n"
        "3) Накопи на велосипед (3500) — ускорит переходы\n\n"
        f"📢 Канал обновлений: {UPDATE_CHANNEL}\n"
        "💬 Чаты группировки и общий — в КПК → 💬 Чаты\n\n"
        "Открываю меню персонажа.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


def ensure_character(message: Message) -> Character | None:
    storage = get_storage()
    player = storage.get_character(message.from_user.id)
    if player is None:
        return None
    touch_player_activity(storage, message.from_user.id)
    return player


def _trader_text(telegram_id: int, body: str) -> str:
    return trader_screen_text(get_storage(), telegram_id, body)


async def reject_if_busy(
    message_or_callback: Message | CallbackQuery,
    telegram_id: int,
    *,
    skip: str | None = None,
) -> bool:
    from app.player_busy import player_busy_reason

    busy = player_busy_reason(get_storage(), telegram_id, skip=skip)
    if busy is None:
        return False
    if isinstance(message_or_callback, CallbackQuery):
        await safe_callback_answer(message_or_callback, busy, show_alert=True)
    else:
        await message_or_callback.answer(busy)
    return True


def _session_hp_for_player(session: Any, pid: int) -> int | None:
    hp_attr = getattr(session, "hp", None)
    if isinstance(hp_attr, dict):
        if str(pid) not in hp_attr:
            return None
        return int(hp_attr[str(pid)])
    if hasattr(session, "telegram_id") and int(session.telegram_id) == pid:
        return int(hp_attr) if hp_attr is not None else None
    return None


def _active_tactical_field_hp(storage: Storage, telegram_id: int) -> int | None:
    """HP на тактическом поле, если игрок в незавершённой сессии."""
    session_refs: list[Any] = []
    coop = get_coop_session_by_player(storage, telegram_id)
    if coop is not None and not coop.finished:
        session_refs.append(coop)
    raid = get_raid_grid_session_by_player(storage, telegram_id)
    if raid is not None and not raid.finished:
        session_refs.append(raid)
    ncap = get_ncap_session(storage, telegram_id)
    if ncap is not None and not ncap.finished:
        session_refs.append(ncap)
    cwar = get_cwar_session_by_player(storage, telegram_id)
    if cwar is not None and not cwar.finished:
        session_refs.append(cwar)
    duel = get_duel_session_by_player(storage, telegram_id)
    if duel is not None and not duel.finished:
        session_refs.append(duel)
    arena = get_arena_session(storage, telegram_id)
    if arena is not None and not getattr(arena, "finished", False):
        session_refs.append(arena)
    for session in session_refs:
        field_hp = _session_hp_for_player(session, telegram_id)
        if field_hp is not None and field_hp > 0:
            return field_hp
    return None


def _raid_grid_downed(storage: Storage, telegram_id: int) -> bool:
    session = get_raid_grid_session_by_player(storage, telegram_id)
    if session is None or getattr(session, "finished", False):
        return False
    from app.tactical_roster import is_downed_in_group_session

    return is_downed_in_group_session(session, telegram_id)


def _tactical_downed_message(storage: Storage, telegram_id: int) -> str | None:
    """Сообщение для игрока с HP=0 на поле в активной group-сессии."""
    from app.tactical_roster import is_downed_in_group_session

    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is not None and player.health <= 0:
        return None

    coop = get_coop_session_by_player(storage, telegram_id)
    if coop is not None and is_downed_in_group_session(coop, telegram_id):
        return (
            "☠️ Ты без сознания на вылазке.\n"
            "Жди эвакуации напарником или конца боя."
        )
    ncap = get_ncap_session(storage, telegram_id)
    if ncap is not None and is_downed_in_group_session(ncap, telegram_id):
        return (
            "☠️ Ты выведен из строя на захвате.\n"
            "Жди, пока союзники закончат бой."
        )
    cwar = get_cwar_session_by_player(storage, telegram_id)
    if cwar is not None and is_downed_in_group_session(cwar, telegram_id):
        return (
            "☠️ Ты без сознания на штурме.\n"
            "Жди, пока отряд закончит бой."
        )
    if _raid_grid_downed(storage, telegram_id):
        return (
            "☠️ Ты без сознания на рейде.\n"
            "Жди, пока союзник поднимет аптечкой, или пока рейд не закончится."
        )
    return None


def resolve_dead_player(
    storage: Storage,
    telegram_id: int,
    *,
    refresh_survival: bool = True,
) -> Character | None:
    """Мёртв для UI: HP=0 в БД (с учётом голода/жажды) или выведен из строя в тактике."""
    player = storage.get_character(telegram_id, refresh_energy=refresh_survival)
    if player is None:
        return None
    if player.health <= 0:
        if _active_tactical_field_hp(storage, telegram_id) is not None:
            return None
        from app.player_busy import _clear_solo_activity

        _clear_solo_activity(storage, telegram_id)
        return storage.get_character(telegram_id, refresh_energy=False)

    from app.tactical_hp import commit_tactical_death

    session_checks: list[tuple[Any, str]] = []
    raid = get_raid_grid_session_by_player(storage, telegram_id)
    if raid is not None and not raid.finished:
        session_checks.append((raid, "raid"))
    coop = get_coop_session_by_player(storage, telegram_id)
    if coop is not None and not coop.finished:
        session_checks.append((coop, "coop"))
    ncap = get_ncap_session(storage, telegram_id)
    if ncap is not None and not ncap.finished:
        session_checks.append((ncap, "combat"))
    cwar = get_cwar_session_by_player(storage, telegram_id)
    if cwar is not None and not cwar.finished:
        session_checks.append((cwar, "combat"))
    duel = get_duel_session_by_player(storage, telegram_id)
    if duel is not None and not duel.finished:
        session_checks.append((duel, "duel"))
    arena = get_arena_session(storage, telegram_id)
    if arena is not None and not getattr(arena, "finished", False):
        session_checks.append((arena, "arena"))

    for session, default_cause in session_checks:
        session_hp = _session_hp_for_player(session, telegram_id)
        if session_hp is None or session_hp > 0:
            continue
        from app.tactical_roster import is_downed_in_group_session

        if is_downed_in_group_session(session, telegram_id):
            continue
        if isinstance(getattr(session, "hp", None), int) and int(
            getattr(session, "telegram_id", 0) or 0
        ) == int(telegram_id):
            continue
        death_causes = getattr(session, "death_causes", {}) or {}
        death_killers = getattr(session, "death_killers", {}) or {}
        cause = str(death_causes.get(str(telegram_id)) or default_cause)
        killer = death_killers.get(str(telegram_id))
        commit_tactical_death(
            storage,
            telegram_id,
            0,
            cause=cause,
            killer_name=str(killer) if killer else None,
        )
        return storage.get_character(telegram_id, refresh_energy=False)

    return None


DEAD_PLAYER_CALLBACKS = frozenset({"respawn:base", "death:log"})

# Режимы с картой: смерть/урон обрабатывает свой хендлер, middleware не перехватывает.
DEATH_MIDDLEWARE_BYPASS_PREFIXES = (
    "qmission:",
    "smission:",
    "hunt:",
    "dgrid:",
    "cwar:",
    "rgrid:",
    "agrid:",
    "ncap:",
    "coop:",
)

# Команды, которые middleware не перехватывает у мёртвого (обрабатываются хендлерами).
DEAD_BYPASS_MESSAGE_COMMANDS = frozenset({
    "/respawn",
    "/респавн",
    "/fixme",
    "/починить",
    "/cancel",
})


def _build_death_text(
    player: Character,
    storage: Storage,
    *,
    where: str | None = None,
    cause: str | None = None,
    killer_name: str | None = None,
) -> str:
    if where is not None or cause is not None:
        return build_battle_death_text(
            player,
            where=where or player.location,
            cause=cause or "combat",
            storage=storage,
            killer_name=killer_name,
        )
    return build_dead_character_text(player, storage=storage)


async def show_death_screen(
    message_or_callback: Message | CallbackQuery,
    player: Character,
    *,
    bot: Bot | None = None,
    where: str | None = None,
    cause: str | None = None,
) -> None:
    storage = get_storage()
    callback: CallbackQuery | None = None
    send_bot = bot
    if isinstance(message_or_callback, CallbackQuery):
        callback = message_or_callback
        await safe_callback_answer(message_or_callback)
        send_bot = send_bot or message_or_callback.bot
    elif hasattr(message_or_callback, "bot"):
        send_bot = send_bot or message_or_callback.bot  # type: ignore[attr-defined]

    if send_bot is not None:
        msg = message_or_callback if isinstance(message_or_callback, Message) else None
        await _send_battle_death_notice(
            send_bot,
            player.telegram_id,
            player,
            callback=callback,
            message=msg,
            where=where,
            cause=cause,
        )
        return

    text = _build_death_text(player, storage, where=where, cause=cause)
    append_death_log_once(storage, player.telegram_id, text)
    plain = _plain_death_text(text)
    sent_msg: Message | None = None
    if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message is not None:
        sent_msg = await message_or_callback.message.answer(plain, parse_mode=None)
    elif isinstance(message_or_callback, Message):
        sent_msg = await message_or_callback.answer(plain, parse_mode=None)
    await _finalize_death_delivery(storage, player.telegram_id, sent_msg is not None)
    if sent_msg is not None:
        respawned = await _auto_respawn_after_death(
            sent_msg.bot,
            player.telegram_id,
            message=sent_msg,
        )
        if not respawned:
            await sent_msg.answer(
                _DEATH_FALLBACK_TEXT,
                reply_markup=dead_character_keyboard(),
                parse_mode=None,
            )


class PlayerActivityMiddleware(BaseMiddleware):
    """Отмечает активность игрока для индикатора «в сети» в списке игроков."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None:
            storage = get_storage()
            if storage.get_character(user.id, refresh_energy=False) is not None:
                touch_player_activity(storage, user.id)
        return await handler(event, data)


class DeadPlayerMenuMiddleware(BaseMiddleware):
    """Любое сообщение при HP=0 — экран смерти (кроме /respawn и /fixme)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        text = (event.text or "").strip()
        if text:
            cmd = text.split(maxsplit=1)[0].casefold()
            if cmd in DEAD_BYPASS_MESSAGE_COMMANDS:
                return await handler(event, data)
        storage = get_storage()
        telegram_id = event.from_user.id
        downed_msg = _tactical_downed_message(storage, telegram_id)
        if downed_msg is not None:
            await event.answer(downed_msg)
            return None
        player = resolve_dead_player(storage, telegram_id)
        if player is not None:
            await _send_battle_death_notice(
                event.bot,
                telegram_id,
                player,
                message=event,
            )
            return None
        return await handler(event, data)


class DeadPlayerCallbackMiddleware(BaseMiddleware):
    """Inline-кнопки при смерти: только респавн/журнал; остальное — экран смерти."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)
        callback_data = (event.data or "").strip()
        if callback_data in DEAD_PLAYER_CALLBACKS:
            return await handler(event, data)
        if callback_data.startswith(DEATH_MIDDLEWARE_BYPASS_PREFIXES):
            return await handler(event, data)
        storage = get_storage()
        telegram_id = event.from_user.id
        downed_msg = _tactical_downed_message(storage, telegram_id)
        if downed_msg is not None:
            await safe_callback_answer(event, downed_msg, show_alert=True)
            return None
        player = resolve_dead_player(storage, telegram_id, refresh_survival=False)
        if player is None:
            return await handler(event, data)
        await _ensure_death_keyboard(event, telegram_id)
        return None


async def reject_if_dead(message_or_callback: Message | CallbackQuery, player: Character) -> bool:
    """Если персонаж мёртв — показать историю смерти + клавиатуру спасения и вернуть True.

    Используй сразу после ensure_character/ensure_ready:
        player = ensure_character(message)
        if player is None: ...
        if await reject_if_dead(message, player): return
    """
    dead = resolve_dead_player(get_storage(), player.telegram_id)
    if dead is None:
        return False
    await show_death_screen(message_or_callback, dead)
    return True


async def _reject_tactical_callback_if_dead(callback: CallbackQuery) -> bool:
    """Если HP=0 в БД — кнопка респавна и True."""
    storage = get_storage()
    telegram_id = callback.from_user.id
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is not None and player.health <= 0:
        if _active_tactical_field_hp(storage, telegram_id) is not None:
            return False
        await _ensure_death_keyboard(callback, telegram_id)
        return True
    return False


def action_result_text(telegram_id: int, text: str) -> str:
    storage = get_storage()
    arrival = storage.pop_arrival_notice(telegram_id)
    encounter = roll_arrival_encounter(storage, telegram_id, arrival) if arrival else None
    smuggle_text = resolve_smuggling_if_pending(storage, telegram_id)
    # Отчёт по контракту сдаётся сам при прибытии на базу.
    auto_turnin = try_auto_turn_in_contract(storage, telegram_id) if arrival else None
    body = (text or "").strip()
    parts: list[str] = []
    if arrival:
        parts.append(f"🚐 Прибыл в «{h(arrival)}».")
    if encounter:
        parts.append(encounter)
    if smuggle_text:
        parts.append(smuggle_text.strip())
    if auto_turnin:
        parts.append(auto_turnin)
    if body:
        parts.append(body)
    combined = "\n\n".join(parts)
    return append_survival_craving_notice(storage, telegram_id, combined)


async def send_profile_snapshot(
    message: Message | None,
    player: Character,
    *,
    bot: Bot | None = None,
    chat_id: int | None = None,
    reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | None = None,
) -> None:
    storage = get_storage()
    rank = character_rank_title(storage, player)
    rank_line = f"\nЗвание: {rank}" if rank else ""
    caption = (
        f"Профиль сталкера {player.nickname}\n"
        f"ID: {player.player_uid}\n"
        f"Фракция: {player.faction or 'не выбрана'}{rank_line}"
    )
    stats = storage.get_player_stats(player.telegram_id)
    rating = int(stats.get("rating_points", 0))
    image_bytes = build_character_card(player, rating_points=rating, storage=storage)
    image = BufferedInputFile(image_bytes, filename=f"{player.player_uid}.png")
    if message is not None:
        await message.answer_photo(photo=image, caption=caption, reply_markup=reply_markup)
        return
    target_bot = bot
    target_chat = chat_id
    if target_bot is None or target_chat is None:
        return
    await target_bot.send_photo(
        chat_id=target_chat,
        photo=image,
        caption=caption,
        reply_markup=reply_markup,
    )


@router.message(F.text == "🎒 Инвентарь")
async def show_inventory(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if player.health <= 0:
        await show_death_screen(message, player)
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    await message.answer(
        action_result_text(
            player.telegram_id,
            format_inventory(
                player,
                rating_points=int(get_storage().get_player_stats(player.telegram_id).get("rating_points", 0)),
                storage=get_storage(),
            ),
        ),
        reply_markup=inventory_equipment_keyboard(money=player.money),
    )


@router.callback_query(F.data == "inventory:open")
async def open_inventory_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await show_death_screen(callback, player, bot=callback.bot)
        return
    await edit_menu_message(
        callback,
        format_inventory(
            player,
            rating_points=int(get_storage().get_player_stats(player.telegram_id).get("rating_points", 0)),
            storage=get_storage(),
        ),
        inventory_equipment_keyboard(money=player.money),
    )


@router.callback_query(F.data == "inventory:consumables")
async def open_inventory_consumables_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await show_death_screen(callback, player, bot=callback.bot)
        return
    await edit_menu_message(
        callback,
        "🧰 Расходники\nВыбери предмет для использования:",
        inventory_consumables_keyboard(),
    )


def _stash_menu_payload(storage, player) -> tuple[str, object]:
    home = faction_home_base(player.faction)
    at_home = player.location == home and not bool(player.travel_destination)
    text = format_personal_stash(storage, player.telegram_id)
    if at_home:
        text += (
            f"\n\nТы на базе «{home}».\n"
            "Схрон сохраняет вещи при смерти (мутанты берут только рюкзак)."
        )
    else:
        text += (
            f"\n\nСхрон открывается только на домашней базе «{home}».\n"
            f"Сейчас ты в «{player.location}»."
        )
    return text, personal_stash_menu_keyboard(at_home=at_home)


@router.callback_query(F.data == "stash:menu")
async def stash_menu_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await show_death_screen(callback, player, bot=callback.bot)
        return
    text, keyboard = _stash_menu_payload(storage, player)
    await edit_menu_message(callback, text, keyboard)


@router.callback_query(F.data.startswith("stash:putlist:"))
async def stash_put_list_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    try:
        page = int((callback.data or "").rsplit(":", 1)[1])
    except ValueError:
        page = 0
    buttons, safe_page, total_pages = list_stash_deposit_buttons(player, page=page)
    if not buttons:
        await callback.answer("Инвентарь пуст.", show_alert=True)
        return
    await edit_menu_message(
        callback,
        "📥 Что положить в схрон?\nВыбери предмет, затем количество.",
        personal_stash_items_keyboard(
            buttons,
            page=safe_page,
            total_pages=total_pages,
            page_prefix="stash:putlist",
        ),
    )


@router.callback_query(F.data.startswith("stash:takelist:"))
async def stash_take_list_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    try:
        page = int((callback.data or "").rsplit(":", 1)[1])
    except ValueError:
        page = 0
    buttons, safe_page, total_pages = list_stash_withdraw_buttons(
        storage, player.telegram_id, page=page
    )
    if not buttons:
        await callback.answer("Схрон пуст.", show_alert=True)
        return
    await edit_menu_message(
        callback,
        "📤 Что забрать из схрона?\nВыбери предмет, затем количество.",
        personal_stash_items_keyboard(
            buttons,
            page=safe_page,
            total_pages=total_pages,
            page_prefix="stash:takelist",
        ),
    )


@router.callback_query(F.data.startswith("stash:put:"))
async def stash_put_pick_callback(callback: CallbackQuery) -> None:
    # stash:put:<item_key>
    item_key = (callback.data or "").removeprefix("stash:put:").strip()
    if not item_key or item_key.startswith("list:"):
        return
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    have = int(player.inventory.get(item_key, 0))
    if have <= 0:
        await callback.answer("Этого предмета уже нет.", show_alert=True)
        return
    from app.game_logic import ITEM_LABELS

    await edit_menu_message(
        callback,
        f"📥 В схрон: {ITEM_LABELS.get(item_key, item_key)}\nСколько положить? (есть {have})",
        personal_stash_amount_keyboard("put", item_key, have),
    )


@router.callback_query(F.data.startswith("stash:take:"))
async def stash_take_pick_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").removeprefix("stash:take:").strip()
    if not item_key or item_key.startswith("list:"):
        return
    storage = get_storage()
    have = int(storage.get_personal_stash(callback.from_user.id).get(item_key, 0))
    if have <= 0:
        await callback.answer("Этого предмета уже нет в схроне.", show_alert=True)
        return
    from app.game_logic import ITEM_LABELS

    await edit_menu_message(
        callback,
        f"📤 Из схрона: {ITEM_LABELS.get(item_key, item_key)}\nСколько забрать? (есть {have})",
        personal_stash_amount_keyboard("take", item_key, have),
    )


@router.callback_query(F.data.startswith("stash:putqty:"))
async def stash_put_qty_callback(callback: CallbackQuery) -> None:
    # stash:putqty:<item_key>:<qty>
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer("Некорректное количество.", show_alert=True)
        return
    item_key = parts[2]
    try:
        qty = int(parts[3])
    except ValueError:
        await callback.answer("Некорректное количество.", show_alert=True)
        return
    result = deposit_to_personal_stash(get_storage(), callback.from_user.id, item_key, qty)
    await reply_action_result(callback, result.text)
    if result.ok:
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            text, keyboard = _stash_menu_payload(storage, player)
            await edit_menu_message(callback, text, keyboard, answer_callback=False)


@router.callback_query(F.data.startswith("stash:takeqty:"))
async def stash_take_qty_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer("Некорректное количество.", show_alert=True)
        return
    item_key = parts[2]
    try:
        qty = int(parts[3])
    except ValueError:
        await callback.answer("Некорректное количество.", show_alert=True)
        return
    result = withdraw_from_personal_stash(get_storage(), callback.from_user.id, item_key, qty)
    await reply_action_result(callback, result.text)
    if result.ok:
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            text, keyboard = _stash_menu_payload(storage, player)
            await edit_menu_message(callback, text, keyboard, answer_callback=False)


@router.callback_query(F.data == "respawn:base")
async def respawn_base_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    from app.player_busy import recover_stuck_player

    recover_stuck_player(storage, callback.from_user.id, force_clear=True)
    result = respawn_character(storage, callback.from_user.id)
    await reply_action_result(callback, result.text)
    if result.ok:
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            if callback.message is not None:
                await callback.message.answer(
                    "С возвращением в Зону.",
                    reply_markup=main_menu_keyboard(),
                )
                await send_profile_snapshot(callback.message, player)
            elif callback.bot is not None:
                await callback.bot.send_message(
                    callback.from_user.id,
                    "С возвращением в Зону.",
                    reply_markup=main_menu_keyboard(),
                )
                await send_profile_snapshot(
                    None,
                    player,
                    bot=callback.bot,
                    chat_id=callback.from_user.id,
                )



@router.message(F.text == "🧾 Профиль")
async def show_profile(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if player.health <= 0:
        await show_death_screen(message, player)
        return
    await send_profile_snapshot(message, player, reply_markup=_pda_keyboard_for(player))


@router.message(F.text == "🛒 Торговец")
async def show_trader(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if player.health <= 0:
        await show_death_screen(message, player)
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    await message.answer(
        _trader_text(message.from_user.id, "Торговая зона. Выбери специалиста:"),
        reply_markup=trader_keyboard(),
    )


@router.callback_query(F.data == "trade:menu:buy")
async def show_buy_menu(callback: CallbackQuery) -> None:
    # Совместимость со старой кнопкой «Покупка» → бармен.
    storage = get_storage()
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            _vendor_intro(storage, callback.from_user.id, "barkeep"),
        ),
        barkeep_menu_keyboard(),
    )


@router.callback_query(F.data == "trade:vendor:barkeep")
async def show_barkeep(callback: CallbackQuery) -> None:
    storage = get_storage()
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            _vendor_intro(storage, callback.from_user.id, "barkeep"),
        ),
        barkeep_menu_keyboard(),
    )


@router.callback_query(F.data == "trade:vendor:medic")
async def show_medic(callback: CallbackQuery) -> None:
    storage = get_storage()
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            _vendor_intro(storage, callback.from_user.id, "medic"),
        ),
        medic_menu_keyboard(),
    )


@router.callback_query(F.data == "trade:vendor:tech")
async def show_tech(callback: CallbackQuery) -> None:
    storage = get_storage()
    from app.vendors import vendor_item_is_unlocked

    can_upgrade = vendor_item_is_unlocked(storage, callback.from_user.id, "armor_upgrade")
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            _vendor_intro(storage, callback.from_user.id, "tech"),
        ),
        tech_menu_keyboard(can_buy_upgrade=can_upgrade),
    )


def _vendor_intro(storage, telegram_id: int, vendor: str) -> str:
    from app.vendors import vendor_assortment_blurb, VENDOR_TITLES

    title = VENDOR_TITLES.get(vendor, vendor)
    return f"«{title}».\n{vendor_assortment_blurb(storage, telegram_id, vendor)}"


@router.callback_query(F.data == "trade:menu:sell")
async def show_sell_menu(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    categories = trader_sell_categories_with_stock(player) if player is not None else []
    body = (
        "Продажа: выбери категорию.\nПоказаны только вещи, которые у тебя есть."
        if categories
        else "Продажа: нечего продавать торговцу."
    )
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, body),
        trader_sell_categories_keyboard(categories),
    )


@router.callback_query(F.data == "trade:menu:root")
async def show_trade_root(callback: CallbackQuery) -> None:
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, "Торговая зона. Выбери специалиста:"),
        trader_keyboard(),
    )


def _trade_category_page(data: str | None, *, prefix: str) -> int:
    raw = data or ""
    if not raw.startswith(prefix):
        return 0
    tail = raw[len(prefix) :]
    if not tail:
        return 0
    if tail.startswith(":"):
        tail = tail[1:]
    try:
        return max(0, int(tail))
    except ValueError:
        return 0


def _sell_category_keyboard(player, category: str, page: int):
    items = list_owned_trader_sell_buttons(player, category) if player is not None else []
    if category == "consumables":
        return trader_sell_consumables_keyboard(items, page=page)
    if category == "trophies":
        return trader_sell_trophies_keyboard(items, page=page)
    if category == "gear":
        return trader_sell_gear_keyboard(items, page=page)
    if category == "armor":
        return trader_sell_armor_keyboard(items, page=page)
    if category == "weapons":
        return trader_sell_weapons_keyboard(items, page=page)
    return trader_sell_categories_keyboard()


def _barkeep_unlocked(storage, telegram_id: int):
    from app.vendors import get_vendor_tier, unlocked_vendor_item_keys

    return unlocked_vendor_item_keys("barkeep", get_vendor_tier(storage, telegram_id, "barkeep"))


@router.callback_query(
    F.data.startswith("trade:barkeep:food") | F.data.startswith("trade:buy:consumables")
)
async def show_barkeep_food(callback: CallbackQuery) -> None:
    storage = get_storage()
    page = _trade_category_page(callback.data, prefix="trade:barkeep:food")
    if (callback.data or "").startswith("trade:buy:consumables"):
        page = _trade_category_page(callback.data, prefix="trade:buy:consumables")
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            "Бармен — еда, вода и бытовые расходники.\nВыбери товар, затем количество.",
        ),
        barkeep_food_keyboard(page=page, unlocked_keys=_barkeep_unlocked(storage, callback.from_user.id)),
    )


@router.callback_query(
    F.data.startswith("trade:barkeep:gear") | F.data.startswith("trade:buy:gear")
)
async def show_barkeep_gear(callback: CallbackQuery) -> None:
    storage = get_storage()
    page = _trade_category_page(callback.data, prefix="trade:barkeep:gear")
    if (callback.data or "").startswith("trade:buy:gear"):
        page = _trade_category_page(callback.data, prefix="trade:buy:gear")
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            "Бармен — детекторы, транспорт, спальник, тайник.\n"
            "На кнопке: арт.% / скорость× / нагр.× / цена.",
        ),
        trader_buy_gear_keyboard(page=page, unlocked_keys=_barkeep_unlocked(storage, callback.from_user.id)),
    )


@router.callback_query(
    F.data.startswith("trade:barkeep:armor") | F.data.startswith("trade:buy:armor")
)
async def show_barkeep_armor(callback: CallbackQuery) -> None:
    storage = get_storage()
    page = _trade_category_page(callback.data, prefix="trade:barkeep:armor")
    if (callback.data or "").startswith("trade:buy:armor"):
        page = _trade_category_page(callback.data, prefix="trade:buy:armor")
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            "Бармен — броня и костюмы.\n"
            "На кнопке: сила · −N HP (всегда) · блок N% · цена.\n"
            "После покупки предмет в инвентаре.",
        ),
        trader_buy_armor_keyboard(page=page, unlocked_keys=_barkeep_unlocked(storage, callback.from_user.id)),
    )


@router.callback_query(
    F.data.startswith("trade:barkeep:weapons") | F.data.startswith("trade:buy:weapons")
)
async def show_barkeep_weapons(callback: CallbackQuery) -> None:
    storage = get_storage()
    page = _trade_category_page(callback.data, prefix="trade:barkeep:weapons")
    if (callback.data or "").startswith("trade:buy:weapons"):
        page = _trade_category_page(callback.data, prefix="trade:buy:weapons")
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            "Бармен — оружие.\n"
            "На кнопке: сила · д.N (дальность клеток) · цена.\n"
            "После покупки предмет в инвентаре.",
        ),
        trader_buy_weapons_keyboard(page=page, unlocked_keys=_barkeep_unlocked(storage, callback.from_user.id)),
    )


@router.callback_query(F.data.startswith("trade:medic:buy"))
async def show_medic_buy(callback: CallbackQuery) -> None:
    storage = get_storage()
    from app.vendors import get_vendor_tier, unlocked_vendor_item_keys

    page = _trade_category_page(callback.data, prefix="trade:medic:buy")
    unlocked = unlocked_vendor_item_keys("medic", get_vendor_tier(storage, callback.from_user.id, "medic"))
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            "Медик — аптечки и антирад.\nВыбери товар, затем количество.",
        ),
        medic_buy_keyboard(page=page, unlocked_keys=unlocked),
    )


@router.callback_query(F.data.startswith("trade:upgrade:"))
async def vendor_upgrade_callback(callback: CallbackQuery) -> None:
    from app.vendors import (
        VENDOR_KEYS,
        VENDOR_TIER_MAX,
        VENDOR_UPGRADE_COST,
        VENDOR_STAGE_LABELS,
        get_vendor_tier,
        upgrade_vendor_tier,
        vendor_assortment_blurb,
    )

    raw = callback.data or ""
    parts = raw.split(":")
    # trade:upgrade:<vendor> or trade:upgrade:<vendor>:confirm
    vendor = parts[2] if len(parts) >= 3 else ""
    if vendor not in VENDOR_KEYS:
        await safe_callback_answer(callback, "Неизвестный специалист.", show_alert=True)
        return
    storage = get_storage()
    tid = callback.from_user.id
    confirm = len(parts) >= 4 and parts[3] == "confirm"
    if confirm:
        result = upgrade_vendor_tier(storage, tid, vendor)
        await reply_action_result(callback, result.text)
    tier = get_vendor_tier(storage, tid, vendor)
    can_upgrade = tier < VENDOR_TIER_MAX
    body = vendor_assortment_blurb(storage, tid, vendor)
    if can_upgrade:
        nxt = tier + 1
        cost = int(VENDOR_UPGRADE_COST.get(vendor, {}).get(nxt, 0))
        nxt_label = VENDOR_STAGE_LABELS.get(vendor, {}).get(nxt, f"этап {nxt}")
        body += f"\n\nУлучшение до этапа {nxt}/{VENDOR_TIER_MAX} ({nxt_label}) — {cost} RU."
    await edit_menu_message(
        callback,
        _trader_text(tid, body),
        vendor_upgrade_keyboard(vendor, can_upgrade=can_upgrade),
        answer_callback=not confirm,
    )


@router.callback_query(F.data == "trade:buy:repair")
async def show_buy_repair(callback: CallbackQuery) -> None:
    # Совместимость → техник.
    storage = get_storage()
    from app.vendors import vendor_item_is_unlocked

    can_upgrade = vendor_item_is_unlocked(storage, callback.from_user.id, "armor_upgrade")
    await edit_menu_message(
        callback,
        _trader_text(
            callback.from_user.id,
            _vendor_intro(storage, callback.from_user.id, "tech"),
        ),
        tech_menu_keyboard(can_buy_upgrade=can_upgrade),
    )


@router.callback_query(F.data.startswith("trade:sell:consumables"))
async def show_sell_consumables(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:consumables")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, "Продажа расходников (только то, что есть):"),
        _sell_category_keyboard(player, "consumables", page),
    )


@router.callback_query(F.data.startswith("trade:sell:trophies"))
async def show_sell_trophies(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:trophies")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, "Продажа трофеев (только то, что есть):"),
        _sell_category_keyboard(player, "trophies", page),
    )


@router.callback_query(F.data.startswith("trade:sell:gear"))
async def show_sell_gear(callback: CallbackQuery) -> None:
    # Keep old nested armor alias working: trade:sell:gear:armor
    raw = callback.data or ""
    if raw == "trade:sell:gear:armor" or raw.startswith("trade:sell:gear:armor:"):
        page = _trade_category_page(raw, prefix="trade:sell:gear:armor")
        player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
        await edit_menu_message(
            callback,
            _trader_text(callback.from_user.id, "Продажа брони и костюмов (только то, что есть):"),
            _sell_category_keyboard(player, "armor", page),
        )
        return
    page = _trade_category_page(callback.data, prefix="trade:sell:gear")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, "Продажа снаряжения (только то, что есть):"),
        _sell_category_keyboard(player, "gear", page),
    )


@router.callback_query(F.data.startswith("trade:sell:armor"))
async def show_sell_armor_alias_callback(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:armor")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, "Продажа брони и костюмов (только то, что есть):"),
        _sell_category_keyboard(player, "armor", page),
    )


@router.callback_query(F.data.startswith("trade:sell:weapons"))
async def show_sell_weapons(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:weapons")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, "Продажа оружия (только то, что есть):"),
        _sell_category_keyboard(player, "weapons", page),
    )


@router.callback_query(F.data.startswith("buyqty:"))
async def show_buy_consumable_qty(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=1)[1]
    item = SHOP_ITEMS.get(item_key)
    if item is None or item_key not in BULK_BUY_ITEM_KEYS or int(item.get("buy_price", 0)) <= 0:
        await reply_action_result(callback, "Такого товара нельзя купить пачкой.")
        return
    title = str(item["name"])
    unit_price = int(item["buy_price"])
    if item_key == "stash_case":
        qty_keyboard = buy_item_qty_keyboard(
            item_key,
            unit_price=unit_price,
            back_callback="trade:buy:gear:0",
            back_text="⬅️ Назад",
        )
    else:
        qty_keyboard = trader_buy_consumable_qty_keyboard(item_key, unit_price=unit_price, title=title)
    await edit_menu_message(
        callback,
        _trader_text(callback.from_user.id, f"Покупка: {title}\nЦена за 1 шт.: {unit_price} RU\nВыбери количество:"),
        qty_keyboard,
    )


@router.callback_query(F.data.startswith("invbuyqty:"))
async def show_inventory_buy_qty(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=1)[1]
    item = SHOP_ITEMS.get(item_key)
    if item is None or item_key not in BULK_BUY_ITEM_KEYS or int(item.get("buy_price", 0)) <= 0:
        await reply_action_result(callback, "Этот предмет нельзя купить пачкой из инвентаря.")
        return
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    title = str(item["name"])
    unit_price = int(item["buy_price"])
    text = (
        f"Покупка: {title}\n"
        f"Цена за 1 шт.: {unit_price} RU\n"
        f"Баланс: {player.money:,} RU\n"
        f"Выбери количество:"
    )
    await edit_menu_message(
        callback,
        text,
        buy_item_qty_keyboard(
            item_key,
            unit_price=unit_price,
            back_callback="inventory:open",
            back_text="⬅️ Назад в инвентарь",
            buy_prefix="invbuy",
        ),
    )


@router.callback_query(F.data.startswith("invbuy:"))
async def handle_inventory_bulk_buy(callback: CallbackQuery) -> None:
    raw = (callback.data or "").split(":")
    # invbuy:<item>:<amount>
    if len(raw) < 3 or not raw[1]:
        await reply_action_result(callback, "Некорректная покупка.")
        return
    item_key = raw[1]
    try:
        amount = max(1, int(raw[2]))
    except ValueError:
        await reply_action_result(callback, "Некорректное количество.")
        return
    db = get_storage()
    result = buy_item(db, callback.from_user.id, item_key, amount=amount)
    await reply_action_result(callback, result.text)
    if result.ok:
        player = db.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            try:
                await edit_menu_message(
                    callback,
                    format_inventory(
                        player,
                        rating_points=int(db.get_player_stats(player.telegram_id).get("rating_points", 0)),
                        storage=db,
                    ),
                    inventory_equipment_keyboard(money=player.money),
                    answer_callback=False,
                )
            except TelegramBadRequest:
                pass


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery) -> None:
    raw = (callback.data or "").split(":")
    # buy:<item> или buy:<item>:<amount>
    if len(raw) < 2 or not raw[1]:
        await reply_action_result(callback, "Некорректная покупка.")
        return
    item_key = raw[1]
    amount = 1
    if len(raw) >= 3:
        try:
            amount = max(1, int(raw[2]))
        except ValueError:
            await reply_action_result(callback, "Некорректное количество.")
            return
    db = get_storage()
    result = buy_item(db, callback.from_user.id, item_key, amount=amount)
    await reply_action_result(callback, result.text)
    if result.ok and item_key == "truck":
        player = db.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            await send_profile_snapshot(callback.message, player)


@router.callback_query(F.data.startswith("sell:"))
async def handle_sell(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=1)[1]
    result = sell_item(get_storage(), callback.from_user.id, item_key)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "repair:weapon")
async def repair_weapon_callback(callback: CallbackQuery) -> None:
    result = repair_gear(get_storage(), callback.from_user.id, "weapon")
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "repair:armor")
async def repair_armor_callback(callback: CallbackQuery) -> None:
    result = repair_gear(get_storage(), callback.from_user.id, "armor")
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "upgrade:armor")
async def upgrade_armor_callback(callback: CallbackQuery) -> None:
    result = upgrade_armor(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "repair:truck")
async def repair_truck_callback(callback: CallbackQuery) -> None:
    result = repair_truck(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "repair:niva")
async def repair_niva_callback(callback: CallbackQuery) -> None:
    result = repair_niva(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "equip:root")
async def equip_root_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await show_death_screen(callback, player, bot=callback.bot)
        return
    text, items = build_equip_root_text(player)
    inv_upgrades = int(player.inventory.get("armor_upgrade", 0))
    installed = 0
    try:
        installed = max(0, int(player.equipment.get("armor_upgrade_level", 0)))
    except (TypeError, ValueError):
        installed = 0
    await edit_menu_message(
        callback,
        text,
        equip_root_keyboard(
            items,
            can_install_upgrade=inv_upgrades > 0,
            can_remove_upgrade=installed > 0,
        ),
    )


@router.callback_query(F.data == "equip:upgrade:install")
async def equip_upgrade_install_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    result = install_armor_upgrade(db, callback.from_user.id)
    await reply_action_result(callback, result.text)
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or callback.message is None:
        return
    text, items = build_equip_root_text(player)
    inv_upgrades = int(player.inventory.get("armor_upgrade", 0))
    try:
        installed = max(0, int(player.equipment.get("armor_upgrade_level", 0)))
    except (TypeError, ValueError):
        installed = 0
    try:
        await callback.message.edit_text(
            text,
            reply_markup=equip_root_keyboard(
                items,
                can_install_upgrade=inv_upgrades > 0,
                can_remove_upgrade=installed > 0,
            ),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "equip:upgrade:remove")
async def equip_upgrade_remove_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    result = unequip_armor_upgrade(db, callback.from_user.id)
    await reply_action_result(callback, result.text)
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or callback.message is None:
        return
    text, items = build_equip_root_text(player)
    inv_upgrades = int(player.inventory.get("armor_upgrade", 0))
    try:
        installed = max(0, int(player.equipment.get("armor_upgrade_level", 0)))
    except (TypeError, ValueError):
        installed = 0
    try:
        await callback.message.edit_text(
            text,
            reply_markup=equip_root_keyboard(
                items,
                can_install_upgrade=inv_upgrades > 0,
                can_remove_upgrade=installed > 0,
            ),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("equip:slot:"))
async def equip_slot_page_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    # equip:slot:<slot>:<page>
    if len(parts) < 4:
        await callback.answer("Некорректная категория.", show_alert=True)
        return
    slot = parts[2]
    try:
        page = int(parts[3])
    except ValueError:
        page = 0
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, slot, page)
    equipped_art = str(player.equipment.get("artifact", "Нет") or "Нет")
    await edit_menu_message(
        callback,
        text,
        equip_slot_page_keyboard(
            safe_slot,
            page=safe_page,
            total_pages=total_pages,
            options=options,
            can_unequip_artifact=safe_slot == "artifact" and equipped_art not in ("", "Нет"),
        ),
    )


@router.callback_query(F.data.startswith("equip:put:"))
async def equip_put_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    # equip:put:<slot>:<item_key>
    if len(parts) < 4:
        await callback.answer("Некорректный предмет.", show_alert=True)
        return
    slot = parts[2]
    item_key = parts[3]
    db = get_storage()
    if slot == "weapon":
        result = equip_weapon(db, callback.from_user.id, item_key)
    elif slot == "armor":
        result = equip_armor(db, callback.from_user.id, item_key)
    elif slot == "artifact":
        result = equip_artifact(db, callback.from_user.id, item_key)
    else:
        await callback.answer("Неизвестная категория.", show_alert=True)
        return

    await reply_action_result(callback, result.text)
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, slot, 0)
    equipped_art = str(player.equipment.get("artifact", "Нет") or "Нет")
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=equip_slot_page_keyboard(
                    safe_slot,
                    page=safe_page,
                    total_pages=total_pages,
                    options=options,
                    can_unequip_artifact=safe_slot == "artifact" and equipped_art not in ("", "Нет"),
                ),
            )
        except TelegramBadRequest:
            pass
    if result.ok:
        await send_profile_snapshot(callback.message, player)


@router.callback_query(F.data == "equip:unequip:artifact")
async def unequip_artifact_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    result = unequip_artifact(db, callback.from_user.id)
    await reply_action_result(callback, result.text)
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, "artifact", 0)
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=equip_slot_page_keyboard(
                    safe_slot,
                    page=safe_page,
                    total_pages=total_pages,
                    options=options,
                    can_unequip_artifact=False,
                ),
            )
        except TelegramBadRequest:
            pass


@router.callback_query(F.data == "equip:artifact")
async def equip_artifact_legacy_callback(callback: CallbackQuery) -> None:
    # Старый callback → меню выбора артефактов.
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, "artifact", 0)
    equipped_art = str(player.equipment.get("artifact", "Нет") or "Нет")
    await edit_menu_message(
        callback,
        text,
        equip_slot_page_keyboard(
            safe_slot,
            page=safe_page,
            total_pages=total_pages,
            options=options,
            can_unequip_artifact=equipped_art not in ("", "Нет"),
        ),
    )


@router.callback_query(F.data == "equip:menu:weapon")
async def equip_weapon_menu_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, "weapon", 0)
    await edit_menu_message(
        callback,
        text,
        equip_slot_page_keyboard(
            safe_slot,
            page=safe_page,
            total_pages=total_pages,
            options=options,
        ),
    )


@router.callback_query(F.data == "equip:menu:armor")
async def equip_armor_menu_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, "armor", 0)
    await edit_menu_message(
        callback,
        text,
        equip_slot_page_keyboard(
            safe_slot,
            page=safe_page,
            total_pages=total_pages,
            options=options,
        ),
    )


@router.callback_query(F.data.startswith("equip:weapon:"))
async def equip_weapon_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=2)[2]
    db = get_storage()
    result = equip_weapon(db, callback.from_user.id, item_key)
    await reply_action_result(callback, result.text)
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, "weapon", 0)
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=equip_slot_page_keyboard(
                    safe_slot,
                    page=safe_page,
                    total_pages=total_pages,
                    options=options,
                ),
            )
        except TelegramBadRequest:
            pass
    if result.ok:
        await send_profile_snapshot(callback.message, player)


@router.callback_query(F.data.startswith("equip:armor:"))
async def equip_armor_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=2)[2]
    db = get_storage()
    result = equip_armor(db, callback.from_user.id, item_key)
    await reply_action_result(callback, result.text)
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        return
    text, safe_slot, safe_page, total_pages, options = build_equip_slot_page(player, "armor", 0)
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=equip_slot_page_keyboard(
                    safe_slot,
                    page=safe_page,
                    total_pages=total_pages,
                    options=options,
                ),
            )
        except TelegramBadRequest:
            pass
    if result.ok:
        await send_profile_snapshot(callback.message, player)


QUEST_DIFFICULTY_EMOJI = {
    "easy": "🟢",
    "hard": "🟡",
    "heavy": "🟠",
    "impossible": "🔴",
}


def _quests_rules_text() -> str:
    return (
        "Контракты с переходами: прими на базе, доберись до точки, нажми «Выполнить работу» "
        "(ресурсы спишутся при старте вылазки).\n"
        "Поле 6×6, лимит ходов ~28+ (зависит от локации).\n"
        "Угрозы: 🟢 — аномалии; 🟡 — аномалии+мутанты; "
        "🟠/🔴 — аномалии+мутанты+НПС (сложнее = больше угроз и награда).\n"
        "НПС с тир-2 стволами могут стрелять на 2 клетки после твоего хода.\n"
        "На 🟠/🔴 мутанты каждый ход идут к тебе (на твою клетку не встают); "
        "на 🟡 — случайный сдвиг. НПС с шансом 50% сдвигаются случайно.\n"
        "🛡 Сопровождение: доведи NPC от A до B (он идёт за тобой). "
        "Аномалии всегда; вокруг — мутанты или НПС с T1-стволами. "
        "Если подопечного схватят — контракт сорван.\n"
        "📡 Поиск артефактов — тактическая охота на сетке (нужен детектор).\n"
        "🚚 Контрабанда — отдельный рейс с риском."
    )


def _quests_compact_status(storage, player) -> str:
    """Короткий статус для меню кнопок — без простыни правил."""
    lines = ["📋 Задания"]
    active = storage.get_active_contract(player.telegram_id)
    if active:
        template = QUEST_CONTRACTS.get(str(active.get("template_key", "")))
        stage = str(active.get("stage", "work"))
        title = template.title if template else "контракт"
        lines.append(f"📌 {title} · этап: {stage}")
        if template and stage == "work":
            lines.append(f"Точка: «{template.work_location}»")
    else:
        lines.append("Выбери контракт, поиск артефактов или контрабанду.")
    if is_traveling(player):
        lines.append("⏱ Ты в пути — таймер в отдельном сообщении.")
    return "\n".join(lines)


def _quests_menu_payload(storage, player):
    active = storage.get_active_contract(player.telegram_id)
    home = faction_home_base(player.faction)
    traveling = is_traveling(player)
    at_home = player.location == home and not traveling

    contract_buttons: list[tuple[str, str]] = []
    show_work = False
    show_go_work = False
    work_location = ""
    show_go_home = False
    show_cancel = bool(active)

    if active:
        stage = str(active.get("stage", "work"))
        template = QUEST_CONTRACTS.get(str(active.get("template_key", "")))
        if stage == "work" and template:
            show_work = player.location == template.work_location and not traveling
            if not show_work and not traveling:
                show_go_work = True
                work_location = template.work_location
        if stage == "return":
            show_go_home = player.location != home and not traveling
    elif at_home:
        from app.game_logic import (
            list_quest_contracts_for_character,
            _has_transport,
            get_daily_contract_keys,
            get_weekly_contract_key,
        )

        daily_keys = set(get_daily_contract_keys(storage))
        weekly_key = get_weekly_contract_key(storage)
        for template in list_quest_contracts_for_character(player):
            if not _has_transport(player, template.min_transport):
                continue
            emoji = QUEST_DIFFICULTY_EMOJI.get(template.difficulty, "📋")
            badge = ""
            if template.key == weekly_key:
                badge = "📅 "
            elif template.key in daily_keys:
                badge = "🗓 "
            contract_buttons.append(
                (f"{badge}{emoji} {template.title}", f"contract:accept:{template.key}")
            )

    keyboard = quests_keyboard(
        contract_buttons=contract_buttons,
        show_work=show_work,
        show_go_work=show_go_work,
        work_location=work_location,
        show_go_home=show_go_home,
        show_cancel=show_cancel,
    )
    return _quests_compact_status(storage, player), keyboard


def _quests_info_payload(storage, player) -> tuple[str, object]:
    overview = build_quest_overview(storage, player)
    text = f"{_quests_rules_text()}\n\n{overview}"
    return text, quests_info_keyboard()


@router.message(F.text == "📋 Задания")
async def show_quests(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return

    storage = get_storage()
    auto = try_auto_turn_in_contract(storage, player.telegram_id)
    player = storage.get_character(player.telegram_id, refresh_energy=False) or player
    text, keyboard = _quests_menu_payload(storage, player)
    if auto:
        text = f"{auto}\n\n{text}"
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "contract:refresh")
async def refresh_quests_menu(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    auto = try_auto_turn_in_contract(storage, player.telegram_id)
    player = storage.get_character(player.telegram_id, refresh_energy=False) or player
    text, keyboard = _quests_menu_payload(storage, player)
    if auto:
        text = f"{auto}\n\n{text}"
    await edit_menu_message(callback, text, keyboard)


@router.callback_query(F.data == "quests:info")
async def quests_info_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    text, keyboard = _quests_info_payload(storage, player)
    await edit_menu_message(callback, text, keyboard)


@router.callback_query(F.data.startswith("contract:accept:"))
async def accept_contract_callback(callback: CallbackQuery) -> None:
    contract_key = (callback.data or "").split(":", maxsplit=2)[2]
    result = accept_quest_contract(get_storage(), callback.from_user.id, contract_key)
    await reply_action_result(callback, result.text)
    if result.ok:
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            text, keyboard = _quests_menu_payload(storage, player)
            await edit_menu_message(callback, text, keyboard, answer_callback=False)


@router.callback_query(F.data == "contract:work")
async def contract_work_callback(callback: CallbackQuery) -> None:
    result = run_contract_work(get_storage(), callback.from_user.id)
    payload = result.payload or {}
    image = payload.get("mission_image")
    if image and payload.get("mission_active"):
        await _send_or_edit_quest_mission_frame(
            callback,
            image_bytes=image,
            caption=str(payload.get("caption") or result.text),
            note=result.text if payload.get("mission_started") else None,
        )
        return
    await reply_action_result(callback, result.text)
    if not result.ok:
        return
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is not None:
        text, keyboard = _quests_menu_payload(storage, player)
        try:
            await edit_menu_message(callback, text, keyboard, answer_callback=False)
        except TelegramBadRequest:
            pass


async def _dismiss_battle_map(callback: CallbackQuery) -> None:
    """Убрать карту боя (фото с кнопками) из чата."""
    message = callback.message
    if message is None:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        try:
            await message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass


_DEATH_FALLBACK_TEXT = (
    "☠️ Ты погиб.\n"
    "Нажми ♻️ «Спасение на базе» ниже."
)


def _plain_death_text(text: str) -> str:
    """Текст смерти без HTML — бот по умолчанию шлёт parse_mode=HTML."""
    return unescape(text or "")


async def _send_death_text_reply(
    callback: CallbackQuery,
    plain: str,
    keyboard: InlineKeyboardMarkup | None,
) -> bool:
    """Новое текстовое сообщение со смертью; карту-фото убираем."""
    message = callback.message
    if message is None:
        return False
    is_map = bool(message.photo)
    try:
        await message.answer(plain, reply_markup=keyboard, parse_mode=None)
        if is_map:
            await _dismiss_battle_map(callback)
        return True
    except Exception:
        logger.exception("Death reply failed for %s", callback.from_user.id)
    return False


async def _send_death_message_safe(
    bot: Bot,
    chat_id: int,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
) -> bool:
    """Отправить экран смерти в личку (plain text + inline-кнопки)."""
    plain = _plain_death_text(text)
    if len(plain) > 4096:
        plain = plain[:4090].rstrip() + "…"
    try:
        await bot.send_message(
            chat_id,
            plain,
            reply_markup=keyboard,
            parse_mode=None,
        )
        return True
    except Exception:
        logger.exception("Death message send failed for %s", chat_id)
    try:
        await bot.send_message(
            chat_id,
            _DEATH_FALLBACK_TEXT,
            reply_markup=keyboard,
            parse_mode=None,
        )
        return True
    except Exception:
        logger.exception("Death fallback message failed for %s", chat_id)
    return False


async def _deliver_death_screen(
    bot: Bot,
    user_id: int,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
    *,
    callback: CallbackQuery | None = None,
) -> bool:
    """Доставить текст смерти + кнопку респавна. Карту-фото убираем."""
    plain = _plain_death_text(text)
    if len(plain) > 4096:
        plain = plain[:4090].rstrip() + "…"

    if callback is not None and callback.message is not None:
        if await _send_death_text_reply(callback, plain, keyboard):
            return True
        if await _send_death_text_reply(callback, _DEATH_FALLBACK_TEXT, keyboard):
            return True

    if await _send_death_message_safe(bot, user_id, text, keyboard):
        if (
            callback is not None
            and callback.message is not None
            and callback.message.photo
        ):
            await _dismiss_battle_map(callback)
        return True

    return False


async def _finalize_death_delivery(storage: Storage, telegram_id: int, sent: bool) -> None:
    if not sent:
        return
    from app.player_busy import clear_stale_activity_for_dead_player

    clear_stale_activity_for_dead_player(storage, telegram_id)


async def _force_death_keyboard_delivery(
    bot: Bot,
    user_id: int,
    *,
    callback: CallbackQuery | None = None,
    text: str | None = None,
) -> bool:
    """Аварийная доставка: текст смерти + кнопка, карту убрать."""
    keyboard = dead_character_keyboard()
    plain = _plain_death_text(text) if text else _DEATH_FALLBACK_TEXT
    if len(plain) > 4096:
        plain = plain[:4090].rstrip() + "…"
    if callback is not None:
        if await _send_death_text_reply(callback, plain, keyboard):
            return True
    try:
        await bot.send_message(user_id, plain, reply_markup=keyboard, parse_mode=None)
        if (
            callback is not None
            and callback.message is not None
            and callback.message.photo
        ):
            await _dismiss_battle_map(callback)
        return True
    except Exception:
        logger.exception("Emergency death send failed for %s", user_id)
    return False


async def _ensure_death_keyboard(callback: CallbackQuery, telegram_id: int) -> None:
    """Игрок уже мёртв — история смерти и автоспасение на базе."""
    storage = get_storage()
    player = storage.get_character(telegram_id, refresh_energy=False)
    await safe_callback_answer(callback)
    if player is None or player.health > 0:
        return
    await _send_battle_death_notice(
        callback.bot,
        telegram_id,
        player,
        callback=callback,
    )


async def _handle_quest_mission_death_callback(
    callback: CallbackQuery,
    telegram_id: int,
    payload: dict[str, Any],
    *,
    fallback_text: str | None = None,
) -> None:
    storage = get_storage()
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        await safe_callback_answer(callback, "Персонаж не найден.", show_alert=True)
        return
    try:
        sent = await _send_battle_death_notice(
            callback.bot,
            telegram_id,
            player,
            callback=callback,
            where=str(payload.get("death_location") or player.location),
            cause=str(payload.get("death_cause") or "combat"),
        )
        if not sent and fallback_text and callback.message is not None:
            await callback.message.answer(
                _plain_death_text(fallback_text),
                parse_mode=None,
            )
    except Exception:
        logger.exception("Quest mission death delivery failed for %s", telegram_id)
        if fallback_text and callback.message is not None:
            try:
                await callback.message.answer(
                    _plain_death_text(fallback_text),
                    parse_mode=None,
                )
            except Exception:
                logger.exception("Quest mission death fallback failed for %s", telegram_id)
    finally:
        await safe_callback_answer(callback, "☠️ Погиб на вылазке")
        if callback.message is not None and callback.message.photo:
            await _dismiss_battle_map(callback)


SURVIVAL_DEATH_CHECK_EVERY_TICKS = 5  # ~раз в 5 мин при POINTS_INCOME_TICK_SECONDS=60
SURVIVAL_DEATH_CHECK_YIELD_EVERY = 50


async def _push_offline_survival_deaths(bot: Bot, storage: Storage) -> None:
    """Прогнать refresh_survival по всем игрокам и толкнуть тем, кто умер оффлайн от голода/жажды/радиации."""
    for index, telegram_id in enumerate(storage.list_player_ids(), start=1):
        try:
            before = storage.get_character(telegram_id, refresh_energy=False)
            if before is None or before.health <= 0:
                continue
            after = storage.get_character(telegram_id, refresh_energy=True)
        except Exception:
            logger.exception("Survival refresh failed for %s", telegram_id)
            continue
        if after is not None and after.health <= 0:
            if _active_tactical_field_hp(storage, telegram_id) is not None:
                continue
            try:
                await _send_battle_death_notice(bot, telegram_id, after)
            except Exception:
                logger.debug("Failed offline survival death push to %s", telegram_id)
        if index % SURVIVAL_DEATH_CHECK_YIELD_EVERY == 0:
            await asyncio.sleep(0)


async def _auto_respawn_after_death(
    bot: Bot,
    telegram_id: int,
    *,
    callback: CallbackQuery | None = None,
    message: Message | None = None,
) -> bool:
    """Сразу после смерти — спасение на базе без /respawn и кнопки."""
    storage = get_storage()
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None or player.health > 0:
        return False
    result = respawn_character(storage, telegram_id)
    if not result.ok:
        logger.warning("Auto respawn failed for %s: %s", telegram_id, result.text)
        return False
    text = action_result_text(telegram_id, result.text)
    reply_markup = main_menu_keyboard()
    sent_msg: Message | None = None
    try:
        if callback is not None and callback.message is not None:
            sent_msg = await callback.message.answer(text, reply_markup=reply_markup)
        elif message is not None:
            sent_msg = await message.answer(text, reply_markup=reply_markup)
        else:
            sent_msg = await bot.send_message(telegram_id, text, reply_markup=reply_markup)
    except Exception:
        logger.exception("Auto respawn delivery failed for %s", telegram_id)
        return False
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is not None and sent_msg is not None:
        try:
            await send_profile_snapshot(sent_msg, player)
        except Exception:
            logger.debug(
                "Profile snapshot after auto respawn failed for %s",
                telegram_id,
                exc_info=True,
            )
    return True


async def _send_battle_death_notice(
    bot: Bot,
    user_id: int,
    player: Character,
    *,
    callback: CallbackQuery | None = None,
    message: Message | None = None,
    where: str | None = None,
    cause: str | None = None,
    killer_name: str | None = None,
) -> bool:
    storage = get_storage()
    text = _build_death_text(
        player,
        storage,
        where=where,
        cause=cause,
        killer_name=killer_name,
    )
    append_death_log_once(storage, user_id, text)
    sent = await _deliver_death_screen(bot, user_id, text, None, callback=callback)
    if not sent:
        sent = await _force_death_keyboard_delivery(
            bot,
            user_id,
            callback=callback,
            text=text,
        )
    await _finalize_death_delivery(storage, user_id, sent)
    if sent:
        respawned = await _auto_respawn_after_death(
            bot,
            user_id,
            callback=callback,
            message=message,
        )
        if not respawned:
            await _force_death_keyboard_delivery(
                bot,
                user_id,
                callback=callback,
                text=text,
            )
    return sent


async def _deliver_player_message_or_death(
    bot: Bot,
    telegram_id: int,
    result_text: str,
    *,
    cause: str | None = None,
    where: str | None = None,
    killer_name: str | None = None,
    dead_player_ids: set[int] | None = None,
    death_causes: dict[str, str] | None = None,
    death_killers: dict[str, str] | None = None,
) -> None:
    storage = get_storage()
    player = storage.get_character(telegram_id, refresh_energy=False)
    dead_ids = dead_player_ids or set()
    causes_map = death_causes or {}
    killers_map = death_killers or {}
    is_dead = player is not None and (player.health <= 0 or telegram_id in dead_ids)
    if is_dead and player is not None:
        await _send_battle_death_notice(
            bot,
            telegram_id,
            player,
            where=where or player.location,
            cause=causes_map.get(str(telegram_id)) or cause or "combat",
            killer_name=killers_map.get(str(telegram_id)) or killer_name,
        )
        return
    await bot.send_message(telegram_id, action_result_text(telegram_id, result_text))


async def _push_fresh_tactical_deaths(
    bot: Bot,
    storage: Storage,
    session: Any,
    player_ids: list[int],
    *,
    cause_default: str = "combat",
) -> None:
    """Сразу после тактического хода: если HP на поле = 0, а в БД ещё жив — экран смерти."""
    from app.tactical_hp import commit_tactical_death
    from app.tactical_roster import is_downed_in_group_session

    death_causes = getattr(session, "death_causes", {}) or {}
    death_killers = getattr(session, "death_killers", {}) or {}
    for pid in player_ids:
        session_hp = _session_hp_for_player(session, pid)
        if session_hp is None or session_hp > 0:
            continue
        if is_downed_in_group_session(session, pid):
            continue
        player = storage.get_character(pid, refresh_energy=False)
        if player is None or player.health <= 0:
            continue
        cause = str(death_causes.get(str(pid)) or cause_default)
        killer = death_killers.get(str(pid))
        commit_tactical_death(
            storage,
            pid,
            0,
            cause=cause,
            killer_name=str(killer) if killer else None,
        )
        player = storage.get_character(pid, refresh_energy=False)
        if player is not None:
            await _send_battle_death_notice(
                bot,
                pid,
                player,
                where=player.location,
                cause=cause,
            )


async def _send_or_edit_quest_mission_frame(
    callback: CallbackQuery,
    *,
    image_bytes: bytes,
    caption: str,
    note: str | None = None,
) -> None:
    storage = get_storage()
    telegram_id = callback.from_user.id
    player = storage.get_character(telegram_id, refresh_energy=False)
    meds = 0
    if player is not None:
        meds = sum(int(player.inventory.get(k, 0)) for k in ("medkit", "medkit_army", "medkit_science"))
    session = get_mission_session(storage, telegram_id)
    shoot_available = mission_shoot_available(session) if session is not None else False
    media = BufferedInputFile(image_bytes, filename="quest_mission.png")
    text = caption if not note else f"{caption}\n\n{note}"
    markup = quest_mission_keyboard(medkits=meds, shoot_available=shoot_available)
    try:
        if callback.message and callback.message.photo:
            await callback.message.edit_media(
                media=InputMediaPhoto(media=media, caption=text),
                reply_markup=markup,
            )
        elif callback.message:
            await callback.message.answer_photo(photo=media, caption=text, reply_markup=markup)
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        else:
            await callback.bot.send_photo(
                callback.from_user.id,
                photo=media,
                caption=text,
                reply_markup=markup,
            )
    except TelegramBadRequest:
        await callback.bot.send_photo(
            callback.from_user.id,
            photo=media,
            caption=text,
            reply_markup=markup,
        )
    finally:
        await safe_callback_answer(callback)


async def _send_or_edit_smuggle_frame(
    callback: CallbackQuery,
    *,
    image_bytes: bytes,
    caption: str,
    note: str | None = None,
) -> None:
    media = BufferedInputFile(image_bytes, filename="smuggle_mission.png")
    text = caption if not note else f"{caption}\n\n{note}"
    markup = smuggle_mission_keyboard()
    try:
        if callback.message and callback.message.photo:
            await callback.message.edit_media(
                media=InputMediaPhoto(media=media, caption=text),
                reply_markup=markup,
            )
        elif callback.message:
            await callback.message.answer_photo(photo=media, caption=text, reply_markup=markup)
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        else:
            await callback.bot.send_photo(
                callback.from_user.id,
                photo=media,
                caption=text,
                reply_markup=markup,
            )
    except TelegramBadRequest:
        await callback.bot.send_photo(
            callback.from_user.id,
            photo=media,
            caption=text,
            reply_markup=markup,
        )
    finally:
        await safe_callback_answer(callback)


def _player_has_medkit(player: Character | None) -> bool:
    if player is None:
        return False
    return any(int(player.inventory.get(k, 0)) > 0 for k in ("medkit", "medkit_army", "medkit_science"))


def _duel_status_caption(storage: Storage, session: Any, viewer_id: int) -> str:
    from app.tactical_roster import format_player_name

    active_pid = session.active_player()
    active_name = format_player_name(storage, active_pid, html=True)
    lines = [f"⚔️ Тактическая дуэль · ход {active_name} (10 сек)"]
    for pid in (session.challenger_id, session.target_id):
        ch = storage.get_character(pid, refresh_energy=False)
        name = h(ch.nickname) if ch else str(pid)
        hp = session.hp.get(str(pid), 0)
        mark = " ◀" if pid == active_pid else ""
        if pid == viewer_id:
            mark += " (ты)"
        weapon = str(ch.equipment.get("weapon", "Нож")) if ch else "Нож"
        from app.tactical_combat import weapon_shoot_range

        rng = weapon_shoot_range(weapon)
        lines.append(f"{name}{mark}: HP {hp} · дальность {rng}")
    deadline_raw = getattr(session, "match_deadline", None)
    if getattr(session, "wave_mode", False):
        lines.append("🌊 Волна мутантов!")
    elif deadline_raw:
        from app.duel_grid import _parse_deadline, _utc_now

        dl = _parse_deadline(deadline_raw)
        if dl:
            secs = max(0, int((dl - _utc_now()).total_seconds()))
            lines.append(f"⏱ До волны: {secs // 60}:{secs % 60:02d}")
    lines.append("🔷 синяя клетка на карте = вы")
    if session.log:
        lines.append(session.log[-1][:80])
    return "\n".join(lines)


def _tactical_photo_file(image_bytes: bytes) -> BufferedInputFile:
    return BufferedInputFile(image_bytes, filename="tactical.png")


async def _upsert_tactical_photo(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int | None,
    image_bytes: bytes,
    caption: str,
    markup: InlineKeyboardMarkup | None,
    callback_message: Message | None = None,
    parse_mode: ParseMode | None | str = ParseMode.HTML,
) -> int:
    photo_kwargs: dict[str, Any] = {
        "caption": caption,
        "reply_markup": markup,
    }
    if parse_mode is not None:
        photo_kwargs["parse_mode"] = parse_mode

    if message_id is not None:
        try:
            await bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=InputMediaPhoto(
                    media=_tactical_photo_file(image_bytes),
                    caption=caption,
                    parse_mode=parse_mode,
                ),
                reply_markup=markup,
            )
            return message_id
        except TelegramBadRequest:
            pass

    if callback_message is not None:
        try:
            if callback_message.photo:
                await callback_message.edit_media(
                    media=InputMediaPhoto(
                        media=_tactical_photo_file(image_bytes),
                        caption=caption,
                        parse_mode=parse_mode,
                    ),
                    reply_markup=markup,
                )
                return callback_message.message_id
            sent = await callback_message.answer_photo(
                photo=_tactical_photo_file(image_bytes),
                **photo_kwargs,
            )
            try:
                await callback_message.delete()
            except TelegramBadRequest:
                pass
            return sent.message_id
        except TelegramBadRequest:
            pass

    sent = await bot.send_photo(
        chat_id,
        photo=_tactical_photo_file(image_bytes),
        **photo_kwargs,
    )
    return sent.message_id


async def _clear_tactical_keyboards(bot: Bot, message_ids: dict[str, int]) -> None:
    for pid_raw, msg_id in message_ids.items():
        try:
            await bot.edit_message_reply_markup(chat_id=int(pid_raw), message_id=int(msg_id), reply_markup=None)
        except TelegramBadRequest:
            pass
        except Exception:
            logger.debug("Failed to clear tactical keyboard for %s", pid_raw, exc_info=True)


def _patch_duel_message_ids(storage: Storage, session: Any) -> None:
    from app.duel_grid import DuelGridSession, _session_key, save_duel_session
    from app.tactical_turn import patch_session_message_ids

    patch_session_message_ids(
        storage,
        meta_key=_session_key(session.duel_id),
        message_ids=session.message_ids,
        from_dict=DuelGridSession.from_dict,
        save_fn=save_duel_session,
    )


def _patch_cwar_message_ids(storage: Storage, session: Any) -> None:
    from app.clan_war_grid import ClanWarGridSession, _session_key, save_cwar_session
    from app.tactical_turn import patch_session_message_ids

    patch_session_message_ids(
        storage,
        meta_key=_session_key(session.session_id),
        message_ids=session.message_ids,
        from_dict=ClanWarGridSession.from_dict,
        save_fn=save_cwar_session,
    )


def _patch_rgrid_message_ids(storage: Storage, session: Any) -> None:
    from app.raid_grid import RaidGridSession, _session_key, save_raid_grid_session
    from app.tactical_turn import patch_session_message_ids

    patch_session_message_ids(
        storage,
        meta_key=_session_key(session.session_id),
        message_ids=session.message_ids,
        from_dict=RaidGridSession.from_dict,
        save_fn=save_raid_grid_session,
    )


def _patch_ncap_message_ids(storage: Storage, session: Any) -> None:
    from app.neutral_capture import NeutralCaptureSession, _session_key, save_ncap_session
    from app.tactical_turn import patch_session_message_ids

    patch_session_message_ids(
        storage,
        meta_key=_session_key(session.session_id),
        message_ids=session.message_ids,
        from_dict=NeutralCaptureSession.from_dict,
        save_fn=save_ncap_session,
    )


def _patch_coop_message_ids(storage: Storage, session: Any) -> None:
    from app.coop_mission import CoopMissionSession, _session_key, save_coop_session
    from app.tactical_turn import patch_session_message_ids

    patch_session_message_ids(
        storage,
        meta_key=_session_key(session.session_id),
        message_ids=session.message_ids,
        from_dict=CoopMissionSession.from_dict,
        save_fn=save_coop_session,
    )


async def _broadcast_duel_session(
    bot: Bot,
    storage: Storage,
    session: Any,
    *,
    note: str | None = None,
    notes: dict[int, str] | None = None,
) -> None:
    active_pid = session.active_player()
    for pid in (session.challenger_id, session.target_id):
        ch = storage.get_character(pid, refresh_energy=False)
        is_active = active_pid == pid
        medkit = not session.medkits_used.get(str(pid), False) and _player_has_medkit(ch)
        markup = duel_grid_keyboard(is_active_turn=is_active, medkit_available=medkit)
        caption = _duel_status_caption(storage, session, pid)
        action_note = (notes or {}).get(pid) or note
        if action_note:
            caption = f"{caption}\n\n{action_note}" if pid == active_pid else f"{caption}\n\n↪ {action_note}"
        frame = render_duel_frame(storage, session, pid)
        msg_id = session.message_ids.get(str(pid))
        new_id = await _upsert_tactical_photo(
            bot,
            chat_id=pid,
            message_id=msg_id,
            image_bytes=frame,
            caption=caption,
            markup=markup,
        )
        session.message_ids[str(pid)] = new_id
    _patch_duel_message_ids(storage, session)
    await _push_fresh_tactical_deaths(
        bot,
        storage,
        session,
        [session.challenger_id, session.target_id],
        cause_default="duel",
    )


async def _notify_duel_finished(bot: Bot, result: Any) -> None:
    payload = result.payload or {}
    if not payload.get("duel_done"):
        return
    await _clear_tactical_keyboards(bot, payload.get("message_ids") or {})
    winner_id = int(payload.get("winner_id") or 0)
    loser_id = int(payload.get("loser_id") or 0)
    for pid, key in ((winner_id, "winner_text"), (loser_id, "loser_text")):
        text = str(payload.get(key) or result.text)
        try:
            await _deliver_player_message_or_death(bot, pid, text, cause="duel")
        except Exception:
            logger.exception("Failed duel result notify to %s", pid)


async def _handle_duel_action(bot: Bot, callback: CallbackQuery, result: Any) -> None:
    storage = get_storage()
    payload = result.payload or {}
    if payload.get("duel_done"):
        await _clear_tactical_keyboards(bot, payload.get("message_ids") or {})
        await _notify_duel_finished(bot, result)
        await safe_callback_answer(callback, "Дуэль завершена")
        return
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    session = get_duel_session_by_player(storage, callback.from_user.id)
    if session is None:
        await reply_action_result(callback, result.text)
        return
    await _broadcast_duel_session(bot, storage, session, note=result.text)
    await safe_callback_answer(callback, result.text[:CALLBACK_ALERT_MAX_LEN] if len(result.text) <= CALLBACK_ALERT_MAX_LEN else "Готово")


async def _broadcast_cwar_session(
    bot: Bot,
    storage: Storage,
    session: Any,
    *,
    note: str | None = None,
) -> None:
    active_pid = session.active_player()
    for pid in session.player_ids:
        ch = storage.get_character(pid, refresh_energy=False)
        is_active = active_pid == pid
        medkit = not session.medkits_used.get(str(pid), False) and _player_has_medkit(ch)
        markup = cwar_grid_keyboard(is_active_turn=is_active, medkit_available=medkit)
        caption = cwar_status_caption(storage, session, pid)
        if note:
            caption = f"{caption}\n\n{note}" if pid == active_pid else f"{caption}\n\n↪ {note}"
        frame = render_cwar_frame(storage, session, pid)
        msg_id = session.message_ids.get(str(pid))
        new_id = await _upsert_tactical_photo(
            bot,
            chat_id=pid,
            message_id=msg_id,
            image_bytes=frame,
            caption=caption,
            markup=markup,
        )
        session.message_ids[str(pid)] = new_id
    _patch_cwar_message_ids(storage, session)


async def _notify_cwar_finished(bot: Bot, result: Any) -> None:
    payload = result.payload or {}
    if not payload.get("cwar_done"):
        return
    await _clear_tactical_keyboards(bot, payload.get("message_ids") or {})
    member_ids = payload.get("member_ids") or []
    dead_player_ids = {int(x) for x in (payload.get("dead_players") or [])}
    death_causes = {str(k): str(v) for k, v in (payload.get("death_causes") or {}).items()}
    death_killers = {str(k): str(v) for k, v in (payload.get("death_killers") or {}).items()}
    for pid in member_ids:
        try:
            await _deliver_player_message_or_death(
                bot,
                int(pid),
                result.text,
                cause="cwar",
                dead_player_ids=dead_player_ids,
                death_causes=death_causes,
                death_killers=death_killers,
            )
        except Exception:
            logger.exception("Failed cwar result notify to %s", pid)


async def _handle_cwar_action(bot: Bot, callback: CallbackQuery, result: Any) -> None:
    storage = get_storage()
    payload = result.payload or {}
    if payload.get("cwar_done"):
        await _notify_cwar_finished(bot, result)
        await safe_callback_answer(callback, "Штурм завершён")
        return
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    session = get_cwar_session_by_player(storage, callback.from_user.id)
    if session is None:
        await reply_action_result(callback, result.text)
        return
    await _broadcast_cwar_session(bot, storage, session, note=result.text)
    await safe_callback_answer(callback, result.text[:CALLBACK_ALERT_MAX_LEN] if len(result.text) <= CALLBACK_ALERT_MAX_LEN else "Готово")


async def _broadcast_rgrid_session(
    bot: Bot,
    storage: Storage,
    session: Any,
    *,
    note: str | None = None,
    callback: CallbackQuery | None = None,
) -> None:
    active_pid = session.active_player()
    for pid in session.participant_ids():
        ch = storage.get_character(pid, refresh_energy=False)
        is_active = active_pid == pid
        medkit = not session.medkits_used.get(str(pid), False) and _player_has_medkit(ch)
        revive_targets: list[tuple[int, str]] = []
        if is_active:
            from app.raid_grid import _adjacent_down_allies

            for ally_id in _adjacent_down_allies(session, pid):
                ally = storage.get_character(ally_id, refresh_energy=False)
                if ally is not None and _player_has_medkit(ch):
                    revive_targets.append((ally_id, ally.nickname[:16]))
        markup = rgrid_keyboard(
            is_active_turn=is_active,
            medkit_available=medkit,
            revive_targets=revive_targets or None,
        )
        caption = rgrid_status_caption(storage, session, pid)
        if note:
            caption = f"{caption}\n\n{note}" if pid == active_pid else f"{caption}\n\n↪ {note}"
        frame = render_rgrid_frame(storage, session, pid)
        msg_id = session.message_ids.get(str(pid))
        callback_message = callback.message if callback is not None and pid == callback.from_user.id else None
        new_id = await _upsert_tactical_photo(
            bot,
            chat_id=pid,
            message_id=msg_id,
            image_bytes=frame,
            caption=caption,
            markup=markup,
            callback_message=callback_message,
            parse_mode=None,
        )
        session.message_ids[str(pid)] = new_id
    _patch_rgrid_message_ids(storage, session)


async def _notify_rgrid_finished(bot: Bot, result: Any) -> None:
    payload = result.payload or {}
    if not payload.get("rgrid_done"):
        return
    await _clear_tactical_keyboards(bot, payload.get("message_ids") or {})
    member_ids = payload.get("member_ids") or []
    defender_leader_id = payload.get("defender_leader_id")
    dead_player_ids = {int(x) for x in (payload.get("dead_players") or [])}
    death_causes = {str(k): str(v) for k, v in (payload.get("death_causes") or {}).items()}
    death_killers = {str(k): str(v) for k, v in (payload.get("death_killers") or {}).items()}
    notify_set = set(int(x) for x in member_ids)
    if defender_leader_id is not None:
        notify_set.add(int(defender_leader_id))
    for pid in notify_set:
        try:
            await _deliver_player_message_or_death(
                bot,
                int(pid),
                result.text,
                cause="raid",
                dead_player_ids=dead_player_ids,
                death_causes=death_causes,
                death_killers=death_killers,
            )
        except Exception:
            logger.exception("Failed rgrid result notify to %s", pid)


async def _handle_rgrid_action(bot: Bot, callback: CallbackQuery, result: Any) -> None:
    storage = get_storage()
    payload = result.payload or {}
    if payload.get("rgrid_done"):
        await _notify_rgrid_finished(bot, result)
        await safe_callback_answer(callback, "Рейд завершён")
        return
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    session = get_raid_grid_session_by_player(storage, callback.from_user.id)
    if session is None:
        await reply_action_result(callback, result.text)
        return
    await _broadcast_rgrid_session(bot, storage, session, note=result.text, callback=callback)
    await safe_callback_answer(callback, result.text[:CALLBACK_ALERT_MAX_LEN] if len(result.text) <= CALLBACK_ALERT_MAX_LEN else "Готово")


async def _broadcast_ncap_session(
    bot: Bot,
    storage: Storage,
    session: Any,
    *,
    note: str | None = None,
) -> None:
    active_pid = session.active_player()
    for pid in session.player_ids:
        player = storage.get_character(pid, refresh_energy=False)
        is_active = active_pid == pid
        medkit = not session.medkits_used.get(str(pid), False) and _player_has_medkit(player)
        markup = ncap_grid_keyboard(is_active_turn=is_active, medkit_available=medkit)
        caption = ncap_status_caption(session, player, pid)
        if note:
            caption = f"{caption}\n\n{note}" if pid == active_pid else f"{caption}\n\n↪ {note}"
        frame = render_ncap_frame(storage, session, pid)
        msg_id = session.message_ids.get(str(pid))
        new_id = await _upsert_tactical_photo(
            bot,
            chat_id=pid,
            message_id=msg_id,
            image_bytes=frame,
            caption=caption,
            markup=markup,
        )
        session.message_ids[str(pid)] = new_id
    _patch_ncap_message_ids(storage, session)


async def _notify_ncap_finished(bot: Bot, result: Any) -> None:
    payload = result.payload or {}
    if not payload.get("ncap_done"):
        return
    await _clear_tactical_keyboards(bot, payload.get("message_ids") or {})
    notify_ids = [int(x) for x in (payload.get("notify_all") or [])]
    dead_player_ids = {int(x) for x in (payload.get("dead_players") or [])}
    death_causes = {str(k): str(v) for k, v in (payload.get("death_causes") or {}).items()}
    death_killers = {str(k): str(v) for k, v in (payload.get("death_killers") or {}).items()}
    for notify_pid in notify_ids:
        await _deliver_player_message_or_death(
            bot,
            notify_pid,
            result.text,
            cause="ncap",
            dead_player_ids=dead_player_ids,
            death_causes=death_causes,
            death_killers=death_killers,
        )


async def _show_ncap_lobby_menu(callback: CallbackQuery, telegram_id: int) -> None:
    storage = get_storage()
    lobby = get_ncap_lobby_by_player(storage, telegram_id)
    await edit_menu_message(
        callback,
        ncap_lobby_menu_text(storage, telegram_id),
        ncap_lobby_keyboard(
            in_lobby=lobby is not None,
            is_host=lobby.host_id == telegram_id if lobby else False,
            lobby_id=lobby.lobby_id if lobby else None,
        ),
    )


async def _handle_ncap_action(bot: Bot, callback: CallbackQuery, result: Any) -> None:
    storage = get_storage()
    payload = result.payload or {}
    if payload.get("ncap_done"):
        await _notify_ncap_finished(bot, result)
        await safe_callback_answer(callback, "Захват завершён")
        return
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    session = get_ncap_session(storage, callback.from_user.id)
    if session is None:
        await reply_action_result(callback, result.text)
        return
    await _broadcast_ncap_session(bot, storage, session, note=result.text)
    await safe_callback_answer(callback, result.text[:CALLBACK_ALERT_MAX_LEN] if len(result.text) <= CALLBACK_ALERT_MAX_LEN else "Готово")


async def _broadcast_arena_session(
    bot: Bot,
    storage: Storage,
    session: Any,
    *,
    note: str | None = None,
    callback: CallbackQuery | None = None,
) -> None:
    medkit = session.arena_medkits > 0 and session.hp < session.max_hp
    markup = arena_grid_keyboard(medkit_available=medkit)
    caption = arena_status_caption(session)
    if note:
        caption = f"{caption}\n\n{note}"
    frame = render_arena_frame(storage, session)
    callback_message = callback.message if callback is not None else None
    new_id = await _upsert_tactical_photo(
        bot,
        chat_id=session.telegram_id,
        message_id=session.message_id,
        image_bytes=frame,
        caption=caption,
        markup=markup,
        callback_message=callback_message,
        parse_mode=None,
    )
    session.message_id = new_id
    from app.arena_grid import patch_arena_message_id

    patch_arena_message_id(storage, session.session_id, new_id)


async def _handle_arena_action(bot: Bot, callback: CallbackQuery, result: Any) -> None:
    storage = get_storage()
    payload = result.payload or {}
    if payload.get("arena_done"):
        msg_id = payload.get("message_id")
        tid = int(payload.get("telegram_id") or callback.from_user.id)
        if msg_id:
            await _clear_tactical_keyboards(bot, {str(tid): int(msg_id)})
        # Арена — тренировка: без экрана смерти и автореспавна.
        await bot.send_message(tid, action_result_text(tid, result.text))
        await safe_callback_answer(callback, "Арена завершена")
        return
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    session = get_arena_session(storage, callback.from_user.id)
    if session is None:
        await reply_action_result(callback, result.text)
        return
    await _broadcast_arena_session(bot, storage, session, note=result.text, callback=callback)
    await safe_callback_answer(callback, result.text[:CALLBACK_ALERT_MAX_LEN] if len(result.text) <= CALLBACK_ALERT_MAX_LEN else "Готово")


async def _broadcast_coop_session(
    bot: Bot,
    storage: Storage,
    session: Any,
    *,
    note: str | None = None,
) -> None:
    active_pid = session.active_player()
    for pid in session.player_ids:
        ch = storage.get_character(pid, refresh_energy=False)
        is_active = active_pid == pid
        medkit = not session.medkits_used.get(str(pid), False) and _player_has_medkit(ch)
        evac = can_evacuate(session, pid)
        markup = coop_mission_keyboard(is_active_turn=is_active, medkit_available=medkit, evac_available=evac)
        caption = coop_status_caption(session, storage, pid)
        if note:
            caption = f"{caption}\n\n{note}" if pid == active_pid else f"{caption}\n\n↪ {note}"
        frame = render_coop_frame(storage, session, pid)
        msg_id = session.message_ids.get(str(pid))
        new_id = await _upsert_tactical_photo(
            bot,
            chat_id=pid,
            message_id=msg_id,
            image_bytes=frame,
            caption=caption,
            markup=markup,
        )
        session.message_ids[str(pid)] = new_id
    _patch_coop_message_ids(storage, session)


async def _notify_coop_finished(bot: Bot, result: Any) -> None:
    payload = result.payload or {}
    if not payload.get("coop_done"):
        return
    await _clear_tactical_keyboards(bot, payload.get("message_ids") or {})
    storage = get_storage()
    notify_ids = [int(x) for x in (payload.get("notify_all") or [])]
    death_where = payload.get("death_location")
    death_causes = {
        str(k): str(v) for k, v in (payload.get("death_causes") or {}).items()
    }
    death_killers = {
        str(k): str(v) for k, v in (payload.get("death_killers") or {}).items()
    }
    default_cause = str(payload.get("death_cause") or "coop")
    dead_player_ids = {int(x) for x in (payload.get("dead_players") or [])}
    for pid in notify_ids:
        player = storage.get_character(pid, refresh_energy=False)
        try:
            is_dead = player is not None and (
                player.health <= 0 or pid in dead_player_ids
            )
            if is_dead and player is not None:
                cause = death_causes.get(str(pid), default_cause)
                killer_name = death_killers.get(str(pid))
                await _send_battle_death_notice(
                    bot,
                    pid,
                    player,
                    where=str(death_where or player.location),
                    cause=cause,
                    killer_name=killer_name,
                )
                # На успешном коопе живые видят награду; погибшему — только смерть.
                if payload.get("coop_success"):
                    continue
            elif is_notify_enabled(storage, pid, "coop"):
                await bot.send_message(pid, action_result_text(pid, result.text))
        except Exception:
            logger.exception("Failed coop result notify to %s", pid)


async def _handle_coop_action(bot: Bot, callback: CallbackQuery, result: Any) -> None:
    storage = get_storage()
    payload = result.payload or {}
    if payload.get("coop_done"):
        await _clear_tactical_keyboards(bot, payload.get("message_ids") or {})
        await _notify_coop_finished(bot, result)
        await safe_callback_answer(callback, "Вылазка завершена")
        return
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    session = get_coop_session_by_player(storage, callback.from_user.id)
    if session is None:
        await reply_action_result(callback, result.text)
        return
    await _broadcast_coop_session(bot, storage, session, note=result.text)
    await safe_callback_answer(callback, "Готово")


@router.callback_query(F.data.startswith("qmission:"))
async def quest_mission_callback(callback: CallbackQuery) -> None:
    action = (callback.data or "").removeprefix("qmission:").strip()
    storage = get_storage()
    telegram_id = callback.from_user.id

    player = storage.get_character(telegram_id, refresh_energy=False)
    dead = resolve_dead_player(storage, telegram_id, refresh_survival=False)
    if dead is not None:
        await _ensure_death_keyboard(callback, telegram_id)
        return

    try:
        if action == "leave":
            result = abandon_quest_mission(storage, telegram_id)
            await reply_action_result(callback, result.text)
            return

        if action == "medkit":
            result = use_mission_medkit(storage, telegram_id)
            payload = result.payload or {}
            if payload.get("mission_dead"):
                await _handle_quest_mission_death_callback(
                    callback, telegram_id, payload, fallback_text=result.text
                )
                return
            image = payload.get("mission_image")
            if image and payload.get("mission_active"):
                await _send_or_edit_quest_mission_frame(
                    callback,
                    image_bytes=image,
                    caption=str(payload.get("caption") or ""),
                    note=str(payload.get("move_note") or result.text),
                )
                return
            await reply_action_result(callback, result.text)
            return

        if action == "refresh":
            session = get_mission_session(storage, telegram_id)
            player = storage.get_character(telegram_id, refresh_energy=False)
            if session is None or player is None:
                await callback.answer("Активной вылазки нет.", show_alert=True)
                return
            image = render_mission_for_player(storage, telegram_id, session, player)
            await _send_or_edit_quest_mission_frame(
                callback,
                image_bytes=image,
                caption=mission_status_caption(session, player),
            )
            return

        if action.startswith("shoot:"):
            direction = action.removeprefix("shoot:")
            if direction not in {"up", "down", "left", "right"}:
                await callback.answer("Неизвестное действие.", show_alert=True)
                return
            result = shoot_quest_mission(storage, telegram_id, direction)
        elif action in {"up", "down", "left", "right"}:
            result = move_quest_mission(storage, telegram_id, action)
        else:
            await callback.answer("Неизвестное действие.", show_alert=True)
            return

        payload = result.payload or {}

        if payload.get("mission_dead"):
            await _handle_quest_mission_death_callback(
                callback, telegram_id, payload, fallback_text=result.text
            )
            return

        if payload.get("mission_done") or payload.get("mission_active") is False:
            await reply_action_result(callback, result.text)
            player = storage.get_character(telegram_id, refresh_energy=False)
            if player is not None and callback.message is not None:
                auto = try_auto_turn_in_contract(storage, telegram_id)
                player = storage.get_character(telegram_id, refresh_energy=False) or player
                text, keyboard = _quests_menu_payload(storage, player)
                if auto:
                    text = f"{auto}\n\n{text}"
                try:
                    await callback.message.answer(text, reply_markup=keyboard)
                except Exception:
                    pass
            return

        image = payload.get("mission_image")
        if not image:
            await reply_action_result(callback, result.text)
            return
        await _send_or_edit_quest_mission_frame(
            callback,
            image_bytes=image,
            caption=str(payload.get("caption") or ""),
            note=str(payload.get("move_note") or result.text),
        )
    except Exception:
        logger.exception("Quest mission callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка вылазки. Попробуй ещё раз или /fixme", show_alert=True)


@router.callback_query(F.data.startswith("smission:"))
async def smuggle_mission_callback(callback: CallbackQuery) -> None:
    action = (callback.data or "").removeprefix("smission:").strip()
    storage = get_storage()
    telegram_id = callback.from_user.id

    player = storage.get_character(telegram_id, refresh_energy=False)
    dead = resolve_dead_player(storage, telegram_id, refresh_survival=False)
    if dead is not None:
        await _ensure_death_keyboard(callback, telegram_id)
        return

    try:
        if action == "abandon":
            result = abandon_smuggle_mission(storage, telegram_id)
            await reply_action_result(callback, result.text)
            return

        if action == "refresh":
            session = get_smuggle_session(storage, telegram_id)
            player = storage.get_character(telegram_id, refresh_energy=False)
            if session is None or player is None:
                await callback.answer("Активного рейса нет.", show_alert=True)
                return
            image = render_smuggle_for_player(storage, telegram_id, session, player)
            await _send_or_edit_smuggle_frame(
                callback,
                image_bytes=image,
                caption=smuggle_status_caption(session, player),
            )
            return

        if action not in {"up", "down", "left", "right"}:
            await callback.answer("Неизвестное действие.", show_alert=True)
            return

        result = move_smuggle_mission(storage, telegram_id, action)
        payload = result.payload or {}

        if payload.get("mission_dead"):
            await _handle_quest_mission_death_callback(
                callback, telegram_id, payload, fallback_text=result.text
            )
            return

        if payload.get("mission_travel_started"):
            await reply_action_result(callback, result.text, bot=callback.bot)
            clear_travel_eta_message_id(storage, telegram_id)
            await publish_travel_live_eta(callback.bot, telegram_id)
            return

        if payload.get("mission_done") or payload.get("mission_active") is False:
            await reply_action_result(callback, result.text)
            return

        image = payload.get("mission_image")
        if not image:
            await reply_action_result(callback, result.text)
            return
        await _send_or_edit_smuggle_frame(
            callback,
            image_bytes=image,
            caption=str(payload.get("caption") or ""),
            note=str(payload.get("move_note") or result.text),
        )
    except Exception:
        logger.exception("Smuggle mission callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка рейса. Попробуй ещё раз или /fixme", show_alert=True)


@router.callback_query(F.data == "contract:travel_work")
async def contract_travel_work_callback(callback: CallbackQuery, bot: Bot) -> None:
    storage = get_storage()
    telegram_id = callback.from_user.id
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    active = storage.get_active_contract(telegram_id)
    if not active or str(active.get("stage", "")) != "work":
        await callback.answer("Сейчас некуда ехать по контракту.", show_alert=True)
        return
    template = QUEST_CONTRACTS.get(str(active.get("template_key", "")))
    if template is None:
        await callback.answer("Контракт не найден.", show_alert=True)
        return
    dest = template.work_location
    if player.location == dest:
        await callback.answer("Ты уже на точке задания.", show_alert=True)
        return
    bound = storage.get_bound_transport(telegram_id)
    preferred_mode: str | None = None
    if bound in ("niva", "truck"):
        preferred_mode = bound
    result = travel_to(storage, telegram_id, dest, transport_mode=preferred_mode)
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    await safe_callback_answer(callback, "В путь!")
    if callback.message is not None:
        await callback.message.answer(action_result_text(telegram_id, result.text))
    else:
        await bot.send_message(telegram_id, action_result_text(telegram_id, result.text))
    clear_travel_eta_message_id(storage, telegram_id)
    await publish_travel_live_eta(bot, telegram_id)
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is not None:
        text, keyboard = _quests_menu_payload(storage, player)
        try:
            await edit_menu_message(callback, text, keyboard, answer_callback=False)
        except TelegramBadRequest:
            pass


@router.callback_query(F.data == "contract:go_home")
async def contract_go_home_callback(callback: CallbackQuery, bot: Bot) -> None:
    storage = get_storage()
    telegram_id = callback.from_user.id
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    home = faction_home_base(player.faction)
    if player.location == home:
        await callback.answer("Ты уже на базе.", show_alert=True)
        return
    active = storage.get_active_contract(telegram_id)
    if not active or str(active.get("stage", "")) != "return":
        await callback.answer("Сейчас нечего везти на базу.", show_alert=True)
        return
    bound = storage.get_bound_transport(telegram_id)
    preferred_mode: str | None = None
    if bound in ("niva", "truck"):
        preferred_mode = bound
    result = travel_to(storage, telegram_id, home, transport_mode=preferred_mode)
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    await safe_callback_answer(callback, "На базу!")
    if callback.message is not None:
        await callback.message.answer(action_result_text(telegram_id, result.text))
    else:
        await bot.send_message(telegram_id, action_result_text(telegram_id, result.text))
    clear_travel_eta_message_id(storage, telegram_id)
    await publish_travel_live_eta(bot, telegram_id)
    player = storage.get_character(telegram_id, refresh_energy=False)
    if player is not None:
        text, keyboard = _quests_menu_payload(storage, player)
        try:
            await edit_menu_message(callback, text, keyboard, answer_callback=False)
        except TelegramBadRequest:
            pass


@router.callback_query(F.data == "contract:cancel")
async def contract_cancel_callback(callback: CallbackQuery) -> None:
    result = cancel_quest_contract(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is not None:
        text, keyboard = _quests_menu_payload(storage, player)
        await edit_menu_message(callback, text, keyboard, answer_callback=False)



@router.message(F.text == "☠️ Смерти")
async def show_death_log(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    text = build_death_log_text(get_storage(), player.telegram_id)
    await message.answer(text, reply_markup=_pda_keyboard_for(player))


@router.callback_query(F.data == "death:log")
async def show_death_log_callback(callback: CallbackQuery) -> None:
    """Журнал смертей (из КПК, когда игрок жив)."""
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text = build_death_log_text(get_storage(), player.telegram_id)
    await safe_callback_answer(callback)
    if callback.message is not None:
        await callback.message.answer(text)


@router.message(F.text == "📟 КПК")
async def show_pda(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    await message.answer(
        "📟 КПК сталкера\n"
        "Профиль, связь, рейтинг, карта, журнал смертей, игроки и рефералка.",
        reply_markup=_pda_keyboard_for(player),
    )


@router.message(F.text == "🔗 Реферальная система")
async def show_referral_system(message: Message, bot: Bot) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    referral_link = None
    try:
        me = await bot.get_me()
        if me.username:
            referral_link = build_referral_link(me.username, player.telegram_id)
    except Exception:
        logger.exception("Failed to resolve bot username for referral link")
    await message.answer(
        _build_referral_system_text(referral_link=referral_link),
        reply_markup=_pda_keyboard_for(player),
    )


@router.message(F.text == "💬 Чаты")
async def show_pda_chats(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    await message.answer(_build_pda_chats_text(player), reply_markup=_pda_keyboard_for(player))


@router.message(F.text == "📅 Ежедневка")
async def show_daily_login(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    result = claim_daily_login(get_storage(), player.telegram_id)
    await message.answer(result.text, reply_markup=_pda_keyboard_for(player))


@router.message(F.text == "🔔 Уведомления")
async def show_notify_prefs(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    prefs = get_notify_prefs(get_storage(), player.telegram_id)
    await message.answer(build_notify_prefs_text(prefs), reply_markup=notify_prefs_keyboard(prefs))


@router.callback_query(F.data.startswith("notify:toggle:"))
async def notify_toggle_callback(callback: CallbackQuery) -> None:
    key = (callback.data or "").removeprefix("notify:toggle:").strip()
    storage = get_storage()
    prefs = toggle_notify_pref(storage, callback.from_user.id, key)
    await safe_callback_answer(callback, "Готово")
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                build_notify_prefs_text(prefs),
                reply_markup=notify_prefs_keyboard(prefs),
            )
        except TelegramBadRequest:
            pass


@router.message(F.text == "📘 Обучение")
async def show_tutorial(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    text, page, total = build_tutorial_page(0)
    await message.answer(text, reply_markup=tutorial_keyboard(page, total))


@router.callback_query(F.data.startswith("tutorial:page:"))
async def tutorial_page_callback(callback: CallbackQuery) -> None:
    raw_page = (callback.data or "").removeprefix("tutorial:page:").strip()
    try:
        requested_page = int(raw_page)
    except ValueError:
        requested_page = 0
    text, page, total = build_tutorial_page(requested_page)
    bonus_note = ""
    if page == total - 1:
        bonus_note = claim_tutorial_completion(get_storage(), callback.from_user.id)
    await safe_callback_answer(callback)
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                f"{text}{bonus_note}",
                reply_markup=tutorial_keyboard(page, total),
            )
        except TelegramBadRequest:
            pass


@router.message(F.text == "🏛 Клановые задачи")
async def show_clan_quest(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    storage = get_storage()
    text = build_clan_quest_overview(storage, player.telegram_id)
    await message.answer(
        text,
        reply_markup=clan_quest_keyboard(can_claim=can_claim_clan_quest(storage, player.telegram_id)),
    )


@router.callback_query(F.data == "clanquest:open")
async def clan_quest_open_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    text = build_clan_quest_overview(storage, callback.from_user.id)
    can_claim = can_claim_clan_quest(storage, callback.from_user.id)
    await safe_callback_answer(callback)
    await edit_menu_message(
        callback,
        text,
        clan_quest_keyboard(can_claim=can_claim),
        answer_callback=False,
    )


@router.callback_query(F.data == "clanquest:claim")
async def clan_quest_claim_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    result = claim_clan_quest(storage, callback.from_user.id)
    await reply_action_result(callback, result.text)
    text = build_clan_quest_overview(storage, callback.from_user.id)
    can_claim = can_claim_clan_quest(storage, callback.from_user.id)
    await edit_menu_message(
        callback,
        text,
        clan_quest_keyboard(can_claim=can_claim),
        answer_callback=False,
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Ввод отменён.", reply_markup=main_menu_keyboard())


@router.message(F.text == "⬅️ В меню")
async def pda_back_to_menu(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        await state.clear()
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await message.answer("Главное меню.", reply_markup=main_menu_keyboard())


@router.message(F.text == "🏆 Рейтинг")
async def show_rating(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    await message.answer(
        build_rating_menu_text(),
        reply_markup=ratings_keyboard(),
    )


@router.message(nav_button("🗺 Карта"))
async def show_zone_map(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    try:
        locations = get_storage().get_locations()
        image_bytes = build_zone_map_image(
            locations,
            current_location=player.location,
            player_faction=player.faction,
            show_markers=True,
        )
        image = BufferedInputFile(image_bytes, filename="zone_map.jpg")
        caption = (
            "Карта Зоны.\n"
            "Метка: тип территории; контроль; сила NPC.\n"
            "Кольцо = тип точки, заливка = фракция."
        )
        keyboard = _pda_keyboard_for(player)
        if len(image_bytes) > TELEGRAM_PHOTO_MAX_BYTES:
            await message.answer_document(
                document=image,
                caption=caption,
                reply_markup=keyboard,
            )
        else:
            try:
                await message.answer_photo(
                    photo=image,
                    caption=caption,
                    reply_markup=keyboard,
                )
            except Exception:
                logger.exception(
                    "sendPhoto failed for zone map user %s, retry as document",
                    message.from_user.id,
                )
                await message.answer_document(
                    document=image,
                    caption=caption,
                    reply_markup=keyboard,
                )
    except Exception:
        logger.exception("Failed to build/send zone map for user %s", message.from_user.id)
        await message.answer(
            "Не удалось загрузить карту. Попробуй ещё раз через минуту.",
            reply_markup=_pda_keyboard_for(player),
        )


@router.message(F.text == "👥 Игроки")
async def show_players(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    text, items = build_players_root_text(get_storage())
    await message.answer(text, reply_markup=players_factions_keyboard(items))


async def _send_faction_broadcast(message: Message, bot: Bot, custom_text: str | None = None) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    storage = get_storage()
    result = build_faction_broadcast_text(storage, player.telegram_id, custom_text=custom_text)
    if not result.ok:
        await message.answer(result.text)
        return
    targets = list_faction_broadcast_targets(storage, player.telegram_id)
    sent = 0
    for target_id in targets:
        try:
            await bot.send_message(target_id, result.text)
            sent += 1
        except Exception:
            logger.exception("Failed to deliver faction broadcast to %s", target_id)
    await message.answer(f"{result.text}\n\nДоставлено бойцам: {sent}.")


@router.message(F.text == "📣 Сбор")
async def faction_broadcast_button(message: Message, bot: Bot) -> None:
    await _send_faction_broadcast(message, bot)


@router.message(Command("сбор"))
@router.message(Command("sbor"))
async def faction_broadcast_command(message: Message, bot: Bot) -> None:
    parts = (message.text or "").split(maxsplit=1)
    custom = parts[1].strip() if len(parts) > 1 else None
    await _send_faction_broadcast(message, bot, custom_text=custom)


def _extract_broadcast_body(raw_command_text: str) -> str | None:
    parts = (raw_command_text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    body = parts[1].strip()
    if len(body) >= 2 and (
        (body[0] == body[-1] and body[0] in {'"', "'"})
        or (body.startswith("«") and body.endswith("»"))
    ):
        if body.startswith("«") and body.endswith("»"):
            body = body[1:-1].strip()
        else:
            body = body[1:-1].strip()
    return body or None


@router.message(Command("всем"))
@router.message(Command("all"))
async def broadcast_all_command(message: Message, bot: Bot) -> None:
    sender_id = message.from_user.id
    if not is_admin_user(sender_id):
        await message.answer("Команда доступна только администратору.")
        return

    body = _extract_broadcast_body(message.text or "")
    if body is None:
        await message.answer(
            "Использование: /всем [текст]\n"
            "Пример: /всем Внимание, сталкеры! Выброс через час."
        )
        return

    sender = get_storage().get_character(sender_id, refresh_energy=False)
    sender_name = h(sender.nickname if sender is not None else str(sender_id))
    text = f"📢 Объявление:\n{h(body)}\n\n— {sender_name}"

    targets = [tid for tid in get_storage().list_player_ids() if tid != sender_id]
    sent = 0
    for target_id in targets:
        try:
            await bot.send_message(target_id, text)
            sent += 1
        except Exception:
            logger.exception("Failed to deliver global broadcast to %s", target_id)

    await message.answer(f"{text}\n\nДоставлено игрокам: {sent}.")


@router.callback_query(F.data == "players:root")
async def players_root_callback(callback: CallbackQuery) -> None:
    text, items = build_players_root_text(get_storage())
    await edit_menu_message(callback, text, players_factions_keyboard(items))


@router.callback_query(F.data.startswith("players:f:"))
async def players_faction_page_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    # players:f:<faction_key>:<page>
    if len(parts) < 4:
        await callback.answer("Некорректная страница.", show_alert=True)
        return
    faction_key = parts[2]
    try:
        page = int(parts[3])
    except ValueError:
        await callback.answer("Некорректный номер страницы.", show_alert=True)
        return
    text, safe_key, safe_page, total_pages, page_players = build_players_faction_page_text(
        get_storage(),
        faction_key,
        page,
    )
    await edit_menu_message(
        callback,
        text,
        players_faction_page_keyboard(
            safe_key,
            page=safe_page,
            total_pages=total_pages,
            players=page_players,
            self_id=callback.from_user.id,
        ),
    )


@router.callback_query(F.data == "ratings:stats")
async def show_character_stats_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text = build_character_stats_overview(get_storage(), player.telegram_id)
    await edit_menu_message(callback, text, None)


@router.callback_query(F.data == "ratings:achievements")
async def show_achievements_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text = build_achievements_overview(get_storage(), player.telegram_id)
    await edit_menu_message(callback, text, None)


@router.callback_query(F.data == "ratings:menu")
@router.callback_query(F.data == "ratings:leaderboard")
async def show_ratings_menu_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    await edit_menu_message(callback, build_rating_menu_text(), ratings_keyboard())


@router.callback_query(F.data.startswith("rating:alltime:page:"))
@router.callback_query(F.data.startswith("rating:season:page:"))
@router.callback_query(F.data.startswith("rating:page:"))
async def show_rating_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    page = 0
    mode = "alltime"
    raw = callback.data or ""
    if raw.startswith("rating:season:page:"):
        mode = "season"
        try:
            page = int(raw.rsplit(":", maxsplit=1)[-1])
        except ValueError:
            page = 0
    elif raw.startswith("rating:alltime:page:"):
        try:
            page = int(raw.rsplit(":", maxsplit=1)[-1])
        except ValueError:
            page = 0
    elif raw.startswith("rating:page:"):
        try:
            page = int(raw.rsplit(":", maxsplit=1)[-1])
        except ValueError:
            page = 0
    storage = get_storage()
    if mode == "season":
        text, safe_page, total_pages = build_season_rating_overview(
            storage,
            player.telegram_id,
            page=page,
        )
    else:
        text, safe_page, total_pages = build_rating_overview(
            storage,
            player.telegram_id,
            page=page,
        )
    await edit_menu_message(
        callback,
        text,
        rating_page_keyboard(mode=mode, page=safe_page, total_pages=total_pages),
    )


@router.message(F.text == "⚡ Выпить энергетик")
async def drink_energy(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    result = use_energy_drink(get_storage(), message.from_user.id)
    await message.answer(action_result_text(message.from_user.id, result.text))


@router.callback_query(F.data == "use:energy_drink")
async def use_energy_drink_callback(callback: CallbackQuery) -> None:
    result = use_energy_drink(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:medkit")
async def use_medkit_callback(callback: CallbackQuery) -> None:
    result = use_medkit(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:medkit_army")
async def use_medkit_army_callback(callback: CallbackQuery) -> None:
    result = use_medkit_army(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:medkit_science")
async def use_medkit_science_callback(callback: CallbackQuery) -> None:
    result = use_medkit_science(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:vodka")
async def use_vodka_callback(callback: CallbackQuery) -> None:
    result = use_vodka(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:antirad")
async def use_antirad_callback(callback: CallbackQuery) -> None:
    result = use_antirad(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:bread")
async def use_bread_callback(callback: CallbackQuery) -> None:
    result = use_bread(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:sausage")
async def use_sausage_callback(callback: CallbackQuery) -> None:
    result = use_sausage(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:stew")
async def use_stew_callback(callback: CallbackQuery) -> None:
    result = use_stew(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:water_bottle")
async def use_water_callback(callback: CallbackQuery) -> None:
    result = use_water(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:mineral_water")
async def use_mineralka_callback(callback: CallbackQuery) -> None:
    result = use_mineralka(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:beard_tea")
async def use_beard_tea_callback(callback: CallbackQuery) -> None:
    result = use_beard_tea(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "use:stash_case")
async def use_stash_case_callback(callback: CallbackQuery) -> None:
    result = open_stash(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


async def _send_or_edit_hunt_frame(
    callback: CallbackQuery,
    *,
    image_bytes: bytes,
    caption: str,
    note: str | None = None,
) -> None:
    media = BufferedInputFile(image_bytes, filename="artifact_hunt.png")
    text = caption if not note else f"{caption}\n\n{note}"
    markup = artifact_hunt_keyboard()
    try:
        if callback.message and callback.message.photo:
            await callback.message.edit_media(
                media=InputMediaPhoto(media=media, caption=text),
                reply_markup=markup,
            )
        elif callback.message:
            await callback.message.answer_photo(photo=media, caption=text, reply_markup=markup)
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        else:
            await callback.bot.send_photo(
                callback.from_user.id,
                photo=media,
                caption=text,
                reply_markup=markup,
            )
    except TelegramBadRequest:
        await callback.bot.send_photo(
            callback.from_user.id,
            photo=media,
            caption=text,
            reply_markup=markup,
        )
    finally:
        await safe_callback_answer(callback)


@router.callback_query(F.data == "artifact:search")
async def artifact_search_callback(callback: CallbackQuery) -> None:
    result = start_artifact_hunt(get_storage(), callback.from_user.id)
    payload = result.payload or {}
    image = payload.get("hunt_image")
    if image and payload.get("hunt_active"):
        await _send_or_edit_hunt_frame(
            callback,
            image_bytes=image,
            caption=str(payload.get("caption") or result.text),
            note=result.text if payload.get("hunt_started") else None,
        )
        return
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("hunt:"))
async def artifact_hunt_callback(callback: CallbackQuery) -> None:
    action = (callback.data or "").removeprefix("hunt:").strip()
    storage = get_storage()
    telegram_id = callback.from_user.id

    player = storage.get_character(telegram_id, refresh_energy=False)
    dead = resolve_dead_player(storage, telegram_id, refresh_survival=False)
    if dead is not None:
        await _ensure_death_keyboard(callback, telegram_id)
        return

    try:
        if action == "leave":
            result = abandon_artifact_hunt(storage, telegram_id)
            await reply_action_result(callback, result.text)
            return

        if action == "refresh":
            session = get_hunt_session(storage, telegram_id)
            player = storage.get_character(telegram_id, refresh_energy=False)
            if session is None or player is None:
                await callback.answer("Активной вылазки нет.", show_alert=True)
                return
            image = render_hunt_for_player(storage, telegram_id, session, player)
            await _send_or_edit_hunt_frame(
                callback,
                image_bytes=image,
                caption=hunt_status_caption(session, player),
            )
            return

        if action not in {"up", "down", "left", "right"}:
            await callback.answer("Неизвестное действие.", show_alert=True)
            return

        result = move_artifact_hunt(storage, telegram_id, action)
        payload = result.payload or {}

        if payload.get("hunt_dead"):
            await _handle_quest_mission_death_callback(
                callback, telegram_id, payload, fallback_text=result.text
            )
            return

        if payload.get("hunt_done") or payload.get("hunt_active") is False:
            await reply_action_result(callback, result.text)
            return

        image = payload.get("hunt_image")
        if not image:
            await reply_action_result(callback, result.text)
            return
        await _send_or_edit_hunt_frame(
            callback,
            image_bytes=image,
            caption=str(payload.get("caption") or ""),
            note=str(payload.get("move_note") or result.text),
        )
    except Exception:
        logger.exception("Artifact hunt callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка охоты. Попробуй ещё раз или /fixme", show_alert=True)


@router.message(Command("pay"))
async def pay_command(message: Message, bot: Bot) -> None:
    sender_id = message.from_user.id
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_busy(message, sender_id):
        return
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.answer("Использование: /pay [telegram_id] [сумма]")
        return
    try:
        target_telegram_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("Telegram ID и сумма должны быть целыми числами.")
        return
    result = transfer_money_with_fee(get_storage(), sender_id, target_telegram_id, amount)
    await message.answer(action_result_text(sender_id, result.text))
    await apply_action_notifies(bot, result)


async def _send_duel_challenge(bot: Bot, sender_id: int, target_telegram_id: int) -> str:
    result, target_text = create_duel_challenge(get_storage(), sender_id, target_telegram_id)
    reply = action_result_text(sender_id, result.text)
    if result.ok and target_text:
        try:
            await bot.send_message(
                target_telegram_id,
                target_text,
                reply_markup=duel_challenge_keyboard(sender_id),
            )
        except Exception:
            logger.exception("Failed to deliver duel challenge to %s", target_telegram_id)
            reply = (
                f"{reply}\n\nВызов сохранён, но не удалось доставить сообщение сопернику "
                "(он должен написать боту /start)."
            )
    return reply


@router.message(Command("дуэль"))
@router.message(Command("duel"))
async def duel_command(message: Message, bot: Bot) -> None:
    sender_id = message.from_user.id
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer(
            "Использование: /дуэль [telegram_id]\n"
            "ID смотри в КПК → «👥 Игроки»."
        )
        return
    try:
        target_telegram_id = int(parts[1])
    except ValueError:
        await message.answer("Telegram ID должен быть целым числом.")
        return
    await message.answer(await _send_duel_challenge(bot, sender_id, target_telegram_id))


@router.callback_query(F.data.startswith("duel:challenge:"))
async def duel_challenge_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    try:
        target_telegram_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await reply_action_result(callback, "Некорректный вызов.")
        return
    text = await _send_duel_challenge(bot, callback.from_user.id, target_telegram_id)
    await reply_action_result(callback, text)


@router.callback_query(F.data.startswith("duel:accept:"))
async def duel_accept_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    try:
        challenger_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await reply_action_result(callback, "Некорректный вызов.")
        return
    target_id = callback.from_user.id
    storage = get_storage()
    result, challenger_text = accept_duel(storage, target_id, challenger_id)
    if not result.ok:
        await reply_action_result(callback, result.text)
        return
    session = get_duel_session_by_player(storage, target_id)
    if session is None:
        await reply_action_result(callback, result.text)
        return
    await safe_callback_answer(callback, "Дуэль началась!")
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
    await _broadcast_duel_session(
        bot,
        storage,
        session,
        notes={target_id: result.text, challenger_id: challenger_text or result.text},
    )


@router.callback_query(F.data.startswith("dgrid:"))
async def duel_grid_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    storage = get_storage()
    telegram_id = callback.from_user.id
    action = (callback.data or "").removeprefix("dgrid:").strip()

    try:
        if await _reject_tactical_callback_if_dead(callback):
            return

        if action == "refresh":
            session = get_duel_session_by_player(storage, telegram_id)
            if session is None:
                await callback.answer("Активной дуэли нет.", show_alert=True)
                return
            await _broadcast_duel_session(bot, storage, session)
            await safe_callback_answer(callback)
            return

        if action == "forfeit":
            result = duel_forfeit(storage, telegram_id)
            await _handle_duel_action(bot, callback, result)
            return

        if action == "medkit":
            result = duel_use_medkit(storage, telegram_id)
            await _handle_duel_action(bot, callback, result)
            return

        if action.startswith("move:"):
            direction = action.removeprefix("move:")
            result = duel_move(storage, telegram_id, direction)
            await _handle_duel_action(bot, callback, result)
            return

        if action.startswith("shoot:"):
            direction = action.removeprefix("shoot:")
            result = duel_shoot(storage, telegram_id, direction)
            await _handle_duel_action(bot, callback, result)
            return

        await callback.answer("Неизвестное действие.", show_alert=True)
    except Exception:
        logger.exception("Duel grid callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка дуэли. Попробуй ещё раз или /fixme", show_alert=True)


@router.callback_query(F.data.startswith("cwar:"))
async def cwar_grid_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    storage = get_storage()
    telegram_id = callback.from_user.id
    action = (callback.data or "").removeprefix("cwar:").strip()

    try:
        if await _reject_tactical_callback_if_dead(callback):
            return

        if action == "refresh":
            session = get_cwar_session_by_player(storage, telegram_id)
            if session is None:
                await callback.answer("Нет активного штурма.", show_alert=True)
                return
            await _broadcast_cwar_session(bot, storage, session)
            await safe_callback_answer(callback)
            return

        if action == "forfeit":
            await callback.answer("Сдаться нельзя — только захват или поражение.", show_alert=True)
            return

        if action == "medkit":
            result = cwar_use_medkit(storage, telegram_id)
            await _handle_cwar_action(bot, callback, result)
            return

        if action.startswith("move:"):
            result = cwar_move(storage, telegram_id, action.removeprefix("move:"))
            await _handle_cwar_action(bot, callback, result)
            return

        if action.startswith("shoot:"):
            result = cwar_shoot(storage, telegram_id, action.removeprefix("shoot:"))
            await _handle_cwar_action(bot, callback, result)
            return

        await callback.answer("Неизвестное действие.", show_alert=True)
    except Exception:
        logger.exception("Clan war grid callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка штурма. Попробуй ещё раз или /fixme", show_alert=True)


@router.callback_query(F.data.startswith("rgrid:"))
async def rgrid_grid_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    storage = get_storage()
    telegram_id = callback.from_user.id
    action = (callback.data or "").removeprefix("rgrid:").strip()

    try:
        if await _reject_tactical_callback_if_dead(callback):
            return

        if action == "refresh":
            session = get_raid_grid_session_by_player(storage, telegram_id)
            if session is None:
                await callback.answer("Нет активного рейда.", show_alert=True)
                return
            await _broadcast_rgrid_session(bot, storage, session, callback=callback)
            await safe_callback_answer(callback)
            return

        if action == "forfeit":
            result = rgrid_forfeit(storage, telegram_id)
            await _handle_rgrid_action(bot, callback, result)
            return

        if action == "medkit":
            result = rgrid_use_medkit(storage, telegram_id)
            await _handle_rgrid_action(bot, callback, result)
            return

        if action.startswith("revive:"):
            try:
                target_id = int(action.removeprefix("revive:"))
            except ValueError:
                await callback.answer("Некорректный союзник.", show_alert=True)
                return
            result = rgrid_revive_ally(storage, telegram_id, target_id)
            await _handle_rgrid_action(bot, callback, result)
            return

        if action.startswith("move:"):
            result = rgrid_move(storage, telegram_id, action.removeprefix("move:"))
            await _handle_rgrid_action(bot, callback, result)
            return

        if action.startswith("shoot:"):
            result = rgrid_shoot(storage, telegram_id, action.removeprefix("shoot:"))
            await _handle_rgrid_action(bot, callback, result)
            return

        await callback.answer("Неизвестное действие.", show_alert=True)
    except Exception:
        logger.exception("Raid grid callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка рейда. Попробуй ещё раз или /fixme", show_alert=True)


@router.callback_query(F.data.startswith("agrid:"))
async def arena_grid_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    storage = get_storage()
    telegram_id = callback.from_user.id
    action = (callback.data or "").removeprefix("agrid:").strip()

    try:
        if await _reject_tactical_callback_if_dead(callback):
            return

        if action == "refresh":
            session = get_arena_session(storage, telegram_id)
            if session is None:
                await callback.answer("Нет активной арены.", show_alert=True)
                return
            await _broadcast_arena_session(bot, storage, session, callback=callback)
            await safe_callback_answer(callback)
            return

        if action == "forfeit":
            result = arena_forfeit(storage, telegram_id)
            await _handle_arena_action(bot, callback, result)
            return

        if action == "medkit":
            result = arena_use_medkit(storage, telegram_id)
            await _handle_arena_action(bot, callback, result)
            return

        if action.startswith("move:"):
            result = arena_move(storage, telegram_id, action.removeprefix("move:"))
            await _handle_arena_action(bot, callback, result)
            return

        if action.startswith("shoot:"):
            result = arena_shoot(storage, telegram_id, action.removeprefix("shoot:"))
            await _handle_arena_action(bot, callback, result)
            return

        await callback.answer("Неизвестное действие.", show_alert=True)
    except Exception:
        logger.exception("Arena grid callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка арены. Попробуй ещё раз или /fixme", show_alert=True)


@router.callback_query(F.data.startswith("ncap:"))
async def ncap_grid_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    storage = get_storage()
    telegram_id = callback.from_user.id
    action = (callback.data or "").removeprefix("ncap:").strip()

    try:
        if await _reject_tactical_callback_if_dead(callback):
            return

        if action in {"menu", "refresh"}:
            session = get_ncap_session(storage, telegram_id)
            if session is not None:
                await _broadcast_ncap_session(bot, storage, session)
                await safe_callback_answer(callback)
                return
            await _show_ncap_lobby_menu(callback, telegram_id)
            await safe_callback_answer(callback)
            return

        if action == "leave":
            result = leave_ncap_lobby(storage, telegram_id)
            await apply_action_notifies(bot, result)
            await reply_action_result(callback, result.text)
            if result.ok:
                await edit_menu_message(
                    callback,
                    ncap_lobby_menu_text(storage, telegram_id),
                    ncap_lobby_keyboard(in_lobby=False, is_host=False),
                )
            return

        if action.startswith("join:"):
            lobby_id = action.removeprefix("join:")
            result = join_ncap_lobby(storage, telegram_id, lobby_id)
            if not result.ok:
                await reply_action_result(callback, result.text)
                return
            await apply_action_notifies(bot, result)
            await _show_ncap_lobby_menu(callback, telegram_id)
            await safe_callback_answer(callback, "Ты в группе")
            return

        if action.startswith("start:"):
            lobby_id = action.removeprefix("start:")
            lobby = get_ncap_lobby_by_player(storage, telegram_id)
            if lobby is None or lobby.lobby_id != lobby_id:
                await callback.answer("Группа не найдена.", show_alert=True)
                return
            result, session = start_ncap_from_lobby(storage, telegram_id)
            if not result.ok:
                await reply_action_result(callback, result.text)
                return
            if session is not None:
                await _broadcast_ncap_session(bot, storage, session, note=result.text)
            notify_ids = [int(x) for x in (result.payload or {}).get("notify_all") or []]
            for pid in notify_ids:
                if pid != telegram_id:
                    await bot.send_message(pid, action_result_text(pid, result.text))
            await safe_callback_answer(callback, "Захват начался!")
            return

        if action == "forfeit":
            result = ncap_forfeit(storage, telegram_id)
            await _handle_ncap_action(bot, callback, result)
            return

        if action == "medkit":
            result = ncap_use_medkit(storage, telegram_id)
            await _handle_ncap_action(bot, callback, result)
            return

        if action.startswith("move:"):
            result = ncap_move(storage, telegram_id, action.removeprefix("move:"))
            await _handle_ncap_action(bot, callback, result)
            return

        if action.startswith("shoot:"):
            result = ncap_shoot(storage, telegram_id, action.removeprefix("shoot:"))
            await _handle_ncap_action(bot, callback, result)
            return

        await callback.answer("Неизвестное действие.", show_alert=True)
    except Exception:
        logger.exception("Neutral capture callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка захвата. Попробуй ещё раз или /fixme", show_alert=True)


@router.callback_query(F.data.startswith("duel:decline:"))
async def duel_decline_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    try:
        challenger_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await reply_action_result(callback, "Некорректный вызов.")
        return
    target_id = callback.from_user.id
    result, challenger_text = decline_duel(get_storage(), target_id, challenger_id)
    if result.ok:
        await safe_callback_answer(callback, "Дуэль отклонена")
        if callback.message:
            await callback.message.answer(action_result_text(target_id, result.text))
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
        if challenger_text:
            try:
                await bot.send_message(challenger_id, action_result_text(challenger_id, challenger_text))
            except Exception:
                logger.exception("Failed to notify duel decline to %s", challenger_id)
    else:
        await reply_action_result(callback, result.text)


@router.message(F.text == "🏕 Вылазка")
async def show_sortie(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    await message.answer(
        "🏕 Вылазка\n"
        "Война, переходы по Зоне, арена, рейды и кооп.",
        reply_markup=sortie_keyboard(),
    )


@router.message(F.text == "⚔️ Арена")
async def show_arena(message: Message, bot: Bot) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id, skip="arena"):
        return
    storage = get_storage()
    session = get_arena_session(storage, player.telegram_id)
    if session is not None:
        await _broadcast_arena_session(bot, storage, session)
        return
    result = start_arena(storage, player.telegram_id)
    if not result.ok:
        await message.answer(result.text)
        return
    session = get_arena_session(storage, player.telegram_id)
    if session is None:
        await message.answer(result.text)
        return
    await _broadcast_arena_session(bot, storage, session, note=result.text)


@router.message(F.text == "👥 Совместная вылазка")
async def show_coop_menu(message: Message, bot: Bot) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id, skip="coop"):
        return
    storage = get_storage()
    session = get_coop_session_by_player(storage, player.telegram_id)
    if session is not None:
        frame = render_coop_frame(storage, session, player.telegram_id)
        is_active = session.active_player() == player.telegram_id
        medkit = not session.medkits_used.get(str(player.telegram_id), False) and _player_has_medkit(player)
        evac = can_evacuate(session, player.telegram_id)
        markup = coop_mission_keyboard(is_active_turn=is_active, medkit_available=medkit, evac_available=evac)
        caption = coop_status_caption(session, storage, player.telegram_id)
        msg_id = session.message_ids.get(str(player.telegram_id))
        new_id = await _upsert_tactical_photo(
            bot,
            chat_id=player.telegram_id,
            message_id=msg_id,
            image_bytes=frame,
            caption=caption,
            markup=markup,
        )
        session.message_ids[str(player.telegram_id)] = new_id
        _patch_coop_message_ids(storage, session)
        return
    lobby = get_coop_lobby_by_player(storage, player.telegram_id)
    text = coop_menu_text(storage, player.telegram_id)
    await message.answer(
        text,
        reply_markup=coop_menu_keyboard(
            in_lobby=lobby is not None,
            is_host=lobby.host_id == player.telegram_id if lobby else False,
            lobby_id=lobby.lobby_id if lobby else None,
        ),
    )


@router.callback_query(F.data.startswith("coop:"))
async def coop_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.from_user
    storage = get_storage()
    telegram_id = callback.from_user.id
    action = (callback.data or "").removeprefix("coop:").strip()

    try:
        if await _reject_tactical_callback_if_dead(callback):
            return

        if action == "menu" or action == "refresh":
            text = coop_menu_text(storage, telegram_id)
            lobby = get_coop_lobby_by_player(storage, telegram_id)
            session = get_coop_session_by_player(storage, telegram_id)
            if session is not None:
                await _broadcast_coop_session(bot, storage, session)
                await safe_callback_answer(callback)
                return
            await edit_menu_message(
                callback,
                text,
                coop_menu_keyboard(
                    in_lobby=lobby is not None,
                    is_host=lobby.host_id == telegram_id if lobby else False,
                    lobby_id=lobby.lobby_id if lobby else None,
                ),
            )
            return

        if action == "create":
            result = create_coop_lobby(storage, telegram_id)
            if not result.ok:
                await reply_action_result(callback, result.text)
                return
            lobby = get_coop_lobby_by_player(storage, telegram_id)
            await edit_menu_message(
                callback,
                coop_menu_text(storage, telegram_id),
                coop_menu_keyboard(in_lobby=True, is_host=True, lobby_id=lobby.lobby_id if lobby else None),
            )
            return

        if action == "list":
            player = storage.get_character(telegram_id, refresh_energy=False)
            if player is None:
                await reply_action_result(callback, "Сначала создай персонажа.")
                return
            lobbies = list_open_coop_lobbies(storage, player.location)
            await edit_menu_message(
                callback,
                f"Открытые группы на «{player.location}»:",
                coop_lobby_list_keyboard(lobbies),
            )
            return

        if action == "leave":
            result = leave_coop_lobby(storage, telegram_id)
            await apply_action_notifies(bot, result)
            await reply_action_result(callback, result.text)
            if result.ok:
                await edit_menu_message(
                    callback,
                    coop_menu_text(storage, telegram_id),
                    coop_menu_keyboard(in_lobby=False, is_host=False),
                )
            return

        if action.startswith("join:"):
            lobby_id = action.removeprefix("join:")
            result = join_coop_lobby(storage, telegram_id, lobby_id)
            if not result.ok:
                await reply_action_result(callback, result.text)
                return
            await apply_action_notifies(bot, result)
            lobby = get_coop_lobby_by_player(storage, telegram_id)
            await edit_menu_message(
                callback,
                coop_menu_text(storage, telegram_id),
                coop_menu_keyboard(
                    in_lobby=True,
                    is_host=lobby.host_id == telegram_id if lobby else False,
                    lobby_id=lobby.lobby_id if lobby else None,
                ),
            )
            return

        if action.startswith("start:"):
            lobby_id = action.removeprefix("start:")
            lobby = get_coop_lobby_by_player(storage, telegram_id)
            if lobby is None or lobby.lobby_id != lobby_id:
                await reply_action_result(callback, "Группа не найдена.")
                return
            result = start_coop_mission(storage, telegram_id)
            if not result.ok:
                await reply_action_result(callback, result.text)
                return
            session = get_coop_session_by_player(storage, telegram_id)
            if session is None:
                await reply_action_result(callback, result.text)
                return
            await _broadcast_coop_session(bot, storage, session, note=result.text)
            await safe_callback_answer(callback, "Вылазка началась!")
            return

        if action == "forfeit":
            result = coop_forfeit(storage, telegram_id)
            await _handle_coop_action(bot, callback, result)
            return

        if action == "medkit":
            result = coop_use_medkit(storage, telegram_id)
            await _handle_coop_action(bot, callback, result)
            return

        if action.startswith("move:"):
            direction = action.removeprefix("move:")
            result = coop_move(storage, telegram_id, direction)
            await _handle_coop_action(bot, callback, result)
            return

        if action == "evac":
            result = coop_evacuate(storage, telegram_id)
            await _handle_coop_action(bot, callback, result)
            return

        await callback.answer("Неизвестное действие.", show_alert=True)
    except Exception:
        logger.exception("Coop callback failed for %s action=%s", telegram_id, action)
        await safe_callback_answer(callback, "Ошибка кооп-вылазки. Попробуй ещё раз или /fixme", show_alert=True)


@router.message(nav_button("🗺 Переход"))
async def show_travel(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id, skip="travel"):
        return
    db = get_storage()
    locations = db.get_locations()
    traveling = is_traveling(player)
    if traveling:
        loc = format_location_display(player)
        text = (
            f"{loc}\n"
            "⏱ Отсчёт времени — в отдельном сообщении с таймером.\n\n"
            "Пока идёт переход, другие действия на точке недоступны."
        )
    else:
        text = (
            "Выбери локацию, затем транспорт (велик доступен даже если есть Нива/грузовик).\n"
            f"Пешком ×1, велосипед ×{TRAVEL_SPEED_BICYCLE:g} "
            f"(+награда контракта ×{TRANSPORT_QUEST_REWARD_MULT['bicycle']:g} если доехал на нём), "
            f"Нива ×{TRAVEL_SPEED_NIVA:g}, грузовик ×{TRAVEL_SPEED_TRUCK:g} (+ дизель).\n"
            "Переход занимает реальное время (1 игровая мин ≈ 10 сек).\n\n"
            f"{describe_travel_fuel_status(player)}"
        )
    await message.answer(
        text,
        reply_markup=travel_keyboard(locations, traveling=traveling),
    )


@router.callback_query(F.data == "travel:status")
async def travel_status_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    status = travel_status_with_smuggle(get_storage(), callback.from_user.id) or travel_status_text(player)
    if not status:
        await callback.answer("Сейчас ты никуда не едешь.", show_alert=True)
        return
    if len(status) <= CALLBACK_ALERT_MAX_LEN:
        await callback.answer(status, show_alert=True)
        return
    await safe_callback_answer(callback)
    if callback.message:
        await callback.message.answer(status)


@router.callback_query(F.data == "travel:back")
async def travel_back_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    locations = get_storage().get_locations()
    traveling = bool(player.travel_destination)
    text = (
        "Выбери локацию, затем транспорт.\n\n"
        f"{describe_travel_fuel_status(player)}"
    )
    await edit_menu_message(
        callback,
        text,
        travel_keyboard(locations, traveling=traveling),
    )


@router.callback_query(F.data.startswith("travel:to:"))
async def travel_pick_destination(callback: CallbackQuery) -> None:
    destination = (callback.data or "").removeprefix("travel:to:").strip()
    storage = get_storage()
    player = storage.get_character(callback.from_user.id)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    if not destination:
        await callback.answer("Некорректная локация.", show_alert=True)
        return
    modes = [
        (mode, f"{label} (−{energy} эн.)")
        for mode, label, _speed, energy in list_available_travel_modes(
            player, bound_transport=storage.get_bound_transport(callback.from_user.id)
        )
    ]
    await edit_menu_message(
        callback,
        f"Куда: «{destination}».\nВыбери транспорт:",
        travel_transport_keyboard(destination, modes),
    )


@router.callback_query(F.data.startswith("travel:go:"))
async def travel_go_callback(callback: CallbackQuery, bot: Bot) -> None:
    parts = (callback.data or "").split(":", maxsplit=3)
    if len(parts) < 4:
        await callback.answer("Некорректный переход.", show_alert=True)
        return
    mode = parts[2]
    destination = parts[3]
    storage = get_storage()
    result = travel_to(
        storage,
        callback.from_user.id,
        destination,
        transport_mode=mode,
    )
    if not result.ok:
        await reply_action_result(callback, result.text, bot=bot)
        return
    await safe_callback_answer(callback, "В путь!")
    # Разовые детали выезда + live-таймер, который правится каждую секунду.
    if callback.message is not None:
        await callback.message.answer(action_result_text(callback.from_user.id, result.text))
    else:
        await bot.send_message(callback.from_user.id, action_result_text(callback.from_user.id, result.text))
    clear_travel_eta_message_id(get_storage(), callback.from_user.id)
    await publish_travel_live_eta(bot, callback.from_user.id)


@router.callback_query(F.data.startswith("travel:"))
async def handle_travel_legacy(callback: CallbackQuery) -> None:
    """Совместимость: travel:<destination> → выбор транспорта."""
    raw = (callback.data or "").split(":", maxsplit=1)
    if len(raw) < 2:
        return
    destination = raw[1]
    if destination in {"status", "back"} or destination.startswith(("to:", "go:")):
        return
    callback.data = f"travel:to:{destination}"
    await travel_pick_destination(callback)


@router.message(F.text == "⚔️ Война")
async def show_war(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return

    await message.answer("Раздел войны: выбери нужный блок.", reply_markup=war_sections_keyboard())


@router.callback_query(F.data == "war:section:root")
async def war_root_section_callback(callback: CallbackQuery) -> None:
    await edit_menu_message(
        callback,
        "Раздел войны: выбери нужный блок.",
        war_sections_keyboard(),
    )


@router.callback_query(F.data == "war:section:scenario")
async def war_scenario_section_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    alliance_overview = build_alliance_overview(db, player.telegram_id)
    explainer = (
        "Правила войны:\n"
        f"• Нейтральные — от {NCAP_MIN_MEMBERS} бойцов на 6×6 («🎯 Захват нейтральных точек», +{NCAP_SUCCESS_PAY_RU} RU, "
        f"+{RATING_REWARD['war_success']} рейт., −18 энергии, 8 мин; захват удержанием центра) "
        "или лобби от 5 на ту же точку (9×9, −24 энергии).\n"
        "• Занятые точки и базы — только лобби (мин. 5 бойцов), штурм 9×9, 10 мин / ход 10 сек, "
        f"−{WAR_LOBBY_ENERGY_COST} энергии, 1 аптечка/боец.\n"
        f"• Награды лобби (выжившим): хост +{WAR_SUCCESS_PAY_RU} RU (+{RATING_REWARD['war_success']} рейт.), "
        f"союзники +{WAR_ALLY_SUCCESS_PAY_RU} RU (+{WAR_ALLY_SUCCESS_RATING} рейт.).\n"
        "• Лидер группировки, стоя на своей точке, может передать её союзнику "
        "(«🎁 Передача точки союзнику»).\n"
        "• Рейды на логова — в «🪖 Рейды» (2–5 бойцов); "
        "успех: 1400 + 180×выживших RU в казну, −18 энергии; "
        f"склад/гараж — −{DEPOT_RAID_ENERGY_COST} энергии, только без союза.\n"
        "• В рейде: 1 аптечка, «💊 Поднять» раненого; «🏳 Сдаться» — провал для всех.\n"
        "• Нельзя штурмовать свои и союзнические точки.\n"
        "• При успехе лобби контроль получает группировка-хост.\n"
        "• Укрепление базы: 10000 RU из казны, +1 защитник и +1 урон за уровень в штурме.\n"
        "• Казна и склад — в «👥 Группировка».\n"
    )
    await edit_menu_message(
        callback,
        explainer + "\n" + alliance_overview,
        alliance_keyboard(),
    )


@router.callback_query(F.data == "war:section:ncap")
async def war_ncap_section_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    neutral = [
        loc
        for loc in storage.get_locations()
        if not str(loc.get("controlled_by") or "").strip()
    ]
    if not neutral:
        await edit_menu_message(
            callback,
            "Сейчас нет нейтральных точек для захвата.",
            war_sections_keyboard(),
        )
        return
    await edit_menu_message(
        callback,
        "Выбери нейтральную точку для захвата (нужна группа от 2 бойцов):",
        locations_keyboard(neutral, mode="war", back_callback="war:section:root"),
    )


@router.callback_query(F.data == "war:section:transfer")
async def war_transfer_section_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    if player.faction is None or storage.get_faction_leader_id(player.faction) != callback.from_user.id:
        await callback.answer("Передавать точку может только лидер группировки.", show_alert=True)
        return
    loc_name = player.location
    location = storage.get_location(loc_name)
    if location is None or str(location.get("controlled_by") or "") != player.faction:
        await edit_menu_message(
            callback,
            f"Передача доступна только на точке под контролем «{player.faction}».\n"
            f"Сейчас ты на «{loc_name}».",
            war_sections_keyboard(),
        )
        return
    allies = sorted(storage.list_faction_alliances(player.faction))
    if not allies:
        await edit_menu_message(
            callback,
            f"Точка «{loc_name}» под вашим контролем, но нет союзников для передачи.",
            war_sections_keyboard(),
        )
        return
    await edit_menu_message(
        callback,
        f"Точка «{loc_name}» под контролем «{player.faction}». Кому передать?",
        war_transfer_keyboard(allies, loc_name),
    )


@router.callback_query(F.data == "war:section:lobby")
async def war_lobby_section_callback(callback: CallbackQuery, bot: Bot) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    await _show_war_lobby_menu(callback, bot)


async def _show_war_lobby_menu(callback: CallbackQuery, bot: Bot) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        return
    overview = build_war_lobby_overview(db, player.telegram_id)
    markup = war_lobby_keyboard(
        list_assaultable_locations(db, player.faction or ""),
        can_dissolve=can_dissolve_war_lobby(db, player.telegram_id),
    )
    session = get_cwar_session_by_player(db, player.telegram_id)
    if session is not None:
        await _broadcast_cwar_session(bot, db, session)
        await safe_callback_answer(callback)
        return
    await edit_menu_message(callback, overview, markup)


async def _refresh_war_lobby_menu(callback: CallbackQuery, bot: Bot) -> None:
    await _show_war_lobby_menu(callback, bot)


@router.callback_query(F.data.startswith("war:transfer:"))
async def war_transfer_location_callback(callback: CallbackQuery) -> None:
    ally_faction = (callback.data or "").split(":", maxsplit=2)[2]
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    result = transfer_location_to_ally(get_storage(), callback.from_user.id, player.location, ally_faction)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("war:"))
async def handle_war_legacy_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Кнопки штурма: нейтральные точки — тактический захват."""
    location = (callback.data or "").split(":", maxsplit=1)[1]
    if location.startswith("section:") or location.startswith("transfer:"):
        await safe_callback_answer(callback)
        return
    result = attack_location(get_storage(), callback.from_user.id, location)
    if result.ok and (result.payload or {}).get("ncap_lobby"):
        await _show_ncap_lobby_menu(callback, callback.from_user.id)
        await safe_callback_answer(callback, result.text[:CALLBACK_ALERT_MAX_LEN] if len(result.text) <= CALLBACK_ALERT_MAX_LEN else "Группа")
        return
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("war_lobby:create:"))
async def war_lobby_create_callback(callback: CallbackQuery, bot: Bot) -> None:
    location = (callback.data or "").split(":", maxsplit=2)[2]
    result = create_or_join_war_lobby(get_storage(), callback.from_user.id, location)
    await reply_action_result(callback, result.text)
    if result.ok:
        await _refresh_war_lobby_menu(callback, bot)


@router.callback_query(F.data == "war_lobby:join")
async def war_lobby_join_callback(callback: CallbackQuery, bot: Bot) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Нужен персонаж с группировкой.", show_alert=True)
        return
    lobby = get_storage().get_open_war_lobby_for_faction(player.faction)
    if lobby is None:
        await callback.answer("Открытых лобби войны нет.", show_alert=True)
        return
    result = create_or_join_war_lobby(get_storage(), callback.from_user.id, str(lobby["location"]))
    await reply_action_result(callback, result.text)
    if result.ok:
        await _refresh_war_lobby_menu(callback, bot)


@router.callback_query(F.data == "war_lobby:launch")
async def war_lobby_launch_callback(callback: CallbackQuery, bot: Bot) -> None:
    result = launch_war_lobby(get_storage(), callback.from_user.id)
    if result.ok and result.tactical_cwar:
        storage = get_storage()
        session = get_cwar_session_by_player(storage, callback.from_user.id)
        if session is not None:
            await _broadcast_cwar_session(bot, storage, session, note=result.text)
            await safe_callback_answer(callback, "Тактический штурм!")
            return
    await deliver_group_result(callback, bot, result, prefix="📣 Итог штурма:")
    if result.ok:
        await _refresh_war_lobby_menu(callback, bot)


@router.callback_query(F.data == "war_lobby:dissolve")
async def war_lobby_dissolve_callback(callback: CallbackQuery, bot: Bot) -> None:
    result = dissolve_war_lobby(get_storage(), callback.from_user.id)
    await deliver_group_result(callback, bot, result, prefix="📣 Лобби распущено:")
    if result.ok:
        await _refresh_war_lobby_menu(callback, bot)


@router.callback_query(F.data.startswith("alliance:propose:"))
async def alliance_propose_callback(callback: CallbackQuery, bot: Bot) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = propose_alliance(get_storage(), callback.from_user.id, target_faction)
    await finish_callback_action(callback, result, bot)


@router.callback_query(F.data == "alliance:menu:propose")
async def alliance_propose_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    others = [
        str(faction.get("name", ""))
        for faction in db.get_factions()
        if str(faction.get("name", "")) and str(faction["name"]) != player.faction
    ]
    if not others:
        await edit_menu_message(callback, "Нет доступных группировок для предложения договора о союзе.", alliance_keyboard())
        return
    await edit_menu_message(
        callback,
        "Выбери группировку для предложения договора о союзе:",
        alliance_target_keyboard(db.get_factions(), player.faction, mode="propose"),
    )


@router.callback_query(F.data == "alliance:menu:declare_war")
async def alliance_war_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    others = [
        str(faction.get("name", ""))
        for faction in db.get_factions()
        if str(faction.get("name", "")) and str(faction["name"]) != player.faction
    ]
    if not others:
        await edit_menu_message(callback, "Нет доступных группировок для объявления войны.", alliance_keyboard())
        return
    await edit_menu_message(
        callback,
        "Выбери группировку для объявления войны:",
        alliance_target_keyboard(db.get_factions(), player.faction, mode="declare_war"),
    )


@router.callback_query(F.data == "alliance:menu:break")
async def alliance_break_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    others = [
        str(faction.get("name", ""))
        for faction in db.get_factions()
        if str(faction.get("name", "")) and str(faction["name"]) != player.faction
    ]
    if not others:
        await edit_menu_message(callback, "Нет доступных группировок для разрыва союза.", alliance_keyboard())
        return
    await edit_menu_message(
        callback,
        "Выбери группировку для разрыва союза:",
        alliance_target_keyboard(db.get_factions(), player.faction, mode="break"),
    )


@router.callback_query(F.data == "alliance:menu:confirm")
async def alliance_confirm_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    incoming = db.list_incoming_alliance_requests(player.faction)
    pending_from = [str(row["requester_faction"]) for row in incoming]
    if not pending_from:
        await edit_menu_message(callback, "Входящих предложений на союз нет.", alliance_keyboard())
        return
    await edit_menu_message(
        callback,
        "Входящие предложения на союз:",
        alliance_pending_keyboard(pending_from),
    )


@router.callback_query(F.data == "alliance:menu:back")
async def alliance_menu_back_callback(callback: CallbackQuery) -> None:
    await edit_menu_message(callback, "Раздел дипломатии:", alliance_keyboard())



@router.callback_query(F.data.startswith("alliance:confirm:"))
async def alliance_confirm_callback(callback: CallbackQuery, bot: Bot) -> None:
    source_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = accept_alliance(get_storage(), callback.from_user.id, source_faction)
    await finish_callback_action(callback, result, bot)


@router.callback_query(F.data.startswith("alliance:break:"))
async def alliance_break_callback(callback: CallbackQuery, bot: Bot) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = break_alliance(get_storage(), callback.from_user.id, target_faction)
    await finish_callback_action(callback, result, bot)


@router.callback_query(F.data.startswith("alliance:war:"))
async def alliance_war_callback(callback: CallbackQuery, bot: Bot) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = declare_war(get_storage(), callback.from_user.id, target_faction)
    await finish_callback_action(callback, result, bot)


@router.message(F.text == "🪖 Рейды")
async def show_raids(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return
    db = get_storage()
    text = build_raids_overview(db, player.telegram_id)
    led_raids = db.list_open_raids_led_by(player.telegram_id)
    war_enemies = list_war_enemy_factions(db, player.faction) if player.faction else []
    await message.answer(
        text,
        reply_markup=raid_keyboard(db.get_locations(), led_raids=led_raids, war_enemy_factions=war_enemies),
    )


@router.callback_query(F.data.startswith("raid:create:"))
async def create_raid_callback(callback: CallbackQuery, bot: Bot) -> None:
    location = (callback.data or "").split(":", maxsplit=2)[2]
    result = create_or_join_faction_raid(get_storage(), callback.from_user.id, location)
    await reply_action_result(callback, result.text, bot=bot)
    await apply_action_notifies(bot, result)


@router.callback_query(F.data.startswith("raid:depot:"))
async def create_depot_raid_callback(callback: CallbackQuery, bot: Bot) -> None:
    parts = (callback.data or "").split(":", maxsplit=3)
    if len(parts) != 4 or parts[2] not in DEPOT_RAID_KINDS:
        await callback.answer("Некорректный запрос рейда.", show_alert=True)
        return
    depot_kind, target_faction = parts[2], parts[3]
    result = create_or_join_depot_raid(get_storage(), callback.from_user.id, target_faction, depot=depot_kind)
    await reply_action_result(callback, result.text, bot=bot)
    await apply_action_notifies(bot, result)


@router.callback_query(F.data == "raid:join")
async def join_raid_callback(callback: CallbackQuery, bot: Bot) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Нужен персонаж с группировкой.", show_alert=True)
        return
    open_raid = get_storage().get_open_raid_for_faction(player.faction)
    if open_raid is None:
        await callback.answer("Открытых рейдов нет.", show_alert=True)
        return
    raid_kind = resolve_open_raid_kind(open_raid)
    if raid_kind in DEPOT_RAID_KINDS:
        result = create_or_join_depot_raid(
            get_storage(),
            callback.from_user.id,
            str(open_raid.get("target_faction") or ""),
            depot=raid_kind,
        )
    else:
        result = create_or_join_faction_raid(get_storage(), callback.from_user.id, str(open_raid["location"]))
    await reply_action_result(callback, result.text, bot=bot)
    await apply_action_notifies(bot, result)


@router.callback_query(F.data == "raid:ally:join")
async def join_raid_as_ally_callback(callback: CallbackQuery, bot: Bot) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Нужен персонаж с группировкой.", show_alert=True)
        return
    storage = get_storage()
    open_raid = storage.get_open_raid_for_faction(player.faction)
    if open_raid is None:
        for ally in storage.list_faction_alliances(player.faction):
            ally_open = storage.get_open_raid_for_faction(ally)
            if ally_open is not None:
                open_raid = ally_open
                break
    if open_raid is None:
        await callback.answer("Открытых рейдов союзников нет.", show_alert=True)
        return
    raid_kind = resolve_open_raid_kind(open_raid)
    if raid_kind in DEPOT_RAID_KINDS:
        result = create_or_join_depot_raid(
            storage,
            callback.from_user.id,
            str(open_raid.get("target_faction") or ""),
            depot=raid_kind,
        )
    else:
        result = create_or_join_faction_raid(storage, callback.from_user.id, str(open_raid["location"]))
    await reply_action_result(callback, result.text, bot=bot)
    await apply_action_notifies(bot, result)


@router.callback_query(F.data == "raid:launch")
async def launch_raid_callback(callback: CallbackQuery, bot: Bot) -> None:
    storage = get_storage()
    telegram_id = callback.from_user.id
    clear_stale_raid_grid_session(storage, telegram_id)

    session = get_raid_grid_session_by_player(storage, telegram_id)
    if session is None:
        player = storage.get_character(telegram_id, refresh_energy=False)
        if player is not None and player.faction:
            session = find_raid_grid_session_for_faction(storage, player.faction)

    if session is not None:
        await safe_callback_answer(callback, "Карта рейда")
        try:
            await _broadcast_rgrid_session(bot, storage, session, callback=callback)
        except Exception:
            logger.exception("Failed to re-open tactical raid map for user %s", telegram_id)
            await reply_action_result(callback, "Не удалось показать карту рейда.", bot=bot)
        return

    result = launch_open_raid(storage, telegram_id)
    if result.ok and result.tactical_raid:
        session = get_raid_grid_session_by_player(storage, telegram_id)
        if session is None:
            for pid in result.notify_member_ids:
                session = get_raid_grid_session_by_player(storage, pid)
                if session is not None:
                    break
        if session is not None:
            await safe_callback_answer(callback, "Тактический рейд!")
            try:
                await _broadcast_rgrid_session(bot, storage, session, note=result.text, callback=callback)
            except Exception:
                logger.exception("Failed to broadcast tactical raid map for raid #%s", session.raid_id)
                await reply_action_result(
                    callback,
                    f"{result.text}\n\n⚠️ Не удалось отправить карту. Попробуй нажать «Запустить» ещё раз.",
                    bot=bot,
                )
                return
            for pid in result.notify_member_ids:
                if pid == telegram_id:
                    continue
                try:
                    await bot.send_message(pid, action_result_text(pid, result.text))
                except Exception:
                    logger.exception("Failed to notify rgrid start to %s", pid)
            return
        logger.error(
            "Tactical raid started but rgrid session missing (leader=%s, members=%s)",
            telegram_id,
            result.notify_member_ids,
        )
        await reply_action_result(
            callback,
            f"{result.text}\n\n⚠️ Карта не найдена. Попробуй нажать «Запустить» ещё раз.",
            bot=bot,
        )
        return

    await deliver_group_result(callback, bot, result, prefix="📣 Итог рейда:")


@router.callback_query(F.data == "raid:cancel:all")
async def cancel_all_raids_callback(callback: CallbackQuery, bot: Bot) -> None:
    storage = get_storage()
    leader_id = callback.from_user.id
    open_raids = storage.list_open_raids_led_by(leader_id)
    notify_ids: set[int] = set()
    for raid in open_raids:
        notify_ids.update(storage.get_raid_member_ids(int(raid["id"])))

    result = cancel_all_raids_by_leader(storage, leader_id)
    if result.ok and notify_ids:
        from types import SimpleNamespace

        group = SimpleNamespace(
            ok=True,
            text=f"Рейд отменён создателем.\n{result.text}",
            notify_member_ids=tuple(notify_ids),
        )
        await deliver_group_result(callback, bot, group, prefix="📣")
    else:
        await reply_action_result(callback, result.text, bot=bot)


@router.callback_query(F.data.startswith("raid:cancel:"))
async def cancel_one_raid_callback(callback: CallbackQuery, bot: Bot) -> None:
    payload = (callback.data or "").split(":")
    # raid:cancel:all handled above; raid:cancel:<id>
    if len(payload) != 3 or payload[2] == "all":
        return
    try:
        raid_id = int(payload[2])
    except ValueError:
        await callback.answer("Некорректный рейд", show_alert=True)
        return

    storage = get_storage()
    leader_id = callback.from_user.id
    member_ids = tuple(storage.get_raid_member_ids(raid_id))
    result = cancel_raid_by_leader(storage, leader_id, raid_id)
    if result.ok and member_ids:
        from types import SimpleNamespace

        group = SimpleNamespace(
            ok=True,
            text=result.text,
            notify_member_ids=member_ids,
        )
        await deliver_group_result(callback, bot, group, prefix="📣")
    else:
        await reply_action_result(callback, result.text, bot=bot)


def _pda_keyboard_for(player: Character | None):
    is_leader = False
    if player is not None and player.faction:
        storage = get_storage()
        is_leader = storage.get_faction_leader_id(player.faction) == player.telegram_id
    return pda_keyboard(is_leader=is_leader)


def _faction_group_keyboard_for(telegram_id: int):
    storage = get_storage()
    player = storage.get_character(telegram_id, refresh_energy=False)
    is_leader = bool(
        player
        and player.faction
        and storage.get_faction_leader_id(player.faction) == telegram_id
    )
    can_wh = bool(player and can_withdraw_faction_warehouse(storage, player))
    can_tr = bool(player and can_withdraw_faction_treasury(storage, player))
    can_request = bool(player and can_request_garage_vehicle_rental(storage, player))
    pending = 0
    if player and player.faction and can_wh:
        pending = len(list_garage_rental_requests_for_faction(storage, player.faction))
    return faction_group_keyboard(
        is_leader=is_leader,
        can_withdraw_warehouse=can_wh,
        can_withdraw_treasury=can_tr,
        can_request_garage_rental=can_request,
        pending_garage_requests=pending,
    )


@router.message(F.text == "🛰 События")
async def show_events(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    overview = build_events_overview(get_storage())
    await message.answer(overview)


@router.message(F.text == "👥 Группировка")
async def show_faction_group(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return
    text = build_faction_group_overview(get_storage(), player.telegram_id)
    await message.answer(text, reply_markup=_faction_group_keyboard_for(player.telegram_id))


@router.message(F.text == "🏦 Экономика")
async def show_economy(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if await reject_if_dead(message, player):
        return
    if await reject_if_busy(message, player.telegram_id):
        return
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return
    text = build_economy_overview(get_storage(), player.telegram_id)
    await message.answer(text, reply_markup=economy_keyboard())


@router.callback_query(F.data.startswith("eco:warehouse:deposit:"))
async def warehouse_deposit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
    if item_key not in WAREHOUSE_CUSTOM_ITEM_KEYS:
        await callback.answer("Неизвестный предмет для склада.", show_alert=True)
        return
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    label = ITEM_LABELS.get(item_key, item_key)
    await state.set_state(Registration.warehouse_deposit_custom)
    await state.update_data(warehouse_item_key=item_key)
    if callback.message is not None:
        await callback.message.answer(
            f"Сколько «{label}» сдать на склад?\n"
            f"Введи целое число от {WAREHOUSE_CUSTOM_MIN} до {WAREHOUSE_CUSTOM_MAX}."
            f"{FSM_CANCEL_HINT}"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("eco:warehouse:withdraw:"))
async def warehouse_withdraw_callback(callback: CallbackQuery, state: FSMContext) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
    if item_key not in WAREHOUSE_CUSTOM_ITEM_KEYS:
        await callback.answer("Неизвестный предмет для склада.", show_alert=True)
        return
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    if not can_withdraw_faction_warehouse(storage, player):
        await callback.answer(
            "Забирать со склада можно с 5 ранга (или лидеру группировки).",
            show_alert=True,
        )
        return
    label = ITEM_LABELS.get(item_key, item_key)
    await state.set_state(Registration.warehouse_withdraw_custom)
    await state.update_data(warehouse_item_key=item_key)
    if callback.message is not None:
        await callback.message.answer(
            f"Сколько «{label}» забрать со склада?\n"
            f"Введи целое число от {WAREHOUSE_CUSTOM_MIN} до {WAREHOUSE_CUSTOM_MAX}."
            f"{FSM_CANCEL_HINT}"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("faction:garage:deposit:"))
async def faction_garage_deposit_callback(callback: CallbackQuery) -> None:
    kind = (callback.data or "").split(":", maxsplit=3)[3]
    storage = get_storage()
    if kind == "niva":
        result = garage_deposit_niva(storage, callback.from_user.id)
    elif kind == "truck":
        result = garage_deposit_truck(storage, callback.from_user.id)
    elif kind in ("gasoline", "diesel"):
        result = garage_deposit_fuel(storage, callback.from_user.id, kind)
    else:
        result = ActionResult(False, "Неизвестный тип сдачи в гараж.")
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("faction:garage:withdraw:"))
async def faction_garage_withdraw_callback(callback: CallbackQuery) -> None:
    kind = (callback.data or "").split(":", maxsplit=3)[3]
    storage = get_storage()
    if kind == "niva":
        result = garage_withdraw_niva(storage, callback.from_user.id)
    elif kind == "truck":
        result = garage_withdraw_truck(storage, callback.from_user.id)
    elif kind in ("gasoline", "diesel"):
        result = garage_withdraw_fuel(storage, callback.from_user.id, kind)
    else:
        result = ActionResult(False, "Неизвестный тип выдачи из гаража.")
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("faction:garage:request:"))
async def faction_garage_request_callback(callback: CallbackQuery) -> None:
    kind = (callback.data or "").split(":", maxsplit=3)[3]
    storage = get_storage()
    if kind not in ("niva", "truck"):
        await callback.answer("Неизвестный запрос.", show_alert=True)
        return
    result = request_garage_vehicle_rental(storage, callback.from_user.id, kind)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "faction:garage:requests:back")
async def faction_garage_requests_back_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    text = build_faction_group_overview(storage, callback.from_user.id)
    await edit_menu_message(callback, text, _faction_group_keyboard_for(callback.from_user.id))


@router.callback_query(F.data == "faction:garage:requests")
async def faction_garage_requests_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    if not can_withdraw_faction_warehouse(storage, player):
        await callback.answer("Запросы видят бойцы 5+ ранга.", show_alert=True)
        return
    requests = list_garage_rental_requests_for_faction(storage, player.faction)
    text = build_garage_rental_requests_overview(storage, callback.from_user.id)
    keyboard = garage_rental_requests_keyboard(requests) if requests else _faction_group_keyboard_for(
        callback.from_user.id
    )
    await edit_menu_message(callback, text, keyboard)


@router.callback_query(F.data.startswith("faction:garage:approve:"))
async def faction_garage_approve_callback(callback: CallbackQuery) -> None:
    request_id = (callback.data or "").split(":", maxsplit=3)[3]
    storage = get_storage()
    result = approve_garage_rental_request(storage, callback.from_user.id, request_id)
    await reply_action_result(callback, result.text)
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is not None and player.faction:
        requests = list_garage_rental_requests_for_faction(storage, player.faction)
        text = build_garage_rental_requests_overview(storage, callback.from_user.id)
        keyboard = garage_rental_requests_keyboard(requests) if requests else _faction_group_keyboard_for(
            callback.from_user.id
        )
        try:
            await edit_menu_message(callback, text, keyboard, answer_callback=False)
        except TelegramBadRequest:
            pass


@router.callback_query(F.data.startswith("faction:garage:deny:"))
async def faction_garage_deny_callback(callback: CallbackQuery) -> None:
    request_id = (callback.data or "").split(":", maxsplit=3)[3]
    storage = get_storage()
    result = deny_garage_rental_request(storage, callback.from_user.id, request_id)
    await reply_action_result(callback, result.text)
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is not None and player.faction:
        requests = list_garage_rental_requests_for_faction(storage, player.faction)
        text = build_garage_rental_requests_overview(storage, callback.from_user.id)
        keyboard = garage_rental_requests_keyboard(requests) if requests else _faction_group_keyboard_for(
            callback.from_user.id
        )
        try:
            await edit_menu_message(callback, text, keyboard, answer_callback=False)
        except TelegramBadRequest:
            pass


def _parse_warehouse_custom_amount(raw: str) -> int | None:
    cleaned = (raw or "").strip().replace(" ", "").replace("_", "")
    try:
        amount = int(cleaned)
    except ValueError:
        return None
    if amount < WAREHOUSE_CUSTOM_MIN or amount > WAREHOUSE_CUSTOM_MAX:
        return None
    return amount


@router.message(Registration.warehouse_deposit_custom)
async def process_warehouse_deposit_custom(message: Message, state: FSMContext) -> None:
    if await abort_fsm_if_nav(message, state):
        return
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return
    if player.faction is None:
        await state.clear()
        await message.answer("Сначала выбери группировку.")
        return
    data = await state.get_data()
    item_key = str(data.get("warehouse_item_key") or "")
    if item_key not in WAREHOUSE_CUSTOM_ITEM_KEYS:
        await state.clear()
        await message.answer("Неизвестный предмет. Начни снова из меню группировки.")
        return
    amount = _parse_warehouse_custom_amount(message.text or "")
    if amount is None:
        await message.answer(
            f"Нужно целое число от {WAREHOUSE_CUSTOM_MIN} до {WAREHOUSE_CUSTOM_MAX}, например: 5"
        )
        return
    await state.clear()
    result = deposit_to_faction_warehouse(get_storage(), message.from_user.id, item_key, amount)
    await message.answer(action_result_text(message.from_user.id, result.text))


@router.message(Registration.warehouse_withdraw_custom)
async def process_warehouse_withdraw_custom(message: Message, state: FSMContext) -> None:
    if await abort_fsm_if_nav(message, state):
        return
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return
    storage = get_storage()
    if player.faction is None or not can_withdraw_faction_warehouse(storage, player):
        await state.clear()
        await message.answer("Забирать со склада можно с 5 ранга (или лидеру группировки).")
        return
    data = await state.get_data()
    item_key = str(data.get("warehouse_item_key") or "")
    if item_key not in WAREHOUSE_CUSTOM_ITEM_KEYS:
        await state.clear()
        await message.answer("Неизвестный предмет. Начни снова из меню группировки.")
        return
    amount = _parse_warehouse_custom_amount(message.text or "")
    if amount is None:
        await message.answer(
            f"Нужно целое число от {WAREHOUSE_CUSTOM_MIN} до {WAREHOUSE_CUSTOM_MAX}, например: 5"
        )
        return
    await state.clear()
    result = withdraw_from_faction_warehouse(storage, message.from_user.id, item_key, amount)
    await message.answer(action_result_text(message.from_user.id, result.text))


@router.callback_query(F.data.startswith("eco:treasury:deposit:"))
async def treasury_deposit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    raw_amount = (callback.data or "").split(":", maxsplit=3)[3]
    if raw_amount == "custom":
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is None or player.faction is None:
            await callback.answer("Сначала выбери группировку.", show_alert=True)
            return
        await state.set_state(Registration.treasury_deposit_custom)
        if callback.message is not None:
            await callback.message.answer(
                "Введи сумму для внесения в казну (целое число RU).\n"
                f"Допустимо: от {TREASURY_CUSTOM_MIN_RU} до {TREASURY_CUSTOM_MAX_RU}."
                f"{FSM_CANCEL_HINT}"
            )
        await callback.answer()
        return
    try:
        amount = int(raw_amount)
    except ValueError:
        await callback.answer("Некорректная сумма.", show_alert=True)
        return
    result = deposit_to_faction_treasury(get_storage(), callback.from_user.id, amount)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("eco:treasury:withdraw:"))
async def treasury_withdraw_callback(callback: CallbackQuery, state: FSMContext) -> None:
    raw_amount = (callback.data or "").split(":", maxsplit=3)[3]
    if raw_amount == "custom":
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is None or player.faction is None:
            await callback.answer("Сначала выбери группировку.", show_alert=True)
            return
        if not can_withdraw_faction_treasury(storage, player):
            await callback.answer(
                "Снимать из казны может только лидер группировки.",
                show_alert=True,
            )
            return
        await state.set_state(Registration.treasury_withdraw_custom)
        if callback.message is not None:
            await callback.message.answer(
                "Введи сумму для снятия из казны (целое число RU).\n"
                f"Допустимо: от {TREASURY_CUSTOM_MIN_RU} до {TREASURY_CUSTOM_MAX_RU}."
                f"{FSM_CANCEL_HINT}"
            )
        await callback.answer()
        return
    try:
        amount = int(raw_amount)
    except ValueError:
        await callback.answer("Некорректная сумма.", show_alert=True)
        return
    result = withdraw_from_faction_treasury(get_storage(), callback.from_user.id, amount)
    await reply_action_result(callback, result.text)


def _parse_treasury_custom_amount(raw: str) -> int | None:
    cleaned = (raw or "").strip().replace(" ", "").replace("_", "")
    try:
        amount = int(cleaned)
    except ValueError:
        return None
    if amount < TREASURY_CUSTOM_MIN_RU or amount > TREASURY_CUSTOM_MAX_RU:
        return None
    return amount


@router.message(Registration.treasury_deposit_custom)
async def process_treasury_deposit_custom(message: Message, state: FSMContext) -> None:
    if await abort_fsm_if_nav(message, state):
        return
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return
    if player.faction is None:
        await state.clear()
        await message.answer("Сначала выбери группировку.")
        return
    amount = _parse_treasury_custom_amount(message.text or "")
    if amount is None:
        await message.answer(
            f"Нужно целое число от {TREASURY_CUSTOM_MIN_RU} до {TREASURY_CUSTOM_MAX_RU}, например: 2500"
        )
        return
    await state.clear()
    result = deposit_to_faction_treasury(get_storage(), message.from_user.id, amount)
    await message.answer(action_result_text(message.from_user.id, result.text))


@router.message(Registration.treasury_withdraw_custom)
async def process_treasury_withdraw_custom(message: Message, state: FSMContext) -> None:
    if await abort_fsm_if_nav(message, state):
        return
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return
    storage = get_storage()
    if player.faction is None or not can_withdraw_faction_treasury(storage, player):
        await state.clear()
        await message.answer("Снимать из казны может только лидер группировки.")
        return
    amount = _parse_treasury_custom_amount(message.text or "")
    if amount is None:
        await message.answer(
            f"Нужно целое число от {TREASURY_CUSTOM_MIN_RU} до {TREASURY_CUSTOM_MAX_RU}, например: 2500"
        )
        return
    await state.clear()
    result = withdraw_from_faction_treasury(storage, message.from_user.id, amount)
    await message.answer(action_result_text(message.from_user.id, result.text))


@router.callback_query(F.data == "faction:menu:root")
@router.callback_query(F.data == "faction:warehouse:view")
@router.callback_query(F.data == "eco:warehouse:view")
async def faction_group_root_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    if not player_ready(player):
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    text = build_faction_group_overview(get_storage(), player.telegram_id)
    await edit_menu_message(callback, text, _faction_group_keyboard_for(player.telegram_id))


@router.callback_query(F.data == "faction:base:fortify")
async def faction_base_fortify_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    if not player_ready(player):
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    result = upgrade_faction_base(storage, callback.from_user.id)
    overview = build_faction_group_overview(storage, player.telegram_id)
    await edit_menu_message(
        callback,
        f"{result.text}\n\n{overview}",
        _faction_group_keyboard_for(player.telegram_id),
    )


@router.callback_query(F.data == "faction:bots:upgrade")
async def faction_bots_upgrade_callback(callback: CallbackQuery) -> None:
    from app.faction_bots import upgrade_faction_bots

    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    result = upgrade_faction_bots(storage, callback.from_user.id)
    overview = build_faction_group_overview(storage, player.telegram_id)
    await edit_menu_message(
        callback,
        f"{result.text}\n\n{overview}",
        _faction_group_keyboard_for(player.telegram_id),
    )


@router.callback_query(F.data == "faction:bots:count")
async def faction_bots_count_callback(callback: CallbackQuery) -> None:
    from app.faction_bots import upgrade_faction_bot_count

    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    result = upgrade_faction_bot_count(storage, callback.from_user.id)
    overview = build_faction_group_overview(storage, player.telegram_id)
    await edit_menu_message(
        callback,
        f"{result.text}\n\n{overview}",
        _faction_group_keyboard_for(player.telegram_id),
    )


@router.callback_query(F.data == "eco:menu:root")
async def economy_root_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    if not player_ready(player):
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    text = build_economy_overview(get_storage(), player.telegram_id)
    await edit_menu_message(callback, text, economy_keyboard())


@router.callback_query(F.data == "rank:leader:info")
async def rank_leader_info_callback(callback: CallbackQuery) -> None:
    await callback.answer("Лидеру нельзя назначить звание самому себе.", show_alert=True)


@router.callback_query(F.data == "rank:menu")
async def faction_ranks_menu_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    if storage.get_faction_leader_id(player.faction) != player.telegram_id:
        await callback.answer("Назначать звания может только лидер.", show_alert=True)
        return
    members = storage.list_faction_members(player.faction)
    text = build_faction_ranks_overview(storage, player.telegram_id)
    await edit_menu_message(
        callback,
        text,
        faction_ranks_members_keyboard(members, leader_id=player.telegram_id),
    )


@router.callback_query(F.data.startswith("rank:member:"))
async def faction_rank_member_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Сначала выбери группировку.", show_alert=True)
        return
    if storage.get_faction_leader_id(player.faction) != player.telegram_id:
        await callback.answer("Назначать звания может только лидер.", show_alert=True)
        return
    raw_id = (callback.data or "").split(":", maxsplit=2)[2]
    try:
        target_id = int(raw_id)
    except ValueError:
        await callback.answer("Некорректный игрок.", show_alert=True)
        return
    text = build_faction_member_rank_pick_text(storage, player.telegram_id, target_id)
    ranks = [(rank.key, f"{rank.level}) {rank.title}") for rank in ranks_for_faction(player.faction)]
    await edit_menu_message(callback, text, faction_rank_pick_keyboard(target_id, ranks))


@router.callback_query(F.data.startswith("rank:set:"))
async def faction_rank_set_callback(callback: CallbackQuery, bot: Bot) -> None:
    storage = get_storage()
    parts = (callback.data or "").split(":", maxsplit=3)
    if len(parts) != 4:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        target_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный игрок.", show_alert=True)
        return
    rank_key = parts[3]
    result = assign_faction_rank(storage, callback.from_user.id, target_id, rank_key)
    if not result.ok:
        await callback.answer(result.text, show_alert=True)
        return
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await reply_action_result(callback, result.text)
        return
    members = storage.list_faction_members(player.faction)
    overview = build_faction_ranks_overview(storage, player.telegram_id)
    await edit_menu_message(
        callback,
        f"{result.text}\n\n{overview}",
        faction_ranks_members_keyboard(members, leader_id=player.telegram_id),
    )
    await apply_action_notifies(bot, result)


@router.callback_query(F.data.startswith("eco:auction:create:"))
async def auction_create_callback(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":", maxsplit=3)
    if len(parts) < 4:
        await callback.answer("Некорректный лот.", show_alert=True)
        return
    lot_key = parts[3]
    result = create_faction_auction(get_storage(), callback.from_user.id, lot_key)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("eco:market:create:"))
async def market_create_callback(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":", maxsplit=3)
    if len(parts) < 4:
        await callback.answer("Некорректный предмет.", show_alert=True)
        return
    item_key = parts[3]
    if item_key == "choose":
        await state.clear()
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is None:
            await callback.answer("Сначала создай персонажа.", show_alert=True)
            return
        options = list_sellable_market_equipment(storage, callback.from_user.id)
        if not options:
            await callback.answer("В инвентаре нет оружия или брони для выставления на рынок.", show_alert=True)
            return
        await edit_menu_message(
            callback,
            "Выбери предмет из инвентаря для выставления на рынок:",
            market_create_select_keyboard(options),
        )
        return
    await state.set_state(Registration.market_lot_price)
    await state.update_data(market_item_key=item_key)
    await edit_menu_message(
        callback,
        "Введи цену лота в RU (целое число больше 0).\n"
        "Пример: 800\n"
        "Комиссия рынка 25%: покупатель платит цену лота, продавец получает 75%.",
        economy_keyboard(),
    )


@router.message(Registration.market_lot_price)
async def process_market_lot_price(message: Message, state: FSMContext) -> None:
    if await abort_fsm_if_nav(message, state):
        return
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return

    raw_price = (message.text or "").strip().replace(" ", "")
    try:
        lot_price = int(raw_price)
    except ValueError:
        await message.answer("Цена должна быть целым числом, например: 800")
        return
    if lot_price <= 0:
        await message.answer("Цена должна быть больше нуля.")
        return

    data = await state.get_data()
    item_key = str(data.get("market_item_key", "")).strip()
    if not item_key:
        await state.clear()
        await message.answer("Не удалось определить предмет для лота. Попробуй снова через Экономику.")
        return

    result = create_market_lot(get_storage(), message.from_user.id, item_key, 1, price=lot_price)
    await state.clear()
    await message.answer(action_result_text(message.from_user.id, result.text))



@router.callback_query(F.data == "eco:market:list")
async def market_list_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    text, lots = build_market_lots_overview(storage, callback.from_user.id, limit=12)
    menu_text = text if not lots else f"{text}\n\nВыбери лот для покупки:"
    await edit_menu_message(callback, menu_text, market_lots_keyboard(lots))


@router.callback_query(F.data.startswith("eco:market:buy:"))
async def market_buy_by_id_callback(callback: CallbackQuery, bot: Bot) -> None:
    lot_id = (callback.data or "").split(":", maxsplit=3)[3]
    try:
        auction_id = int(lot_id)
    except ValueError:
        await callback.answer("Некорректный ID лота.", show_alert=True)
        return
    result = buy_market_lot(get_storage(), callback.from_user.id, auction_id)
    await finish_callback_action(callback, result, bot)


@router.callback_query(F.data == "eco:market:cancel:mine")
async def market_cancel_mine_callback(callback: CallbackQuery) -> None:
    result = cancel_own_first_market_lot(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "eco:auction:buy:first")
async def auction_buy_first_callback(callback: CallbackQuery, bot: Bot) -> None:
    result = buy_first_faction_auction(get_storage(), callback.from_user.id)
    await finish_callback_action(callback, result, bot)


@router.callback_query(F.data == "eco:auction:cancel:mine")
async def auction_cancel_mine_callback(callback: CallbackQuery) -> None:
    result = cancel_own_first_auction(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "eco:auction:custom:choose")
async def auction_custom_choose_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    options = list_sellable_exchange_items(storage, callback.from_user.id)
    if not options:
        await callback.answer("В инвентаре нет подходящих предметов для своего лота на бирже.", show_alert=True)
        return
    await edit_menu_message(
        callback,
        "Выбери предмет из инвентаря для своего лота на бирже:",
        exchange_custom_select_keyboard(options),
    )


@router.callback_query(F.data.startswith("eco:auction:custom:"))
async def auction_custom_create_callback(callback: CallbackQuery, state: FSMContext) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
    await state.set_state(Registration.auction_lot_price)
    await state.update_data(auction_item_key=item_key)
    await edit_menu_message(
        callback,
        "Введи цену лота в RU (целое число больше 0).\n"
        "Пример: 500\n"
        f"Комиссия биржи {EXCHANGE_SELL_FEE_PERCENT}%: покупатель платит цену лота, продавец получает остаток.",
        economy_keyboard(),
    )


@router.message(Registration.auction_lot_price)
async def process_auction_lot_price(message: Message, state: FSMContext) -> None:
    if await abort_fsm_if_nav(message, state):
        return
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return

    raw_price = (message.text or "").strip().replace(" ", "")
    try:
        lot_price = int(raw_price)
    except ValueError:
        await message.answer("Цена должна быть целым числом, например: 500")
        return
    if lot_price <= 0:
        await message.answer("Цена должна быть больше нуля.")
        return

    data = await state.get_data()
    item_key = str(data.get("auction_item_key", "")).strip()
    if not item_key:
        await state.clear()
        await message.answer("Не удалось определить предмет для лота. Попробуй снова через Экономику.")
        return

    result = create_custom_exchange_lot(get_storage(), message.from_user.id, item_key, 1, price=lot_price)
    await state.clear()
    await message.answer(action_result_text(message.from_user.id, result.text))


@router.callback_query(F.data == "eco:auction:list")
async def auction_list_callback(callback: CallbackQuery) -> None:
    await _render_exchange_lots_list(callback, category="all")


@router.callback_query(F.data.startswith("eco:auction:list:"))
async def auction_list_filtered_callback(callback: CallbackQuery) -> None:
    category = (callback.data or "").split(":", maxsplit=3)[3]
    await _render_exchange_lots_list(callback, category=category)


async def _render_exchange_lots_list(callback: CallbackQuery, *, category: str) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    text, lots = build_exchange_lots_overview(storage, callback.from_user.id, limit=12, category=category)
    menu_text = text if not lots else f"{text}\n\nВыбери лот:"
    await edit_menu_message(callback, menu_text, exchange_lots_keyboard(lots, category=category))


@router.callback_query(F.data.startswith("eco:auction:buy:"))
async def auction_buy_by_id_callback(callback: CallbackQuery, bot: Bot) -> None:
    lot_id = (callback.data or "").split(":", maxsplit=3)[3]
    try:
        auction_id = int(lot_id)
    except ValueError:
        await callback.answer("Некорректный ID лота.", show_alert=True)
        return
    result = buy_exchange_lot(get_storage(), callback.from_user.id, auction_id)
    await finish_callback_action(callback, result, bot)


@router.callback_query(F.data.startswith("eco:auction:cancel:"))
async def auction_cancel_by_id_callback(callback: CallbackQuery) -> None:
    lot_id = (callback.data or "").split(":", maxsplit=3)[3]
    try:
        auction_id = int(lot_id)
    except ValueError:
        await callback.answer("Некорректный ID лота.", show_alert=True)
        return
    result = cancel_own_auction(get_storage(), callback.from_user.id, auction_id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "eco:smuggle:menu")
async def smuggle_menu_callback(callback: CallbackQuery) -> None:
    try:
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is None:
            await callback.answer("Сначала создай персонажа", show_alert=True)
            return
        overview = build_smuggling_overview(storage, callback.from_user.id)
        active = get_active_smuggling(storage, callback.from_user.id)
        grid_active = get_smuggle_session(storage, callback.from_user.id) is not None
        destinations = list_smuggling_destinations(storage, callback.from_user.id)
        if callback.message is None:
            await callback.answer("Сообщение недоступно.", show_alert=True)
            return
        await callback.message.answer(
            overview,
            reply_markup=smuggling_keyboard(
                destinations,
                has_active=bool(active) or grid_active,
            ),
        )
        await callback.answer()
    except Exception:
        logger.exception("Smuggle menu callback failed for %s", callback.from_user.id)
        await safe_callback_answer(callback, "Ошибка меню контрабанды. /fixme", show_alert=True)


@router.callback_query(F.data == "eco:smuggle:status")
async def smuggle_status_callback(callback: CallbackQuery) -> None:
    try:
        overview = build_smuggling_overview(get_storage(), callback.from_user.id)
        if callback.message is None:
            await callback.answer(overview[:CALLBACK_ALERT_MAX_LEN], show_alert=True)
            return
        await callback.message.answer(overview)
        await callback.answer()
    except Exception:
        logger.exception("Smuggle status callback failed for %s", callback.from_user.id)
        await safe_callback_answer(callback, "Ошибка статуса рейса.", show_alert=True)


@router.callback_query(F.data == "eco:smuggle:abandon")
async def smuggle_abandon_callback(callback: CallbackQuery, bot: Bot) -> None:
    try:
        result = abandon_smuggling_run(get_storage(), callback.from_user.id)
        await reply_action_result(callback, result.text, bot=bot)
    except Exception:
        logger.exception("Smuggle abandon callback failed for %s", callback.from_user.id)
        await safe_callback_answer(callback, "Ошибка сброса груза. /fixme", show_alert=True)


@router.callback_query(F.data.startswith("eco:smuggle:to:"))
async def smuggle_to_callback(callback: CallbackQuery, bot: Bot) -> None:
    try:
        destination = (callback.data or "").removeprefix("eco:smuggle:to:").strip()
        if not destination:
            await callback.answer("Некорректная точка", show_alert=True)
            return
        result = start_smuggling_run(
            get_storage(),
            callback.from_user.id,
            destination,
            transport_mode=None,
        )
        if result.ok:
            payload = result.payload or {}
            image = payload.get("mission_image")
            if image and payload.get("mission_active"):
                await _send_or_edit_smuggle_frame(
                    callback,
                    image_bytes=image,
                    caption=str(payload.get("caption") or result.text),
                    note=result.text if payload.get("mission_started") else None,
                )
                return
            await safe_callback_answer(callback, "Рейс начат!")
            if callback.message is not None:
                await callback.message.answer(
                    action_result_text(callback.from_user.id, result.text)
                )
            else:
                await bot.send_message(
                    callback.from_user.id,
                    action_result_text(callback.from_user.id, result.text),
                )
            return
        await reply_action_result(callback, result.text, bot=bot)
    except Exception:
        logger.exception("Smuggle destination callback failed for %s", callback.from_user.id)
        await safe_callback_answer(callback, "Ошибка выбора точки.", show_alert=True)


@router.callback_query(F.data.startswith("eco:smuggle:go:"))
async def smuggle_go_callback(callback: CallbackQuery, bot: Bot) -> None:
    try:
        parts = (callback.data or "").split(":", maxsplit=4)
        if len(parts) < 5:
            await callback.answer("Некорректный рейс.", show_alert=True)
            return
        mode = parts[3]
        destination = parts[4]
        result = start_smuggling_run(
            get_storage(),
            callback.from_user.id,
            destination,
            transport_mode=mode,
        )
        if result.ok:
            payload = result.payload or {}
            image = payload.get("mission_image")
            if image and payload.get("mission_active"):
                await _send_or_edit_smuggle_frame(
                    callback,
                    image_bytes=image,
                    caption=str(payload.get("caption") or result.text),
                    note=result.text if payload.get("mission_started") else None,
                )
                return
            await safe_callback_answer(callback, "Рейс начат!")
            if callback.message is not None:
                await callback.message.answer(action_result_text(callback.from_user.id, result.text))
            else:
                await bot.send_message(callback.from_user.id, action_result_text(callback.from_user.id, result.text))
            return
        await reply_action_result(callback, result.text, bot=bot)
    except Exception:
        logger.exception("Smuggle start callback failed for %s", callback.from_user.id)
        await safe_callback_answer(callback, "Ошибка старта рейса. /fixme", show_alert=True)


@router.callback_query(F.data.in_({"eco:smuggle:coop", "eco:smuggle:run"}))
async def smuggle_legacy_menu_callback(callback: CallbackQuery) -> None:
    """Старые callback → меню контрабанды."""
    await smuggle_menu_callback(callback)


@router.message()
async def fallback(message: Message, bot: Bot) -> None:
    player = ensure_character(message)
    normalized_text = _normalize_info_trigger(message.text)
    if player is not None and (
        normalized_text.endswith("информация") or normalized_text.startswith("/info")
    ):
        await message.answer(_build_info_text(player))
        return
    dead = resolve_dead_player(get_storage(), message.from_user.id) if player is not None else None
    if dead is not None:
        await show_death_screen(message, dead, bot=bot)
        return
    if player is not None:
        await message.answer(
            "Команда не распознана. Используй кнопки меню.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await message.answer(
        "Команда не распознана. Нажми /start или /menu.",
        reply_markup=main_menu_keyboard(),
    )


async def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    global storage, admin_ids
    admin_ids = settings.admin_ids
    if admin_ids:
        logger.info("Admin IDs configured: %s", ", ".join(str(i) for i in admin_ids))
    else:
        logger.warning("ADMIN_IDS not set — /всем and admin commands are disabled")
    storage = Storage(
        settings.db_path,
        snapshot_path=settings.snapshot_path,
        database_url=settings.database_url,
    )
    storage.init_db()
    storage.restore_from_snapshot_if_empty()
    try:
        synced = storage.backfill_all_gear_power()
        if synced:
            logger.info("Backfilled gear_power for %s characters", synced)
    except Exception:
        logger.exception("gear_power backfill failed")
    try:
        from app.game_logic import apply_pending_admin_faction_transfers

        for note in apply_pending_admin_faction_transfers(storage):
            logger.info("Admin faction transfer: %s", note)
    except Exception:
        logger.exception("Pending admin faction transfers failed")

    async def periodic_snapshot_sync() -> None:
        while True:
            await asyncio.sleep(SNAPSHOT_SYNC_SECONDS)
            try:
                get_storage().save_snapshot(force=True)
            except Exception:
                logger.exception("Periodic snapshot sync failed")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    zone_tick_counter = {"n": 0}

    async def periodic_zone_systems() -> None:
        while True:
            await asyncio.sleep(POINTS_INCOME_TICK_SECONDS)
            zone_tick_counter["n"] += 1
            try:
                apply_controlled_points_income(get_storage())
            except Exception:
                logger.exception("Points income tick failed")
            try:
                storage = get_storage()
                return_messages = process_due_garage_vehicle_rentals(storage)
                for message_text, faction in return_messages:
                    notify_ids: set[int] = set()
                    for user_id in storage.list_faction_member_ids(faction):
                        notify_ids.add(int(user_id))
                    for user_id in notify_ids:
                        if not is_notify_enabled(storage, user_id, "garage"):
                            continue
                        try:
                            await bot.send_message(user_id, message_text)
                        except Exception:
                            logger.debug("Failed garage rental return notify to %s", user_id)
            except Exception:
                logger.exception("Garage vehicle rental tick failed")
            try:
                storage = get_storage()
                message_text, notify_ids, killed_ids = process_emission_cycle(storage)
                if message_text:
                    for user_id in notify_ids:
                        if not is_notify_enabled(storage, user_id, "emission"):
                            continue
                        try:
                            await bot.send_message(user_id, message_text)
                        except Exception:
                            logger.debug("Failed emission notify to %s", user_id)
                for killed_id in killed_ids:
                    try:
                        killed_player = storage.get_character(killed_id, refresh_energy=False)
                        if killed_player is not None:
                            await _send_battle_death_notice(
                                bot,
                                killed_id,
                                killed_player,
                                cause="emission",
                            )
                    except Exception:
                        logger.debug("Failed emission death notice to %s", killed_id)
            except Exception:
                logger.exception("Emission cycle tick failed")
            try:
                message_text, notify_ids = process_zone_event_cycle(get_storage())
                if message_text:
                    for user_id in notify_ids:
                        try:
                            await bot.send_message(user_id, message_text)
                        except Exception:
                            logger.debug("Failed zone event notify to %s", user_id)
            except Exception:
                logger.exception("Zone event cycle tick failed")
            try:
                season_message = process_rating_season(get_storage())
                if season_message:
                    for user_id in get_storage().list_player_ids():
                        try:
                            await bot.send_message(user_id, season_message)
                        except Exception:
                            logger.debug("Failed rating season notify to %s", user_id)
                    try:
                        from app.season_chat_titles import apply_pending_season_chat_titles

                        title_notes = await apply_pending_season_chat_titles(bot, get_storage())
                        if title_notes:
                            logger.info("Season chat titles: %s", "; ".join(title_notes))
                    except Exception:
                        logger.exception("Season chat title apply failed")
            except Exception:
                logger.exception("Rating season tick failed")
            if zone_tick_counter["n"] % SURVIVAL_DEATH_CHECK_EVERY_TICKS == 0:
                try:
                    await _push_offline_survival_deaths(bot, get_storage())
                except Exception:
                    logger.exception("Offline survival death tick failed")

    async def periodic_travel_live_eta() -> None:
        """Каждую секунду правит сообщение «сколько осталось ехать»."""
        while True:
            await asyncio.sleep(TRAVEL_ETA_TICK_SECONDS)
            storage = get_storage()
            try:
                for user_id, _destination in process_due_travels(storage):
                    # Один раз: прибытие ("Прибыл в …") + энкаунтер/контрабанда — всё через
                    # action_result_text (иначе строка прибытия дублируется).
                    arrival_body = action_result_text(user_id, "")
                    try:
                        await upsert_travel_eta_message(bot, user_id, arrival_body)
                    except Exception:
                        logger.debug("Failed travel arrival ETA edit for %s", user_id)
                    clear_travel_eta_message_id(storage, user_id)
            except Exception:
                logger.exception("Travel live arrival tick failed")
            try:
                for user_id, text in collect_travel_eta_notices(storage):
                    try:
                        # Без action_result_text — иначе каждую секунду дергаются сайд-эффекты.
                        await upsert_travel_eta_message(bot, user_id, text)
                    except Exception:
                        logger.debug("Failed travel live ETA for %s", user_id)
            except Exception:
                logger.exception("Travel live ETA tick failed")

    async def periodic_tactical_turns() -> None:
        """Таймер ходов тактической дуэли и кооп-вылазки (~10 сек)."""
        tick = 0
        while True:
            await asyncio.sleep(1)
            tick += 1
            storage = get_storage()
            try:
                duel_updates: set[str] = set()
                duel_done_ids: set[str] = set()
                for pid, result in process_duel_turn_timeouts(storage):
                    payload = result.payload or {}
                    if payload.get("duel_done"):
                        did = str(payload.get("duel_id") or "")
                        if did and did in duel_done_ids:
                            continue
                        if did:
                            duel_done_ids.add(did)
                        await _notify_duel_finished(bot, result)
                        continue
                    session = get_duel_session_by_player(storage, pid)
                    if session and session.duel_id not in duel_updates:
                        duel_updates.add(session.duel_id)
                        await _broadcast_duel_session(bot, storage, session, note=result.text)
            except Exception:
                logger.exception("Duel timeout tick failed")
            try:
                coop_updates: set[str] = set()
                coop_done_ids: set[str] = set()
                for pid, result in process_coop_turn_timeouts(storage):
                    payload = result.payload or {}
                    if payload.get("coop_done"):
                        sid = str(payload.get("session_id") or "")
                        if sid and sid in coop_done_ids:
                            continue
                        if sid:
                            coop_done_ids.add(sid)
                        await _notify_coop_finished(bot, result)
                        continue
                    session = get_coop_session_by_player(storage, pid)
                    if session and session.session_id not in coop_updates:
                        coop_updates.add(session.session_id)
                        await _broadcast_coop_session(bot, storage, session, note=result.text)
            except Exception:
                logger.exception("Coop timeout tick failed")
            try:
                cwar_updates: set[str] = set()
                cwar_done_ids: set[str] = set()
                for pid, result in process_cwar_turn_timeouts(storage):
                    payload = result.payload or {}
                    if payload.get("cwar_done"):
                        sid = str(payload.get("session_id") or "")
                        if sid and sid in cwar_done_ids:
                            continue
                        if sid:
                            cwar_done_ids.add(sid)
                        await _notify_cwar_finished(bot, result)
                        continue
                    session = get_cwar_session_by_player(storage, pid)
                    if session and session.session_id not in cwar_updates:
                        cwar_updates.add(session.session_id)
                        await _broadcast_cwar_session(bot, storage, session, note=result.text)
            except Exception:
                logger.exception("Clan war timeout tick failed")
            try:
                rgrid_updates: set[str] = set()
                rgrid_done_ids: set[str] = set()
                for pid, result in process_rgrid_turn_timeouts(storage):
                    payload = result.payload or {}
                    if payload.get("rgrid_done"):
                        sid = str(payload.get("session_id") or "")
                        if sid and sid in rgrid_done_ids:
                            continue
                        if sid:
                            rgrid_done_ids.add(sid)
                        await _notify_rgrid_finished(bot, result)
                        continue
                    session = get_raid_grid_session_by_player(storage, pid)
                    if session and session.session_id not in rgrid_updates:
                        rgrid_updates.add(session.session_id)
                        await _broadcast_rgrid_session(bot, storage, session, note=result.text)
            except Exception:
                logger.exception("Raid grid timeout tick failed")
            try:
                ncap_done_ids: set[str] = set()
                ncap_updates: set[str] = set()
                for pid, result in process_ncap_turn_timeouts(storage):
                    payload = result.payload or {}
                    if payload.get("ncap_done"):
                        sid = payload.get("session_id")
                        if sid and sid in ncap_done_ids:
                            continue
                        if sid:
                            ncap_done_ids.add(str(sid))
                        await _notify_ncap_finished(bot, result)
                        continue
                    session = get_ncap_session(storage, pid)
                    if session and session.session_id not in ncap_updates:
                        ncap_updates.add(session.session_id)
                        await _broadcast_ncap_session(bot, storage, session, note=result.text)
            except Exception:
                logger.exception("Neutral capture timeout tick failed")
            try:
                for pid, result in process_arena_turn_timeouts(storage):
                    payload = result.payload or {}
                    if payload.get("arena_done"):
                        msg_id = payload.get("message_id")
                        if msg_id:
                            await _clear_tactical_keyboards(bot, {str(pid): int(msg_id)})
                        await bot.send_message(pid, action_result_text(pid, result.text))
                        continue
                    session = get_arena_session(storage, pid)
                    if session:
                        await _broadcast_arena_session(bot, storage, session, note=result.text)
            except Exception:
                logger.exception("Arena timeout tick failed")
            if tick % 30 == 0:
                try:
                    for tid, result in process_smuggle_timeouts(storage):
                        try:
                            await bot.send_message(tid, action_result_text(tid, result.text))
                        except Exception:
                            logger.exception("Failed smuggle timeout notify to %s", tid)
                except Exception:
                    logger.exception("Smuggle timeout tick failed")
                try:
                    for tid, result in process_quest_timeouts(storage):
                        try:
                            await bot.send_message(tid, action_result_text(tid, result.text))
                        except Exception:
                            logger.exception("Failed quest timeout notify to %s", tid)
                except Exception:
                    logger.exception("Quest timeout tick failed")
                try:
                    for tid, result in process_hunt_timeouts(storage):
                        try:
                            await bot.send_message(tid, action_result_text(tid, result.text))
                        except Exception:
                            logger.exception("Failed hunt timeout notify to %s", tid)
                except Exception:
                    logger.exception("Hunt timeout tick failed")

    sync_task = asyncio.create_task(periodic_snapshot_sync())
    zone_task = asyncio.create_task(periodic_zone_systems())
    travel_eta_task = asyncio.create_task(periodic_travel_live_eta())
    tactical_task = asyncio.create_task(periodic_tactical_turns())
    dp = Dispatcher()
    dp.callback_query.outer_middleware(PlayerActivityMiddleware())
    dp.message.outer_middleware(PlayerActivityMiddleware())
    dp.callback_query.outer_middleware(DeadPlayerCallbackMiddleware())
    dp.message.outer_middleware(DeadPlayerMenuMiddleware())
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        sync_task.cancel()
        zone_task.cancel()
        travel_eta_task.cancel()
        tactical_task.cancel()
        for task in (sync_task, zone_task, travel_eta_task, tactical_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Background task finished with error")
        try:
            get_storage().save_snapshot(force=True)
        except Exception:
            logger.exception("Final snapshot save failed during shutdown")


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
