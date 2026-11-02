from rag.ingest.parse_gk import parse, split_lines, to_chunks

ROWS = [
    ("s3", "Часть первая"),
    ("s3", "Раздел I. Общие положения"),
    ("s3", "Глава 4. Юридические лица"),
    ("s3", "§ 6. Некоммерческие корпоративные организации"),
    ("s3", "3.1. Общественные движения"),
    ("s15", "Статья 123.7-1. Общественные движения"),
    ("s9header", "ГАРАНТ:"),
    ("s9", "См. комментарии к статье 123.7-1 ГК РФ"),
    ("s1", "1. Общественным движением признается объединение граждан."),
    ("s22header", "Информация об изменениях:"),
    ("s22", "Пункт 2 изменен с 1 марта 2023 г."),
    ("s1", "2. Утратил силу с 1 марта 2023 г."),
    ("s1", "3. К общественным движениям применяются правила."),
    ("s15", "Статья 124. Утратила силу."),
    ("s3", "Глава 5. Участие РФ"),
    ("s1", "Статья 125. Порядок участия"),
    ("s1", "Текст статьи 125."),
]


def test_parse_structure():
    arts = parse(ROWS)
    assert [a.number for a in arts] == ["123.7-1", "124", "125"]

    first = arts[0]
    assert first.part == 1
    assert first.chapter == "4. Юридические лица"
    assert first.paragraph == "§ 6. Некоммерческие корпоративные организации"
    assert first.subparagraph == "3.1. Общественные движения"
    assert first.lines == [
        "1. Общественным движением признается объединение граждан.",
        "3. К общественным движениям применяются правила.",
    ]


def test_statuses_and_headers_from_body_style():
    arts = parse(ROWS)
    assert arts[1].status == "repealed"
    assert arts[2].chapter == "5. Участие РФ"
    assert arts[2].paragraph is None
    assert arts[2].lines == ["Текст статьи 125."]


def test_chunk_ids_and_header():
    chunks = to_chunks(parse(ROWS)[0])
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "gk1-123.7-1"
    assert chunks[0]["text"].startswith("ГК РФ, часть 1, глава 4. Юридические лица")


def test_split_respects_points_and_limit():
    lines = [
        "1. " + "а" * 50,
        "продолжение пункта 1",
        "2. " + "б" * 50,
        "3. " + "в" * 50,
    ]
    pieces = split_lines(lines, max_chars=120)
    assert pieces[0] == ["1. " + "а" * 50, "продолжение пункта 1"]
    assert all(sum(len(x) + 1 for x in p) <= 120 for p in pieces)
    assert sum(len(p) for p in pieces) == len(lines)