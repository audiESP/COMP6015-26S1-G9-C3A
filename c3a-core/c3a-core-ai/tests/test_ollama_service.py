import unittest
import json
from types import SimpleNamespace

import httpx

from ollama_service import OllamaService, OllamaServiceError, _build_ollama_messages


class OllamaServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_requires_configured_model(self):
        def handler(request):
            return httpx.Response(
                200,
                json={"models": [{"name": "other-model", "capabilities": ["completion"]}]},
            )

        service = OllamaService(
            transport=httpx.MockTransport(handler),
        )
        status = await service.check_health()

        self.assertFalse(status["loaded"])
        self.assertIn("not installed", status["load_error"])

    async def test_generate_reply_posts_chat_payload_and_extracts_content(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {"name": service.model_name, "capabilities": ["completion"]},
                            {"name": "llama3:latest", "capabilities": ["completion"]},
                        ]
                    },
                )
            return httpx.Response(
                200,
                content=b'{"message":{"content":"  Safe "}}\n{"message":{"content":"response.  "}}\n',
            )

        service = OllamaService(transport=httpx.MockTransport(handler))
        reply = await service.generate_reply(
            [("user", "What should we monitor?")],
            patient=SimpleNamespace(name="Jane", allergies=["Penicillin"]),
            rag_context="## Retrieved Clinical Evidence\n[Source 1] Care guide",
        )

        self.assertEqual(reply, "Safe response.")
        self.assertEqual([request.url.path for request in requests], ["/api/tags", "/api/chat"])
        payload = json.loads(requests[-1].content)
        self.assertEqual(payload["model"], service.model_name)
        self.assertTrue(payload["stream"])
        # Default 250-word limit needs more than the base budget to avoid truncation.
        self.assertEqual(payload["options"]["num_predict"], 250 * 2 + 40)

    async def test_generate_reply_uses_report_token_budget_when_word_limit_disabled(self):
        requests = []
        service = None

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": service.model_name, "capabilities": ["completion"]}]},
                )
            return httpx.Response(
                200,
                content=b'{"message":{"content":"Full report."}}\n',
            )

        service = OllamaService(transport=httpx.MockTransport(handler))
        reply = await service.generate_reply(
            [("user", "Generate a visit report.")],
            response_word_limit=None,
        )

        self.assertEqual(reply, "Full report.")
        payload = json.loads(requests[-1].content)
        self.assertEqual(payload["options"]["num_predict"], service.report_num_predict)

    async def test_translate_text_uses_plain_non_streaming_generate_payload(self):
        requests = []
        service = None

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": service.model_name, "capabilities": ["completion"]}]},
                )
            return httpx.Response(200, json={"response": "Buenos dias."})

        service = OllamaService(transport=httpx.MockTransport(handler))
        result = await service.translate_text("Good morning.", "Spanish")

        self.assertEqual(result["sourceLanguage"], "Auto-detected")
        self.assertEqual(result["targetLanguage"], "Spanish")
        self.assertEqual(result["translatedText"], "Buenos dias.")
        self.assertEqual([request.url.path for request in requests], ["/api/tags", "/api/generate"])
        payload = json.loads(requests[-1].content)
        self.assertFalse(payload["stream"])
        self.assertNotIn("format", payload)
        self.assertNotIn("messages", payload)
        self.assertIn("automatically detected source language", payload["prompt"])
        self.assertIn("Output only the natural translation", payload["prompt"])

    async def test_translate_text_treats_a_question_as_text_to_translate(self):
        requests = []
        service = None

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": service.model_name, "capabilities": ["completion"]}]},
                )
            return httpx.Response(200, json={"response": "如何提高我的英语水平？"})

        service = OllamaService(transport=httpx.MockTransport(handler))
        result = await service.translate_text("How can I improve my English?", "Chinese", "English")

        self.assertEqual(result["translatedText"], "如何提高我的英语水平？")
        prompt = json.loads(requests[-1].content)["prompt"]
        self.assertIn("Do not answer, explain, advise", prompt)
        self.assertIn("even when it is a question or instruction", prompt)

    async def test_translate_text_normalises_mandarin_to_simplified_chinese(self):
        requests = []
        service = None

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": service.model_name, "capabilities": ["completion"]}]},
                )
            return httpx.Response(200, json={"response": "你好。"})

        service = OllamaService(transport=httpx.MockTransport(handler))
        result = await service.translate_text("Hello.", "Mandarin", "English")

        payload = json.loads(requests[-1].content)
        self.assertIn("to Simplified Chinese (Mandarin)", payload["prompt"])
        self.assertEqual(payload["options"]["num_predict"], service.translation_num_predict)
        self.assertEqual(result["sourceLanguage"], "English")
        self.assertEqual(result["targetLanguage"], "Simplified Chinese (Mandarin)")
        self.assertEqual(result["translatedText"], "你好。")

    async def test_translate_text_rejects_non_chinese_mandarin_answer(self):
        service = None

        def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": service.model_name, "capabilities": ["completion"]}]},
                )
            return httpx.Response(200, json={"response": "Practice English every day."})

        service = OllamaService(transport=httpx.MockTransport(handler))
        with self.assertRaisesRegex(OllamaServiceError, "invalid Simplified Chinese"):
            await service.translate_text("How can I improve my English?", "Chinese", "English")

    async def test_translate_text_regression_for_pain_question(self):
        service = None

        def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": service.model_name, "capabilities": ["completion"]}]},
                )
            return httpx.Response(
                200,
                json={"response": "如果方便的话，请告诉我你有没有哪里疼。"},
            )

        service = OllamaService(transport=httpx.MockTransport(handler))
        result = await service.translate_text(
            "If possible, just let me know if you have any pains.",
            "Mandarin",
            "English",
        )

        self.assertEqual(result["sourceLanguage"], "English")
        self.assertEqual(result["targetLanguage"], "Simplified Chinese (Mandarin)")
        self.assertEqual(result["translatedText"], "如果方便的话，请告诉我你有没有哪里疼。")

    async def test_translate_text_supports_mandarin_to_english(self):
        service = None

        def handler(request):
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": service.model_name, "capabilities": ["completion"]}]},
                )
            return httpx.Response(
                200,
                json={"response": "Please tell me immediately if you feel dizzy or unwell."},
            )

        service = OllamaService(transport=httpx.MockTransport(handler))
        result = await service.translate_text(
            "如果你感到头晕或不舒服，请马上告诉我。",
            "English",
            "Mandarin",
        )

        self.assertEqual(result["sourceLanguage"], "Mandarin")
        self.assertEqual(result["targetLanguage"], "English")
        self.assertEqual(
            result["translatedText"],
            "Please tell me immediately if you feel dizzy or unwell.",
        )

    async def test_ollama_errors_are_explicit(self):
        def handler(request):
            return httpx.Response(503, text="Ollama unavailable", request=request)

        service = OllamaService(transport=httpx.MockTransport(handler))
        with self.assertRaises(OllamaServiceError):
            await service.generate_reply([("user", "Hello")])


