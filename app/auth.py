"""Кто зашёл на сайт.

Два режима:
- Вход через Яндекс ID (если заданы YANDEX_ID_CLIENT_ID и YANDEX_ID_CLIENT_SECRET).
  Пускаются только логины из ALLOWED_LOGINS и владелец OWNER_LOGIN.
- Старый общий пароль APP_PASSWORD, пока Яндекс ID не настроен.
  Если нет и пароля (например, при запуске на своём компьютере), сайт открыт без входа.
"""

import hashlib
import hmac
import os
import time
from typing import Optional

from app import yandex_id

COOKIE_NAME = "yachords_session"
STATE_COOKIE = "yachords_state"
COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 дней: на телефоне не придётся входить каждый раз
# Кем считается посетитель в режиме общего пароля: это всегда владелец.
OWNER = "владелец"


def password() -> Optional[str]:
    """Пароль из настроек или None, если вход без пароля."""
    value = os.getenv("APP_PASSWORD", "").strip()
    return value or None


def normalize_login(login: str) -> str:
    """Приводит логин Яндекса к единому виду.

    Яндекс считает точку и дефис в логине одним и тем же, а регистр не важен.
    Если вписали почту (anna@yandex.ru), берётся часть до @.
    """
    return login.strip().lower().split("@")[0].replace(".", "-")


def owner_login() -> Optional[str]:
    """Логин владельца: его плейлисты открываются по токену из настроек."""
    value = os.getenv("OWNER_LOGIN", "").strip()
    return normalize_login(value) if value else None


def allowed_logins() -> set[str]:
    """Логины, которых пускают на сайт: список ALLOWED_LOGINS и владелец."""
    raw = os.getenv("ALLOWED_LOGINS", "").replace(";", ",").replace(" ", ",")
    logins = {normalize_login(x) for x in raw.split(",") if x.strip()}
    owner = owner_login()
    if owner:
        logins.add(owner)
    return logins


def is_allowed(login: str) -> bool:
    """Есть ли логин в списке разрешённых."""
    return normalize_login(login) in allowed_logins()


def is_owner(login: str) -> bool:
    """Владелец ли это. В режиме пароля владелец — любой, кто знает пароль."""
    return login == OWNER or normalize_login(login) == owner_login()


def _sign(value: str, secret: str) -> str:
    """Подпись, по которой сайт узнаёт свою cookie и замечает подделку."""
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _password_session(secret: str) -> str:
    """Значение cookie для входа по паролю: отпечаток пароля, по которому нельзя восстановить сам пароль."""
    return hmac.new(secret.encode(), b"yachords-session", hashlib.sha256).hexdigest()


def make_session(login: str) -> str:
    """Значение cookie после входа через Яндекс ID: логин, срок и подпись."""
    expires = int(time.time()) + COOKIE_MAX_AGE
    value = f"{normalize_login(login)}:{expires}"
    return f"{value}:{_sign(value, yandex_id.client_secret() or '')}"


def current_login(cookie: Optional[str]) -> Optional[str]:
    """Логин вошедшего человека или None, если он не вошёл (или его убрали из списка)."""
    if yandex_id.configured():
        if not cookie or cookie.count(":") != 2:
            return None
        login, expires, signature = cookie.split(":")
        expected = _sign(f"{login}:{expires}", yandex_id.client_secret() or "")
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return None
        if not expires.isdigit() or int(expires) < time.time():
            return None
        return login if is_allowed(login) else None
    secret = password()
    if secret is None:
        return OWNER
    if cookie is not None and hmac.compare_digest(cookie.encode(), _password_session(secret).encode()):
        return OWNER
    return None


def login_required() -> bool:
    """Нужен ли вообще вход: да, если настроен Яндекс ID или задан пароль."""
    return yandex_id.configured() or password() is not None


def check_password(attempt: str) -> Optional[str]:
    """Сверяет введённый пароль. Возвращает значение cookie при успехе, иначе None."""
    secret = password()
    if secret is None or not hmac.compare_digest(attempt.encode(), secret.encode()):
        return None
    return _password_session(secret)
