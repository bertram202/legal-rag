"""Разбор ГК РФ из .odt (выгрузка Гаранта) в чанки по статьям.

Запуск: uv run python -m rag.ingest.parse_gk
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

RAW_DIR = Path("data/raw")
OUT_FILE = Path("data/processed/gk_chunks.jsonl")
MAX_CHARS = 2000

TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"

PART_WORDS = {"первая": 1, "вторая": 2, "третья": 3, "четвертая": 4, "четвёртая": 4}

RE_PART = re.compile(r"^Часть\s+(\S+)$", re.IGNORECASE)
RE_SECTION = re.compile(r"^Раздел\s+([IVXLC]+)\.?\s*(.*)$")
RE_SUBSECTION = re.compile(r"^Подраздел\s+(\d+)\.?\s*(.*)$")
RE_CHAPTER = re.compile(r"^Глава\s+(\d+(?:\.\d+)?)\.?\s*(.*)$")
RE_PARAGRAPH = re.compile(r"^§\s*(\d+(?:\.\d+)?)\.?\s*(.*)$")
RE_SUBPARAGRAPH = re.compile(r"^(\d+(?:\.\d+)?)\.\s+(.*)$")
RE_ARTICLE = re.compile(r"^Статья\s+(\d+(?:[.-]\d+)*)\.?\s*(.*)$")
RE_POINT = re.compile(r"^\d+(?:\.\d+)*\.\s")
RE_REPEALED = re.compile(r"утратил[аио]?\s+силу", re.IGNORECASE)
RE_REPEALED_LINE = re.compile(
    r"^(?:(?:Абзац|Подпункт|Пункт|Часть)\b[^.]{0,40}|\d+(?:\.\d+)*\.)\s*утратил[аио]?\s+силу",
    re.IGNORECASE,
)


@dataclass
class Article:
    part: int
    section: str | None
    subsection: str | None
    chapter: str | None
    paragraph: str | None
    subparagraph: str | None
    number: str
    title: str
    status: str = "active"
    lines: list[str] = field(default_factory=list)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def read_odt(path: Path) -> list[tuple[str, str]]:
    root = ET.fromstring(zipfile.ZipFile(path).read("content.xml"))
    rows = []
    for el in root.iter():
        if el.tag in (TEXT_NS + "p", TEXT_NS + "h"):
            text = clean("".join(el.itertext()))
            if text:
                rows.append((el.get(TEXT_NS + "style-name") or "", text))
    return rows


def role(style: str) -> str:
    if style == "s3":
        return "heading"
    if style == "s15":
        return "article"
    if style.startswith(("s1_right", "s16")):
        return "skip"
    if style == "s1" or style.startswith(("s1_", "s7")):
        return "body"
    return "skip"


def parse(rows: list[tuple[str, str]]) -> list[Article]:
    state: dict[str, str | None] = dict.fromkeys(
        ["section", "subsection", "chapter", "paragraph", "subparagraph"]
    )
    part = 0
    articles: list[Article] = []
    current: Article | None = None

    def start_article(number: str, title: str) -> Article:
        art = Article(
            part=part,
            section=state["section"],
            subsection=state["subsection"],
            chapter=state["chapter"],
            paragraph=state["paragraph"],
            subparagraph=state["subparagraph"],
            number=number,
            title=title,
        )
        if RE_REPEALED.search(title):
            art.status = "repealed"
        articles.append(art)
        return art

    for style, text in rows:
        r = role(style)

        if r == "body" and RE_ARTICLE.match(text):
            r = "article"

        if r == "heading":
            current = None
            if m := RE_PART.match(text):
                part = PART_WORDS.get(m.group(1).lower(), part)
                state = dict.fromkeys(state)
            elif m := RE_SECTION.match(text):
                state = dict.fromkeys(state) | {"section": f"{m[1]}. {m[2]}".strip()}
            elif m := RE_SUBSECTION.match(text):
                state |= {
                    "subsection": f"{m[1]}. {m[2]}",
                    "chapter": None,
                    "paragraph": None,
                    "subparagraph": None,
                }
            elif m := RE_CHAPTER.match(text):
                state |= {
                    "chapter": f"{m[1]}. {m[2]}",
                    "paragraph": None,
                    "subparagraph": None,
                }
            elif m := RE_PARAGRAPH.match(text):
                state |= {"paragraph": f"§ {m[1]}. {m[2]}", "subparagraph": None}
            elif m := RE_SUBPARAGRAPH.match(text):
                state |= {"subparagraph": f"{m[1]}. {m[2]}"}
        elif r == "article":
            m = RE_ARTICLE.match(text)
            if m:
                current = start_article(m[1], m[2])
        elif r == "body" and current is not None:
            if RE_REPEALED_LINE.match(text):
                continue
            current.lines.append(text)

    return articles


def header(art: Article) -> str:
    parts = [f"ГК РФ, часть {art.part}"]
    if art.chapter:
        parts.append(f"глава {art.chapter}")
    if art.paragraph:
        parts.append(art.paragraph)
    if art.subparagraph:
        parts.append(art.subparagraph)
    parts.append(f"статья {art.number}. {art.title}".strip())
    return ", ".join(parts)


def split_lines(lines: list[str], max_chars: int) -> list[list[str]]:
    groups: list[list[str]] = []
    for line in lines:
        if not groups or RE_POINT.match(line):
            groups.append([line])
        else:
            groups[-1].append(line)

    chunks: list[list[str]] = []
    buf: list[str] = []
    size = 0
    for group in groups:
        group_size = sum(len(x) + 1 for x in group)
        if buf and size + group_size > max_chars:
            chunks.append(buf)
            buf, size = [], 0
        if group_size > max_chars:
            for line in group:
                if buf and size + len(line) + 1 > max_chars:
                    chunks.append(buf)
                    buf, size = [], 0
                buf.append(line)
                size += len(line) + 1
        else:
            buf.extend(group)
            size += group_size
    if buf:
        chunks.append(buf)
    return chunks


def to_chunks(art: Article, max_chars: int = MAX_CHARS) -> list[dict]:
    base_id = f"gk{art.part}-{art.number}"
    meta = asdict(art)
    meta.pop("lines")
    meta["article"] = meta.pop("number")
    meta["article_title"] = meta.pop("title")
    head = header(art)

    if art.status == "repealed" or not art.lines:
        return [
            {
                "chunk_id": base_id,
                "chunk_index": 0,
                "chunk_count": 1,
                **meta,
                "text": head,
            }
        ]

    pieces = split_lines(art.lines, max_chars)
    result = []
    for i, piece in enumerate(pieces):
        chunk_id = base_id if len(pieces) == 1 else f"{base_id}-c{i + 1}"
        result.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": i,
                "chunk_count": len(pieces),
                **meta,
                "text": head + "\n" + "\n".join(piece),
            }
        )
    return result


def main() -> None:
    files = sorted(RAW_DIR.glob("*.odt"))
    if not files:
        raise SystemExit(f"Нет .odt файлов в {RAW_DIR}")

    articles: list[Article] = []
    for f in files:
        parsed = parse(read_odt(f))
        print(f"{f.name}: статей {len(parsed)}")
        articles.extend(parsed)

    chunks = [c for art in articles for c in to_chunks(art)]

    ids = [c["chunk_id"] for c in chunks]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"Повторяющиеся chunk_id: {sorted(dupes)[:10]}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    repealed = sum(a.status == "repealed" for a in articles)
    print(f"Всего статей: {len(articles)}, утратили силу: {repealed}")
    print(f"Чанков: {len(chunks)} → {OUT_FILE}")


if __name__ == "__main__":
    main()