from qdrant_client import QdrantClient

from rag.config import settings

qc = QdrantClient(url=settings.qdrant_url)

cols = qc.get_collections()
print(cols)
