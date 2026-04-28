from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from app.config import load_settings
from app.game_logic import (
    apply_dynamic_zone_event,
    attack_location,
    attempt_smuggling,
    build_achievements_overview,
    build_economy_overview,
    build_events_overview,
    build_raids_overview,
    build_rating_overview,
    buy_item,
    buy_first_faction_auction,
    cancel_own_first_auction,
    create_faction_auction,
    create_or_join_faction_raid,
    launch_open_raid,
    build_quest_overview,
    deposit_to_faction_warehouse,
    format_inventory,
    repair_gear,
    run_quest,
    sell_item,
    travel_to,
    use_energy_drink,
    use_medkit,
    use_vodka,
    use_antirad,
    use_bread,
    use_sausage,
    use_stew,
    use_water,
    use_mineralka,
    use_beard_tea,
    search_artifacts,
    transfer_money_with_fee,
    create_or_join_war_lobby,
    launch_war_lobby,
    build_war_lobby_overview,
    transfer_location_to_ally,
    create_market_lot,
    buy_first_market_lot,
    buy_market_lot,
    build_market_lots_overview,
    list_sellable_market_equipment,
    cancel_own_first_market_lot,
    withdraw_from_faction_warehouse,
    build_dead_character_text,
    respawn_character,
    build_alliance_overview,
    propose_alliance,
    break_alliance,
    accept_alliance,
    declare_war,
    equip_armor,
    equip_weapon,
    list_equippable_armor,
    list_equippable_weapons,
)
from app.keyboards import (
    economy_keyboard,
    inventory_equipment_keyboard,
    dead_character_keyboard,
    faction_keyboard,
    gender_keyboard,
    locations_keyboard,
    main_menu_keyboard,
    quests_keyboard,
    raid_keyboard,
    ratings_keyboard,
    topup_keyboard,
    trader_buy_categories_keyboard,
    trader_buy_armor_keyboard,
    trader_buy_consumables_keyboard,
    trader_buy_gear_keyboard,
    trader_buy_weapons_keyboard,
    trader_keyboard,
    trader_sell_categories_keyboard,
    trader_sell_armor_keyboard,
    trader_sell_consumables_keyboard,
    trader_sell_gear_keyboard,
    trader_sell_weapons_keyboard,
    equip_armor_keyboard,
    equip_weapon_keyboard,
    alliance_keyboard,
    alliance_target_keyboard,
    alliance_pending_keyboard,
    war_lobby_keyboard,
    war_transfer_keyboard,
    market_lots_keyboard,
    market_create_select_keyboard,
    war_sections_keyboard,
)
from app.profile_card import build_character_card
from app.storage import Character, Storage
from app.zone_map import build_zone_map_image

logger = logging.getLogger(__name__)

