from qdrant_client import QdrantClient

from rag.config import settings


if __name__ == "__main__":
    qc = QdrantClient(url=settings.qdrant_url)

    cols = qc.get_collections()
    print(cols)
