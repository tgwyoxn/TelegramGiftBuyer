# --- Стандартные библиотеки ---
import json
import os
import logging
from typing import Optional

# --- Сторонние библиотеки ---
import aiofiles

logger = logging.getLogger(__name__)

CURRENCY = 'XTR'
VERSION = '1.2.0'
CONFIG_PATH = "config.json"
DEV_MODE = False # Покупка тестовых подарков
MAX_PROFILES = 3 # Максимальная длина сообщения 4096 символов
PURCHASE_COOLDOWN = 0.3 # Количество покупок в секунду

def DEFAULT_PROFILE(user_id: int) -> dict:
    """Создаёт профиль с дефолтными настройками для указанного пользователя."""
    return {
        "MIN_PRICE": 5000,
        "MAX_PRICE": 10000,
        "MIN_SUPPLY": 1000,
        "MAX_SUPPLY": 10000,
        "LIMIT": 1000000,
        "COUNT": 5,
        "TARGET_USER_ID": user_id,
        "TARGET_CHAT_ID": None,
        "BOUGHT": 0,
        "SPENT": 0,
        "DONE": False
    }

def DEFAULT_CONFIG(user_id: int) -> dict:
    """Дефолтная конфигурация: глобальные поля + список профилей."""
    return {
        "BALANCE": 0,
        "ACTIVE": False,
        "LAST_MENU_MESSAGE_ID": None,
        "PROFILES": [DEFAULT_PROFILE(user_id)]
    }

# Типы и требования для каждого поля профиля
PROFILE_TYPES = {
    "MIN_PRICE": (int, False),
    "MAX_PRICE": (int, False),
    "MIN_SUPPLY": (int, False),
    "MAX_SUPPLY": (int, False),
    "LIMIT": (int, False),
    "COUNT": (int, False),
    "TARGET_USER_ID": (int, True),
    "TARGET_CHAT_ID": (str, True),
    "BOUGHT": (int, False),
    "SPENT": (int, False),
    "DONE": (bool, False),
}

# Типы и требования для глобальных полей
CONFIG_TYPES = {
    "BALANCE": (int, False),
    "ACTIVE": (bool, False),
    "LAST_MENU_MESSAGE_ID": (int, True),
    "PROFILES": (list, False),  # список профилей
}


def is_valid_type(value, expected_type, allow_none=False):
    """
    Проверяет тип значения с учётом допуска None.
    """
    if value is None:
        return allow_none
    return isinstance(value, expected_type)


async def ensure_config(user_id: int, path: str = CONFIG_PATH):
    """
    Гарантирует существование config.json.
    """
    if not os.path.exists(path):
        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(DEFAULT_CONFIG(user_id), indent=2))
        logger.info(f"Создана конфигурация: {path}")


