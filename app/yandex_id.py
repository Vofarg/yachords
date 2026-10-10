"""Вход через Яндекс ID: официальная кнопка «Войти с Яндексом».

Яндекс ID сообщает сайту только логин человека. Доступа к Яндекс.Музыке этот вход
не даёт: плейлисты подключаются отдельно.

Ключи приложения берутся из настроек YANDEX_ID_CLIENT_ID и YANDEX_ID_CLIENT_SECRET.
Приложение регистрируется на https://oauth.yandex.ru/client/new (инструкция в README).
"""

import logging
import os
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
TOKEN_URL = "https://oauth.yandex.ru/token"
INFO_URL = "https://login.yandex.ru/info"
TIMEOUT_SECONDS = 10
RETRIES = 2


class YandexIdError(Exception):
    """Яндекс ID не ответил или не подтвердил вход."""


def client_id() -> Optional[str]:
    """ClientID приложения из настроек или None."""
    return os.getenv("YANDEX_ID_CLIENT_ID", "").strip() or None


def client_secret() -> Optional[str]:
    """Client secret приложения из настроек или None."""
    return os.getenv("YANDEX_ID_CLIENT_SECRET", "").strip() or None


def configured() -> bool:
    """Заданы ли ключи приложения Яндекс ID. Без них сайт работает по старому паролю."""
    return bool(client_id() and client_secret())


def authorize_url(redirect_uri: str, state: str) -> str:
    """Адрес страницы Яндекса, где человек подтверждает вход на сайт."""
    query = {
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def _request(method: str, url: str, what: str, **kwargs) -> dict:
    """Запрос к Яндекс ID с таймаутом и повтором при сетевом сбое."""
    for attempt in range(RETRIES + 1):
        try:
            response = httpx.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
        except httpx.HTTPError as error:
            logger.warning("Яндекс ID не ответил на запрос «%s», попытка %d: %s", what, attempt + 1, error)
            if attempt == RETRIES:
                raise YandexIdError from error
            time.sleep(1)
            continue
        if response.status_code != 200:
            logger.warning("Яндекс ID отказал в запросе «%s»: код %s", what, response.status_code)
            raise YandexIdError
        try:
            return response.json()
        except ValueError as error:
            logger.warning("Яндекс ID прислал непонятный ответ на «%s»", what)
            raise YandexIdError from error
    raise YandexIdError


def login_by_code(code: str) -> str:
    """Меняет одноразовый код из адреса возврата на логин человека.

    Сначала код меняется на временный токен Яндекс ID, затем по токену узнаётся логин.
    Сам токен нигде не сохраняется.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id(),
        "client_secret": client_secret(),
    }
    token = _request("POST", TOKEN_URL, "токен входа", data=data).get("access_token")
    if not token:
        logger.warning("Яндекс ID не прислал токен входа")
        raise YandexIdError
    info = _request(
        "GET", INFO_URL, "логин", params={"format": "json"}, headers={"Authorization": f"OAuth {token}"}
    )
    login = info.get("login")
    if not login:
        logger.warning("Яндекс ID не прислал логин")
        raise YandexIdError
    return str(login)
