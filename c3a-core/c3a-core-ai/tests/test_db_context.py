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

    async def test_unlinked_this_patient_query_does_not_sample_other_patients(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://configured"}):
            retriever = DbContextRetriever()
        with patch.object(retriever, "_retrieve_sync") as retrieve_sync:
            result = await retriever.retrieve("What medicines does this patient take?")
        retrieve_sync.assert_not_called()
        self.assertFalse(result.metadata["used_for_chat"])

    async def test_missing_patient_id_does_not_fall_back_to_sample_rows(self):
        from contextlib import contextmanager
        from unittest.mock import MagicMock

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://configured"}):
            retriever = DbContextRetriever()
        cursor = MagicMock()
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        @contextmanager
        def fake_connection():
            yield connection

        with patch.object(retriever, "_connection", fake_connection), patch.object(
            retriever, "_run_query", return_value=[]
        ) as run_query:
            result = retriever._retrieve_sync(
                "What medicines does this patient take?",
                PATIENT.id,
                ["patients", "medications"],
            )
        self.assertEqual(run_query.call_count, 1)
        self.assertEqual(result.context, "")
        self.assertEqual(result.metadata["result_counts"], {"patients": 0})


if __name__ == "__main__":
    unittest.main()
