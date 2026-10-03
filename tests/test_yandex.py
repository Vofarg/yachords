"""Проверки перевода данных Яндекс.Музыки в формат сайта."""

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
