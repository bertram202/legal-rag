"""Ручная проверка черновика вопросов.

Запуск: uv run python scripts/review_questions.py
Enter — принять, e — исправить вопрос, n — выкинуть, q — выйти (прогресс сохраняется).
Результат: eval/golden.jsonl
"""

import json
from pathlib import Path

CHUNKS = Path("data/processed/gk_chunks.jsonl")
DRAFT = Path("eval/golden_draft.jsonl")
GOLDEN = Path("eval/golden.jsonl")
REJECTED = Path("eval/golden_rejected.jsonl")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    texts = {c["chunk_id"]: c["text"] for c in read_jsonl(CHUNKS)}
    draft = read_jsonl(DRAFT)
    golden = read_jsonl(GOLDEN)
    seen = {r["chunk_id"] for r in golden} | {
        r["chunk_id"] for r in read_jsonl(REJECTED)
    }
    todo = [r for r in draft if r["chunk_id"] not in seen]
    next_id = len(golden) + 1

    print(f"Осталось проверить: {len(todo)}, уже в golden: {len(golden)}\n")

    for n, item in enumerate(todo, 1):
        print("=" * 80)
        print(f"[{n}/{len(todo)}] {item['type']} | {item['chunk_id']}")
        print(texts.get(item["chunk_id"], "(чанк не найден)")[:900])
        print("-" * 80)
        print("ВОПРОС:", item["question"])
        print("ОТВЕТ: ", item["answer"])

        choice = input("\n[Enter] принять  [e] исправить  [n] выкинуть  [q] выйти: ")
        choice = choice.strip().lower()

        if choice == "q":
            break
        if choice == "n":
            append(REJECTED, item)
            continue
        if choice == "e":
            new_q = input("Новый вопрос: ").strip()
            if new_q:
                item["question"] = new_q

        append(
            GOLDEN,
            {
                "id": f"q{next_id:03d}",
                "question": item["question"],
                "answer": item["answer"],
                "type": item["type"],
                "relevant_chunks": [item["chunk_id"]],
                "relevant_articles": [item["article_id"]],
            },
        )
        next_id += 1

    print(f"\nВ golden: {len(read_jsonl(GOLDEN))} вопросов → {GOLDEN}")


if __name__ == "__main__":
    main()
