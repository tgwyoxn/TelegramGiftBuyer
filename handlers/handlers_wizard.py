# --- Стандартные библиотеки ---
import logging

# --- Сторонние библиотеки ---
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

# --- Внутренние модули ---
from services.config import get_valid_config, get_target_display, save_config
from services.menu import update_menu, payment_keyboard
from services.balance import refresh_balance, refund_all_star_payments
from services.config import CURRENCY, MAX_PROFILES, add_profile, remove_profile, update_profile

logger = logging.getLogger(__name__)
wizard_router = Router()

class ConfigWizard(StatesGroup):
    """
    Класс состояний для FSM wizard (пошаговое редактирование конфигурации).
    Каждый state — отдельный шаг процесса.
    """
    min_price = State()
    max_price = State()
    min_supply = State()
    max_supply = State()
    count = State()
    limit = State()
    user_id = State()
    edit_min_price = State()
    edit_max_price = State()
    edit_min_supply = State()
    edit_max_supply = State()
    edit_count = State()
    edit_limit = State()
    edit_user_id = State()
    deposit_amount = State()
    refund_id = State()
    guest_deposit_amount = State()
    guest_refund_id = State()


async def profiles_menu(message: Message, user_id: int):
    """
    Показывает пользователю главное меню управления профилями.
    Отображает список всех созданных профилей и предоставляет кнопки для их редактирования, удаления или добавления нового профиля.
    """
    config = await get_valid_config(user_id)
    profiles = config.get("PROFILES", [])

    # Формируем клавиатуру профилей
    keyboard = []
    for idx, profile in enumerate(profiles):
        btns = [
            InlineKeyboardButton(
                text=f"✏️ Профиль {idx+1}", callback_data=f"profile_edit_{idx}"
            ),
            InlineKeyboardButton(
                text="🗑 Удалить", callback_data=f"profile_delete_{idx}"
            ),
        ]
        keyboard.append(btns)
    # Кнопка добавления (максимум 3 профиля)
    if len(profiles) < MAX_PROFILES:
        keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data="profile_add")])
    # Кнопка назад
    keyboard.append([InlineKeyboardButton(text="☰ Вернуться в меню", callback_data="profiles_main_menu")])

    profiles = config.get("PROFILES", [])

    lines = []
    for idx, profile in enumerate(profiles, 1):
        target_display = get_target_display(profile, user_id)
        if idx == 1 and len(profiles) == 1: line = (f"🔘 <b>Профиль {idx}</b> – {target_display}")
        elif idx == 1: line = (f"┌🔘 <b>Профиль {idx}</b> – {target_display}")
        elif len(profiles) == idx: line = (f"└🔘 <b>Профиль {idx}</b> – {target_display}")
        else: line = (f"├🔘 <b>Профиль {idx}</b> – {target_display}")
        lines.append(line)
    text_profiles = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer(f"📝 <b>Управление профилями (максимум 3):</b>\n\n{text_profiles}", reply_markup=kb)


@wizard_router.callback_query(F.data == "profiles_menu")
async def on_profiles_menu(call: CallbackQuery):
    """
    Обрабатывает нажатие на кнопку "Профили" или переход к списку профилей.
    Открывает меню со всеми профилями пользователя и возможностью их выбора для редактирования или удаления.
    """
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


def profile_text(profile, idx, user_id):
    """
    Формирует текстовое описание параметров профиля по его данным.
    Включает цены, лимиты, supply, получателя и другую основную информацию по выбранному профилю.
    Используется для вывода информации при редактировании профиля.
    """
    target_display = get_target_display(profile, user_id)
    return (f"✏️ <b>Изменение профиля {idx+1}</b>:\n\n"
            f"┌💰 <b>Цена</b>: {profile.get('MIN_PRICE'):,} – {profile.get('MAX_PRICE'):,} ★\n"
            f"├📦 <b>Саплай</b>: {profile.get('MIN_SUPPLY'):,} – {profile.get('MAX_SUPPLY'):,}\n"
            f"├🎁 <b>Куплено</b>: {profile.get('BOUGHT'):,} / {profile.get('COUNT'):,}\n"
            f"├⭐️ <b>Лимит</b>: {profile.get('SPENT'):,} / {profile.get('LIMIT'):,} ★\n"
            f"└👤 <b>Получатель</b>: {target_display}")


