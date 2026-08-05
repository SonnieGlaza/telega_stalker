from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
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
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)

from app.config import load_settings
from app.game_logic import (
    apply_referral_rewards,
    build_referral_link,
    parse_referral_payload,
    REFERRAL_INVITER_BONUS_RU,
    REFERRAL_STARTER_PACK,
    ITEM_LABELS,
    append_survival_craving_notice,
    attack_location,
    attempt_smuggling,
    build_achievements_overview,
    build_character_stats_overview,
    build_economy_overview,
    build_faction_group_overview,
    build_events_overview,
    build_raids_overview,
    build_rating_overview,
    BULK_BUY_ITEM_KEYS,
    SHOP_ITEMS,
    buy_item,
    buy_first_faction_auction,
    cancel_own_first_auction,
    cancel_all_raids_by_leader,
    cancel_raid_by_leader,
    create_faction_auction,
    create_or_join_faction_raid,
    launch_open_raid,
    build_quest_overview,
    apply_controlled_points_income,
    process_emission_cycle,
    process_zone_event_cycle,
    build_players_root_text,
    build_players_faction_page_text,
    build_faction_broadcast_text,
    list_faction_broadcast_targets,
    deposit_to_faction_warehouse,
    format_inventory,
    repair_gear,
    run_quest,
    sell_item,
    list_owned_trader_sell_buttons,
    trader_sell_categories_with_stock,
    travel_to,
    use_energy_drink,
    use_medkit,
    use_medkit_army,
    use_medkit_science,
    repair_truck,
    use_vodka,
    use_antirad,
    use_bread,
    use_sausage,
    use_stew,
    use_water,
    use_mineralka,
    use_beard_tea,
    open_stash,
    search_artifacts,
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
    buy_first_market_lot,
    buy_market_lot,
    build_market_lots_overview,
    list_sellable_market_equipment,
    cancel_own_first_market_lot,
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
    respawn_character,
    build_alliance_overview,
    propose_alliance,
    break_alliance,
    accept_alliance,
    declare_war,
    equip_artifact,
    equip_armor,
    equip_weapon,
    unequip_artifact,
    build_equip_root_text,
    build_equip_slot_page,
)
from app.keyboards import (
    economy_keyboard,
    faction_group_keyboard,
    faction_ranks_members_keyboard,
    faction_rank_pick_keyboard,
    inventory_equipment_keyboard,
    inventory_consumables_keyboard,
    dead_character_keyboard,
    faction_keyboard,
    gender_keyboard,
    locations_keyboard,
    main_menu_keyboard,
    pda_keyboard,
    sortie_keyboard,
    quests_keyboard,
    raid_keyboard,
    topup_keyboard,
    trader_buy_categories_keyboard,
    trader_buy_armor_keyboard,
    trader_buy_consumables_keyboard,
    trader_buy_consumable_qty_keyboard,
    trader_buy_gear_keyboard,
    trader_buy_repair_keyboard,
    trader_buy_weapons_keyboard,
    trader_keyboard,
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
    war_lobby_keyboard,
    war_transfer_keyboard,
    market_lots_keyboard,
    market_create_select_keyboard,
    war_sections_keyboard,
    players_factions_keyboard,
    players_faction_page_keyboard,
    rating_page_keyboard,
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
from app.zone_map import build_zone_map_image

logger = logging.getLogger(__name__)

router = Router()
storage: Storage | None = None
admin_ids: tuple[int, ...] = ()
SNAPSHOT_SYNC_SECONDS = 300
POINTS_INCOME_TICK_SECONDS = 60
TOPUP_RATE_RU_PER_STAR = 150
TOPUP_PAYLOAD_PREFIX = "topup_stars:"
TOPUP_ALLOWED_AMOUNTS = {1, 5, 10, 25}
TOPUP_MIN_STARS = 1
TOPUP_MAX_STARS = 10000
# Telegram callback alerts are limited to 200 characters.
CALLBACK_ALERT_MAX_LEN = 200


def _is_stale_callback_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return "query is too old" in message or "query id is invalid" in message


async def safe_callback_answer(callback: CallbackQuery, *args: Any, **kwargs: Any) -> None:
    try:
        await callback.answer(*args, **kwargs)
    except TelegramBadRequest as exc:
        if _is_stale_callback_error(exc):
            logger.debug("Ignored stale callback answer for user %s", callback.from_user.id)
            return
        raise


def _clip_callback_alert(text: str, *, limit: int = CALLBACK_ALERT_MAX_LEN) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    clipped = clean[: max(1, limit - 1)]
    last_nl = clipped.rfind("\n")
    # If the cut lands mid-line with only a short stub, drop that stub.
    if last_nl >= 0 and (limit - 1 - last_nl) < 24:
        clipped = clipped[:last_nl]
    return clipped.rstrip() + "…"


async def edit_menu_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Any = None,
) -> None:
    """Обновляет меню на месте, чтобы не копить сообщения в чате."""
    message = callback.message
    if message is None:
        await safe_callback_answer(callback)
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "message is not modified" in error_text:
            await safe_callback_answer(callback)
            return
        # Нельзя отредактировать (например, это не текст) — шлём новое и пытаемся убрать старое.
        await message.answer(text, reply_markup=reply_markup)
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
    await safe_callback_answer(callback)


