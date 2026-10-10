"""Обёртка над неофициальной библиотекой yandex-music.

Здесь собрано всё общение с Яндекс.Музыкой: проверка токена, список плейлистов,
треки плейлиста и случайный трек. Остальной код сайта не знает, как устроена
библиотека, поэтому если она сломается, менять придётся только этот файл.
"""

import hashlib
import logging
import os
import random
import re
import threading
import time
from contextvars import ContextVar
from typing import Callable, Optional, TypeVar

from yandex_music import Client, Playlist, Track
from yandex_music.exceptions import NetworkError, UnauthorizedError, YandexMusicError

from app.models import LIKES_KIND, PlaylistDetails, PlaylistInfo, TrackInfo

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
RETRIES = 2
CACHE_SECONDS = 300
COVER_SIZE = "400x400"
TRACKS_BATCH = 200
# Страница Яндекс ID, где выдают новый токен (адрес публичный, ключей в нём нет).
TOKEN_URL = "https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d"
# Слова в названии или версии трека, по которым понятно, что в нём нет слов.
INSTRUMENTAL_RE = re.compile(
    r"\b(instrumental|instr|инструментал\w*|минусовка|karaoke|караоке|backing track)\b", re.IGNORECASE
)

T = TypeVar("T")


class TokenError(Exception):
    """Токен не задан, истёк или Яндекс его не принимает."""


class YandexUnavailableError(Exception):
    """Яндекс.Музыка не ответила даже после повторных попыток."""


class NotFound(Exception):
    """Плейлиста или трека с таким номером нет."""


class EmptyPlaylist(NotFound):
    """Плейлист есть, но в нём нет ни одного трека."""


# Токен того, кто сейчас открыл страницу. Пока он задаётся только через настройки
# (YANDEX_MUSIC_TOKEN), но позже у каждого друга будет свой, сохранённый при входе.
_current_token: ContextVar[Optional[str]] = ContextVar("yandex_token", default=None)
# Можно ли для текущего запроса брать токен из настроек (только владельцу сайта).
_settings_allowed: ContextVar[bool] = ContextVar("yandex_settings_allowed", default=True)

_clients: dict[str, Client] = {}
_clients_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def use_token(token: Optional[str], settings_allowed: bool = True) -> None:
    """Задаёт токен Яндекс.Музыки для текущего запроса.

    Все функции этого файла дальше работают от имени владельца этого токена.
    None означает «взять токен из настроек», но только если settings_allowed:
    друзьям токен владельца из настроек не достаётся никогда.
    """
    _current_token.set(token.strip() if token else None)
    _settings_allowed.set(settings_allowed)


def _token() -> str:
    """Токен текущего пользователя: заданный для запроса или (для владельца) из настроек."""
    token = _current_token.get()
    if not token and _settings_allowed.get():
        token = os.getenv("YANDEX_MUSIC_TOKEN", "").strip()
    if not token:
        logger.warning("Токен Яндекс.Музыки не задан")
        raise TokenError
    return token


