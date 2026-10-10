"""Проверки входа через Яндекс ID: настоящий Яндекс подменяется заготовками."""

import pytest
from fastapi.testclient import TestClient

from app import auth, main, yandex, yandex_id
from app.models import PlaylistInfo


@pytest.fixture
def client(monkeypatch):
    """Сайт с настроенным Яндекс ID: владелец anna, друг boris."""
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("YANDEX_ID_CLIENT_ID", "id123")
    monkeypatch.setenv("YANDEX_ID_CLIENT_SECRET", "secret456")
    monkeypatch.setenv("OWNER_LOGIN", "Anna.Petrova")
    monkeypatch.setenv("ALLOWED_LOGINS", "boris, vera@yandex.ru")
    monkeypatch.setattr(
        yandex, "get_playlists", lambda: [PlaylistInfo(kind="likes", title="Мне нравится", track_count=1, is_likes=True)]
    )
    return TestClient(main.app)


def _log_in(client, monkeypatch, login):
    """Проходит вход так, будто Яндекс ID вернул этот логин."""
    monkeypatch.setattr(yandex_id, "login_by_code", lambda code: login)
    start = client.get("/auth/yandex", follow_redirects=False)
    state = start.headers["location"].split("state=")[1]
    return client.get(f"/auth/yandex/callback?code=c&state={state}", follow_redirects=False)


def test_login_page_shows_yandex_button_instead_of_password(client):
    page = client.get("/login")
    assert "Войти через Яндекс ID" in page.text
    assert 'type="password"' not in page.text
    assert client.post("/login", data={"password": "что угодно"}).status_code == 401


def test_pages_need_login(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


def test_button_leads_to_yandex_with_return_address(client):
    location = client.get("/auth/yandex", follow_redirects=False).headers["location"]
    assert location.startswith("https://oauth.yandex.ru/authorize?")
    assert "client_id=id123" in location
    assert "redirect_uri=http%3A%2F%2Ftestserver%2Fauth%2Fyandex%2Fcallback" in location


def test_owner_sees_own_playlists(client, monkeypatch):
    response = _log_in(client, monkeypatch, "anna-petrova")
    assert response.headers["location"] == "/"
    page = client.get("/")
    assert "Мне нравится" in page.text
    assert 'href="/logout"' in page.text


def test_friend_gets_placeholder_not_owner_playlists(client, monkeypatch):
    _log_in(client, monkeypatch, "Boris")
    response = client.get("/", follow_redirects=False)
    assert response.headers["location"] == "/connect"
    page = client.get("/connect")
    assert "Вы вошли как boris" in page.text
    assert client.get("/chordbook").status_code == 200


def test_friend_never_gets_owner_token_from_settings(monkeypatch):
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "токен-владельца")
    yandex.use_token(None, settings_allowed=False)
    with pytest.raises(yandex.TokenError):
        yandex._token()
    yandex.use_token(None)
    assert yandex._token() == "токен-владельца"


def test_stranger_is_turned_away(client, monkeypatch):
    response = _log_in(client, monkeypatch, "stranger")
    assert response.status_code == 403
    assert "Логина stranger нет в списке" in response.text
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


def test_return_with_foreign_state_is_rejected(client, monkeypatch):
    monkeypatch.setattr(yandex_id, "login_by_code", lambda code: pytest.fail("код не должен меняться"))
    client.get("/auth/yandex", follow_redirects=False)
    assert client.get("/auth/yandex/callback?code=c&state=чужая").status_code == 400


def test_forged_cookie_is_ignored(client):
    client.cookies.set(auth.COOKIE_NAME, "anna-petrova:9999999999:forged")
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


def test_removed_friend_loses_access(client, monkeypatch):
    _log_in(client, monkeypatch, "vera")
    assert client.get("/connect").status_code == 200
    monkeypatch.setenv("ALLOWED_LOGINS", "boris")
    assert client.get("/connect", follow_redirects=False).headers["location"] == "/login"


def test_logout_forgets_login(client, monkeypatch):
    _log_in(client, monkeypatch, "anna-petrova")
    client.get("/logout")
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


@pytest.mark.parametrize("raw, login", [("Anna.Petrova", "anna-petrova"), (" vera@yandex.ru ", "vera"), ("Boris", "boris")])
def test_logins_compare_like_yandex_does(raw, login):
    assert auth.normalize_login(raw) == login


def test_page_works_with_the_token_chosen_at_login(client, monkeypatch):
    monkeypatch.setenv("YANDEX_MUSIC_TOKEN", "owner-token")
    monkeypatch.setattr(
        yandex, "get_playlists", lambda: [PlaylistInfo(kind="1", title=f"Токен {yandex._token()}", track_count=0)]
    )
    _log_in(client, monkeypatch, "anna-petrova")
    assert "Токен owner-token" in client.get("/").text
