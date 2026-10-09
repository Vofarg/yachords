"""Проверки разбора аккордов на заготовленных страницах (без выхода в интернет)."""

import html
import json

import httpx
import pytest

from app.chords import normalize, parser, sources

AMDM_SEARCH_PAGE = """
<table class="items">
  <tr><th>#</th><th></th><th>Исполнитель / песня</th></tr>
  <tr><td class="i">1.</td><td class="photo"><img src="x.jpg"></td>
      <td class="artist_name"><a href="/akkordi/alisa/" class="artist">Алиса</a> - <a href="/akkordi/alisa/1/kukushka/">Кукушка</a></td></tr>
  <tr><td class="i">2.</td><td class="photo"></td>
      <td class="artist_name"><a href="https://amdm.ru/akkordi/kino/" class="artist">Кино</a> - <a href="https://amdm.ru/akkordi/kino/99876/kukushka/">Кукушка</a></td></tr>
  <tr><td class="i">3.</td><td class="photo"></td>
      <td class="artist_name"><a href="/akkordi/kino/5/gruppa_krovi/" class="artist">Кино</a> - <a href="/akkordi/kino/5/gruppa_krovi/">Группа крови</a></td></tr>
</table>
"""

AMDM_SONG_PAGE = """
<h1>Кино - Кукушка, аккорды</h1>
<pre itemprop="chordsBlock" class="field__podbor_new podbor__text"><div class="podbor__keyword">[Куплет 1]</div>
<b data-chord="Am" class="podbor__chord">Am</b>         <b data-chord="F" class="podbor__chord">F</b>
Песен ещё ненаписанных, сколько?
<b data-chord="C" class="podbor__chord">C</b>          <b data-chord="G" class="podbor__chord">G</b>
Скажи, кукушка, пропой.

<div class="podbor__keyword">Припев:</div>
<b data-chord="Am" class="podbor__chord">Am</b>    <b data-chord="F" class="podbor__chord">F</b>
Солнце моё, взгляни на меня
</pre>
"""

MYCHORDS_SEARCH_PAGE = """
<ul class="b-listing">
  <li><a href="/ru/kino/1234-kino-gruppa-krovi.html">Кино - Группа крови</a></li>
  <li><a href="https://mychords.net/ru/kino/5678-kino-kukushka.html">Кино - Кукушка</a></li>
</ul>
"""

MYCHORDS_SONG_PAGE = """
<div class="w-words"><pre class="w-words__text">Вступление: Am F C G

Am            F
Песен ещё ненаписанных, сколько?
C             G
Скажи, кукушка, пропой.
</pre></div>
"""


def ug_page(data: dict) -> str:
    """Страница UG с данными в атрибуте data-content, как на настоящем сайте."""
    payload = html.escape(json.dumps({"store": {"page": {"data": data}}}))
    return f'<div class="js-store" data-content="{payload}"></div>'


UG_SEARCH_PAGE = ug_page(
    {
        "results": [
            {"type": "Tabs", "artist_name": "Kino", "song_name": "Kukushka", "tab_url": "https://ug/tab", "rating": 5},
            {"type": "Chords", "artist_name": "Kino", "song_name": "Kukushka", "tab_url": "https://ug/low", "rating": 3},
            {"type": "Chords", "artist_name": "Kino", "song_name": "Kukushka", "tab_url": "https://ug/high", "rating": 4.8},
        ]
    }
)
UG_SONG_PAGE = ug_page(
    {
        "tab_view": {
            "wiki_tab": {
                "content": "[Verse 1]\n[tab][ch]Am[/ch]        [ch]F[/ch]\nPesen eshche[/tab]\n[tab][ch]C[/ch]   [ch]G[/ch]\nSkazhi[/tab]"
            }
        }
    }
)


def chord_names(sheet):
    return [t.text for line in sheet.lines for t in line.tokens if t.is_chord]


def test_amdm_picks_the_right_artist():
    url = parser.amdm_pick(AMDM_SEARCH_PAGE, "Кино", "Кукушка")
    assert url == "https://amdm.ru/akkordi/kino/99876/kukushka/"


def test_amdm_ignores_other_songs():
    assert parser.amdm_pick(AMDM_SEARCH_PAGE, "Кино", "Звезда по имени Солнце") is None


def test_amdm_song_keeps_chords_above_words():
    sheet = parser.amdm_parse(AMDM_SONG_PAGE, "https://amdm.ru/x/")
    assert sheet.source == "AmDm.ru"
    assert sheet.chords == ["Am", "F", "C", "G"]
    kinds = [line.kind for line in sheet.lines]
    assert kinds[:3] == ["section", "chords", "text"]
    assert sheet.lines[0].tokens[0].text == "Куплет 1"
    chord_line = "".join(t.text for t in sheet.lines[1].tokens)
    assert chord_line.index("F") == 11  # аккорд стоит над тем же слогом, что и на сайте
    assert any(line.kind == "section" and line.tokens[0].text == "Припев" for line in sheet.lines)


def test_mychords_search_and_plain_text_chords():
    url = parser.mychords_pick(MYCHORDS_SEARCH_PAGE, "Кино", "Кукушка")
    assert url == "https://mychords.net/ru/kino/5678-kino-kukushka.html"
    sheet = parser.mychords_parse(MYCHORDS_SONG_PAGE, url)
    assert sheet.chords == ["Am", "F", "C", "G"]
    assert sheet.lines[0].kind == "text"  # «Вступление: Am F C G» — не строка из одних аккордов


