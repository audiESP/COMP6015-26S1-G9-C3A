import unittest
from unittest.mock import patch

from rag.config import RagSettings
from rag.qdrant_store import QdrantKnowledgeStore


class QdrantStoreTest(unittest.TestCase):
    def test_client_is_reused_and_closed(self):
        settings = RagSettings(
            qdrant_url="https://qdrant.example",
            qdrant_api_key="test-key",
        )
        store = QdrantKnowledgeStore(settings)

        with patch("qdrant_client.QdrantClient") as client_factory:
            first = store.client
            second = store.client
            store.close()

        self.assertIs(first, second)
        client_factory.assert_called_once()
        first.close.assert_called_once()
        self.assertNotIn("client", store.__dict__)


if __name__ == "__main__":
    unittest.main()
