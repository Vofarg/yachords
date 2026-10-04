"""Разбор страниц сайтов с аккордами: AmDm.ru, MyChords.net, Ultimate-Guitar.com.

Для каждого сайта две функции: найти ссылку на песню в результатах поиска
и достать аккорды со страницы песни. Вёрстка сайтов меняется, поэтому
каждая функция пробует несколько способов и пишет в лог, что не нашлось.
"""

import html
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser, LexborNode

from app.chords.normalize import (
    CHORD_END,
    CHORD_START,
    ChordSheet,
    build_sheet,
    mark_chord_lines,
    simplify,
)

logger = logging.getLogger(__name__)

MIN_MATCH = 0.6


def _similar(a: str, b: str) -> float:
    """Насколько похожи две строки, от 0 до 1."""
    a, b = simplify(a), simplify(b)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _score(found_artist: str, found_title: str, artist: str, title: str) -> float:
    """Оценка результата поиска: название важнее исполнителя."""
    title_score = _similar(found_title, title)
    if title_score < MIN_MATCH:
        return 0.0
    artist_score = _similar(found_artist, artist) if found_artist else 0.5
    return title_score * 0.6 + artist_score * 0.4


def _text_with_chords(node: LexborNode, chord_selectors: tuple[str, ...]) -> str:
    """Текст блока, где каждый аккорд обёрнут метками.

    Аккордом считается элемент с атрибутом data-chord или подходящий под один из селекторов.
    """
    chord_nodes = set()
    for selector in chord_selectors:
        for found in node.css(selector):
            chord_nodes.add(found.mem_id)

    parts: list[str] = []

    def walk(current: LexborNode) -> None:
        child = current.child
        while child is not None:
            if child.tag == "-text":
                parts.append(child.text_content or "")
            elif child.tag == "br":
                parts.append("\n")
            elif child.mem_id in chord_nodes or "data-chord" in (child.attributes or {}):
                parts.append(f"{CHORD_START}{child.text(deep=True)}{CHORD_END}")
            else:
                walk(child)
                if child.tag in {"div", "p"}:
                    parts.append("\n")
            child = child.next

    walk(node)
    return "".join(parts)


# --- AmDm.ru ---------------------------------------------------------------

AMDM_SEARCH = "https://amdm.ru/search/"


def amdm_pick(page: str, artist: str, title: str) -> Optional[str]:
    """Находит в результатах поиска AmDm ссылку на нужную песню."""
    tree = LexborHTMLParser(page)
    best: tuple[float, Optional[str]] = (0.0, None)
    cells = tree.css("td.artist_name") or tree.css("table tr")
    if not cells:
        logger.info("AmDm: в результатах поиска не нашлось строк таблицы")
    for cell in cells:
        links = [a for a in cell.css("a") if a.attributes.get("href")]
        song_links = [a for a in links if re.search(r"/akkordi/[^/]+/\d+/", a.attributes["href"])]
        if not song_links:
            continue
        song = song_links[0]
        artist_links = [a for a in links if a is not song and "/akkordi/" in a.attributes["href"]]
        found_artist = artist_links[0].text(strip=True) if artist_links else ""
        score = _score(found_artist, song.text(strip=True), artist, title)
        if score > best[0]:
            best = (score, urljoin("https://amdm.ru/", song.attributes["href"]))
    return best[1]


def amdm_parse(page: str, url: str = "") -> Optional[ChordSheet]:
    """Достаёт аккорды со страницы песни на AmDm."""
    tree = LexborHTMLParser(page)
    for selector in ("pre.podbor__text", "pre[itemprop=chordsBlock]", "div.podbor__text pre", "pre"):
        block = tree.css_first(selector)
        if block is None:
            continue
        sheet = build_sheet(_text_with_chords(block, ("b", ".podbor__chord")), "AmDm.ru", url)
        if sheet:
            return sheet
    logger.info("AmDm: на странице %s не нашёлся блок с аккордами", url)
    return None


