from rag.config import settings


def test_qdrant_url():
    assert settings.qdrant_url.startswith("http")
