"""Простой пароль на вход, чтобы чужой человек по ссылке не увидел ваши плейлисты.

Пароль задаётся переменной APP_PASSWORD. Если её нет (например, при запуске
на своём компьютере), сайт открывается без пароля.
"""

import hashlib
import hmac
import os
from typing import Optional

COOKIE_NAME = "yachords_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 дней: на телефоне не придётся вводить пароль каждый раз


def password() -> Optional[str]:
    """Пароль из настроек или None, если вход без пароля."""
    value = os.getenv("APP_PASSWORD", "").strip()
    return value or None


def _session_value(secret: str) -> str:
    """Значение для cookie: отпечаток пароля, по которому нельзя восстановить сам пароль."""
    return hmac.new(secret.encode(), b"yachords-session", hashlib.sha256).hexdigest()


def is_logged_in(cookie: Optional[str]) -> bool:
    """Проверяет, вошёл ли посетитель. Без пароля в настройках вход всегда открыт."""
    secret = password()
    if secret is None:
        return True
    return cookie is not None and hmac.compare_digest(cookie, _session_value(secret))


def check_password(attempt: str) -> Optional[str]:
    """Сверяет введённый пароль. Возвращает значение cookie при успехе, иначе None."""
    secret = password()
    if secret is None or not hmac.compare_digest(attempt.encode(), secret.encode()):
        return None
    return _session_value(secret)
