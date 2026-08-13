import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from db_context import DbContextRetriever


PATIENT = SimpleNamespace(id="11111111-1111-1111-1111-111111111111")


class DbContextRetrieverTest(unittest.IsolatedAsyncioTestCase):
    async def test_patient_id_without_database_intent_does_not_query_all_tables(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://configured"}):
            retriever = DbContextRetriever()

        with patch.object(retriever, "_retrieve_sync") as retrieve_sync:
            result = await retriever.retrieve(
                "According to the restorative care pathway guide, what does it provide?",
                patient_context=PATIENT,
            )

        retrieve_sync.assert_not_called()
        self.assertEqual(result.context, "")
        self.assertEqual(result.metadata["matched_intents"], [])

    async def test_previous_progress_notes_trigger_encounter_intent(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://configured"}):
            retriever = DbContextRetriever()

        with patch.object(retriever, "_retrieve_sync") as retrieve_sync:
            await retriever.retrieve(
                "Retrieve the patient's previous progress notes.",
                patient_context=PATIENT,
            )

        retrieve_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
