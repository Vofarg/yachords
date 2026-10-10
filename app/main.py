"""Сайт: адреса страниц и что на каждой показывается."""

import logging
import os
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

from app import auth, music_link, yandex, yandex_id  # noqa: E402  (настройки из .env должны загрузиться раньше)
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

PUBLIC_PATHS = ("/login", "/auth/", "/logout", "/static/", "/healthz")
# Страницы, которые открываются и без подключённой Яндекс.Музыки.
NO_MUSIC_PATHS = ("/connect", "/chordbook")
# Адрес ссылки с QR-кода, по которой телефон получает уже подключённую Музыку.
PHONE_PATH = "/connect/phone"
# Куда вернуть человека после входа через Яндекс ID (только ссылка для телефона).
NEXT_COOKIE = "yachords_next"


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Пускает на страницы сайта только вошедших и решает, чьи плейлисты им показывать."""
    request.state.login = None
    request.state.can_logout = False
    request.state.music = None
    path = request.url.path
    if path.startswith(PUBLIC_PATHS):
        return await call_next(request)
    login = auth.current_login(request.cookies.get(auth.COOKIE_NAME))
    if login is None:
        if path == PHONE_PATH:
            # Ссылку с QR-кода откроем снова сразу после входа.
            return RedirectResponse(f"/login?next={quote(str(request.url.path) + '?' + request.url.query)}", status_code=303)
        return RedirectResponse("/login", status_code=303)
    request.state.login = login
    request.state.can_logout = auth.login_required()
    token = music_link.unseal(login, request.cookies.get(music_link.COOKIE_NAME))
    if token:
        # Человек подключил свою Музыку: показываем его плейлисты.
        yandex.use_token(token, settings_allowed=False)
        request.state.music = "own"
    elif auth.is_owner(login):
        yandex.use_token(None)
        request.state.music = "settings"
    else:
        # Друзьям токен владельца из настроек не достаётся никогда.
        yandex.use_token(None, settings_allowed=False)
        if not path.startswith(NO_MUSIC_PATHS):
            return RedirectResponse("/connect", status_code=303)
    return await call_next(request)


def _is_https(request: Request) -> bool:
    """Открыт ли сайт по https. На Render это видно по заголовку от его прокси."""
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _set_cookie(request: Request, response: Response, name: str, value: str, max_age: int) -> None:
    """Ставит cookie, недоступную скриптам страницы и (на https) передаваемую только по https."""
    response.set_cookie(name, value, max_age=max_age, httponly=True, samesite="lax", secure=_is_https(request))


def _site_url(request: Request) -> str:
    """Адрес сайта, например https://yachords.onrender.com."""
    scheme = "https" if _is_https(request) else "http"
    return f"{scheme}://{request.url.netloc}"


def _callback_url(request: Request) -> str:
    """Адрес, на который Яндекс ID вернёт человека после входа.

    Он должен в точности совпадать с Redirect URI в настройках приложения на oauth.yandex.ru.
    """
    return f"{_site_url(request)}/auth/yandex/callback"


def _safe_next(value: Optional[str]) -> Optional[str]:
    """Куда вернуть человека после входа: только на ссылку для телефона, никуда больше."""
    if value and value.startswith(PHONE_PATH + "?"):
        return value
    return None


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
async def token_error(request: Request, exc: yandex.TokenError) -> Response:
    """Токен Яндекса не задан или истёк: показываем, как получить новый.

    Кто подключал Музыку сам, тот попадает на страницу подключения, чтобы вставить новый токен.
    Владельцу с токеном из настроек показывается инструкция для Render.
    """
    if getattr(request.state, "music", None) != "settings":
        response = RedirectResponse("/connect?expired=1", status_code=303)
        response.delete_cookie(music_link.COOKIE_NAME)
        return response
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


LOGIN_ERRORS = {
    "not_allowed": "Логина {login} нет в списке друзей сайта. Попросите владельца добавить его.",
    "failed": "Не получилось войти через Яндекс. Попробуйте ещё раз.",
    "cancelled": "Вход отменён. Чтобы открыть сайт, разрешите доступ на странице Яндекса.",
}


def _login_page(request: Request, error: str = "", login: str = "", status: int = 200) -> Response:
    """Страница входа: кнопка Яндекс ID или поле пароля, смотря что настроено."""
    message = LOGIN_ERRORS.get(error, "").format(login=login)
    next_url = _safe_next(request.query_params.get("next"))
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "yandex_id": yandex_id.configured(),
            "failed": False,
            "message": message,
            "next": quote(next_url) if next_url else "",
        },
        status_code=status,
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    """Страница входа. Если вход не нужен (ни Яндекс ID, ни пароля), сразу на главную."""
    if not yandex_id.configured() and auth.password() is None:
        return RedirectResponse("/", status_code=303)
    return _login_page(request)


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form("")) -> Response:
    """Проверяет общий пароль (работает, только пока не настроен Яндекс ID)."""
    session = None if yandex_id.configured() else auth.check_password(password)
    if session is None:
        logger.info("Неверный пароль на входе")
        return templates.TemplateResponse(
            request, "login.html", {"yandex_id": yandex_id.configured(), "failed": True, "message": ""}, status_code=401
        )
    response = RedirectResponse("/", status_code=303)
    _set_cookie(request, response, auth.COOKIE_NAME, session, auth.COOKIE_MAX_AGE)
    return response


@app.get("/auth/yandex")
def yandex_login(request: Request) -> Response:
    """Отправляет человека на страницу Яндекс ID, где он подтверждает вход."""
    if not yandex_id.configured():
        return RedirectResponse("/login", status_code=303)
    # Случайная метка защищает от подделки возврата: Яндекс вернёт её обратно, а мы сверим с cookie.
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(yandex_id.authorize_url(_callback_url(request), state), status_code=303)
    _set_cookie(request, response, auth.STATE_COOKIE, state, 600)
    next_url = _safe_next(request.query_params.get("next"))
    if next_url:
        _set_cookie(request, response, NEXT_COOKIE, next_url, 600)
    return response


