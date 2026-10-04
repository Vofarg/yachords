"""Приведение текста аккордов с разных сайтов к единому виду.

Каждый сайт размечает аккорды по-своему. Здесь всё сводится к одному формату:
песня — это список строк, строка — список кусочков «текст» или «аккорд».
Аккорд хранится отдельно, чтобы на странице его можно было подсветить
и транспонировать, не трогая слова.
"""

import re
from dataclasses import dataclass, field

# Метки, которыми парсеры обрамляют аккорд внутри обычного текста.
CHORD_START = "\x01"
CHORD_END = "\x02"

# Аккорд: нота (H — русское обозначение си), диез/бемоль, вид аккорда, бас через «/».
CHORD_RE = re.compile(
    r"^[A-H](?:#|b)?"
    r"(?:maj|min|m|M|dim|aug|sus|add|\+|-|°|ø|Δ|\d|\(|\)|#|b)*"
    r"(?:/[A-H](?:#|b)?)?$"
)
SECTION_RE = re.compile(
    r"^\s*\[?\s*(вступление|интро|intro|куплет|припев|бридж|проигрыш|кода|концовка|аутро|outro|"
    r"verse|chorus|bridge|pre-?chorus|предприпев|соло|solo|instrumental)[^\]]*\]?\s*:?\s*$",
    re.IGNORECASE,
)


@dataclass
class Token:
    """Кусочек строки: либо обычный текст, либо аккорд."""

    text: str
    is_chord: bool = False


@dataclass
class Line:
    """Строка песни. kind: chords — только аккорды, section — заголовок вроде «Припев», text — слова."""

    tokens: list[Token] = field(default_factory=list)
    kind: str = "text"


@dataclass
class ChordSheet:
    """Готовые аккорды песни: строки, список уникальных аккордов и откуда они взяты."""

    lines: list[Line]
    chords: list[str]
    source: str = ""
    url: str = ""


def is_chord(word: str) -> bool:
    """Похоже ли слово на аккорд (Am, F#m7, C/G, Hm и т.п.)."""
    return bool(CHORD_RE.match(word.strip()))


def is_chord_line(line: str) -> bool:
    """Строка из одних аккордов (допускаются разделители вроде «|» и «-»)."""
    words = [w for w in re.split(r"[\s|]+", line.strip()) if w and w not in {"-", "–", "x2", "х2", "(x2)"}]
    return bool(words) and all(is_chord(w) for w in words)


def mark_chord_lines(text: str) -> str:
    """Для сайтов без разметки: находит строки из одних аккордов и помечает каждый аккорд."""
    def mark(part: str) -> str:
        return re.sub(
            r"\S+",
            lambda m: f"{CHORD_START}{m.group(0)}{CHORD_END}" if is_chord(m.group(0)) else m.group(0),
            part,
        )

    result = []
    for line in text.split("\n"):
        label, colon, rest = line.partition(":")
        if is_chord_line(line):
            line = mark(line)
        elif colon and is_chord_line(rest):
            # Строки вида «Вступление: Am F C G».
            line = label + colon + mark(rest)
        result.append(line)
    return "\n".join(result)


def _tokenize(line: str) -> list[Token]:
    """Разбивает строку с метками на кусочки текста и аккорды."""
    tokens: list[Token] = []
    pattern = re.compile(re.escape(CHORD_START) + r"(.*?)" + re.escape(CHORD_END))
    pos = 0
    for match in pattern.finditer(line):
        if match.start() > pos:
            tokens.append(Token(line[pos:match.start()]))
        chord = match.group(1).strip()
        if is_chord(chord):
            tokens.append(Token(chord, is_chord=True))
        elif chord:
            tokens.append(Token(chord))
        pos = match.end()
    if pos < len(line):
        tokens.append(Token(line[pos:]))
    return tokens


def build_sheet(marked_text: str, source: str = "", url: str = "") -> ChordSheet | None:
    """Собирает аккорды песни из текста с метками. Возвращает None, если аккордов не нашлось."""
    text = marked_text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ").replace("\xa0", " ")
    lines: list[Line] = []
    unique: list[str] = []
    for raw in text.split("\n"):
        raw = raw.rstrip()
        tokens = _tokenize(raw)
        plain = "".join(t.text for t in tokens if not t.is_chord)
        chords = [t.text for t in tokens if t.is_chord]
        for chord in chords:
            if chord not in unique:
                unique.append(chord)
        if chords and not plain.strip(" |-–"):
            kind = "chords"
        elif not chords and SECTION_RE.match(plain):
            kind = "section"
            tokens = [Token(plain.strip().strip("[]").rstrip(":").strip().capitalize())]
        else:
            kind = "text"
        if kind != "section" and not plain.strip() and not chords and lines and lines[-1].kind == "section":
            continue  # пустая строка сразу после заголовка раздела
        lines.append(Line(tokens=tokens, kind=kind))

    # Убираем пустые строки в начале и в конце и сжимаем подряд идущие пустые.
    cleaned: list[Line] = []
    for line in lines:
        empty = not any(t.text.strip() for t in line.tokens)
        if empty and (not cleaned or not any(t.text.strip() for t in cleaned[-1].tokens)):
            continue
        cleaned.append(line)
    while cleaned and not any(t.text.strip() for t in cleaned[-1].tokens):
        cleaned.pop()

    if len(unique) < 2:
        return None
    return ChordSheet(lines=cleaned, chords=unique, source=source, url=url)


_BRACKETS_RE = re.compile(r"[\(\[].*?[\)\]]")
_FEAT_RE = re.compile(r"\s+(feat\.?|ft\.?|при участии)\s+.*$", re.IGNORECASE)


def clean_title(title: str) -> str:
    """Убирает из названия хвосты вроде «(Remastered 2009)» и «feat. …», мешающие поиску."""
    title = _BRACKETS_RE.sub("", title)
    title = _FEAT_RE.sub("", title)
    title = re.sub(r"\s+-\s+.*$", "", title)
    return " ".join(title.split())


def simplify(text: str) -> str:
    """Упрощает строку для сравнения: нижний регистр, ё→е, только буквы и цифры."""
    text = text.lower().replace("ё", "е")
    return " ".join(re.findall(r"[a-zа-я0-9]+", text))
