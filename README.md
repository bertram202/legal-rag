# RAG-ассистент

Отвечает на вопросы по документам и показывает, откуда взят ответ.
Каждое улучшение поиска проверяется на тестовом наборе вопросов, результаты ниже.

## Стек

- Python
- Qdrant
- Docker

## Как запустить

```bash
uv sync
cp .env.example .env
docker compose up -d
uv run python scripts/check_qdrant.py
uv run pytest
```

Панель Qdrant: http://localhost:6333/dashboard

## Архитектура

Будет позже.

## Эксперименты

| Конфигурация | recall@5 | MRR | faithfulness |
|---|---|---|---|
| | | | |