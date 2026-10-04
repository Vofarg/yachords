"""Проверки страниц без настоящего Яндекса: ответы Яндекса подменяются заготовками."""

import pytest
from fastapi.testclient import TestClient

from app import main, yandex
from app.models import PlaylistDetails, PlaylistInfo, TrackInfo

PLAYLISTS = [
    PlaylistInfo(kind="likes", title="Мне нравится", track_count=2, is_likes=True),
    PlaylistInfo(kind="1003", title="Рок классика", track_count=1, cover_url="https://example.com/c.jpg"),
]
TRACKS = [
    TrackInfo(id="1:10", title="Кукушка", artists="Кино", duration="6:35"),
    TrackInfo(id="2:20", title="Пачка сигарет", artists="Кино", duration="4:28"),
]


@pytest.fixture
def client(monkeypatch):
    """Сайт с подменённым Яндексом и без пароля."""
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr(yandex, "get_playlists", lambda: PLAYLISTS)
    monkeypatch.setattr(
        yandex, "get_playlist", lambda kind: PlaylistDetails(playlist=PLAYLISTS[0], tracks=TRACKS)
    )
    monkeypatch.setattr(yandex, "get_track", lambda track_id: TRACKS[0])
    return TestClient(main.app)


def test_home_lists_playlists(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Мне нравится" in page.text
    assert "Рок классика" in page.text
    assert "2 трека" in page.text


def test_playlist_page_shows_tracks_and_random_button(client):
    page = client.get("/playlist/likes")
    assert page.status_code == 200
    assert "Кукушка" in page.text
    assert "/random?kind=likes" in page.text


def test_random_opens_a_track_from_the_playlist(client):
    response = client.get("/random?kind=likes", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] in {"/track/1:10?from=likes", "/track/2:20?from=likes"}


def test_track_page_ignores_strange_back_link(client):
    page = client.get('/track/1:10?from="><script>')
    assert page.status_code == 200
    assert '"><script>' not in page.text


def test_expired_token_shows_instructions(client, monkeypatch):
    def broken():
        raise yandex.TokenError

    monkeypatch.setattr(yandex, "get_playlists", broken)
    page = client.get("/")
    assert page.status_code == 401
    assert "Токен истёк" in page.text
    assert "oauth.yandex.ru/authorize" in page.text
    assert "YANDEX_MUSIC_TOKEN" in page.text


def test_password_protects_pages(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "секрет")
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.post("/login", data={"password": "не тот"}).status_code == 401
    client.post("/login", data={"password": "секрет"})
    assert client.get("/").status_code == 200


@pytest.mark.parametrize(
    "n, word", [(1, "трек"), (2, "трека"), (5, "треков"), (11, "треков"), (21, "трек"), (124, "трека")]
)
def test_plural(n, word):
    assert main.plural(n, "трек", "трека", "треков") == word


def test_chordbook_page_opens_and_is_linked_from_header(client):
    page = client.get("/chordbook")
    assert page.status_code == 200
    assert "Справочник аккордов" in page.text
    assert "chordbook.js" in page.text
    assert 'href="/chordbook"' in client.get("/").text


def test_chords_block_shows_sheet_and_transpose_panel(client, monkeypatch):
    from app.chords import normalize, sources

    sheet = normalize.build_sheet("\x01Am\x02  \x01F\x02\nПесен ещё ненаписанных", "AmDm.ru", "https://amdm.ru/x/")
    monkeypatch.setattr(sources, "find_chords", lambda artist, title: sources.SearchResult(sheet=sheet))
    page = client.get("/track/1:10/chords?from=likes")
    assert page.status_code == 200
    assert 'data-chord="Am"' in page.text
    assert "data-transpose" in page.text
    assert "data-diagrams" in page.text and "data-tabs" in page.text
    assert 'data-pdf="Кино - Кукушка"' in page.text
    assert "AmDm.ru" in page.text
    assert "/random?kind=likes" in page.text


def test_chords_block_lists_checked_sites_when_not_found(client, monkeypatch):
    from app.chords import sources

    result = sources.SearchResult(checked=[("AmDm.ru", "нет этой песни"), ("Ultimate-Guitar.com", "сайт не пустил (код 403)")])
    monkeypatch.setattr(sources, "find_chords", lambda artist, title: result)
    page = client.get("/track/1:10/chords")
    assert "Аккорды не найдены" in page.text
    assert "сайт не пустил (код 403)" in page.text
    assert "data-show-tabs" in page.text


def test_all_sites_down_says_so(client, monkeypatch):
    from app.chords import sources

    result = sources.SearchResult(checked=[("AmDm.ru", "сайт не ответил"), ("MyChords.net", "сайт не пустил (код 403)")])
    monkeypatch.setattr(sources, "find_chords", lambda artist, title: result)
    page = client.get("/track/1:10/chords")
    assert "Сайты с аккордами не ответили" in page.text
    assert "MyChords.net" in page.text


def test_instrumental_track_shows_tabs_right_away(client, monkeypatch):
    from app.chords import sources

    instrumental = TrackInfo(id="3:30", title="Кукушка", artists="Кино", duration="6:35", instrumental=True)
    monkeypatch.setattr(yandex, "get_track", lambda track_id: instrumental)
    monkeypatch.setattr(sources, "find_chords", lambda artist, title: sources.SearchResult(checked=[("AmDm.ru", "нет этой песни")]))
    page = client.get("/track/3:30/chords")
    assert "Это инструментальный трек" in page.text
    assert 'data-example="Am F C G">' in page.text  # без hidden: перебор виден сразу
    assert "data-show-tabs" not in page.text


def test_random_from_empty_playlist_opens_the_playlist(client, monkeypatch):
    def empty(kind):
        raise yandex.EmptyPlaylist

    monkeypatch.setattr(yandex, "random_track", empty)
    response = client.get("/random?kind=1003", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/playlist/1003"


def test_empty_likes_asks_to_add_tracks(client, monkeypatch):
    monkeypatch.setattr(yandex, "get_playlist", lambda kind: PlaylistDetails(playlist=PLAYLISTS[0], tracks=[]))
    page = client.get("/playlist/likes")
    assert "Добавьте треки в избранное" in page.text
    assert "/random?kind=likes" not in page.text


def test_unexpected_error_shows_friendly_page(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)

    def crash():
        raise RuntimeError("сломалось")

    monkeypatch.setattr(yandex, "get_playlists", crash)
    page = TestClient(main.app, raise_server_exceptions=False).get("/")
    assert page.status_code == 500
    assert "Что-то пошло не так" in page.text