async def reply_action_result(callback: CallbackQuery, text: str) -> None:
    """Итог действия — всегда всплывающее окно, без спама в чат."""
    clean = append_survival_craving_notice(
        get_storage(),
        callback.from_user.id,
        (text or "").strip(),
    )
    if not clean:
        await safe_callback_answer(callback)
        return
    await safe_callback_answer(callback, _clip_callback_alert(clean), show_alert=True)


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
    treasury_deposit_custom = State()
    treasury_withdraw_custom = State()


TREASURY_CUSTOM_MIN_RU = 1
TREASURY_CUSTOM_MAX_RU = 1_000_000


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
            f"👥 По твоей ссылке в Зону пришёл {invitee_name}.\n"
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
        await message.answer(
            f"С возвращением, {player.nickname}! Добро пожаловать в Зону.",
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
            "💎 Поиск артефактов: шансы зависят от локации и детектора.\n"
            "❤️ Смерть и респавн: если персонаж «падает», нужно восстанавливаться по правилам игры.\n\n"
            f"Если ты готов, то назови свое имя!{referral_hello}"
        )
        return
    # Defensive fallback (should be unreachable).
    await message.answer("Сбой проверки аккаунта. Попробуй /start еще раз.")


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню открыто.", reply_markup=main_menu_keyboard())


