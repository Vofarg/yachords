"""Схемы данных, которые сайт получает из Яндекс.Музыки и показывает на страницах."""

from typing import Optional

from pydantic import BaseModel

# Особый «плейлист» — треки из «Мне нравится». У него нет числового номера,
# поэтому в адресах страниц он обозначается этим словом.
LIKES_KIND = "likes"


class PlaylistInfo(BaseModel):
    """Карточка плейлиста на главной странице."""

    kind: str
    title: str
    track_count: int
    cover_url: Optional[str] = None
    is_likes: bool = False


class TrackInfo(BaseModel):
    """Строка трека в списке плейлиста и заголовок страницы трека."""

    id: str
    title: str
    artists: str
    duration: str
    cover_url: Optional[str] = None
    instrumental: bool = False


class PlaylistDetails(BaseModel):
    """Плейлист вместе со списком его треков."""

    playlist: PlaylistInfo
    tracks: list[TrackInfo]
    # Треки, которые есть в плейлисте, но Яндекс их больше не отдаёт (удалены или недоступны).
    unavailable: int = 0