def _user_key(token: str) -> str:
    """Короткий отпечаток токена: по нему разделяются данные разных людей.

    Сам токен в памяти как ключ не используется и в логи не попадает.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _call(action: Callable[[], T], what: str) -> T:
    """Выполняет запрос к Яндексу с повтором при сетевых сбоях.

    Неверный токен не повторяется: повтор тут не поможет.
    """
    for attempt in range(RETRIES + 1):
        try:
            return action()
        except UnauthorizedError as error:
            logger.warning("Яндекс отклонил токен при запросе «%s»: %s", what, error)
            raise TokenError from error
        except NetworkError as error:
            logger.warning("Сбой сети при запросе «%s», попытка %d: %s", what, attempt + 1, error)
            if attempt == RETRIES:
                raise YandexUnavailableError from error
            time.sleep(1)
        except YandexMusicError as error:
            logger.error("Ошибка Яндекс.Музыки при запросе «%s»: %s", what, error)
            raise YandexUnavailableError from error
    raise YandexUnavailableError


def _get_client() -> Client:
    """Возвращает подключённый клиент Яндекс.Музыки текущего пользователя.

    У каждого токена свой клиент, поэтому люди никогда не видят чужие плейлисты.
    """
    token = _token()
    key = _user_key(token)
    with _clients_lock:
        client = _clients.get(key)
        if client is not None:
            return client
        client = Client(token)
        if not _settings_uid(token):
            # Без UID библиотека сама узнаёт номер аккаунта по токену.
            _call(lambda: client.init(), "данные аккаунта")
        _clients[key] = client
        return client


def _settings_uid(token: str) -> Optional[int]:
    """UID из настроек, но только для токена из тех же настроек (то есть для владельца)."""
    uid = os.getenv("YANDEX_MUSIC_UID", "").strip()
    if uid and token == os.getenv("YANDEX_MUSIC_TOKEN", "").strip():
        return int(uid)
    return None


def _uid() -> int:
    """Номер аккаунта текущего пользователя: из настроек, а если его там нет, то по токену."""
    client = _get_client()
    return _settings_uid(_token()) or client.me.account.uid


def _cached(key: str, load: Callable[[], T]) -> T:
    """Держит ответ Яндекса в памяти несколько минут, чтобы страницы открывались быстрее.

    Ответы хранятся отдельно для каждого пользователя.
    """
    key = f"{_user_key(_token())}:{key}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]  # type: ignore[return-value]
    value = load()
    _cache[key] = (now, value)
    return value


def reset() -> None:
    """Забывает всех клиентов и сохранённые ответы, например после смены токена."""
    with _clients_lock:
        _clients.clear()
    _cache.clear()


def check_token() -> bool:
    """Проверяет, что токен из .env рабочий. Удобно запускать из командной строки."""
    try:
        client = _get_client()
        status = _call(lambda: client.account_status(timeout=TIMEOUT_SECONDS), "статус аккаунта")
        return bool(status and status.account and status.account.uid)
    except (TokenError, YandexUnavailableError):
        return False


def _format_duration(ms: Optional[int]) -> str:
    """Превращает длительность в миллисекундах в вид «4:07»."""
    if not ms:
        return ""
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def _cover(uri: Optional[str]) -> Optional[str]:
    """Собирает ссылку на обложку из шаблона Яндекса."""
    if not uri:
        return None
    return "https://" + uri.replace("%%", COVER_SIZE)


def _playlist_cover(playlist: Playlist) -> Optional[str]:
    """Обложка плейлиста: своя картинка или коллаж из обложек треков."""
    cover = playlist.cover
    if cover:
        if cover.uri:
            return _cover(cover.uri)
        if cover.items_uri:
            return _cover(cover.items_uri[0])
    return _cover(playlist.og_image)


def is_instrumental(title: Optional[str], version: Optional[str]) -> bool:
    """Похоже ли по названию и версии трека, что это инструментал (без слов)."""
    return bool(INSTRUMENTAL_RE.search(f"{title or ''} {version or ''}"))


def _track_info(track: Track) -> TrackInfo:
    """Переводит трек из формата библиотеки в формат сайта."""
    artists = ", ".join(a.name for a in track.artists if a.name) or "Неизвестный исполнитель"
    album_id = track.albums[0].id if track.albums else None
    track_id = f"{track.id}:{album_id}" if album_id else str(track.id)
    return TrackInfo(
        id=track_id,
        title=track.title or "Без названия",
        artists=artists,
        duration=_format_duration(track.duration_ms),
        cover_url=_cover(track.cover_uri),
        instrumental=is_instrumental(track.title, track.version),
    )


def _fetch_tracks(track_ids: list[str]) -> list[TrackInfo]:
    """Загружает полные данные треков пачками, чтобы не упереться в лимиты Яндекса."""
    client = _get_client()
    result: list[TrackInfo] = []
    for start in range(0, len(track_ids), TRACKS_BATCH):
        batch = track_ids[start:start + TRACKS_BATCH]
        tracks = _call(lambda: client.tracks(batch, timeout=TIMEOUT_SECONDS), "треки")
        result.extend(_track_info(t) for t in tracks if t.available is not False)
    return result


def _likes_ids() -> list[str]:
    """Номера треков из «Мне нравится» в том порядке, в каком их показывает Яндекс."""
    client = _get_client()
    likes = _call(lambda: client.users_likes_tracks(_uid(), timeout=TIMEOUT_SECONDS), "«Мне нравится»")
    if not likes:
        return []
    return [short.track_id for short in likes.tracks]


def get_playlists() -> list[PlaylistInfo]:
    """Список плейлистов для главной: первым идёт «Мне нравится», за ним остальные."""

    def load() -> list[PlaylistInfo]:
        client = _get_client()
        own = _call(lambda: client.users_playlists_list(_uid(), timeout=TIMEOUT_SECONDS), "список плейлистов")
        likes = PlaylistInfo(
            kind=LIKES_KIND,
            title="Мне нравится",
            track_count=len(_likes_ids()),
            is_likes=True,
        )
        others = [
            PlaylistInfo(
                kind=str(p.kind),
                title=p.title or "Без названия",
                track_count=p.track_count or 0,
                cover_url=_playlist_cover(p),
            )
            for p in own
        ]
        return [likes, *others]

    return _cached("playlists", load)


def get_playlist(kind: str) -> PlaylistDetails:
    """Плейлист со всеми треками. kind — номер плейлиста или слово likes."""

    def load() -> PlaylistDetails:
        info = next((p for p in get_playlists() if p.kind == kind), None)
        if info is None:
            raise NotFound
        if kind == LIKES_KIND:
            ids = _likes_ids()
        else:
            client = _get_client()
            playlist = _call(
                lambda: client.users_playlists(int(kind), _uid(), timeout=TIMEOUT_SECONDS), "треки плейлиста"
            )
            ids = [short.track_id for short in (playlist.tracks or [])] if playlist else []
        tracks = _fetch_tracks(ids)
        unavailable = max(len(ids) - len(tracks), 0)
        if unavailable:
            logger.info("В плейлисте %s недоступно треков: %d из %d", kind, unavailable, len(ids))
        return PlaylistDetails(playlist=info, tracks=tracks, unavailable=unavailable)

    return _cached(f"playlist:{kind}", load)


def random_track(kind: str) -> TrackInfo:
    """Случайный трек из плейлиста."""
    tracks = get_playlist(kind).tracks
    if not tracks:
        raise EmptyPlaylist
    return random.choice(tracks)


def get_track(track_id: str) -> TrackInfo:
    """Название, исполнитель и обложка одного трека."""
    tracks = _cached(f"track:{track_id}", lambda: _fetch_tracks([track_id]))
    if not tracks:
        raise NotFound
    return tracks[0]
