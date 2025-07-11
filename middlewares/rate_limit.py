# --- Стандартные библиотеки ---
import time
import logging

# --- Сторонние библиотеки ---
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, commands_limits: dict = None, allowed_user_ids: list[int] = None):
        self.last_times = {}  # user_id -> {command: timestamp}
        self.commands_limits = commands_limits or {}  # command: seconds
        self.allowed_user_ids = allowed_user_ids or []

    async def __call__(self, handler, event: TelegramObject, data: dict):
        message = data.get("message") or data.get("event_message") or event
        if not isinstance(message, Message):
            return await handler(event, data)

        user_id = message.from_user.id
        if user_id in self.allowed_user_ids:
            return await handler(event, data)
        text = message.text
        now = time.monotonic()

        if text:
            for cmd, limit in self.commands_limits.items():
                if text.split()[0] == cmd:  # Только команда без аргументов/или с ними
                    user_times = self.last_times.setdefault(user_id, {})
                    last = user_times.get(cmd, 0)
                    if now - last < limit:
                        await message.answer("⏳ Не спамьте, пожалуйста. Попробуйте чуть позже.")
                        return  # игнорируем спам
                    user_times[cmd] = now
        return await handler(event, data)