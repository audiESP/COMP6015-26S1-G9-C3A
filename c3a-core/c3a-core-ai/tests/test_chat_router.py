import unittest
from types import SimpleNamespace

from chat_router import decide_route


PATIENT = SimpleNamespace(
    id="11111111-1111-1111-1111-111111111111",
    name="Jane Smith",
)


class ChatRouterTest(unittest.TestCase):
    def test_patient_record_overlap_routes_to_database_only(self):
        decision = decide_route("What medications does this patient take?", PATIENT)

        self.assertEqual(decision.mode, "database_only")
        self.assertTrue(decision.uses_db)
        self.assertFalse(decision.uses_rag)
        self.assertIn("patient_context_id", decision.matched_signals)
        self.assertIn("patient_record_term", decision.matched_signals)

    def test_general_guidance_overlap_routes_to_rag_only(self):
        decision = decide_route("What are safe medication management steps for an older adult at home?")

        self.assertEqual(decision.mode, "rag_only")
        self.assertFalse(decision.uses_db)
        self.assertTrue(decision.uses_rag)
        self.assertIn("guideline_phrase", decision.matched_signals)

    def test_patient_fact_plus_action_routes_to_hybrid(self):
        decision = decide_route(
            "Given this patient's medications, what should the care worker monitor today?",
            PATIENT,
        )

        self.assertEqual(decision.mode, "hybrid")
        self.assertTrue(decision.uses_db)
        self.assertTrue(decision.uses_rag)
        self.assertIn("workflow_action_phrase", decision.matched_signals)

    def test_overlap_without_enough_intent_routes_to_uncertain(self):
        decision = decide_route("Show fall risk for residents")

        self.assertEqual(decision.mode, "uncertain")
        self.assertTrue(decision.uses_db)
        self.assertTrue(decision.uses_rag)
        self.assertIn("ambiguous_overlap_phrase", decision.matched_signals)

    def test_smalltalk_routes_to_direct_ai(self):
        decision = decide_route("Hello, what can you do?")

        self.assertEqual(decision.mode, "direct_ai")
        self.assertFalse(decision.uses_db)
        self.assertFalse(decision.uses_rag)


if __name__ == "__main__":
    unittest.main()