@app.get("/auth/yandex/callback")
def yandex_callback(request: Request, code: str = "", state: str = "", error: str = "") -> Response:
    """Сюда Яндекс ID возвращает человека после входа: узнаём логин и пускаем, если он в списке."""
    if not yandex_id.configured():
        return RedirectResponse("/login", status_code=303)
    if error:
        logger.info("Вход через Яндекс ID отменён: %s", error)
        return _login_page(request, "cancelled", status=401)
    expected = request.cookies.get(auth.STATE_COOKIE)
    if not code or not expected or not secrets.compare_digest(state.encode(), expected.encode()):
        logger.warning("Возврат из Яндекс ID без кода или с чужой меткой")
        return _login_page(request, "failed", status=400)
    try:
        login = yandex_id.login_by_code(code)
    except yandex_id.YandexIdError:
        return _login_page(request, "failed", status=502)
    if not auth.is_allowed(login):
        logger.info("Вход отклонён: логина нет в списке друзей")
        return _login_page(request, "not_allowed", login=login, status=403)
    logger.info("Вход через Яндекс ID выполнен")
    response = RedirectResponse(_safe_next(request.cookies.get(NEXT_COOKIE)) or "/", status_code=303)
    response.delete_cookie(NEXT_COOKIE)
    _set_cookie(request, response, auth.COOKIE_NAME, auth.make_session(login), auth.COOKIE_MAX_AGE)
    response.delete_cookie(auth.STATE_COOKIE)
    return response


@app.get("/logout")
def logout() -> Response:
    """Выход: забываем cookie входа и подключённую Музыку на этом устройстве."""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME)
    response.delete_cookie(music_link.COOKIE_NAME)
    return response


CONNECT_ERRORS = {
    "no_token": "Не нашли токен в том, что вы вставили. Скопируйте весь адрес страницы, на которую перекинул Яндекс, "
    "он начинается с https://music.yandex.ru/ и содержит access_token=.",
    "rejected": "Яндекс.Музыка не приняла этот токен. Получите новый по кнопке в шаге 1 и вставьте ещё раз.",
    "yandex_down": "Яндекс.Музыка сейчас не ответила. Попробуйте ещё раз через минуту.",
    "no_key": "Сайт пока не настроен для подключения Музыки. Напишите владельцу сайта.",
    "phone_link": "Ссылка для телефона устарела или открыта под другим аккаунтом Яндекса. "
    "Откройте на компьютере страницу «Моя Музыка» и отсканируйте новый QR-код.",
}


def _connect_page(request: Request, error: str = "", status: int = 200) -> Response:
    """Страница «Моя Музыка»: инструкция и поле для токена или, если подключено, QR-код для телефона."""
    login = request.state.login
    connected = request.state.music == "own"
    phone_url = qr = None
    if connected:
        token = music_link.unseal(login, request.cookies.get(music_link.COOKIE_NAME))
        sealed = music_link.seal(login, token) if token else None
        if sealed:
            phone_url = f"{_site_url(request)}{PHONE_PATH}?t={quote(sealed)}"
            qr = music_link.qr_svg(phone_url)
    return templates.TemplateResponse(
        request,
        "connect.html",
        {
            "login": login if login != auth.OWNER else None,
            "connected": connected,
            "uses_settings": request.state.music == "settings",
            "expired": request.query_params.get("expired") == "1",
            "error": CONNECT_ERRORS.get(error, ""),
            "token_url": yandex.TOKEN_URL,
            "phone_url": phone_url,
            "qr": qr,
        },
        status_code=status,
    )


@app.get("/connect", response_class=HTMLResponse)
def connect(request: Request) -> Response:
    """Страница подключения своей Яндекс.Музыки с пошаговой инструкцией."""
    return _connect_page(request)


@app.post("/connect", response_class=HTMLResponse)
def connect_save(request: Request, token_text: str = Form("")) -> Response:
    """Принимает вставленный адрес или токен, проверяет его у Яндекса и запоминает в браузере."""
    token = music_link.extract_token(token_text)
    if token is None:
        return _connect_page(request, "no_token", 400)
    try:
        if not yandex.verify_token(token):
            return _connect_page(request, "rejected", 400)
    except yandex.YandexUnavailableError:
        return _connect_page(request, "yandex_down", 503)
    sealed = music_link.seal(request.state.login, token)
    if sealed is None:
        return _connect_page(request, "no_key", 500)
    logger.info("Пользователь подключил свою Яндекс.Музыку")
    response = RedirectResponse("/", status_code=303)
    _set_cookie(request, response, music_link.COOKIE_NAME, sealed, music_link.COOKIE_MAX_AGE)
    return response


@app.post("/connect/disconnect")
def connect_remove() -> Response:
    """Отключает Музыку на этом устройстве: забываем токен из cookie."""
    response = RedirectResponse("/connect", status_code=303)
    response.delete_cookie(music_link.COOKIE_NAME)
    return response


@app.get(PHONE_PATH)
def connect_phone(request: Request, t: str = "") -> Response:
    """Ссылка с QR-кода: переносит подключённую Музыку на телефон без повторной возни с токеном."""
    token = music_link.unseal(request.state.login, t, max_age=music_link.TRANSFER_SECONDS)
    if token is None:
        return _connect_page(request, "phone_link", 400)
    response = RedirectResponse("/", status_code=303)
    _set_cookie(request, response, music_link.COOKIE_NAME, t, music_link.COOKIE_MAX_AGE)
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