def profile_edit_keyboard(idx):
    """
    Создаёт инлайн-клавиатуру для быстрого редактирования параметров выбранного профиля.
    Каждая кнопка отвечает за редактирование отдельного поля (цены, supply, лимита и т.д.).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Цена", callback_data=f"edit_profile_price_{idx}"),
                InlineKeyboardButton(text="📦 Саплай", callback_data=f"edit_profile_supply_{idx}"),
            ],
            [
                InlineKeyboardButton(text="🎁 Количество", callback_data=f"edit_profile_count_{idx}"),
                InlineKeyboardButton(text="⭐️ Лимит", callback_data=f"edit_profile_limit_{idx}")
            ],
            [
                InlineKeyboardButton(text="👤 Получатель", callback_data=f"edit_profile_target_{idx}"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit_profiles_menu_{idx}")
            ]
        ]
    )


@wizard_router.callback_query(lambda c: c.data.startswith("profile_edit_"))
async def on_profile_edit(call: CallbackQuery, state: FSMContext):
    """
    Открывает экран подробного редактирования конкретного профиля.
    Показывает все параметры профиля и инлайн-кнопки для выбора нужного параметра для изменения.
    """
    idx = int(call.data.split("_")[-1])
    config = await get_valid_config(call.from_user.id)
    profile = config["PROFILES"][idx]
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    await call.message.edit_text(
        profile_text(profile, idx, call.from_user.id),
        reply_markup=profile_edit_keyboard(idx)
    )
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_price_"))
async def edit_profile_min_price(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения минимальной цены в профиле.
    Переводит пользователя в состояние ввода новой минимальной цены.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    await call.message.answer(f"✏️ <b>Редактирование профиля {idx + 1}:</b>\n\n💰 Минимальная цена подарка, например: <code>5000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.edit_min_price)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_supply_"))
async def edit_profile_min_supply(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения минимального supply для профиля.
    Переводит пользователя в состояние ввода нового минимального значения supply.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    await call.message.answer(f"✏️ <b>Редактирование профиля {idx + 1}:</b>\n\n📦 Минимальный саплай подарка, например: <code>1000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.edit_min_supply)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_limit_"))
async def edit_profile_limit(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения лимита по звёздам (максимальной суммы расходов) для профиля.
    Переводит пользователя в состояние ввода нового лимита.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    await call.message.answer(
            f"✏️ <b>Редактирование профиля {idx + 1}:</b>\n\n"
            "⭐️ Введите лимит звёзд для этого профиля (например: <code>10000</code>)\n\n"
            "/cancel — отменить"
        )
    await state.set_state(ConfigWizard.edit_limit)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_count_"))
async def edit_profile_count(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения количества подарков в профиле.
    Переводит пользователя в состояние ввода нового количества.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    await call.message.answer(f"✏️ <b>Редактирование профиля {idx + 1}:</b>\n\n🎁 Максимальное количество подарков, например: <code>5</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.edit_count)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_target_"))
async def edit_profile_target(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения получателя подарков (user_id или @username).
    Переводит пользователя в состояние ввода нового получателя.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    await call.message.answer(
            f"✏️ <b>Редактирование профиля {idx + 1}:</b>\n\n"
            "👤 Введите адрес получателя:\n\n"
            f"• <b>ID пользователя</b> (например ваш: <code>{call.from_user.id}</code>)\n"
            "• Или <b>username канала</b> (например: <code>@channel</code>)\n\n"
            "❗️ Узнать ID пользователя тут @userinfobot\n\n"
            "/cancel — отменить"
        )
    await state.set_state(ConfigWizard.edit_user_id)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profiles_menu_"))
async def edit_profiles_menu(call: CallbackQuery):
    """
    Обрабатывает возврат из режима редактирования профиля в основное меню профилей.
    Открывает пользователю общий список всех профилей.
    """
    idx = int(call.data.split("_")[-1])
    await safe_edit_text(call.message, f"✅ Редактирование <b>профиля {idx + 1}</b> завершено.", reply_markup=None)
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


@wizard_router.message(ConfigWizard.edit_min_price)
async def step_edit_min_price(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения минимальной цены для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_PRICE=value)
        await message.answer(f"✏️ <b>Редактирование профиля {idx + 1}:</b>\n\n💰 Максимальная цена подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.edit_max_price)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.edit_max_price)
async def step_edit_max_price(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения максимальной цены для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_price = data.get("MIN_PRICE")
        if min_price and value < min_price:
            await message.answer("🚫 Максимальная цена не может быть меньше минимальной. Попробуйте ещё раз.")
            return

        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["MIN_PRICE"] = data["MIN_PRICE"]
        config["PROFILES"][idx]["MAX_PRICE"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.edit_min_supply)
async def step_edit_min_supply(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения минимального supply для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_SUPPLY=value)
        await message.answer(f"✏️ <b>Редактирование профиля {idx + 1}:</b>\n\n📦 Максимальный саплай подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.edit_max_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.edit_max_supply)
async def step_edit_max_supply(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения максимального supply для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_supply = data.get("MIN_SUPPLY")
        if min_supply and value < min_supply:
            await message.answer("🚫 Максимальный саплай не может быть меньше минимального. Попробуйте ещё раз.")
            return
        
        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["MIN_SUPPLY"] = data["MIN_SUPPLY"]
        config["PROFILES"][idx]["MAX_SUPPLY"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.edit_limit)
async def step_edit_limit(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения лимита (максимальной суммы расходов) для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return

    data = await state.get_data()
    idx = data["profile_index"]

    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        
        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["LIMIT"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.edit_count)
async def step_edit_count(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового количества подарков для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    data = await state.get_data()
    idx = data["profile_index"]

    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        
        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["COUNT"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.edit_user_id)
async def step_edit_user_id(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового получателя (user_id или @username) для профиля.
    Проверяет корректность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    data = await state.get_data()
    idx = data["profile_index"]

    user_input = message.text.strip()
    if user_input.startswith("@"):
        chat_type = await get_chat_type(bot=message.bot, username=user_input)
        if chat_type == "channel":
            target_chat = user_input
            target_user = None
        else:
            await message.answer("🚫 Вы указали неправильный <b>username канала</b>. Попробуйте ещё раз.")
            return
    elif user_input.isdigit():
        target_chat = None
        target_user = int(user_input)
    else:
        await message.answer("🚫 Введите ID или @username канала. Попробуйте ещё раз.")
        return
    
    config = await get_valid_config(message.from_user.id)
    config["PROFILES"][idx]["TARGET_USER_ID"] = target_user
    config["PROFILES"][idx]["TARGET_CHAT_ID"] = target_chat
    await save_config(config)

    try:
        await message.bot.delete_message(message.chat.id, data["message_id"])
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
    await state.clear()


@wizard_router.callback_query(F.data == "profile_add")
async def on_profile_add(call: CallbackQuery, state: FSMContext):
    """
    Запускает мастер пошагового создания нового профиля подарков.
    Переводит пользователя к первому этапу ввода параметров нового профиля.
    """
    await state.update_data(profile_index=None)
    await call.message.answer("➕ Добавление <b>нового профиля</b>.\n\n"
                              "💰 Минимальная цена подарка, например: <code>5000</code>\n\n"
                              "/cancel — отменить", reply_markup=None)
    await state.set_state(ConfigWizard.min_price)
    await call.answer()


@wizard_router.message(ConfigWizard.user_id)
async def step_user_id(message: Message, state: FSMContext):
    """
    Обрабатывает ввод адреса получателя (user ID или username) и сохраняет профиль.
    """
    if await try_cancel(message, state):
        return

    user_input = message.text.strip()
    if user_input.startswith("@"):
        chat_type = await get_chat_type(bot=message.bot, username=user_input)
        if chat_type == "channel":
            target_chat = user_input
            target_user = None
        else:
            await message.answer("🚫 Вы указали неправильный <b>username канала</b>. Попробуйте ещё раз.")
            return
    elif user_input.isdigit():
        target_chat = None
        target_user = int(user_input)
    else:
        await message.answer("🚫 Введите ID или @username канала. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    profile_data = {
        "MIN_PRICE": data["MIN_PRICE"],
        "MAX_PRICE": data["MAX_PRICE"],
        "MIN_SUPPLY": data["MIN_SUPPLY"],
        "MAX_SUPPLY": data["MAX_SUPPLY"],
        "LIMIT": data["LIMIT"],
        "COUNT": data["COUNT"],
        "TARGET_USER_ID": target_user,
        "TARGET_CHAT_ID": target_chat,
        "BOUGHT": 0,
        "SPENT": 0,
        "DONE": False,
    }

    config = await get_valid_config(message.from_user.id)
    profile_index = data.get("profile_index")

    if profile_index is None:
        await add_profile(config, profile_data)
        await message.answer("✅ <b>Новый профиль</b> создан.")
    else:
        await update_profile(config, profile_index, profile_data)
        await message.answer(f"✅ <b>Профиль {profile_index+1}</b> обновлён.")

    await state.clear()
    await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)


@wizard_router.callback_query(F.data == "profiles_main_menu")
async def start_callback(call: CallbackQuery, state: FSMContext):
    """
    Показывает главное меню по нажатию кнопки "Вернуться в меню".
    Очищает все состояния FSM для пользователя.
    """
    await state.clear()
    await call.answer()
    await safe_edit_text(call.message, "✅ Редактирование профилей завершено.", reply_markup=None)
    await refresh_balance(call.bot)
    await update_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        message_id=call.message.message_id
    )


@wizard_router.callback_query(lambda c: c.data.startswith("profile_delete_"))
async def on_profile_delete_confirm(call: CallbackQuery, state: FSMContext):
    """
    Запрашивает подтверждение удаления профиля.
    """
    idx = int(call.data.split("_")[-1])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_{idx}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_delete_{idx}"),
            ]
        ]
    )
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    target_display = get_target_display(profile, call.from_user.id)
    message = (f"┌🔘 <b>Профиль {idx+1}</b> (куплено {profile.get('BOUGHT'):,} из {profile.get('COUNT'):,})\n"
            f"├💰 <b>Цена</b>: {profile.get('MIN_PRICE'):,} – {profile.get('MAX_PRICE'):,} ★\n"
            f"├📦 <b>Саплай</b>: {profile.get('MIN_SUPPLY'):,} – {profile.get('MAX_SUPPLY'):,}\n"
            f"└👤 <b>Получатель</b>: {target_display}")
    await call.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить <b>профиль {idx+1}</b>?\n\n{message}",
        reply_markup=kb
    )
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("confirm_delete_"))
async def on_profile_delete_final(call: CallbackQuery):
    """
    Окончательно удаляет профиль после подтверждения.
    """
    idx = int(call.data.split("_")[-1])
    config = await get_valid_config(call.from_user.id)
    deafult_added = "\n➕ <b>Добавлен</b> стандартный профиль.\n🚦 Статус изменён на 🔴 (неактивен)." if len(config["PROFILES"]) == 1 else ""
    if len(config["PROFILES"]) == 1:
        config["ACTIVE"] = False
        await save_config(config)
    await remove_profile(config, idx, call.from_user.id)
    await call.message.edit_text(f"✅ <b>Профиль {idx+1}</b> удалён.{deafult_added}", reply_markup=None)
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("cancel_delete_"))
async def on_profile_delete_cancel(call: CallbackQuery):
    """
    Отмена удаления профиля.
    """
    idx = int(call.data.split("_")[-1])
    await call.message.edit_text(f"🚫 Удаление <b>профиля {idx + 1}</b> отменено.", reply_markup=None)
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


async def safe_edit_text(message, text, reply_markup=None):
    """
    Безопасно редактирует текст сообщения, игнорируя ошибки "нельзя редактировать" и "сообщение не найдено".
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message can't be edited" in str(e) or "message to edit not found" in str(e):
            # Просто игнорируем — сообщение устарело или удалено
            return False
        else:
            raise