def test_ug_picks_best_rated_chords_and_reads_markup():
    assert parser.ug_pick(UG_SEARCH_PAGE, "Кино", "Kukushka") == "https://ug/high"
    sheet = parser.ug_parse(UG_SONG_PAGE, "https://ug/high")
    assert sheet.chords == ["Am", "F", "C", "G"]
    assert sheet.lines[0].kind == "section"


@pytest.mark.parametrize("word", ["Am", "F#m7", "C/G", "Hm", "Bb", "Dsus4", "Cmaj7", "E7(b9)", "A#dim"])
def test_chords_are_recognised(word):
    assert normalize.is_chord(word)


@pytest.mark.parametrize("word", ["Am,", "Ах", "Cool", "Be", "Hello", "a"])
def test_words_are_not_chords(word):
    assert not normalize.is_chord(word)


def test_clean_title():
    assert normalize.clean_title("Кукушка (Remastered 2009)") == "Кукушка"
    assert normalize.clean_title("Song feat. Someone") == "Song"


REAL_CLIENT = httpx.Client


def make_client(routes: dict) -> httpx.Client:
    """Клиент, который вместо интернета отвечает заготовками по адресу."""

    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, (status, body) in routes.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(status, text=body)
        return httpx.Response(404, text="")

    return REAL_CLIENT(transport=httpx.MockTransport(handler))


def run_find(monkeypatch, routes):
    monkeypatch.setattr(sources.httpx, "Client", lambda **kwargs: make_client(routes))
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    return sources.find_chords("Кино", "Кукушка")


def test_find_uses_first_source_that_has_the_song(monkeypatch):
    result = run_find(
        monkeypatch,
        {
            "https://amdm.ru/search/": (200, AMDM_SEARCH_PAGE),
            "https://amdm.ru/akkordi/kino/99876/": (200, AMDM_SONG_PAGE),
        },
    )
    assert result.sheet.source == "AmDm.ru"
    assert result.checked == []


def test_find_falls_back_when_first_site_blocks(monkeypatch):
    result = run_find(
        monkeypatch,
        {
            "https://amdm.ru/": (403, "forbidden"),
            "https://mychords.net/search": (200, MYCHORDS_SEARCH_PAGE),
            "https://mychords.net/ru/kino/5678": (200, MYCHORDS_SONG_PAGE),
        },
    )
    assert result.sheet.source == "MyChords.net"
    assert result.checked == [("AmDm.ru", "сайт не пустил (код 403)")]


def test_find_reports_every_site_when_nothing_found(monkeypatch):
    result = run_find(
        monkeypatch,
        {
            "https://amdm.ru/": (200, "<table></table>"),
            "https://mychords.net/": (200, "<ul></ul>"),
            "https://www.ultimate-guitar.com/": (403, "Just a moment..."),
        },
    )
    assert result.sheet is None
    assert [name for name, _ in result.checked] == ["AmDm.ru", "MyChords.net", "Ultimate-Guitar.com"]
    assert not result.all_failed


def test_amdm_skips_same_title_by_another_artist():
    # Поиск по одному названию часто выдаёт одноимённую песню другой группы — её брать нельзя.
    assert parser.amdm_pick(AMDM_SEARCH_PAGE, "Сплин", "Кукушка") is None


@pytest.mark.parametrize(
    "found, wanted",
    [("Кино", "Kino"), ("Земфира", "Zemfira"), ("Мумий Тролль", "Mumiy Troll"), ("Кино", "Кино")],
)
def test_artist_written_in_latin_still_matches(found, wanted):
    assert parser._score(found, "Песня", wanted, "Песня") > 0


def test_other_artist_is_rejected():
    assert parser._score("Алиса", "Кукушка", "Кино", "Кукушка") == 0


def test_manual_link_reads_chords_from_a_song_page(monkeypatch):
    routes = {"https://amdm.ru/akkordi/kino/99876/": (200, AMDM_SONG_PAGE)}
    monkeypatch.setattr(sources.httpx, "Client", lambda **kwargs: make_client(routes))
    result = sources.chords_from_url("http://amdm.ru/akkordi/kino/99876/kukushka/")
    assert result.manual and not result.manual_error
    assert result.sheet.source == "AmDm.ru"
    assert result.sheet.chords == ["Am", "F", "C", "G"]


@pytest.mark.parametrize(
    "url", ["https://example.com/akkordi/1/", "javascript:alert(1)", "https://amdm.ru.evil.com/x/", "не ссылка"]
)
def test_manual_link_only_opens_chord_sites(monkeypatch, url):
    monkeypatch.setattr(sources.httpx, "Client", lambda **kwargs: pytest.fail("не должен ходить в интернет"))
    result = sources.chords_from_url(url)
    assert result.sheet is None
    assert "AmDm.ru" in result.manual_error


def test_manual_link_to_search_page_explains_what_is_wrong(monkeypatch):
    routes = {"https://amdm.ru/search/": (200, AMDM_SEARCH_PAGE)}
    monkeypatch.setattr(sources.httpx, "Client", lambda **kwargs: make_client(routes))
    result = sources.chords_from_url("https://amdm.ru/search/?q=кино")
    assert result.sheet is None
    assert "страницу самой песни" in result.manual_error