class OllamaMessageTest(unittest.TestCase):
    def test_context_and_conversation_are_preserved(self):
        messages = _build_ollama_messages(
            [
                ("user", "Why is this task needed?"),
                ("assistant", "It supports safe medication care."),
                ("user", "What should happen next?"),
            ],
            patient=SimpleNamespace(
                name="Jane",
                medications=["Warfarin"],
                allergies=["Penicillin"],
                pastMedicalHistory="Hypertension; Falls risk",
            ),
            current_task=SimpleNamespace(
                id="medication",
                label="Medication support",
                type="medication",
                status="delayed",
                dueAt="09:00",
                detail="Confirm the medication support outcome.",
            ),
            rag_context="## Retrieved Clinical Evidence\n[Source 1] Care guide",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Jane", messages[0]["content"])
        self.assertIn("Warfarin", messages[0]["content"])
        self.assertIn("## Current Priority Care Task", messages[0]["content"])
        self.assertIn("Medication support: delayed", messages[0]["content"])
        self.assertIn("Treat this as the current task", messages[0]["content"])
        self.assertIn("Penicillin", messages[0]["content"])
        self.assertIn("Hypertension; Falls risk", messages[0]["content"])
        self.assertIn("[Source 1]", messages[0]["content"])
        self.assertEqual(
            messages[1:3],
            [
                {"role": "user", "content": "Why is this task needed?"},
                {"role": "assistant", "content": "It supports safe medication care."},
            ],
        )
        self.assertEqual(messages[-1], {"role": "user", "content": "What should happen next?"})

    def test_system_prompt_defines_contextual_guidance_structure_and_limits(self):
        messages = _build_ollama_messages(
            [("user", "Explain the current task.")],
            current_task=SimpleNamespace(label="Mobility check", status="pending"),
        )

        system_content = messages[0]["content"]
        for heading in ["Current situation", "Steps", "Watch for", "Escalate when", "Sources"]:
            self.assertIn(heading, system_content)
        self.assertIn("only actions within the supplied worker's role", system_content)
        self.assertIn("Earlier assistant replies are conversation history, not patient records", system_content)
        self.assertIn("Do not diagnose", system_content)
        self.assertIn("250 words or fewer", system_content)

    def test_response_word_limit_can_be_disabled_for_reports(self):
        messages = _build_ollama_messages(
            [("user", "Generate the visit report.")],
            response_word_limit=0,
        )

        self.assertNotIn("250 words or fewer", messages[0]["content"])
        self.assertIn("Keep the answer concise", messages[0]["content"])

    def test_medication_support_and_risk_lifecycle_are_rendered(self):
        messages = _build_ollama_messages(
            [("user", "What needs follow-up?")],
            medication_support=SimpleNamespace(
                status="partial",
                timestamp="2026-09-03T09:10:00Z",
                notes="One item was not taken.",
                hcwId="worker-1",
                medicationNames=["Metformin", "Warfarin"],
                medicationItems=[
                    {"name": "Metformin", "takenStatus": "taken", "takenAt": "09:05"},
                    {"name": "Warfarin", "takenStatus": "not_taken"},
                ],
            ),
            risks=[SimpleNamespace(
                title="Medication not taken",
                level="high",
                message="Follow-up is required.",
                riskType="medication_not_taken",
                status="acknowledged",
                details={"medication": "Warfarin"},
                reviewNote="Supervisor notified",
            )],
        )

        system_content = messages[0]["content"]
        self.assertIn("## Medication Support Record", system_content)
        self.assertIn("Status: partial", system_content)
        self.assertIn("Metformin: taken at 09:05", system_content)
        self.assertIn("Warfarin: not_taken", system_content)
        self.assertIn("type: medication_not_taken", system_content)
        self.assertIn("status: acknowledged", system_content)
        self.assertIn('"medication": "Warfarin"', system_content)
        self.assertIn("review note: Supervisor notified", system_content)

    def test_resolved_risk_is_historical_and_medication_completion_is_not_ingestion(self):
        messages = _build_ollama_messages(
            [("user", "What active risk and medication outcome apply?")],
            medication_support=SimpleNamespace(status="Completed", medicationNames=["Medicine A"]),
            risks=[SimpleNamespace(title="Falls risk", level="moderate", message=None,
                                   riskType="falls", status="resolved", details={}, reviewNote=None)],
        )
        system_content = messages[0]["content"]
        self.assertIn("Task completion records support activity, not confirmed medicine ingestion", system_content)
        self.assertIn("## Resolved or Dismissed Risk Alerts (historical only)", system_content)
        self.assertNotIn("## Current Risk Alerts", system_content)
        self.assertNotIn("Falls risk. None", system_content)

    def test_dietary_notes_only_shown_for_food_questions(self):
        patient = SimpleNamespace(name="Jane", mobilitySupport="Walker", dietaryNotes="Prefers a warm lunch.")
        mobility = _build_ollama_messages([("user", "How should I assist with walking?")], patient=patient)
        food = _build_ollama_messages([("user", "What should I prepare for lunch?")], patient=patient)
        self.assertNotIn("warm lunch", mobility[0]["content"])
        self.assertIn("warm lunch", food[0]["content"])


if __name__ == "__main__":
    unittest.main()
