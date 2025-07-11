# --- Стандартные библиотеки ---
from datetime import datetime, timezone

def now_str() -> str:
    """
    Возвращает строку с текущим временем в UTC в формате "дд.мм.гггг чч:мм:сс".

    :return: Строка времени в формате "%d.%m.%Y %H:%M:%S"
    """
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S")
