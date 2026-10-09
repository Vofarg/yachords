"""Сайт: адреса страниц и что на каждой показывается."""

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

from app import auth, yandex  # noqa: E402  (настройки из .env должны загрузиться раньше)
from app.chords import sources  # noqa: E402
from app.models import LIKES_KIND  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="Аккорды", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "app" / "templates")


def plural(n: int, one: str, few: str, many: str) -> str:
    """Подбирает форму слова к числу: 1 трек, 2 трека, 5 треков."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


templates.env.filters["plural"] = plural

PUBLIC_PATHS = ("/login", "/static/", "/healthz")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Пускает на страницы сайта только после ввода пароля (если пароль задан)."""
    path = request.url.path
    if path.startswith(PUBLIC_PATHS) or auth.is_logged_in(request.cookies.get(auth.COOKIE_NAME)):
        return await call_next(request)
    return RedirectResponse("/login", status_code=303)


def _error(
    request: Request,
    title: str,
    text: str,
    status: int,
    action: Optional[dict] = None,
    steps: Optional[list[str]] = None,
) -> HTMLResponse:
    """Страница с понятным сообщением об ошибке и, если нужно, пошаговой инструкцией."""
    return templates.TemplateResponse(
        request,
        "error.html",
        {"title": title, "text": text, "action": action, "steps": steps or []},
        status_code=status,
    )


@app.exception_handler(yandex.TokenError)
async def token_error(request: Request, exc: yandex.TokenError) -> HTMLResponse:
    """Токен Яндекса не задан или истёк: показываем, как получить новый."""
    return _error(
        request,
        "Токен истёк",
        "Яндекс.Музыка не принимает токен: срок его действия закончился или он ещё не задан. "
        "Новый токен получается за пару минут:",
        401,
        {"href": yandex.TOKEN_URL, "label": "Получить токен в Яндекс ID", "external": True},
        [
            "Нажмите кнопку ниже и войдите в свой аккаунт Яндекса, затем разрешите доступ.",
            "Яндекс откроет страницу с длинным адресом. Скопируйте из адресной строки всё, "
            "что стоит между access_token= и следующим знаком &.",
            "На Render откройте сервис yachords → Environment, вставьте скопированное "
            "в YANDEX_MUSIC_TOKEN и сохраните. Сайт перезапустится сам через пару минут.",
            "Если сайт запущен на компьютере, вставьте токен в файл .env и перезапустите его.",
        ],
    )


@app.exception_handler(yandex.YandexUnavailableError)
async def yandex_down(request: Request, exc: yandex.YandexUnavailableError) -> HTMLResponse:
    """Яндекс не ответил даже после повторов."""
    return _error(
        request,
        "Яндекс.Музыка не отвечает",
        "Попробуйте обновить страницу через минуту.",
        503,
        {"href": request.url.path, "label": "Обновить"},
    )


@app.exception_handler(yandex.NotFound)
async def not_found(request: Request, exc: yandex.NotFound) -> HTMLResponse:
    """Плейлист или трек не нашёлся."""
    return _error(request, "Ничего не нашлось", "Такого плейлиста или трека нет.", 404, {"href": "/", "label": "К плейлистам"})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> HTMLResponse:
    """Любая непредвиденная ошибка: пишем подробности в лог, а человеку показываем понятную страницу."""
    logger.exception("Непредвиденная ошибка на %s", request.url.path, exc_info=exc)
    return _error(
        request,
        "Что-то пошло не так",
        "Сайт споткнулся на этой странице. Попробуйте обновить её, а если не поможет, вернитесь к плейлистам.",
        500,
        {"href": "/", "label": "К плейлистам"},
    )


@app.get("/healthz")
def healthz() -> dict:
    """Проверка для хостинга, что сайт запущен."""
    return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    """Форма ввода пароля."""
    if auth.password() is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"failed": False})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form("")) -> Response:
    """Проверяет пароль и запоминает вход в cookie."""
    session = auth.check_password(password)
    if session is None:
        logger.info("Неверный пароль на входе")
        return templates.TemplateResponse(request, "login.html", {"failed": True}, status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME,
        session,
        max_age=auth.COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> Response:
    """Главная: все плейлисты."""
    return templates.TemplateResponse(request, "playlists.html", {"playlists": yandex.get_playlists()})


@app.get("/playlists")
def playlists_redirect() -> Response:
    """Старый адрес из спецификации ведёт на главную."""
    return RedirectResponse("/", status_code=308)


@app.get("/playlist/{kind}", response_class=HTMLResponse)
def playlist(request: Request, kind: str) -> Response:
    """Страница плейлиста со списком треков."""
    details = yandex.get_playlist(kind)
    return templates.TemplateResponse(
        request,
        "playlist.html",
        {"playlist": details.playlist, "tracks": details.tracks, "unavailable": details.unavailable},
    )


@app.get("/random")
def random_track(kind: str) -> Response:
    """Случайный трек из плейлиста: сразу открывает его страницу. Пустой плейлист открывается как есть."""
    try:
        track = yandex.random_track(kind)
    except yandex.EmptyPlaylist:
        return RedirectResponse(f"/playlist/{kind}", status_code=303)
    return RedirectResponse(f"/track/{track.id}?from={kind}", status_code=303)


def _back_kind(request: Request) -> Optional[str]:
    """Плейлист, из которого пришли на трек (для кнопок «назад» и «ещё случайный»)."""
    back = request.query_params.get("from")
    if back and (back.isdigit() or back == LIKES_KIND):
        return back
    return None


@app.get("/chordbook", response_class=HTMLResponse)
def chordbook(request: Request) -> Response:
    """Справочник аккордов: все виды аккордов от каждой ноты со схемами."""
    return templates.TemplateResponse(request, "chordbook.html", {})


@app.get("/track/{track_id}", response_class=HTMLResponse)
def track(request: Request, track_id: str) -> Response:
    """Страница трека. Аккорды подгружаются отдельно, чтобы страница открывалась сразу."""
    back = _back_kind(request)
    return templates.TemplateResponse(request, "track.html", {"track": yandex.get_track(track_id), "back": back})


@app.get("/track/{track_id}/chords", response_class=HTMLResponse)
def track_chords(request: Request, track_id: str, url: str = "") -> Response:
    """Блок с аккордами для страницы трека: ищет песню на сайтах с аккордами.

    Если передана ссылка url (её вставили вручную), аккорды берутся прямо с неё.
    """
    song = yandex.get_track(track_id)
    if url:
        result = sources.chords_from_url(url)
    else:
        result = sources.find_chords(song.artists, song.title)
    return templates.TemplateResponse(
        request, "chords.html", {"result": result, "track": song, "back": _back_kind(request)}
    )
