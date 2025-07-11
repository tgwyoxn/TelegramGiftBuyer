# --- Сторонние библиотеки ---
from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

# --- Внутренние модули ---
from services.config import get_valid_config, save_config, format_config_summary, get_target_display
from services.menu import update_menu, config_action_keyboard 
from services.balance import refresh_balance
from services.buy import buy_gift

def register_main_handlers(dp, bot, version):
    """
    Регистрирует основные хендлеры для главного меню, стартовых и управляющих команд.
    """

    @dp.message(CommandStart())
    async def command_status_handler(message: Message, state: FSMContext):
        """
        Обрабатывает команду /start — обновляет баланс и показывает главное меню.
        Очищает все состояния FSM для пользователя.
        """
        await state.clear()
        await refresh_balance(bot)
        await update_menu(bot=bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)


    @dp.callback_query(F.data == "main_menu")
    async def start_callback(call: CallbackQuery, state: FSMContext):
        """
        Показывает главное меню по нажатию кнопки "Вернуться в меню".
        Очищает все состояния FSM для пользователя.
        """
        await state.clear()
        await call.answer()
        config = await get_valid_config(call.from_user.id)
        await refresh_balance(call.bot)
        await update_menu(
            bot=call.bot,
            chat_id=call.message.chat.id,
            user_id=call.from_user.id,
            message_id=call.message.message_id
        )


    @dp.callback_query(F.data == "show_help")
    async def help_callback(call: CallbackQuery):
        """
        Показывает подробную справку по работе с ботом.
        """
        config = await get_valid_config(call.from_user.id)
        # По умолчанию первый профиль
        profile = config["PROFILES"][0]
        target_display = get_target_display(profile, call.from_user.id)
        bot_info = await call.bot.get_me()
        bot_username = bot_info.username
        help_text = (
            f"<b>🛠 Управление ботом <code>v{version}</code> :</b>\n\n"
            "<b>🟢 Включить / 🔴 Выключить</b> — запускает или останавливает покупки.\n"
            "<b>✏️ Изменить</b> — Добавление и удаление профилей с конфигурациями для покупки подарков.\n"
            "<b>♻️ Сбросить счётчик</b> — обнуляет количество уже купленных подарков для всех профилей, чтобы не создавать снова такие же профили.\n"
            "<b>💰 Пополнить</b> — депозит звёзд в бот.\n"
            "<b>↩️ Вывести</b> — возврат звёзд по ID транзакции или вывести все звёзды сразу по команде /withdraw_all.\n"
            "<b>🎏 Каталог подарков</b> — список доступных к покупке подарков в маркете.\n\n"
            "<b>📌 Подсказки:</b>\n\n"
            f"❗️ Если получатель подарка — другой пользователь, он должен зайти в этот бот <code>@{bot_username}</code> и нажать <code>/start</code>.\n"
            "❗️ Получатель подарка <b>аккаунт</b> — пишите <b>id</b> пользователя (узнать id можно тут @userinfobot).\n"
            "❗️ Получатель подарка <b>канал</b> — пишите <b>username</b> канала.\n"
            f"❗️ Чтобы пополнить баланс бота с любого аккаунта, зайдите в этот бот <code>@{bot_username}</code> и нажмите <code>/start</code>, чтобы вызвать меню пополнения.\n"
            "❗️ Как посмотреть <b>ID транзакции</b> для возврата звёзд?  Нажмите на сообщение об оплате в чате с ботом и там будет ID транзакции.\n"
            f"❗️ Хотите протестировать бот? Купите подарок 🧸 за ★15, получатель {target_display}.\n\n"
            "<b>🐸 Автор: @leozizu</b>\n"
            "<b>📢 Канал: @pepeksey</b>"
        )
        button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Тест? Купить 🧸 за ★15", callback_data="buy_test_gift")],
            [InlineKeyboardButton(text="☰ Вернуться в меню", callback_data="main_menu")]
        ])
        await call.answer()
        await call.message.answer(help_text, reply_markup=button)


    @dp.callback_query(F.data == "buy_test_gift")
    async def buy_test_gift(call: CallbackQuery):
        """
        Покупка тестового подарка для проверки работы бота.
        """
        gift_id = '5170233102089322756'
        config = await get_valid_config(call.from_user.id)
        # Используем первый профиль по умолчанию
        profile = config["PROFILES"][0]
        TARGET_USER_ID = profile["TARGET_USER_ID"]
        TARGET_CHAT_ID = profile["TARGET_CHAT_ID"]
        target_display = get_target_display(profile, call.from_user.id)

        success = await buy_gift(
            bot=call.bot,
            env_user_id=call.from_user.id,
            gift_id=gift_id,
            user_id=TARGET_USER_ID,
            chat_id=TARGET_CHAT_ID,
            gift_price=15,
            file_id=None
        )
        if not success:
            await call.answer()
            await call.message.answer("⚠️ Покупка подарка 🧸 за ★15 невозможна.\n💰 Пополните баланс.\n🚦 Статус изменён на 🔴 (неактивен).")
            await update_menu(bot=bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)
            return

        await call.answer()
        await call.message.answer(f"✅ Подарок 🧸 за ★15 куплен. Получатель: {target_display}.")
        await update_menu(bot=bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


    @dp.callback_query(F.data == "reset_bought")
    async def reset_bought_callback(call: CallbackQuery):
        """
        Сброс счетчиков купленных подарков и статусов выполнения по всем профилям.
        """
        config = await get_valid_config(call.from_user.id)
        # Сбросить счетчики во всех профилях
        for profile in config["PROFILES"]:
            profile["BOUGHT"] = 0
            profile["SPENT"] = 0
            profile["DONE"] = False
        config["ACTIVE"] = False
        await save_config(config)
        info = format_config_summary(config, call.from_user.id)
        try:
            await call.message.edit_text(
                info,
                reply_markup=config_action_keyboard(config["ACTIVE"])
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
        await call.answer("Счётчик покупок сброшен.")


    @dp.callback_query(F.data == "toggle_active")
    async def toggle_active_callback(call: CallbackQuery):
        """
        Переключение статуса работы бота: активен/неактивен.
        """
        config = await get_valid_config(call.from_user.id)
        config["ACTIVE"] = not config.get("ACTIVE", False)
        await save_config(config)
        info = format_config_summary(config, call.from_user.id)
        await call.message.edit_text(
            info,
            reply_markup=config_action_keyboard(config["ACTIVE"])
        )
        await call.answer("Статус обновлён")


    @dp.pre_checkout_query()
    async def pre_checkout_handler(pre_checkout_query):
        """
        Обработка предоплаты в Telegram Invoice.
        """
        await pre_checkout_query.answer(ok=True)


    @dp.message(F.successful_payment)
    async def process_successful_payment(message: Message):
        """
        Обработка успешного пополнения баланса через Telegram Invoice.
        """
        await message.answer(
            f'✅ Баланс успешно пополнен.',
            message_effect_id="5104841245755180586"
        )
        balance = await refresh_balance(bot)
        await update_menu(bot=bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