async def load_config(path: str = CONFIG_PATH) -> dict:
    """
    Загружает конфиг из файла (без валидации). Гарантирует, что файл существует.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл {path} не найден. Используйте ensure_config.")
    async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
        data = await f.read()
        return json.loads(data)


async def save_config(config: dict, path: str = CONFIG_PATH):
    """
    Сохраняет конфиг в файл.
    """
    async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
        await f.write(json.dumps(config, indent=2))
    logger.info(f"Конфигурация сохранена.")


async def validate_profile(profile: dict, user_id: Optional[int] = None) -> dict:
    """
    Валидирует один профиль.
    """
    valid = {}
    default = DEFAULT_PROFILE(user_id or 0)
    for key, (expected_type, allow_none) in PROFILE_TYPES.items():
        if key not in profile or not is_valid_type(profile[key], expected_type, allow_none):
            valid[key] = default[key]
        else:
            valid[key] = profile[key]
    return valid


async def validate_config(config: dict, user_id: int) -> dict:
    """
    Валидирует глобальный конфиг и все профили.
    """
    valid = {}
    default = DEFAULT_CONFIG(user_id)
    # Верхний уровень
    for key, (expected_type, allow_none) in CONFIG_TYPES.items():
        if key == "PROFILES":
            profiles = config.get("PROFILES", [])
            # Валидация профилей
            valid_profiles = []
            for profile in profiles:
                valid_profiles.append(await validate_profile(profile, user_id))
            if not valid_profiles:
                valid_profiles = [DEFAULT_PROFILE(user_id)]
            valid["PROFILES"] = valid_profiles
        else:
            if key not in config or not is_valid_type(config[key], expected_type, allow_none):
                valid[key] = default[key]
            else:
                valid[key] = config[key]
    return valid


async def get_valid_config(user_id: int, path: str = CONFIG_PATH) -> dict:
    """
    Загружает, валидирует и при необходимости обновляет config.json.
    """
    await ensure_config(user_id, path)
    config = await load_config(path)
    validated = await validate_config(config, user_id)
    # Если валидированная версия отличается, сохранить
    if validated != config:
        await save_config(validated, path)
    return validated


async def migrate_config_if_needed(user_id: int, path: str = CONFIG_PATH):
    """
    Проверяет и преобразует config.json из старого формата (без PROFILES)
    в новый (список профилей). Работает асинхронно.
    """
    if not os.path.exists(path):
        return

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = await f.read()
            config = json.loads(data)
    except Exception:
        logger.error(f"Конфиг {path} повреждён.")
        os.remove(path)
        logger.error(f"Повреждённый конфиг {path} удалён.")
        return

    # Если уже новый формат, ничего не делаем
    if "PROFILES" in config:
        return

    # Формируем профиль из старых ключей
    profile_keys = [
        "MIN_PRICE", "MAX_PRICE", "MIN_SUPPLY", "MAX_SUPPLY",
        "COUNT", "LIMIT", "TARGET_USER_ID", "TARGET_CHAT_ID",
        "BOUGHT", "SPENT", "DONE"
    ]
    profile = {}
    for key in profile_keys:
        if key in config:
            profile[key] = config[key]

    profile.setdefault("LIMIT", 1000000)
    profile.setdefault("SPENT", 0)
    profile.setdefault("BOUGHT", 0)
    profile.setdefault("DONE", False)
    profile.setdefault("COUNT", 5)

    # Собираем новый формат
    new_config = {
        "BALANCE": config.get("BALANCE", 0),
        "ACTIVE": config.get("ACTIVE", False),
        "LAST_MENU_MESSAGE_ID": config.get("LAST_MENU_MESSAGE_ID"),
        "PROFILES": [profile],
    }

    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(new_config, ensure_ascii=False, indent=2))
    logger.info(f"Конфиг {path} мигрирован в новый формат.")


# ------------- Работа с профилями -----------------


async def get_profile(config: dict, index: int = 0) -> dict:
    """
    Получить профиль по индексу (по умолчанию первый).
    """
    profiles = config.get("PROFILES", [])
    if not profiles:
        raise ValueError("Нет профилей в конфиге")
    return profiles[index]


async def add_profile(config: dict, profile: dict, save: bool = True) -> dict:
    """
    Добавляет новый профиль в конфиг.
    """
    config.setdefault("PROFILES", []).append(profile)
    if save:
        await save_config(config)
    return config


async def update_profile(config: dict, index: int, new_profile: dict, save: bool = True) -> dict:
    """
    Обновляет профиль по индексу.
    """
    if "PROFILES" not in config or index >= len(config["PROFILES"]):
        raise IndexError("Профиль не найден")
    config["PROFILES"][index] = new_profile
    if save:
        await save_config(config)
    return config


async def remove_profile(config: dict, index: int, user_id: int, save: bool = True) -> dict:
    """
    Удаляет профиль по индексу.
    """
    if "PROFILES" not in config or index >= len(config["PROFILES"]):
        raise IndexError("Профиль не найден")
    config["PROFILES"].pop(index)
    if not config["PROFILES"]:
        # Добавить дефолтный если удалили все
        config["PROFILES"].append(DEFAULT_PROFILE(user_id))
    if save:
        await save_config(config)
    return config


# ------------- Форматирование ---------------------


def format_config_summary(config: dict, user_id: int) -> str:
    """
    Формирует текст для главного меню: статус, баланс, и список всех профилей (каждый с кратким описанием).
    :param config: Вся конфигурация (словарь)
    :param user_id: ID пользователя для отображения "Вы"
    :return: Готовый HTML-текст для меню
    """
    status_text = "🟢 Активен" if config.get("ACTIVE") else "🔴 Неактивен"
    balance = config.get("BALANCE", 0)
    profiles = config.get("PROFILES", [])

    lines = [f"🚦 <b>Статус:</b> {status_text}"]
    for idx, profile in enumerate(profiles, 1):
        target_display = get_target_display(profile, user_id)
        state_profile = (
            " ✅ <b>(завершён)</b>" if profile.get('DONE')
            else " ⚠️ <b>(частично)</b>" if profile.get('SPENT', 0) > 0
            else ""
        )
        line = (
            "\n"
            f"┌🔘 <b>Профиль {idx}</b>{state_profile}\n"
            f"├💰 <b>Цена</b>: {profile.get('MIN_PRICE'):,} – {profile.get('MAX_PRICE'):,} ★\n"
            f"├📦 <b>Саплай</b>: {profile.get('MIN_SUPPLY'):,} – {profile.get('MAX_SUPPLY'):,}\n"
            f"├🎁 <b>Куплено</b>: {profile.get('BOUGHT'):,} / {profile.get('COUNT'):,}\n"
            f"├⭐️ <b>Лимит</b>: {profile.get('SPENT'):,} / {profile.get('LIMIT'):,} ★\n"
            f"└👤 <b>Получатель</b>: {target_display}"
        )
        lines.append(line)

    lines.append(f"\n💰 <b>Баланс</b>: {balance:,} ★")
    return "\n".join(lines)


def get_target_display(profile: dict, user_id: int) -> str:
    """
    Возвращает строковое описание получателя подарка для профиля.
    :param profile: словарь профиля
    :param user_id: id текущего пользователя
    :return: строка для меню
    """
    target_chat_id = profile.get("TARGET_CHAT_ID")
    target_user_id = profile.get("TARGET_USER_ID")
    if target_chat_id:
        return f"{target_chat_id} (Канал)"
    elif str(target_user_id) == str(user_id):
        return f"<code>{target_user_id}</code> (Вы)"
    else:
        return f"<code>{target_user_id}</code>"
    

def get_target_display_local(target_user_id: int, target_chat_id: str, user_id: int) -> str:
    """Возвращает строковое описание получателя подарка на основе выбранного получателя и user_id."""
    if target_chat_id:
        return f"{target_chat_id} (Канал)"
    elif str(target_user_id) == str(user_id):
        return f"<code>{target_user_id}</code> (Вы)"
    else:
        return f"<code>{target_user_id}</code>"