# --- MyChords.net ----------------------------------------------------------

MYCHORDS_SEARCH = "https://mychords.net/search"


def mychords_pick(page: str, artist: str, title: str) -> Optional[str]:
    """Находит в результатах поиска MyChords ссылку на нужную песню."""
    tree = LexborHTMLParser(page)
    best: tuple[float, Optional[str]] = (0.0, None)
    for link in tree.css("a[href]"):
        href = link.attributes.get("href") or ""
        if not re.search(r"/\d+-[^/]+\.html", href):
            continue
        text = link.text(strip=True)
        # Обычно текст ссылки — «Исполнитель - Название».
        found_artist, _, found_title = text.partition(" - ")
        if not found_title:
            found_artist, found_title = "", text
        score = _score(found_artist, found_title, artist, title)
        if score > best[0]:
            best = (score, urljoin("https://mychords.net/", href))
    if best[1] is None:
        logger.info("MyChords: в результатах поиска нет подходящих ссылок")
    return best[1]


def mychords_parse(page: str, url: str = "") -> Optional[ChordSheet]:
    """Достаёт аккорды со страницы песни на MyChords."""
    tree = LexborHTMLParser(page)
    selectors = (".w-words__text", "pre.w-words__text", "div.chords pre", "pre[itemprop=text]", "pre")
    chord_selectors = (".b-accord__symbol", ".chord", "a.b-accord__symbol")
    for selector in selectors:
        for block in tree.css(selector):
            marked = _text_with_chords(block, chord_selectors)
            if CHORD_START not in marked:
                marked = mark_chord_lines(marked)
            sheet = build_sheet(marked, "MyChords.net", url)
            if sheet:
                return sheet
    logger.info("MyChords: на странице %s не нашёлся блок с аккордами", url)
    return None


# --- Ultimate-Guitar.com ---------------------------------------------------

UG_SEARCH = "https://www.ultimate-guitar.com/search.php"


def _ug_store(page: str) -> Optional[dict]:
    """Данные страницы UG: они лежат в JSON внутри атрибута data-content."""
    tree = LexborHTMLParser(page)
    node = tree.css_first("div.js-store") or tree.css_first("[data-content]")
    if node is None:
        logger.info("UG: на странице нет блока с данными")
        return None
    try:
        return json.loads(html.unescape(node.attributes.get("data-content") or ""))
    except (TypeError, ValueError) as error:
        logger.info("UG: не удалось прочитать данные страницы: %s", error)
        return None


def ug_pick(page: str, artist: str, title: str) -> Optional[str]:
    """Находит в результатах поиска UG вариант с аккордами (а не табами) с лучшим рейтингом."""
    store = _ug_store(page)
    results = (((store or {}).get("store") or {}).get("page") or {}).get("data", {}).get("results") or []
    best: tuple[float, Optional[str]] = (0.0, None)
    for item in results:
        if not isinstance(item, dict) or item.get("type") != "Chords" or not item.get("tab_url"):
            continue
        score = _score(item.get("artist_name", ""), item.get("song_name", ""), artist, title)
        if score:
            score += min(float(item.get("rating") or 0), 5) / 100
        if score > best[0]:
            best = (score, item["tab_url"])
    return best[1]


def ug_parse(page: str, url: str = "") -> Optional[ChordSheet]:
    """Достаёт аккорды со страницы песни на UG. Аккорды там размечены как [ch]Am[/ch]."""
    store = _ug_store(page)
    data = (((store or {}).get("store") or {}).get("page") or {}).get("data") or {}
    content = ((data.get("tab_view") or {}).get("wiki_tab") or {}).get("content")
    if not content:
        logger.info("UG: на странице %s нет текста с аккордами", url)
        return None
    content = content.replace("[ch]", CHORD_START).replace("[/ch]", CHORD_END)
    content = re.sub(r"\[/?tab\]", "", content)
    return build_sheet(content, "Ultimate-Guitar.com", url)
