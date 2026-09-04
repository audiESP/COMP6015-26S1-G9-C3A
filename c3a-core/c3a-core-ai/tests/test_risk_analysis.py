import json
import unittest

from main import RiskAnalysisRequest, _parse_json_object, _risk_analysis_prompt


class RiskAnalysisTest(unittest.TestCase):
    def test_prompt_requires_confirmation_and_forbids_medication_changes(self):
        prompt = _risk_analysis_prompt(RiskAnalysisRequest(note="Patient declined medication support."))
        self.assertIn("requiresConfirmation", prompt)
        self.assertIn("Do not diagnose", prompt)
        self.assertIn("never recommend an additional dose", prompt)

    def test_parser_accepts_fenced_json(self):
        payload = _parse_json_object("```json\n{\"suggestions\": []}\n```")
        self.assertEqual(payload, {"suggestions": []})

    def test_parser_rejects_non_object(self):
        with self.assertRaises(ValueError):
            _parse_json_object("[]")


if __name__ == "__main__":
    unittest.main()
