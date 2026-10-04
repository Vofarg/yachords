"""Поиск аккордов по сайтам в порядке приоритета: AmDm → MyChords → Ultimate-Guitar.

Первый сайт, где нашлись аккорды, и даёт результат. Если сайт не отвечает
или закрыт защитой от роботов (так бывает у Ultimate-Guitar), молча
переходим к следующему. HTML сайтов нигде не сохраняется.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

from app.chords import parser
from app.chords.normalize import ChordSheet, clean_title

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
RETRIES = 2
TOTAL_BUDGET_SECONDS = 40
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.6,en;q=0.5",
}


class Blocked(Exception):
    """Сайт не пустил: защита от роботов, ошибка сервера или нет связи."""


@dataclass
class Source:
    """Сайт с аккордами: как искать и как разбирать его страницы."""

    name: str
    search_url: str
    search_params: Callable[[str], dict]
    pick: Callable[[str, str, str], Optional[str]]
    parse: Callable[[str, str], Optional[ChordSheet]]


SOURCES = [
    Source("AmDm.ru", parser.AMDM_SEARCH, lambda q: {"q": q}, parser.amdm_pick, parser.amdm_parse),
    Source("MyChords.net", parser.MYCHORDS_SEARCH, lambda q: {"q": q}, parser.mychords_pick, parser.mychords_parse),
    Source(
        "Ultimate-Guitar.com",
        parser.UG_SEARCH,
        lambda q: {"search_type": "title", "value": q},
        parser.ug_pick,
        parser.ug_parse,
    ),
]


@dataclass
class SearchResult:
    """Итог поиска: аккорды (или None) и что случилось на каждом сайте."""

    sheet: Optional[ChordSheet] = None
    checked: list[tuple[str, str]] = field(default_factory=list)

    @property
    def all_failed(self) -> bool:
        """Ни один сайт не ответил нормально (а не просто «песни нет»)."""
        return bool(self.checked) and all(status != "нет этой песни" for _, status in self.checked)


def _is_blocked(response: httpx.Response) -> bool:
    """Похоже ли, что вместо страницы пришла заглушка защиты от роботов."""
    if response.status_code in (403, 429, 503) or response.headers.get("cf-mitigated"):
        return True
    return "Just a moment..." in response.text[:2000]


def fetch(client: httpx.Client, url: str, params: Optional[dict] = None) -> str:
    """Загружает страницу с повтором при сбоях сети. Защиту от роботов не повторяет."""
    for attempt in range(RETRIES + 1):
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError as error:
            logger.warning("Не удалось открыть %s (попытка %d): %s", url, attempt + 1, error)
            if attempt == RETRIES:
                raise Blocked("сайт не ответил") from error
            time.sleep(1)
            continue
        if _is_blocked(response):
            logger.info("Сайт %s не пустил (код %s)", url, response.status_code)
            raise Blocked(f"сайт не пустил (код {response.status_code})")
        if response.status_code >= 500 and attempt < RETRIES:
            logger.warning("Сайт %s ответил ошибкой %s, повторяю", url, response.status_code)
            time.sleep(1)
            continue
        if response.status_code >= 400:
            raise Blocked(f"ошибка сайта (код {response.status_code})")
        return response.text
    raise Blocked("сайт не ответил")


def _try_source(client: httpx.Client, source: Source, artist: str, title: str) -> Optional[ChordSheet]:
    """Ищет песню на одном сайте и возвращает аккорды, если нашлись."""
    queries = [f"{artist} {title}", title] if artist else [title]
    for query in queries:
        page = fetch(client, source.search_url, source.search_params(query))
        url = source.pick(page, artist, title)
        if url:
            return source.parse(fetch(client, url), url)
    return None


def find_chords(artist: str, title: str) -> SearchResult:
    """Ищет аккорды песни по всем сайтам по очереди."""
    artist = clean_title(artist.split(",")[0])
    title = clean_title(title)
    result = SearchResult()
    started = time.monotonic()
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        for source in SOURCES:
            if time.monotonic() - started > TOTAL_BUDGET_SECONDS:
                result.checked.append((source.name, "не успели проверить"))
                continue
            try:
                sheet = _try_source(client, source, artist, title)
            except Blocked as error:
                result.checked.append((source.name, str(error)))
                continue
            except Exception:  # noqa: BLE001  (сбой одного парсера не должен ронять страницу)
                logger.exception("Ошибка при разборе %s", source.name)
                result.checked.append((source.name, "не удалось разобрать страницу"))
                continue
            if sheet:
                logger.info("Аккорды для «%s — %s» нашлись на %s", artist, title, source.name)
                result.sheet = sheet
                return result
            result.checked.append((source.name, "нет этой песни"))
    logger.info("Аккорды для «%s — %s» не нашлись: %s", artist, title, result.checked)
    return result