router = Router()
storage: Storage | None = None
admin_ids: tuple[int, ...] = ()
SNAPSHOT_SYNC_SECONDS = 300
TOPUP_RATE_RU_PER_STAR = 150
TOPUP_PAYLOAD_PREFIX = "topup_stars:"
TOPUP_ALLOWED_AMOUNTS = {1, 5, 10, 25}
TOPUP_MIN_STARS = 1
TOPUP_MAX_STARS = 10000


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


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    db = get_storage()
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
        current_state = await state.get_state()
        if current_state == Registration.nickname.state:
            await message.answer("Регистрация уже начата. Введи прозвище.")
            return
        if current_state == Registration.gender.state:
            await message.answer("Регистрация уже начата. Выбери пол персонажа:", reply_markup=gender_keyboard())
            return
        await state.clear()
        await state.set_state(Registration.nickname)
        await message.answer(
            "Telegram-бот-игра в стиле S.T.A.L.K.E.R., где это не просто "
            "«нажал кнопку — получил ответ», а целый живой мир с прогрессом игрока.\n\n"
            "Что в нем есть:\n\n"
            "👥 Группировки: можно вступать, назначать лидеров, договариваться о союзе или объявлять войну.\n"
            "⚔️ Рейды и военные лобби: игроки собираются командой и вместе атакуют точки.\n"
            "🛒 Рынок между игроками: вещи можно выставлять лотами, а не только продавать боту.\n"
            "☢️ Выживание: радиация, голод и жажда влияют на персонажа, за этим нужно следить.\n"
            "🔫 Снаряжение с износом: оружие и броня теряют прочность, и это влияет на цену продажи.\n"
            "💎 Поиск артефактов: через детекторы с разной эффективностью.\n"
            "❤️ Смерть и респавн: если персонаж «падает», нужно восстанавливаться по правилам игры.\n\n"
            "Если ты готов, то назови свое имя!"
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


def _build_info_text(player: Character) -> str:
    player = ensure_character(message)
    faction_chats = {
        "Свобода": "https://t.me/+kAvQ4NyrKndlNmI6",
        "Долг": "https://t.me/+IbIz9zSoruY0OTMy",
        "Нейтралы": "https://t.me/+IHxjjCKSFJQwOTky",
        "Бандиты": "https://t.me/+cP-Eihx_QFo0MTAy",
    }
    common_chat = "https://t.me/+R0mfqDJ_HCUyOTI6"
    faction_chat = faction_chats.get(player.faction or "")
    chats_block = (
        f"Чаты:\n"
        f"• 🌐 Общий: {common_chat}\n"
        f"• 🛡️ {player.faction}: {faction_chat}"
        if faction_chat
        else f"Чаты:\n"
        f"• 🌐 Общий: {common_chat}\n"
        f"• Выбери группировку, чтобы увидеть чат своей фракции."
    )
    return (
        "ℹ️ Информация по игре\n\n"
        "Команды:\n"
        "• /start — создать персонажа или войти в существующего.\n"
        "• /menu — открыть главное меню.\n"
        "• /info — открыть эту справку.\n"
        "• /pay <telegram_id> <сумма> — перевод игроку (комиссия 30%).\n\n"
        "Механики:\n"
        "• 🚚 Грузовик ускоряет переходы и снижает расход энергии на поездку,\n"
        "  но тратит 1 топливо за каждый переход.\n"
        "• 🛏️ Спальник пассивно ускоряет восстановление энергии в 2 раза.\n"
        "• 💎 Экипированный артефакт даёт +5% к пассивному восстановлению энергии.\n\n"
        f"{chats_block}"
    )


@router.message(Command("info"))
@router.message(F.text.func(lambda value: _normalize_info_trigger(value).endswith("информация")))
async def show_info(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
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
        await message.answer("Использование: /give <telegram_id> <amount>")
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
async def cmd_set_leader(message: Message) -> None:
    sender_id = message.from_user.id
    if not is_admin_user(sender_id):
        await message.answer("Команда доступна только администратору.")
        return

    parts = (message.text or "").strip().split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Использование: /leader <группировка> <telegram_id>")
        return

    faction_name = parts[1]
    try:
        leader_id = int(parts[2])
    except ValueError:
        await message.answer("Telegram ID лидера должен быть целым числом.")
        return

    db = get_storage()
    if not db.set_faction_leader(faction_name, leader_id):
        await message.answer(
            "Не удалось назначить лидера. Проверь, что группировка существует, "
            "а игрок состоит в этой группировке."
        )
        return
    await message.answer(f"Лидер группировки {faction_name} назначен: {leader_id}.")


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

    await state.update_data(nickname=nickname)
    await state.set_state(Registration.gender)
    await message.answer("Отлично. Выбери пол персонажа:", reply_markup=gender_keyboard())


@router.callback_query(Registration.gender, F.data.startswith("gender:"))
async def process_gender(callback: CallbackQuery, state: FSMContext) -> None:
    payload = (callback.data or "").split(":", maxsplit=1)
    if len(payload) != 2:
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    gender_code = payload[1]
    gender = "Мужской" if gender_code == "male" else "Женский"
    data = await state.get_data()
    nickname = data.get("nickname")
    if not nickname:
        await state.set_state(Registration.nickname)
        await callback.message.answer("Введи прозвище заново.")
        await callback.answer()
        return

    db = get_storage()
    db.create_character(callback.from_user.id, nickname=nickname, gender=gender)

    await state.clear()
    saved = db.get_character(callback.from_user.id, refresh_energy=False)
    uid_line = f"\nТвой ID в Зоне: {saved.player_uid}" if saved else ""
    await callback.message.answer(
        f"Персонаж создан: {nickname} ({gender}).{uid_line}\nВыбери сторону:",
        reply_markup=faction_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("faction:"))
async def process_faction(callback: CallbackQuery, state: FSMContext) -> None:
    faction = (callback.data or "").split(":", maxsplit=1)[1]
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала введи /start", show_alert=True)
        return

    if faction not in {"Долг", "Свобода", "Нейтралы", "Бандиты"}:
        await callback.answer("Неизвестная группировка", show_alert=True)
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


async def send_profile_snapshot(message: Message, player: Character) -> None:
    caption = (
        f"Профиль сталкера {player.nickname}\n"
        f"ID: {player.player_uid}\n"
        f"Фракция: {player.faction or 'не выбрана'}"
    )
    image_bytes = build_character_card(player)
    image = BufferedInputFile(image_bytes, filename=f"{player.player_uid}.png")
    await message.answer_photo(photo=image, caption=caption)


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
        format_inventory(player),
        reply_markup=inventory_equipment_keyboard(),
    )


@router.callback_query(F.data == "inventory:open")
async def open_inventory_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health <= 0:
        await callback.message.answer(build_dead_character_text(player), reply_markup=dead_character_keyboard())
        await callback.answer()
        return
    await callback.message.answer(
        format_inventory(player),
        reply_markup=inventory_equipment_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "respawn:base")
async def respawn_base_callback(callback: CallbackQuery) -> None:
    result = respawn_character(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    if result.ok:
        player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            await send_profile_snapshot(callback.message, player)
    await callback.answer()


@router.callback_query(F.data == "player:respawn")
async def show_respawn_menu_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    if player.health > 0:
        await callback.answer("Респавн доступен только при HP=0.", show_alert=True)
        return
    await callback.message.answer(build_dead_character_text(player), reply_markup=dead_character_keyboard())
    await callback.answer()


@router.message(F.text == "🧾 Профиль")
async def show_profile(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    await send_profile_snapshot(message, player)


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
    await callback.message.answer("Покупка: выбери категорию.", reply_markup=trader_buy_categories_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:menu:sell")
async def show_sell_menu(callback: CallbackQuery) -> None:
    await callback.message.answer("Продажа: выбери категорию.", reply_markup=trader_sell_categories_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:menu:root")
async def show_trade_root(callback: CallbackQuery) -> None:
    await callback.message.answer("Торговец на связи. Выбери раздел:", reply_markup=trader_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:buy:consumables")
async def show_buy_consumables(callback: CallbackQuery) -> None:
    await callback.message.answer("Покупка расходников:", reply_markup=trader_buy_consumables_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:buy:gear")
async def show_buy_gear(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Снаряжение и обслуживание:\n"
        "• Оружие и броня покупаются отдельно в своих разделах.\n"
        "• После покупки предмет попадает в инвентарь.\n"
        "• Экипировка выполняется во вкладке «🎒 Инвентарь».",
        reply_markup=trader_buy_gear_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "trade:buy:armor")
async def show_buy_armor(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Покупка брони и костюмов.\n"
        "После покупки предмет добавляется в инвентарь.",
        reply_markup=trader_buy_armor_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "trade:buy:weapons")
async def show_buy_weapons(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Покупка оружия.\n"
        "После покупки предмет добавляется в инвентарь.",
        reply_markup=trader_buy_weapons_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "trade:sell:consumables")
async def show_sell_consumables(callback: CallbackQuery) -> None:
    await callback.message.answer("Продажа расходников:", reply_markup=trader_sell_consumables_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:sell:gear")
async def show_sell_gear(callback: CallbackQuery) -> None:
    await callback.message.answer("Продажа/ремонт снаряжения:", reply_markup=trader_sell_gear_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:sell:gear:armor")
async def show_sell_gear_armor(callback: CallbackQuery) -> None:
    await callback.message.answer("Продажа брони и костюмов:", reply_markup=trader_sell_armor_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:sell:armor")
async def show_sell_armor_alias_callback(callback: CallbackQuery) -> None:
    # Backward-compatible alias used by current sell categories keyboard.
    await callback.message.answer("Продажа брони и костюмов:", reply_markup=trader_sell_armor_keyboard())
    await callback.answer()


@router.callback_query(F.data == "trade:sell:weapons")
async def show_sell_weapons(callback: CallbackQuery) -> None:
    await callback.message.answer("Продажа оружия:", reply_markup=trader_sell_weapons_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=1)[1]
    db = get_storage()
    result = buy_item(db, callback.from_user.id, item_key)
    await callback.message.answer(result.text)
    if result.ok and item_key == "truck":
        player = db.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            await send_profile_snapshot(callback.message, player)
    await callback.answer()


@router.callback_query(F.data.startswith("sell:"))
async def handle_sell(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=1)[1]
    result = sell_item(get_storage(), callback.from_user.id, item_key)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "repair:weapon")
async def repair_weapon_callback(callback: CallbackQuery) -> None:
    result = repair_gear(get_storage(), callback.from_user.id, "weapon")
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "repair:armor")
async def repair_armor_callback(callback: CallbackQuery) -> None:
    result = repair_gear(get_storage(), callback.from_user.id, "armor")
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "equip:artifact")
async def equip_artifact_callback(callback: CallbackQuery) -> None:
    result = equip_artifact(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "equip:menu:weapon")
async def equip_weapon_menu_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    options = list_equippable_weapons(player)
    if not options:
        await callback.answer("В инвентаре нет оружия для экипировки.", show_alert=True)
        return
    await callback.message.answer(
        "Выбери оружие для экипировки:",
        reply_markup=equip_weapon_keyboard(options),
    )
    await callback.answer()


@router.callback_query(F.data == "equip:menu:armor")
async def equip_armor_menu_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    options = list_equippable_armor(player)
    if not options:
        await callback.answer("В инвентаре нет брони для экипировки.", show_alert=True)
        return
    await callback.message.answer(
        "Выбери броню для экипировки:",
        reply_markup=equip_armor_keyboard(options),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("equip:weapon:"))
async def equip_weapon_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=2)[2]
    db = get_storage()
    result = equip_weapon(db, callback.from_user.id, item_key)
    await callback.message.answer(result.text)
    if result.ok:
        player = db.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            await send_profile_snapshot(callback.message, player)
    await callback.answer()


@router.callback_query(F.data.startswith("equip:armor:"))
async def equip_armor_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=2)[2]
    db = get_storage()
    result = equip_armor(db, callback.from_user.id, item_key)
    await callback.message.answer(result.text)
    if result.ok:
        player = db.get_character(callback.from_user.id, refresh_energy=False)
        if player is not None:
            await send_profile_snapshot(callback.message, player)
    await callback.answer()


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
        "Ниже указан обязательный расход амуниции.\n\n"
        f"{overview}",
        reply_markup=quests_keyboard(),
    )


@router.callback_query(F.data.startswith("quest:"))
async def handle_quest(callback: CallbackQuery) -> None:
    quest_key = (callback.data or "").split(":", maxsplit=1)[1]
    result = run_quest(get_storage(), callback.from_user.id, quest_key)
    await callback.message.answer(result.text)
    await callback.answer()


@router.message(F.text == "🎖 Достижения")
async def show_achievements(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    text = build_achievements_overview(get_storage(), player.telegram_id)
    await message.answer(text)


@router.message(F.text == "🏆 Рейтинг")
async def show_rating(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    text = build_rating_overview(get_storage(), player.telegram_id, limit=10)
    await message.answer(text, reply_markup=ratings_keyboard())


@router.callback_query(F.data == "ratings:achievements")
async def show_achievements_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text = build_achievements_overview(get_storage(), player.telegram_id)
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data == "ratings:leaderboard")
async def show_rating_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа через /start.", show_alert=True)
        return
    text = build_rating_overview(get_storage(), player.telegram_id, limit=10)
    await callback.message.answer(text, reply_markup=ratings_keyboard())
    await callback.answer()


@router.message(F.text == "⚡ Выпить энергетик")
async def drink_energy(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    result = use_energy_drink(get_storage(), message.from_user.id)
    await message.answer(result.text)


@router.callback_query(F.data == "use:medkit")
async def use_medkit_callback(callback: CallbackQuery) -> None:
    result = use_medkit(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:vodka")
async def use_vodka_callback(callback: CallbackQuery) -> None:
    result = use_vodka(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:antirad")
async def use_antirad_callback(callback: CallbackQuery) -> None:
    result = use_antirad(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:bread")
async def use_bread_callback(callback: CallbackQuery) -> None:
    result = use_bread(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:sausage")
async def use_sausage_callback(callback: CallbackQuery) -> None:
    result = use_sausage(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:stew")
async def use_stew_callback(callback: CallbackQuery) -> None:
    result = use_stew(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:water_bottle")
async def use_water_callback(callback: CallbackQuery) -> None:
    result = use_water(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:mineral_water")
async def use_mineralka_callback(callback: CallbackQuery) -> None:
    result = use_mineralka(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "use:beard_tea")
async def use_beard_tea_callback(callback: CallbackQuery) -> None:
    result = use_beard_tea(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "artifact:search")
async def artifact_search_callback(callback: CallbackQuery) -> None:
    result = search_artifacts(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.message(Command("pay"))
async def pay_command(message: Message) -> None:
    sender_id = message.from_user.id
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.answer("Использование: /pay <telegram_id> <сумма>")
        return
    try:
        target_telegram_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("Telegram ID и сумма должны быть целыми числами.")
        return
    result = transfer_money_with_fee(get_storage(), sender_id, target_telegram_id, amount)
    await message.answer(result.text)


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
    )


@router.callback_query(F.data.startswith("travel:"))
async def handle_travel(callback: CallbackQuery) -> None:
    destination = (callback.data or "").split(":", maxsplit=1)[1]
    result = travel_to(get_storage(), callback.from_user.id, destination)
    await callback.message.answer(result.text)
    await callback.answer()


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


@router.callback_query(F.data == "war:section:scenario")
async def war_scenario_section_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    factions = db.get_factions()
    current_faction = player.faction or ""
    own_faction = next((f for f in factions if f["name"] == current_faction), None)
    own_treasury_text = (
        f"• {current_faction}: казна {own_faction['treasury']} RU"
        if own_faction is not None
        else "• Данные по казне временно недоступны"
    )
    alliance_overview = build_alliance_overview(db, player.telegram_id)
    explainer = (
        "Сценарий войны (базовая версия):\n"
        "• Точки ресурсов приносят деньги группировке.\n"
        "• Базы дают безопасную точку и сервис.\n"
        "• Точки интереса уменьшают время прибытия.\n"
        "• Шанс боя: сила отряда / (сила отряда + сила NPC).\n"
    )
    await callback.message.answer(
        explainer + "\nЭкономика твоей группировки:\n" + own_treasury_text + "\n\n" + alliance_overview,
        reply_markup=alliance_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "war:section:lobby")
async def war_lobby_section_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    await callback.message.answer(
        build_war_lobby_overview(db, player.telegram_id),
        reply_markup=war_lobby_keyboard(db.get_locations()),
    )
    await callback.answer()


@router.callback_query(F.data == "war:section:assault")
async def war_assault_section_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player_ready(player):
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    await callback.message.answer(
        "Выбери точку для штурма:",
        reply_markup=locations_keyboard(db.get_locations(), mode="war"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("war:"))
async def handle_war(callback: CallbackQuery) -> None:
    location = (callback.data or "").split(":", maxsplit=1)[1]
    result = attack_location(get_storage(), callback.from_user.id, location)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data.startswith("war_lobby:create:"))
async def war_lobby_create_callback(callback: CallbackQuery) -> None:
    location = (callback.data or "").split(":", maxsplit=2)[2]
    result = create_or_join_war_lobby(get_storage(), callback.from_user.id, location)
    await callback.message.answer(result.text)
    await callback.answer()


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
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "war_lobby:launch")
async def war_lobby_launch_callback(callback: CallbackQuery) -> None:
    result = launch_war_lobby(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data.startswith("war:transfer:"))
async def war_transfer_location_callback(callback: CallbackQuery) -> None:
    ally_faction = (callback.data or "").split(":", maxsplit=2)[2]
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    result = transfer_location_to_ally(get_storage(), callback.from_user.id, player.location, ally_faction)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data.startswith("alliance:propose:"))
async def alliance_propose_callback(callback: CallbackQuery) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = propose_alliance(get_storage(), callback.from_user.id, target_faction)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "alliance:menu:propose")
async def alliance_propose_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    await callback.message.answer(
        "Выбери группировку для предложения договора о союзе:",
        reply_markup=alliance_target_keyboard(db.get_factions(), player.faction, mode="propose"),
    )
    await callback.answer()


@router.callback_query(F.data == "alliance:menu:declare_war")
async def alliance_war_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    await callback.message.answer(
        "Выбери группировку для объявления войны:",
        reply_markup=alliance_target_keyboard(db.get_factions(), player.faction, mode="declare_war"),
    )
    await callback.answer()


@router.callback_query(F.data == "alliance:menu:break")
async def alliance_break_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    await callback.message.answer(
        "Выбери группировку для разрыва союза:",
        reply_markup=alliance_target_keyboard(db.get_factions(), player.faction, mode="break"),
    )
    await callback.answer()


@router.callback_query(F.data == "alliance:menu:confirm")
async def alliance_confirm_menu_callback(callback: CallbackQuery) -> None:
    db = get_storage()
    player = db.get_character(callback.from_user.id, refresh_energy=False)
    if player is None or not player.faction:
        await callback.answer("Сначала создай персонажа и выбери группировку.", show_alert=True)
        return
    incoming = db.list_incoming_alliance_requests(player.faction)
    pending_from = [str(row["requester_faction"]) for row in incoming]
    await callback.message.answer(
        "Входящие предложения на союз:",
        reply_markup=alliance_pending_keyboard(pending_from),
    )
    await callback.answer()


@router.callback_query(F.data == "alliance:menu:back")
async def alliance_menu_back_callback(callback: CallbackQuery) -> None:
    await callback.message.answer("Раздел дипломатии:", reply_markup=alliance_keyboard())
    await callback.answer()


@router.callback_query(F.data == "alliance:none")
async def alliance_none_callback(callback: CallbackQuery) -> None:
    await callback.answer("Список пуст.", show_alert=True)


@router.callback_query(F.data.startswith("alliance:confirm:"))
async def alliance_confirm_callback(callback: CallbackQuery) -> None:
    source_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = accept_alliance(get_storage(), callback.from_user.id, source_faction)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data.startswith("alliance:break:"))
async def alliance_break_callback(callback: CallbackQuery) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = break_alliance(get_storage(), callback.from_user.id, target_faction)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data.startswith("alliance:war:"))
async def alliance_war_callback(callback: CallbackQuery) -> None:
    target_faction = (callback.data or "").split(":", maxsplit=2)[2]
    result = declare_war(get_storage(), callback.from_user.id, target_faction)
    await callback.message.answer(result.text)
    await callback.answer()


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
    await message.answer(text, reply_markup=raid_keyboard(db.get_locations()))


@router.callback_query(F.data.startswith("raid:create:"))
async def create_raid_callback(callback: CallbackQuery) -> None:
    location = (callback.data or "").split(":", maxsplit=2)[2]
    result = create_or_join_faction_raid(get_storage(), callback.from_user.id, location)
    await callback.message.answer(result.text)
    await callback.answer()


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
    await callback.message.answer(result.text)
    await callback.answer()


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
    await callback.message.answer(result.text)
    await callback.answer()


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
        await callback.message.answer(result.text)
    await callback.answer()


@router.message(F.text == "🛰 События")
async def show_events(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    result = apply_dynamic_zone_event(get_storage())
    overview = build_events_overview(get_storage())
    await message.answer(result.text + "\n\n" + overview)


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
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data.startswith("eco:warehouse:withdraw:"))
async def warehouse_withdraw_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
    result = withdraw_from_faction_warehouse(get_storage(), callback.from_user.id, item_key, 1)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "eco:warehouse:view")
async def warehouse_view_callback(callback: CallbackQuery) -> None:
    player = get_storage().get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Персонаж не найден.", show_alert=True)
        return
    text = build_economy_overview(get_storage(), player.telegram_id)
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data.startswith("eco:auction:create:"))
async def auction_create_callback(callback: CallbackQuery) -> None:
    lot_key = (callback.data or "").split(":", maxsplit=3)[3]
    result = create_faction_auction(get_storage(), callback.from_user.id, lot_key)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data.startswith("eco:market:create:"))
async def market_create_callback(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=3)[3]
    if item_key == "choose":
        storage = get_storage()
        player = storage.get_character(callback.from_user.id, refresh_energy=False)
        if player is None:
            await callback.answer("Сначала создай персонажа.", show_alert=True)
            return
        options = list_sellable_market_equipment(storage, callback.from_user.id)
        if not options:
            await callback.message.answer("В инвентаре нет оружия или брони для выставления на рынок.")
            await callback.answer()
            return
        await callback.message.answer(
            "Выбери предмет из инвентаря для выставления на рынок:",
            reply_markup=market_create_select_keyboard(options),
        )
        await callback.answer()
        return
    result = create_market_lot(get_storage(), callback.from_user.id, item_key, 1)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "eco:market:buy:first")
async def market_buy_first_callback(callback: CallbackQuery) -> None:
    result = buy_first_market_lot(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "eco:market:list")
async def market_list_callback(callback: CallbackQuery) -> None:
    storage = get_storage()
    player = storage.get_character(callback.from_user.id, refresh_energy=False)
    if player is None:
        await callback.answer("Сначала создай персонажа.", show_alert=True)
        return
    text, lots = build_market_lots_overview(storage, callback.from_user.id, limit=12)
    await callback.message.answer(text)
    if lots:
        await callback.message.answer("Выбери лот для покупки:", reply_markup=market_lots_keyboard(lots))
    await callback.answer()


@router.callback_query(F.data.startswith("eco:market:buy:"))
async def market_buy_by_id_callback(callback: CallbackQuery) -> None:
    lot_id = (callback.data or "").split(":", maxsplit=3)[3]
    try:
        auction_id = int(lot_id)
    except ValueError:
        await callback.answer("Некорректный ID лота.", show_alert=True)
        return
    result = buy_market_lot(get_storage(), callback.from_user.id, auction_id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "eco:market:cancel:mine")
async def market_cancel_mine_callback(callback: CallbackQuery) -> None:
    result = cancel_own_first_market_lot(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "eco:auction:buy:first")
async def auction_buy_first_callback(callback: CallbackQuery) -> None:
    result = buy_first_faction_auction(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "eco:auction:cancel:mine")
async def auction_cancel_mine_callback(callback: CallbackQuery) -> None:
    result = cancel_own_first_auction(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.callback_query(F.data == "eco:smuggle:run")
async def smuggle_callback(callback: CallbackQuery) -> None:
    result = attempt_smuggling(get_storage(), callback.from_user.id)
    await callback.message.answer(result.text)
    await callback.answer()


@router.message()
async def fallback(message: Message) -> None:
    player = ensure_character(message)
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
    storage = Storage(settings.db_path, snapshot_path=settings.snapshot_path)
    storage.init_db()
    storage.restore_from_snapshot_if_empty()

    async def periodic_snapshot_sync() -> None:
        while True:
            await asyncio.sleep(SNAPSHOT_SYNC_SECONDS)
            try:
                get_storage().save_snapshot()
            except Exception:
                logger.exception("Periodic snapshot sync failed")

    sync_task = asyncio.create_task(periodic_snapshot_sync())

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Snapshot sync task finished with error")
        try:
            get_storage().save_snapshot()
        except Exception:
            logger.exception("Final snapshot save failed during shutdown")


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