@router.message(F.text == "⭐ Пополнить")
async def show_topup(message: Message, state: FSMContext) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await state.clear()
    await message.answer(
        "Выбери пакет пополнения.\nКурс: 1 звезда = 150 RU.",
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


def _build_pda_chats_text(player: Character) -> str:
    faction_chat = FACTION_CHATS.get(player.faction or "")
    lines = [
        "📟 КПК — связь",
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
        "• 📟 КПК — профиль, чаты, рейтинг, карта, игроки, рефералка.\n"
        "• 🏕 Вылазка — война, переходы и рейды.\n"
        "• 👥 Группировка — склад, казна, звания; склад с 5 ранга, казна только лидер.\n"
        "• 🏦 Экономика — биржа и рынок экипировки.\n"
        "• 📋 Задания — сложности и отдельная контрабанда.\n\n"
        "Команды:\n"
        "• /start — создать персонажа или войти в существующего.\n"
        "• /menu — открыть главное меню.\n"
        "• /info — открыть эту справку.\n"
        "• /pay [telegram_id] [сумма] — перевод игроку (комиссия 30%).\n"
        "• /дуэль [telegram_id] — вызвать игрока на дуэль (принять/отклонить).\n"
        "  Шанс от разницы силы снаряги, бросок 1–100;\n"
        "  проигравший: −20 HP и −10% денег (победителю).\n"
        "  ID смотри в КПК → «👥 Игроки».\n\n"
        "Механики:\n"
        "• 🚚 Грузовик ускоряет переходы и снижает расход энергии на поездку,\n"
        "  но тратит 1 топливо за каждый переход.\n"
        "• 🛏 Спальник пассивно ускоряет восстановление энергии в 2 раза.\n"
        "• 💎 Артефакты (поиск детектором по локациям):\n"
        "  — Артефакт Зоны: 0.1% на любой локации; +2 силы, +5% реген энергии\n"
        "  — Арт «Сила» / «Живучесть»: спавн на Болотах; бонусы к силе / HP\n"
        "  — Арт «Антирад»: 0.1% на Радаре; +2 силы, −1 рад. каждые 10 мин\n"
        "  — Мусорные арты: без статов, продажа 300–600 RU\n"
        "• ⚙️ Экипировка в инвентаре: оружие, броня и арты по категориям.\n"
        "• 🎖 Скин персонажа повышается от рейтинга:\n"
        "  — Новичок: 0–499, Опытный: 500–1999,\n"
        "    Ветеран: 2000–4999, Легенда: 5000+.\n\n"
        "Чаты и рефералка: смотри в 📟 КПК."
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
            f"Введи количество звезд для пополнения (от {TOPUP_MIN_STARS} до {TOPUP_MAX_STARS})."
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
    player = ensure_character(message)
    if player is None:
        await state.clear()
        await message.answer("Сначала создай персонажа через /start.")
        return

    raw_value = (message.text or "").strip()
    try:
        stars_amount = int(raw_value)
    except ValueError:
        await message.answer("Нужно ввести целое число звезд, например: 7")
        return
    if stars_amount < TOPUP_MIN_STARS or stars_amount > TOPUP_MAX_STARS:
        await message.answer(
            f"Некорректное количество. Допустимо от {TOPUP_MIN_STARS} до {TOPUP_MAX_STARS} звезд."
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
            f"• Локация: {me.location}\n"
            f"• HP {me.health} | энергия {me.energy}/{me.max_energy} | сила {me.gear_power}\n"
            f"• RU {me.money} | топливо {me.fuel}\n"
            f"• Грузовик: {'да' if me.truck_owned else 'нет'} ({me.truck_durability}%) | "
            f"Спальник: {'да' if me.sleeping_bag_owned else 'нет'}\n"
            f"• Оружие: {me.equipment.get('weapon')} ({me.equipment.get('weapon_durability')}%)\n"
            f"• Броня: {me.equipment.get('armor')} ({me.equipment.get('armor_durability')}%)\n"
            f"• Рад {me.radiation} | голод {me.hunger} | жажда {me.thirst}"
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
    db.save_snapshot()
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
                f"Персонаж уже зарегистрирован: {existing.nickname}. Открываю меню.",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.answer(
                "Персонаж уже создан. Осталось выбрать группировку:",
                reply_markup=faction_keyboard(),
            )
        return

    nickname = (message.text or "").strip()
    if len(nickname) < 2:
        await message.answer("Прозвище слишком короткое. Введи хотя бы 2 символа.")
        return
    if len(nickname) > 24:
        await message.answer("Прозвище слишком длинное. Максимум 24 символа.")
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
    await callback.message.answer(
        f"Принято. Теперь ты в группировке «{faction}».\nОткрываю меню персонажа.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


def ensure_character(message: Message) -> Character | None:
    player = get_storage().get_character(message.from_user.id)
    if player is None:
        return None
    return player


def action_result_text(telegram_id: int, text: str) -> str:
    return append_survival_craving_notice(get_storage(), telegram_id, (text or "").strip())


async def send_profile_snapshot(
    message: Message,
    player: Character,
    *,
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
    await message.answer_photo(photo=image, caption=caption, reply_markup=reply_markup)


@router.message(F.text == "🎒 Инвентарь")
async def show_inventory(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if player.health <= 0:
        await message.answer(build_dead_character_text(player), reply_markup=dead_character_keyboard())
        return
    await message.answer(
        format_inventory(
            player,
            rating_points=int(get_storage().get_player_stats(player.telegram_id).get("rating_points", 0)),
            storage=get_storage(),
        ),
        reply_markup=inventory_equipment_keyboard(),
    )


@router.callback_query(F.data == "inventory:open")
async def open_inventory_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await edit_menu_message(
            callback,
            build_dead_character_text(player),
            dead_character_keyboard(),
        )
        return
    await edit_menu_message(
        callback,
        format_inventory(
            player,
            rating_points=int(get_storage().get_player_stats(player.telegram_id).get("rating_points", 0)),
            storage=get_storage(),
        ),
        inventory_equipment_keyboard(),
    )


@router.callback_query(F.data == "inventory:consumables")
async def open_inventory_consumables_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await edit_menu_message(
            callback,
            build_dead_character_text(player),
            dead_character_keyboard(),
        )
        return
    await edit_menu_message(
        callback,
        "🧰 Расходники\nВыбери предмет для использования:",
        inventory_consumables_keyboard(),
    )


@router.callback_query(F.data == "respawn:base")
async def respawn_base_callback(callback: CallbackQuery) -> None:
    result = respawn_character(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)
    if result.ok:
        player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            await send_profile_snapshot(callback.message, player)


@router.callback_query(F.data == "player:respawn")
async def show_respawn_menu_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health > 0:
        await callback.answer("Респавн доступен только при HP=0.", show_alert=True)
        return
    await edit_menu_message(
        callback,
        build_dead_character_text(player),
        dead_character_keyboard(),
    )


@router.message(F.text == "🧾 Профиль")
async def show_profile(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await send_profile_snapshot(message, player, reply_markup=pda_keyboard())


@router.message(F.text == "🛒 Торговец")
async def show_trader(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await message.answer(
        "Торговец на связи. Выбери раздел:",
        reply_markup=trader_keyboard(),
    )


@router.callback_query(F.data == "trade:menu:buy")
async def show_buy_menu(callback: CallbackQuery) -> None:
    await edit_menu_message(
        callback,
        "Покупка: выбери категорию.",
        trader_buy_categories_keyboard(),
    )


@router.callback_query(F.data == "trade:menu:sell")
async def show_sell_menu(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    categories = trader_sell_categories_with_stock(player) if player is not None else []
    text = (
        "Продажа: выбери категорию.\nПоказаны только вещи, которые у тебя есть."
        if categories
        else "Продажа: нечего продавать торговцу."
    )
    await edit_menu_message(
        callback,
        text,
        trader_sell_categories_keyboard(categories),
    )


@router.callback_query(F.data == "trade:menu:root")
async def show_trade_root(callback: CallbackQuery) -> None:
    await edit_menu_message(
        callback,
        "Торговец на связи. Выбери раздел:",
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


@router.callback_query(F.data.startswith("trade:buy:consumables"))
async def show_buy_consumables(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:buy:consumables")
    await edit_menu_message(
        callback,
        "Покупка расходников:\nВыбери товар, затем количество (×1 / ×5 / ×10 / ×25).",
        trader_buy_consumables_keyboard(page=page),
    )


@router.callback_query(F.data.startswith("trade:buy:gear"))
async def show_buy_gear(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:buy:gear")
    await edit_menu_message(
        callback,
        "Прочее:\n"
        "• Оружие и броня — в своих разделах.\n"
        "• После покупки предмет попадает в инвентарь.\n"
        "• Экипировка — во вкладке «🎒 Инвентарь».\n"
        "• Ремонт — в разделе «🔧 Ремонт».",
        trader_buy_gear_keyboard(page=page),
    )


@router.callback_query(F.data.startswith("trade:buy:armor"))
async def show_buy_armor(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:buy:armor")
    await edit_menu_message(
        callback,
        "Покупка брони и костюмов.\n"
        "После покупки предмет добавляется в инвентарь.",
        trader_buy_armor_keyboard(page=page),
    )


@router.callback_query(F.data.startswith("trade:buy:weapons"))
async def show_buy_weapons(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:buy:weapons")
    await edit_menu_message(
        callback,
        "Покупка оружия.\n"
        "После покупки предмет добавляется в инвентарь.",
        trader_buy_weapons_keyboard(page=page),
    )


@router.callback_query(F.data == "trade:buy:repair")
async def show_buy_repair(callback: CallbackQuery) -> None:
    await edit_menu_message(
        callback,
        "Ремонт снаряжения:\n"
        "• Оружие и броня — по текущей прочности.\n"
        "• Грузовик — восстановление прочности кузова.",
        trader_buy_repair_keyboard(),
    )


@router.callback_query(F.data.startswith("trade:sell:consumables"))
async def show_sell_consumables(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:consumables")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        "Продажа расходников (только то, что есть):",
        _sell_category_keyboard(player, "consumables", page),
    )


@router.callback_query(F.data.startswith("trade:sell:trophies"))
async def show_sell_trophies(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:trophies")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        "Продажа трофеев (только то, что есть):",
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
            "Продажа брони и костюмов (только то, что есть):",
            _sell_category_keyboard(player, "armor", page),
        )
        return
    page = _trade_category_page(callback.data, prefix="trade:sell:gear")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        "Продажа снаряжения (только то, что есть):",
        _sell_category_keyboard(player, "gear", page),
    )


@router.callback_query(F.data.startswith("trade:sell:armor"))
async def show_sell_armor_alias_callback(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:armor")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        "Продажа брони и костюмов (только то, что есть):",
        _sell_category_keyboard(player, "armor", page),
    )


@router.callback_query(F.data.startswith("trade:sell:weapons"))
async def show_sell_weapons(callback: CallbackQuery) -> None:
    page = _trade_category_page(callback.data, prefix="trade:sell:weapons")
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    await edit_menu_message(
        callback,
        "Продажа оружия (только то, что есть):",
        _sell_category_keyboard(player, "weapons", page),
    )


@router.callback_query(F.data.startswith("buyqty:"))
async def show_buy_consumable_qty(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=1)[1]
    item = SHOP_ITEMS.get(item_key)
    if item is None or item_key not in BULK_BUY_ITEM_KEYS or int(item.get("buy_price", 0)) <= 0:
        await reply_action_result(callback, "Такого расходника нет у торговца.")
        return
    title = str(item["name"])
    unit_price = int(item["buy_price"])
    await edit_menu_message(
        callback,
        f"Покупка: {title}\nЦена за 1 шт.: {unit_price} RU\nВыбери количество:",
        trader_buy_consumable_qty_keyboard(item_key, unit_price=unit_price, title=title),
    )


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


@router.callback_query(F.data == "repair:truck")
async def repair_truck_callback(callback: CallbackQuery) -> None:
    result = repair_truck(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "equip:root")
async def equip_root_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await edit_menu_message(
            callback,
            build_dead_character_text(player),
            dead_character_keyboard(),
        )
        return
    text, items = build_equip_root_text(player)
    await edit_menu_message(callback, text, equip_root_keyboard(items))


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


@router.message(F.text == "📋 Задания")
async def show_quests(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return

    overview = build_quest_overview(player)
    await message.answer(
        "Выбери сложность задания.\n"
        "🚚 Контрабанда — отдельная кнопка ниже, это не сложность квеста.\n\n"
        f"{overview}",
        reply_markup=quests_keyboard(),
    )


@router.callback_query(F.data.startswith("quest:"))
async def handle_quest(callback: CallbackQuery) -> None:
    quest_key = (callback.data or "").split(":", maxsplit=1)[1]
    result = run_quest(get_storage(), callback.from_user.id, quest_key)
    await reply_action_result(callback, result.text)


@router.message(F.text == "🎖 Достижения")
async def show_achievements(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    text = build_achievements_overview(get_storage(), player.telegram_id)
    await message.answer(text, reply_markup=pda_keyboard())


@router.message(F.text == "📊 Статистика")
async def show_character_stats(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    text = build_character_stats_overview(get_storage(), player.telegram_id)
    await message.answer(text, reply_markup=pda_keyboard())


@router.message(F.text == "📟 КПК")
async def show_pda(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await message.answer(
        "📟 КПК сталкера\n"
        "Профиль, связь, рейтинг, карта, игроки и рефералка.",
        reply_markup=pda_keyboard(),
    )


@router.message(F.text == "🔗 Реферальная система")
async def show_referral_system(message: Message, bot: Bot) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
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
        reply_markup=pda_keyboard(),
    )


@router.message(F.text == "💬 Чаты")
async def show_pda_chats(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await message.answer(_build_pda_chats_text(player), reply_markup=pda_keyboard())


@router.message(F.text == "⬅️ В меню")
async def pda_back_to_menu(message: Message) -> None:
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
    text, page, total_pages = build_rating_overview(get_storage(), player.telegram_id, page=0)
    await message.answer(
        text,
        reply_markup=rating_page_keyboard(page=page, total_pages=total_pages),
    )


@router.message(F.text == "🗺 Карта")
async def show_zone_map(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    locations = get_storage().get_locations()
    image_bytes = build_zone_map_image(locations, current_location=player.location, player_faction=player.faction)
    image = BufferedInputFile(image_bytes, filename="zone_map.png")
    await message.answer_photo(
        photo=image,
        caption="Карта Зоны: точки, типы и текущий контроль.",
        reply_markup=pda_keyboard(),
    )


@router.message(F.text == "👥 Игроки")
async def show_players(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
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
    sender_name = sender.nickname if sender is not None else str(sender_id)
    text = f"📢 Объявление:\n{body}\n\n— {sender_name}"

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
    text, safe_key, safe_page, total_pages = build_players_faction_page_text(
        get_storage(),
        faction_key,
        page,
    )
    await edit_menu_message(
        callback,
        text,
        players_faction_page_keyboard(safe_key, page=safe_page, total_pages=total_pages),
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


@router.callback_query(F.data == "ratings:leaderboard")
@router.callback_query(F.data.startswith("rating:page:"))
async def show_rating_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    page = 0
    raw = callback.data or ""
    if raw.startswith("rating:page:"):
        try:
            page = int(raw.rsplit(":", maxsplit=1)[-1])
        except ValueError:
            page = 0
    text, safe_page, total_pages = build_rating_overview(
        get_storage(),
        player.telegram_id,
        page=page,
    )
    await edit_menu_message(
        callback,
        text,
        rating_page_keyboard(page=safe_page, total_pages=total_pages),
    )


@router.message(F.text == "⚡ Выпить энергетик")
async def drink_energy(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
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


@router.callback_query(F.data == "artifact:search")
async def artifact_search_callback(callback: CallbackQuery) -> None:
    result = search_artifacts(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.message(Command("pay"))
async def pay_command(message: Message) -> None:
    sender_id = message.from_user.id
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
    result, target_text = create_duel_challenge(get_storage(), sender_id, target_telegram_id)
    await message.answer(action_result_text(sender_id, result.text))
    if result.ok and target_text:
        try:
            await bot.send_message(
                target_telegram_id,
                target_text,
                reply_markup=duel_challenge_keyboard(sender_id),
            )
        except Exception:
            logger.exception("Failed to deliver duel challenge to %s", target_telegram_id)
            await message.answer(
                "Вызов сохранён, но не удалось доставить сообщение сопернику "
                "(он должен написать боту /start)."
            )


@router.callback_query(F.data.startswith("duel:accept:"))
async def duel_accept_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    await callback.answer()
    try:
        challenger_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.message.answer("Некорректный вызов.")  # type: ignore[union-attr]
        return
    target_id = callback.from_user.id
    result, challenger_text = accept_duel(get_storage(), target_id, challenger_id)
    await reply_action_result(callback, result.text)
    if result.ok and challenger_text:
        try:
            await bot.send_message(challenger_id, action_result_text(challenger_id, challenger_text))
        except Exception:
            logger.exception("Failed to notify duel challenger %s", challenger_id)


@router.callback_query(F.data.startswith("duel:decline:"))
async def duel_decline_callback(callback: CallbackQuery, bot: Bot) -> None:
    assert callback.data and callback.from_user
    await callback.answer()
    try:
        challenger_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.message.answer("Некорректный вызов.")  # type: ignore[union-attr]
        return
    target_id = callback.from_user.id
    result, challenger_text = decline_duel(get_storage(), target_id, challenger_id)
    await reply_action_result(callback, result.text)
    if result.ok and challenger_text:
        try:
            await bot.send_message(challenger_id, action_result_text(challenger_id, challenger_text))
        except Exception:
            logger.exception("Failed to notify duel decline to %s", challenger_id)


@router.message(F.text == "🏕 Вылазка")
async def show_sortie(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await message.answer(
        "🏕 Вылазка\n"
        "Война, переходы по Зоне и рейды.",
        reply_markup=sortie_keyboard(),
    )


@router.message(F.text == "🗺 Переход")
async def show_travel(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    locations = get_storage().get_locations()
    await message.answer(
        "Выбирай локацию для перехода. Переходы расходуют энергию, "
        "грузовик ускоряет путь, но тратит топливо.",
        reply_markup=locations_keyboard(locations, mode="travel"),
    )


@router.callback_query(F.data.startswith("travel:"))
async def handle_travel(callback: CallbackQuery) -> None:
    destination = (callback.data or "").split(":", maxsplit=1)[1]
    result = travel_to(get_storage(), callback.from_user.id, destination)
    await reply_action_result(callback, result.text)


@router.message(F.text == "⚔️ Война")
async def show_war(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
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
        "Сценарий войны:\n"
        "• Захват точек — только через военное лобби (минимум 5 бойцов).\n"
        "• Базы штурмуются только лобби; рейды — на логова (не базы).\n"
        "• Соло-штурм одним игроком отключён.\n"
        "• Нельзя штурмовать свои и союзнические точки.\n"
        "• При успехе контроль получает группировка-хост лобби.\n"
        "• Точки ресурсов и базы дают контроль и преимущества на карте.\n"
        "• Точки интереса уменьшают время прибытия.\n"
        "• Шанс боя: сила отряда / (сила отряда + сила NPC + укрепление базы).\n"
        "• Укрепление базы: лидер, 10000 RU из казны, +1 к защите за уровень.\n"
        "• Казна и склад — в разделе «👥 Группировка».\n"
    )
    await edit_menu_message(
        callback,
        explainer + "\n" + alliance_overview,
        alliance_keyboard(),
    )


@router.callback_query(F.data == "war:section:lobby")
async def war_lobby_section_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    await edit_menu_message(
        callback,
        build_war_lobby_overview(db, player.telegram_id),
        war_lobby_keyboard(
            list_assaultable_locations(db, player.faction),
            can_dissolve=can_dissolve_war_lobby(db, player.telegram_id),
        ),
    )


async def _refresh_war_lobby_menu(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or callback.message is None:
        return
    try:
        await callback.message.edit_text(
            build_war_lobby_overview(db, player.telegram_id),
            reply_markup=war_lobby_keyboard(
                list_assaultable_locations(db, player.faction or ""),
                can_dissolve=can_dissolve_war_lobby(db, player.telegram_id),
            ),
        )
    except TelegramBadRequest:
        pass


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
async def handle_war_legacy_callback(callback: CallbackQuery) -> None:
    """Старые кнопки solo-штурма (war:<локация>) — только отказ."""
    location = (callback.data or "").split(":", maxsplit=1)[1]
    if location.startswith("section:") or location.startswith("transfer:"):
        await safe_callback_answer(callback)
        return
    result = attack_location(get_storage(), callback.from_user.id, location)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("war_lobby:create:"))
async def war_lobby_create_callback(callback: CallbackQuery) -> None:
    location = (callback.data or "").split(":", maxsplit=2)[2]
    result = create_or_join_war_lobby(get_storage(), callback.from_user.id, location)
    await reply_action_result(callback, result.text)
    if result.ok:
        await _refresh_war_lobby_menu(callback)


@router.callback_query(F.data == "war_lobby:join")
async def war_lobby_join_callback(callback: CallbackQuery) -> None:
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
        await _refresh_war_lobby_menu(callback)


@router.callback_query(F.data == "war_lobby:launch")
async def war_lobby_launch_callback(callback: CallbackQuery) -> None:
    result = launch_war_lobby(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)
    if result.ok:
        await _refresh_war_lobby_menu(callback)


@router.callback_query(F.data == "war_lobby:dissolve")
async def war_lobby_dissolve_callback(callback: CallbackQuery) -> None:
    result = dissolve_war_lobby(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)
    if result.ok:
        await _refresh_war_lobby_menu(callback)


@router.callback_query(F.data.startswith("alliance:propose:"))
async def alliance_propose_callback(callback: CallbackQuery) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = propose_alliance(get_storage(), callback.from_user.id, target_faction)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "alliance:menu:propose")
async def alliance_propose_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
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
    await edit_menu_message(
        callback,
        "Входящие предложения на союз:",
        alliance_pending_keyboard(pending_from),
    )


@router.callback_query(F.data == "alliance:menu:back")
async def alliance_menu_back_callback(callback: CallbackQuery) -> None:
    await edit_menu_message(callback, "Раздел дипломатии:", alliance_keyboard())


@router.callback_query(F.data == "alliance:none")
async def alliance_none_callback(callback: CallbackQuery) -> None:
    await callback.answer("Список пуст.", show_alert=True)


@router.callback_query(F.data.startswith("alliance:confirm:"))
async def alliance_confirm_callback(callback: CallbackQuery) -> None:
    source_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = accept_alliance(get_storage(), callback.from_user.id, source_faction)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("alliance:break:"))
async def alliance_break_callback(callback: CallbackQuery) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = break_alliance(get_storage(), callback.from_user.id, target_faction)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("alliance:war:"))
async def alliance_war_callback(callback: CallbackQuery) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = declare_war(get_storage(), callback.from_user.id, target_faction)
    await reply_action_result(callback, result.text)


@router.message(F.text == "🪖 Рейды")
async def show_raids(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return
    db = get_storage()
    text = build_raids_overview(db, player.telegram_id)
    led_raids = db.list_open_raids_led_by(player.telegram_id)
    await message.answer(
        text,
        reply_markup=raid_keyboard(db.get_locations(), led_raids=led_raids),
    )


@router.callback_query(F.data.startswith("raid:create:"))
async def create_raid_callback(callback: CallbackQuery) -> None:
    location = (callback.data or "").split(":", maxsplit=2)[2]
    result = create_or_join_faction_raid(get_storage(), callback.from_user.id, location)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "raid:join")
async def join_raid_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None or player.faction is None:
        await callback.answer("Нужен персонаж с группировкой.", show_alert=True)
        return
    open_raid = get_storage().get_open_raid_for_faction(player.faction)
    if open_raid is None:
        await callback.answer("Открытых рейдов нет.", show_alert=True)
        return
    result = create_or_join_faction_raid(get_storage(), callback.from_user.id, str(open_raid["location"]))
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "raid:ally:join")
async def join_raid_as_ally_callback(callback: CallbackQuery) -> None:
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
    result = create_or_join_faction_raid(storage, callback.from_user.id, str(open_raid["location"]))
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "raid:launch")
async def launch_raid_callback(callback: CallbackQuery, bot: Bot) -> None:
    result = launch_open_raid(get_storage(), callback.from_user.id)
    notified: set[int] = set()
    if result.notify_member_ids:
        for member_id in result.notify_member_ids:
            if member_id in notified:
                continue
            notified.add(member_id)
            try:
                await bot.send_message(member_id, f"📣 Итог рейда:\n{result.text}")
            except Exception:
                logger.exception("Failed to deliver raid result to member %s", member_id)
    if callback.from_user.id not in notified:
        await reply_action_result(callback, result.text)
    else:
        await safe_callback_answer(callback)


@router.callback_query(F.data == "raid:cancel:all")
async def cancel_all_raids_callback(callback: CallbackQuery, bot: Bot) -> None:
    storage = get_storage()
    leader_id = callback.from_user.id
    open_raids = storage.list_open_raids_led_by(leader_id)
    notify_ids: set[int] = set()
    for raid in open_raids:
        notify_ids.update(storage.get_raid_member_ids(int(raid["id"])))

    result = cancel_all_raids_by_leader(storage, leader_id)
    if result.ok:
        for member_id in notify_ids:
            if member_id == leader_id:
                continue
            try:
                await bot.send_message(
                    member_id,
                    f"📣 Рейд отменён создателем.\n{result.text}",
                )
            except Exception:
                logger.exception("Failed to notify raid member %s about cancel-all", member_id)
    await reply_action_result(callback, result.text)


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
    member_ids = storage.get_raid_member_ids(raid_id)
    result = cancel_raid_by_leader(storage, leader_id, raid_id)
    if result.ok:
        for member_id in member_ids:
            if member_id == leader_id:
                continue
            try:
                await bot.send_message(member_id, f"📣 {result.text}")
            except Exception:
                logger.exception("Failed to notify raid member %s about cancel", member_id)
    await reply_action_result(callback, result.text)


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
    return faction_group_keyboard(
        is_leader=is_leader,
        can_withdraw_warehouse=can_wh,
        can_withdraw_treasury=can_tr,
    )


@router.message(F.text == "🛰 События")
async def show_events(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    overview = build_events_overview(get_storage())
    await message.answer(overview)


@router.message(F.text == "👥 Группировка")
async def show_faction_group(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
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
    if not player_ready(player):
        await message.answer("Сначала выбери группировку.")
        return
    text = build_economy_overview(get_storage(), player.telegram_id)
    await message.answer(text, reply_markup=economy_keyboard())


@router.callback_query(F.data.startswith("eco:warehouse:deposit:"))
async def warehouse_deposit_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
    result = deposit_to_faction_warehouse(get_storage(), callback.from_user.id, item_key, 1)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("eco:warehouse:withdraw:"))
async def warehouse_withdraw_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
    result = withdraw_from_faction_warehouse(get_storage(), callback.from_user.id, item_key, 1)
    await reply_action_result(callback, result.text)


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
    await callback.answer("Готово." if result.ok else result.text[:180], show_alert=not result.ok)


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
async def faction_rank_set_callback(callback: CallbackQuery) -> None:
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


@router.callback_query(F.data.startswith("eco:auction:create:"))
async def auction_create_callback(callback: CallbackQuery) -> None:
    lot_key = (callback.data or "").split(":", maxsplit=3)[3]
    result = create_faction_auction(get_storage(), callback.from_user.id, lot_key)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data.startswith("eco:market:create:"))
async def market_create_callback(callback: CallbackQuery, state: FSMContext) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
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
        "Комиссия рынка 30%: покупатель платит цену лота, продавец получает 70%.",
        economy_keyboard(),
    )


@router.message(Registration.market_lot_price)
async def process_market_lot_price(message: Message, state: FSMContext) -> None:
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


@router.callback_query(F.data == "eco:market:buy:first")
async def market_buy_first_callback(callback: CallbackQuery) -> None:
    result = buy_first_market_lot(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


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
async def market_buy_by_id_callback(callback: CallbackQuery) -> None:
    lot_id = (callback.data or "").split(":", maxsplit=3)[3]
    try:
        auction_id = int(lot_id)
    except ValueError:
        await callback.answer("Некорректный ID лота.", show_alert=True)
        return
    result = buy_market_lot(get_storage(), callback.from_user.id, auction_id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "eco:market:cancel:mine")
async def market_cancel_mine_callback(callback: CallbackQuery) -> None:
    result = cancel_own_first_market_lot(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "eco:auction:buy:first")
async def auction_buy_first_callback(callback: CallbackQuery) -> None:
    result = buy_first_faction_auction(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "eco:auction:cancel:mine")
async def auction_cancel_mine_callback(callback: CallbackQuery) -> None:
    result = cancel_own_first_auction(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.callback_query(F.data == "eco:smuggle:run")
async def smuggle_callback(callback: CallbackQuery) -> None:
    result = attempt_smuggling(get_storage(), callback.from_user.id)
    await reply_action_result(callback, result.text)


@router.message()
async def fallback(message: Message, bot: Bot) -> None:
    player = ensure_character(message)
    normalized_text = _normalize_info_trigger(message.text)
    if player is not None and (
        normalized_text.endswith("информация") or normalized_text.startswith("/info")
    ):
        await message.answer(_build_info_text(player))
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

    async def periodic_snapshot_sync() -> None:
        while True:
            await asyncio.sleep(SNAPSHOT_SYNC_SECONDS)
            try:
                get_storage().save_snapshot()
            except Exception:
                logger.exception("Periodic snapshot sync failed")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    async def periodic_zone_systems() -> None:
        while True:
            await asyncio.sleep(POINTS_INCOME_TICK_SECONDS)
            try:
                apply_controlled_points_income(get_storage())
            except Exception:
                logger.exception("Points income tick failed")
            try:
                message_text, notify_ids = process_emission_cycle(get_storage())
                if message_text:
                    for user_id in notify_ids:
                        try:
                            await bot.send_message(user_id, message_text)
                        except Exception:
                            logger.debug("Failed emission notify to %s", user_id)
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

    sync_task = asyncio.create_task(periodic_snapshot_sync())
    zone_task = asyncio.create_task(periodic_zone_systems())
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        sync_task.cancel()
        zone_task.cancel()
        for task in (sync_task, zone_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Background task finished with error")
        try:
            get_storage().save_snapshot()
        except Exception:
            logger.exception("Final snapshot save failed during shutdown")


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