@wizard_router.callback_query(F.data == "edit_config")
async def edit_config_handler(call: CallbackQuery, state: FSMContext):
    """
    Запуск мастера редактирования конфигурации.
    """
    await call.message.answer("💰 Минимальная цена подарка, например: <code>5000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.min_price)
    await call.answer()


@wizard_router.message(ConfigWizard.min_price)
async def step_min_price(message: Message, state: FSMContext):
    """
    Обработка ввода минимальной цены подарка.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_PRICE=value)
        await message.answer("💰 Максимальная цена подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.max_price)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.max_price)
async def step_max_price(message: Message, state: FSMContext):
    """
    Обработка ввода максимальной цены подарка и проверка корректности диапазона.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_price = data.get("MIN_PRICE")
        if min_price and value < min_price:
            await message.answer("🚫 Максимальная цена не может быть меньше минимальной. Попробуйте ещё раз.")
            return

        await state.update_data(MAX_PRICE=value)
        await message.answer("📦 Минимальный саплай подарка, например: <code>1000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.min_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.min_supply)
async def step_min_supply(message: Message, state: FSMContext):
    """
    Обработка ввода минимального саплая для подарка.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_SUPPLY=value)
        await message.answer("📦 Максимальный саплай подарка, например: <code>10000</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.max_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.max_supply)
async def step_max_supply(message: Message, state: FSMContext):
    """
    Обработка ввода максимального саплая для подарка, проверка диапазона.
    """
    if await try_cancel(message, state):
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_supply = data.get("MIN_SUPPLY")
        if min_supply and value < min_supply:
            await message.answer("🚫 Максимальный саплай не может быть меньше минимального. Попробуйте ещё раз.")
            return

        await state.update_data(MAX_SUPPLY=value)
        await message.answer("🎁 Максимальное количество подарков, например: <code>5</code>\n\n/cancel — отменить")
        await state.set_state(ConfigWizard.count)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.count)
async def step_count(message: Message, state: FSMContext):
    """
    Обработка ввода количества подарков.
    """
    if await try_cancel(message, state):
        return

    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(COUNT=value)
        await message.answer(
            "⭐️ Введите лимит звёзд для этого профиля (например: <code>10000</code>)\n\n"
            "/cancel — отменить"
        )
        await state.set_state(ConfigWizard.limit)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.message(ConfigWizard.limit)
async def step_limit(message: Message, state: FSMContext):
    """
    Обработка ввода лимита звёзд на ордер.
    """
    if await try_cancel(message, state):
        return

    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(LIMIT=value)
        await message.answer(
            "👤 Введите адрес получателя:\n\n"
            f"• <b>ID пользователя</b> (например ваш: <code>{message.from_user.id}</code>)\n"
            "• Или <b>username канала</b> (например: <code>@channel</code>)\n\n"
            "❗️ Узнать ID пользователя тут @userinfobot\n\n"
            "/cancel — отменить"
        )
        await state.set_state(ConfigWizard.user_id)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.")


@wizard_router.callback_query(F.data == "deposit_menu")
async def deposit_menu(call: CallbackQuery, state: FSMContext):
    """
    Переход к шагу пополнения баланса.
    """
    await call.message.answer("💰 Введите сумму для пополнения, например: <code>5000</code>\n\n/cancel — отменить")
    await state.set_state(ConfigWizard.deposit_amount)
    await call.answer()


@wizard_router.message(ConfigWizard.deposit_amount)
async def deposit_amount_input(message: Message, state: FSMContext):
    """
    Обработка суммы для пополнения и отправка счёта на оплату.
    """
    if await try_cancel(message, state):
        return

    try:
        amount = int(message.text)
        if amount < 1 or amount > 10000:
            raise ValueError
        prices = [LabeledPrice(label=CURRENCY, amount=amount)]
        await message.answer_invoice(
            title="Бот для подарков",
            description="Пополнение баланса",
            prices=prices,
            provider_token="",  # Укажи свой токен
            payload="stars_deposit",
            currency=CURRENCY,
            start_parameter="deposit",
            reply_markup=payment_keyboard(amount=amount),
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите число от 1 до 10000. Попробуйте ещё раз.")


@wizard_router.callback_query(F.data == "refund_menu")
async def refund_menu(call: CallbackQuery, state: FSMContext):
    """
    Переход к возврату звёзд (по ID транзакции).
    """
    await call.message.answer("🆔 Введите ID транзакции для возврата:\n\n/withdraw_all — вывести весь баланс\n/cancel — отменить")
    await state.set_state(ConfigWizard.refund_id)
    await call.answer()


@wizard_router.message(ConfigWizard.refund_id)
async def refund_input(message: Message, state: FSMContext):
    """
    Обработка возврата по ID транзакции. Также поддерживается команда /withdraw_all.
    """
    if message.text and message.text.strip().lower() == "/withdraw_all":
        await state.clear()
        await withdraw_all_handler(message)
        return
    
    if await try_cancel(message, state):
        return

    txn_id = message.text.strip()
    try:
        await message.bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=txn_id
        )
        await message.answer("✅ Возврат успешно выполнен.")
        balance = await refresh_balance(message.bot)
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
    except Exception as e:
        await message.answer(f"🚫 Ошибка при возврате:\n<code>{e}</code>")
    await state.clear()


@wizard_router.callback_query(F.data == "guest_deposit_menu")
async def guest_deposit_menu(call: CallbackQuery, state: FSMContext):
    """
    Переход к шагу пополнения баланса для гостей.
    """
    await call.message.answer("💰 Введите сумму для пополнения, например: <code>5000</code>")
    await state.set_state(ConfigWizard.guest_deposit_amount)
    await call.answer()


@wizard_router.message(ConfigWizard.guest_deposit_amount)
async def guest_deposit_amount_input(message: Message, state: FSMContext):
    """
    Обработка суммы для пополнения и отправка счёта на оплату для гостей.
    """
    if await try_cancel(message, state):
        return

    try:
        amount = int(message.text)
        if amount < 1 or amount > 10000:
            raise ValueError
        prices = [LabeledPrice(label=CURRENCY, amount=amount)]
        await message.answer_invoice(
            title="Бот для подарков",
            description="Пополнение баланса",
            prices=prices,
            provider_token="",  # Укажи свой токен
            payload="stars_deposit",
            currency=CURRENCY,
            start_parameter="deposit",
            reply_markup=payment_keyboard(amount=amount),
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите число от 1 до 10000. Попробуйте ещё раз.")


@wizard_router.callback_query(F.data == "guest_refund_menu")
async def guest_refund_menu(call: CallbackQuery, state: FSMContext):
    """
    Переход к возврату звёзд для гостей (по ID транзакции).
    """
    await call.message.answer("🆔 Введите ID транзакции для возврата:")
    await state.set_state(ConfigWizard.guest_refund_id)
    await call.answer()


@wizard_router.message(ConfigWizard.guest_refund_id)
async def guest_refund_input(message: Message, state: FSMContext):
    """
    Обработка возврата по ID транзакции для гостей.
    """
    if await try_cancel(message, state):
        return

    txn_id = message.text.strip()
    try:
        await message.bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=txn_id
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"🚫 Ошибка при возврате:\n<code>{e}</code>")


@wizard_router.message(Command("withdraw_all"))
async def withdraw_all_handler(message: Message):
    """
    Запрос подтверждения на вывод всех звёзд с баланса.
    """
    balance = await refresh_balance(message.bot)
    if balance == 0:
        await message.answer("⚠️ Не найдено звёзд для возврата.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="withdraw_all_confirm"),
                InlineKeyboardButton(text="❌ Нет", callback_data="withdraw_all_cancel"),
            ]
        ]
    )
    await message.answer(
        "⚠️ Вы уверены, что хотите вывести все звёзды?",
        reply_markup=keyboard,
    )


@wizard_router.callback_query(lambda c: c.data == "withdraw_all_confirm")
async def withdraw_all_confirmed(call: CallbackQuery):
    """
    Подтверждение и запуск процедуры возврата всех звёзд. Выводит отчёт пользователю.
    """
    await call.message.edit_text("⏳ Выполняется вывод звёзд...")  # можно тут добавить вывод/отчёт

    async def send_status(msg):
        await call.message.answer(msg)

    await call.answer()

    result = await refund_all_star_payments(
        bot=call.bot,
        user_id=call.from_user.id,
        username=call.from_user.username,
        message_func=send_status,
    )
    if result["count"] > 0:
        msg = f"✅ Возвращено: ★{result['refunded']}\n🔄 Транзакций: {result['count']}"
        if result["left"] > 0:
            msg += f"\n💰 Остаток звёзд: {result['left']}"
            dep = result.get("next_deposit")
            if dep:
                need = dep['amount'] - result['left']
                msg += (
                    f"\n➕ Пополните баланс ещё минимум на ★{need} (или суммарно до ★{dep['amount']})."
                )
        await call.message.answer(msg)
    else:
        await call.message.answer("🚫 Звёзд для возврата не найдено.")

    balance = await refresh_balance(call.bot)
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


@wizard_router.callback_query(lambda c: c.data == "withdraw_all_cancel")
async def withdraw_all_cancel(call: CallbackQuery):
    """
    Обработка отмены возврата всех звёзд.
    """
    await call.message.edit_text("🚫 Действие отменено.")
    await call.answer()
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


# ------------- Дополнительные функции ---------------------


async def try_cancel(message: Message, state: FSMContext) -> bool:
    """
    Проверка, ввёл ли пользователь /cancel, и отмена мастера, если да.
    """
    if message.text and message.text.strip().lower() == "/cancel":
        await state.clear()
        await message.answer("🚫 Действие отменено.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return True
    return False


async def get_chat_type(bot: Bot, username: str):
    """
    Определяет тип Telegram-объекта по username для каналов.
    """
    if not username.startswith("@"):
        username = "@" + username
    try:
        chat = await bot.get_chat(username)
        if chat.type == "private":
            if getattr(chat, "is_bot", False):
                return "bot"
            else:
                return "user"
        elif chat.type == "channel":
            return "channel"
        elif chat.type in ("group", "supergroup"):
            return "group"
        else:
            return chat.type  # на всякий случай
    except TelegramAPIError as e:
        return f"error: {e}"
    

def register_wizard_handlers(dp):
    """
    Регистрация wizard_router в диспетчере (Dispatcher).
    """
    dp.include_router(wizard_router)
