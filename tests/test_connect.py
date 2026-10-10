"""Проверки подключения своей Яндекс.Музыки: настоящий Яндекс подменяется заготовками."""

import re

import pytest
from fastapi.testclient import TestClient

from app import main, music_link, yandex, yandex_id
from app.models import PlaylistInfo

ADDRESS = "https://music.yandex.ru/#access_token=y0_friendtoken1234567890&token_type=bearer&expires_in=31536000"


@pytest.fixture
def site(monkeypatch):
    """Сайт с Яндекс ID: владелец anna, друзья boris и vera. Плейлисты подписаны токеном."""
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("MUSIC_COOKIE_KEY", raising=False)
    monkeypatch.setenv("YANDEX_ID_CLIENT_ID", "id123")
    monkeypatch.setenv("YANDEX_ID_CLIENT_SECRET", "secret456")
    monkeypatch.setenv("OWNER_LOGIN", "anna")
    monkeypatch.setenv("ALLOWED_LOGINS", "boris, vera")
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "owner-token")
    monkeypatch.setattr(
        yandex, "get_playlists", lambda: [PlaylistInfo(kind="1", title=f"Токен {yandex._token()}", track_count=0)]
    )
    monkeypatch.setattr(yandex, "verify_token", lambda token: token.startswith("y0_"))


def _client(monkeypatch, login):
    """Браузер, вошедший через Яндекс ID под этим логином."""
    client = TestClient(main.app)
    monkeypatch.setattr(yandex_id, "login_by_code", lambda code: login)
    start = client.get("/auth/yandex", follow_redirects=False)
    state = start.headers["location"].split("state=")[1]
    client.get(f"/auth/yandex/callback?code=c&state={state}", follow_redirects=False)
    return client


@pytest.mark.parametrize(
    "text, token",
    [
        (ADDRESS, "y0_friendtoken1234567890"),
        ("  y0_friendtoken1234567890 ", "y0_friendtoken1234567890"),
        ("https://music.yandex.ru/home", None),
        ("привет", None),
    ],
)
def test_token_found_in_pasted_text(text, token):
    assert music_link.extract_token(text) == token


def test_friend_sees_instructions_until_connected(site, monkeypatch):
    boris = _client(monkeypatch, "boris")
    assert boris.get("/", follow_redirects=False).headers["location"] == "/connect"
    page = boris.get("/connect").text
    assert "Откройте страницу Яндекса" in page
    assert yandex.TOKEN_URL.replace("&", "&amp;") in page or yandex.TOKEN_URL in page
    assert "access_token=" in page


def test_friend_connects_and_sees_own_playlists(site, monkeypatch):
    boris = _client(monkeypatch, "boris")
    response = boris.post("/connect", data={"token_text": ADDRESS}, follow_redirects=False)
    assert response.headers["location"] == "/"
    page = boris.get("/").text
    assert "Токен y0_friendtoken1234567890" in page
    assert "owner-token" not in page
    connected = boris.get("/connect").text
    assert "Музыка подключена" in connected
    assert "<svg" in connected and "/connect/phone?t=" in connected


def test_wrong_paste_explains_what_to_copy(site, monkeypatch):
    boris = _client(monkeypatch, "boris")
    page = boris.post("/connect", data={"token_text": "https://music.yandex.ru/home"})
    assert page.status_code == 400
    assert "Не нашли токен" in page.text
    rejected = boris.post("/connect", data={"token_text": "badtoken_but_long_enough_123"})
    assert "не приняла этот токен" in rejected.text


def test_music_cookie_does_not_work_for_another_login(site, monkeypatch):
    boris = _client(monkeypatch, "boris")
    boris.post("/connect", data={"token_text": ADDRESS})
    stolen = boris.cookies.get(music_link.COOKIE_NAME)
    vera = _client(monkeypatch, "vera")
    vera.cookies.set(music_link.COOKIE_NAME, stolen)
    assert vera.get("/", follow_redirects=False).headers["location"] == "/connect"


def test_phone_link_moves_connection_to_another_browser(site, monkeypatch):
    computer = _client(monkeypatch, "boris")
    computer.post("/connect", data={"token_text": ADDRESS})
    page = computer.get("/connect").text
    link = page.split('/connect/phone?t=')[1].split('"')[0].replace("&amp;", "&")
    phone = TestClient(main.app)
    # Телефон ещё не вошёл: после входа через Яндекс ID он вернётся на ту же ссылку.
    first = phone.get(f"/connect/phone?t={link}", follow_redirects=False)
    assert first.headers["location"].startswith("/login?next=")
    login_page = phone.get(first.headers["location"]).text
    assert "/auth/yandex?next=" in login_page
    monkeypatch.setattr(yandex_id, "login_by_code", lambda code: "boris")
    button = re.search(r'href="(/auth/yandex[^"]*)"', login_page).group(1)
    start = phone.get(button, follow_redirects=False)
    state = start.headers["location"].split("state=")[1]
    back = phone.get(f"/auth/yandex/callback?code=c&state={state}", follow_redirects=False)
    assert back.headers["location"].startswith("/connect/phone?t=")
    phone.get(back.headers["location"])
    assert "Токен y0_friendtoken1234567890" in phone.get("/").text


def test_phone_link_from_another_friend_is_refused(site, monkeypatch):
    boris = _client(monkeypatch, "boris")
    boris.post("/connect", data={"token_text": ADDRESS})
    link = boris.get("/connect").text.split('/connect/phone?t=')[1].split('"')[0]
    vera = _client(monkeypatch, "vera")
    page = vera.get(f"/connect/phone?t={link}")
    assert page.status_code == 400
    assert "Ссылка для телефона устарела" in page.text


def test_expired_friend_token_leads_back_to_connect(site, monkeypatch):
    boris = _client(monkeypatch, "boris")
    boris.post("/connect", data={"token_text": ADDRESS})

    def expired():
        raise yandex.TokenError

    monkeypatch.setattr(yandex, "get_playlists", expired)
    response = boris.get("/", follow_redirects=False)
    assert response.headers["location"] == "/connect?expired=1"
    assert "закончился срок" in boris.get("/connect?expired=1").text


def test_disconnect_forgets_music(site, monkeypatch):
    boris = _client(monkeypatch, "boris")
    boris.post("/connect", data={"token_text": ADDRESS})
    boris.post("/connect/disconnect")
    assert boris.get("/", follow_redirects=False).headers["location"] == "/connect"


def test_owner_keeps_settings_token_and_may_connect_own(site, monkeypatch):
    anna = _client(monkeypatch, "anna")
    assert "Токен owner-token" in anna.get("/").text
    assert "токену из настроек сайта" in anna.get("/connect").text
    anna.post("/connect", data={"token_text": "y0_annaowntoken1234567890"})
    assert "Токен y0_annaowntoken1234567890" in anna.get("/").text


def test_redirect_after_login_only_to_phone_link(site, monkeypatch):
    client = TestClient(main.app)
    page = client.get("/login?next=https://evil.example/").text
    assert "/auth/yandex?next" not in page
    assert main._safe_next("/connect/phone?t=abc") == "/connect/phone?t=abc"
    assert main._safe_next("//evil.example/connect/phone?t=abc") is None
