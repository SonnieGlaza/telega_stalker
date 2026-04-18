from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.config import load_settings
from app.game_logic import (
    attack_location,
    buy_item,
    build_quest_overview,
    format_inventory,
    run_quest,
    sell_item,
    travel_to,
    use_energy_drink,
)
from app.keyboards import (
    faction_keyboard,
    gender_keyboard,
    locations_keyboard,
    main_menu_keyboard,
    quests_keyboard,
    trader_keyboard,
)
from app.profile_card import build_character_card
from app.storage import Character, Storage

logger = logging.getLogger(__name__)

router = Router()
storage: Storage | None = None


class Registration(StatesGroup):
    nickname = State()
    gender = State()


def get_storage() -> Storage:
    if storage is None:
        raise RuntimeError("Storage is not initialized")
    return storage


def player_ready(player: Character) -> bool:
    return player.faction is not None


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    player = get_storage().get_character(message.from_user.id)
    if player is None:
        current_state = await state.get_state()
        if current_state == Registration.nickname.state:
            await message.answer("Регистрация уже начата. Введи прозвище.")
            return
        if current_state == Registration.gender.state:
            await message.answer("Регистрация уже начата. Выбери пол персонажа:", reply_markup=gender_keyboard())
            return
        await state.set_state(Registration.nickname)
        await message.answer("Привет, сталкер! Какое у тебя прозвище?")
        return

    await state.clear()
    if not player_ready(player):
        await message.answer(
            "Персонаж уже создан. Теперь выбери группировку:",
            reply_markup=faction_keyboard(),
        )
        return

    await message.answer(
        f"С возвращением, {player.nickname}! Добро пожаловать в Зону.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню открыто.", reply_markup=main_menu_keyboard())


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

    if faction not in {"Долг", "Свобода"}:
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
    await message.answer(format_inventory(player))


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
        "Торговец на связи. Покупай/продавай и строй экономику отряда:",
        reply_markup=trader_keyboard(),
    )


@router.callback_query(F.data.startswith("buy:"))
async def handle_buy(callback: CallbackQuery) -> None:
    item_key = (callback.data or "").split(":", maxsplit=1)[1]
    db = get_storage()
    result = buy_item(db, callback.from_user.id, item_key)
    await callback.message.answer(result.text)
    if result.ok and item_key in {"gear_upgrade", "truck"}:
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
        "Шанс успеха зависит от снаряги и амуниции.\n\n"
        f"{overview}",
        reply_markup=quests_keyboard(),
    )


@router.callback_query(F.data.startswith("quest:"))
async def handle_quest(callback: CallbackQuery) -> None:
    quest_key = (callback.data or "").split(":", maxsplit=1)[1]
    result = run_quest(get_storage(), callback.from_user.id, quest_key)
    await callback.message.answer(result.text)
    await callback.answer()


@router.message(F.text == "⚡ Выпить энергетик")
async def drink_energy(message: Message) -> None:
    player = ensure_character(message)
    if player is None:
        await message.answer("Сначала создай персонажа через /start.")
        return
    result = use_energy_drink(get_storage(), message.from_user.id)
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

    db = get_storage()
    factions = db.get_factions()
    current_faction = player.faction or ""
    own_faction = next((f for f in factions if f["name"] == current_faction), None)
    own_treasury_text = (
        f"• {current_faction}: казна {own_faction['treasury']} RU"
        if own_faction is not None
        else "• Данные по казне временно недоступны"
    )
    explainer = (
        "Сценарий войны (базовая версия):\n"
        "• Точки ресурсов приносят деньги группировке.\n"
        "• Базы дают безопасную точку и сервис.\n"
        "• Точки интереса уменьшают время прибытия.\n"
        "• Шанс боя: сила отряда / (сила отряда + сила NPC).\n"
    )
    await message.answer(explainer + "\nЭкономика твоей группировки:\n" + own_treasury_text)
    await message.answer(
        "Выбери точку для штурма:",
        reply_markup=locations_keyboard(db.get_locations(), mode="war"),
    )


@router.callback_query(F.data.startswith("war:"))
async def handle_war(callback: CallbackQuery) -> None:
    location = (callback.data or "").split(":", maxsplit=1)[1]
    result = attack_location(get_storage(), callback.from_user.id, location)
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
    global storage
    storage = Storage(settings.db_path)
    storage.init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
