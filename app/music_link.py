"""Подключённая Яндекс.Музыка каждого человека.

Токен Музыки хранится не на сервере, а в браузере самого человека: в cookie,
зашифрованной ключом сайта. Без ключа (он есть только в настройках Render) прочитать
токен из cookie нельзя. Кроме того, cookie привязана к логину Яндекс ID: чужой человек
с этой cookie ничего не откроет.
"""

import base64
import hashlib
import io
import logging
import os
import re
from typing import Optional

import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken

from app import yandex_id

logger = logging.getLogger(__name__)

COOKIE_NAME = "yachords_music"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # год: токен Яндекса живёт примерно столько же
TRANSFER_SECONDS = 15 * 60  # ссылка для телефона действует 15 минут
TOKEN_IN_TEXT_RE = re.compile(r"access_token=([^&\s#]+)")
BARE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-.]{20,}$")


def _fernet() -> Optional[Fernet]:
    """Шифровальщик с ключом сайта или None, если ключа нет.

    Ключ берётся из MUSIC_COOKIE_KEY, а если его нет, выводится из секрета Яндекс ID,
    чтобы владельцу не пришлось заводить ещё одну настройку.
    """
    secret = os.getenv("MUSIC_COOKIE_KEY", "").strip() or yandex_id.client_secret()
    if not secret:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(f"yachords-music:{secret}".encode()).digest())
    return Fernet(key)


def extract_token(text: str) -> Optional[str]:
    """Достаёт токен из того, что вставил человек.

    Подходит и весь адрес из адресной строки (…#access_token=y0_…&token_type=…),
    и сам токен отдельно.
    """
    text = (text or "").strip()
    found = TOKEN_IN_TEXT_RE.search(text)
    if found:
        return found.group(1)
    if BARE_TOKEN_RE.match(text):
        return text
    return None


def seal(login: str, token: str) -> Optional[str]:
    """Шифрует токен вместе с логином. None, если на сайте нет ключа."""
    fernet = _fernet()
    if fernet is None:
        logger.warning("Нет ключа для шифрования токенов: не задан YANDEX_ID_CLIENT_SECRET")
        return None
    return fernet.encrypt(f"{login}\n{token}".encode()).decode()


def unseal(login: str, value: Optional[str], max_age: Optional[int] = None) -> Optional[str]:
    """Расшифровывает токен, если cookie (или ссылка) принадлежит именно этому логину."""
    fernet = _fernet()
    if not value or fernet is None:
        return None
    try:
        plain = fernet.decrypt(value.encode(), ttl=max_age).decode()
    except (InvalidToken, ValueError):
        logger.info("Не удалось расшифровать подключение Музыки: устарело или подделано")
        return None
    owner, _, token = plain.partition("\n")
    if owner != login or not token:
        return None
    return token


def qr_svg(url: str) -> str:
    """QR-код ссылки в виде картинки SVG, чтобы открыть её камерой телефона."""
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode()
