"""Черновик золотого датасета

Запуск: uv run python scripts/generate_questions.py
Результат: eval/golden_draft.jsonl
"""

import json
import random
import re
from collections import Counter
from pathlib import Path

from openai import OpenAI

from rag.config import settings

CHUNKS = Path("data/processed/gk_chunks.jsonl")
DRAFT = Path("eval/golden_draft.jsonl")
SEED = 42
PLAN = {"бытовой": 60, "юридический": 45, "по номеру": 15}
MIN_CHARS = 300

TYPE_RULES = {
    "бытовой": (
        "Вопрос задаёт обычный человек без юридического образования: своими словами, "
        "через жизненную ситуацию, без юридических терминов из текста и без номера статьи."
    ),
    "юридический": (
        "Вопрос задаёт юрист: можно использовать термины, но не копируй формулировки "
        "текста дословно и не упоминай номер статьи."
    ),
    "по номеру": (
        "Вопрос прямо ссылается на номер статьи, например: «Что сказано в статье 615 ГК РФ "
        "о ...?» или «Какие требования устанавливает ст. 160 ГК?»."
    ),
}

SYSTEM = (
    "Ты помогаешь собрать тестовый набор вопросов для поиска по Гражданскому кодексу РФ. "
    "Отвечай только JSON без пояснений."
)

PROMPT = """Фрагмент Гражданского кодекса:
---
{text}
---

Придумай один вопрос, на который отвечает этот фрагмент.
{rule}
Вопрос должен быть конкретным и иметь ответ именно в этом фрагменте. Не пиши «в этом фрагменте» или «в тексте».
Ответ — 1–2 предложения строго по фрагменту.

Верни JSON: {{"question": "...", "answer": "..."}} /no_think"""


def article_id(chunk: dict) -> str:
    return f"gk{chunk['part']}-{chunk['article']}"


def ask(client: OpenAI, text: str, qtype: str) -> dict | None:
    resp = client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.7,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": PROMPT.format(text=text, rule=TYPE_RULES[qtype]),
            },
        ],
    )
    content = resp.choices[0].message.content or ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not data.get("question") or not data.get("answer"):
        return None
    return {"question": data["question"].strip(), "answer": data["answer"].strip()}


def pick_chunks(chunks: list[dict], total: int) -> list[dict]:
    pool = [
        c for c in chunks if c["status"] == "active" and len(c["text"]) >= MIN_CHARS
    ]
    rng = random.Random(SEED)
    by_part: dict[int, list[dict]] = {}
    for c in pool:
        by_part.setdefault(c["part"], []).append(c)

    picked = []
    for items in by_part.values():
        k = round(total * len(items) / len(pool))
        picked += rng.sample(items, min(k, len(items)))
    if len(picked) < total:
        chosen = {c["chunk_id"] for c in picked}
        rest = [c for c in pool if c["chunk_id"] not in chosen]
        picked += rng.sample(rest, total - len(picked))
    rng.shuffle(picked)
    return picked[:total]


def main() -> None:
    chunks = [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]
    total = sum(PLAN.values())
    picked = pick_chunks(chunks, total)
    types = [t for t, n in PLAN.items() for _ in range(n)]
    random.Random(SEED).shuffle(types)

    done = set()
    if DRAFT.exists():
        done = {json.loads(line)["chunk_id"] for line in DRAFT.open(encoding="utf-8")}

    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value() or "none",
    )

    DRAFT.parent.mkdir(parents=True, exist_ok=True)
    ok = failed = 0
    with DRAFT.open("a", encoding="utf-8") as fh:
        for i, (chunk, qtype) in enumerate(zip(picked, types, strict=False), 1):
            if chunk["chunk_id"] in done:
                continue
            result = None
            for _ in range(2):
                result = ask(client, chunk["text"], qtype)
                if result:
                    break
            if not result:
                failed += 1
                print(f"[{i}/{total}] {chunk['chunk_id']}: не получилось")
                continue
            record = {
                "chunk_id": chunk["chunk_id"],
                "article_id": article_id(chunk),
                "type": qtype,
                **result,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            ok += 1
            print(f"[{i}/{total}] {qtype}: {result['question']}")

    print(f"\nГотово: {ok}, ошибок: {failed} → {DRAFT}")
    if DRAFT.exists():
        types_done = Counter(
            json.loads(line)["type"] for line in DRAFT.open(encoding="utf-8")
        )
        print("По типам:", dict(types_done))


if __name__ == "__main__":
    main()
