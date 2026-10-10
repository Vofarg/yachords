"""Проверки перевода данных Яндекс.Музыки в формат сайта."""

import pytest
from yandex_music import Playlist, Track

from app import yandex


def test_track_info_from_yandex_data():
    track = Track.de_json(
        {
            "id": "123",
            "title": "Кукушка",
            "artists": [{"id": 1, "name": "Кино"}],
            "albums": [{"id": 456}],
            "durationMs": 395000,
            "coverUri": "avatars.yandex.net/get-music-content/abc/%%",
        },
        None,
    )
    info = yandex._track_info(track)
    assert info.id == "123:456"
    assert info.artists == "Кино"
    assert info.duration == "6:35"
    assert info.cover_url == "https://avatars.yandex.net/get-music-content/abc/400x400"


def test_playlist_cover_falls_back_to_track_collage():
    playlist = Playlist.de_json(
        {"kind": 3, "title": "Рок", "cover": {"type": "mosaic", "itemsUri": ["a.net/1/%%", "a.net/2/%%"]}},
        None,
    )
    assert yandex._playlist_cover(playlist) == "https://a.net/1/400x400"


def test_missing_token_is_reported(monkeypatch):
    monkeypatch.delenv("YANDEX_MUSIC_TOKEN", raising=False)
    yandex.reset()
    assert yandex.check_token() is False


@pytest.mark.parametrize(
    "title, version, expected",
    [
        ("Кукушка", None, False),
        ("Кукушка", "Instrumental", True),
        ("Группа крови (инструментал)", None, True),
        ("Минус на минус", None, False),
        ("Звезда", "Karaoke Version", True),
        ("Минусовка", "", True),
    ],
)
def test_is_instrumental(title, version, expected):
    assert yandex.is_instrumental(title, version) is expected


class _FakeClient:
    """Поддельный клиент Яндекса: у каждого токена свой плейлист с названием по токену."""

    def __init__(self, token):
        self.token = token
        self.me = type("Me", (), {"account": type("Account", (), {"uid": hash(token) % 1000})()})()

    def init(self):
        return self

    def users_playlists_list(self, uid, timeout=None):
        return [Playlist.de_json({"kind": 1, "title": f"Плейлист {self.token}", "trackCount": 0}, None)]

    def users_likes_tracks(self, uid, timeout=None):
        return None


def test_two_users_never_share_playlists(monkeypatch):
    monkeypatch.setattr(yandex, "Client", _FakeClient)
    monkeypatch.delenv("YANDEX_MUSIC_TOKEN", raising=False)
    yandex.reset()

    yandex.use_token("token-anna")
    anna = [p.title for p in yandex.get_playlists()]
    yandex.use_token("token-boris")
    boris = [p.title for p in yandex.get_playlists()]
    yandex.use_token("token-anna")
    anna_again = [p.title for p in yandex.get_playlists()]

    assert "Плейлист token-anna" in anna
    assert "Плейлист token-boris" in boris
    assert "Плейлист token-anna" not in boris
    assert anna_again == anna
    yandex.use_token(None)
    yandex.reset()
