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
        self.assertEqual(payload["options"]["num_predict"], service.num_predict)

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

    async def test_translate_text_detects_language_and_posts_non_streaming_payload(self):
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
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "sourceLanguage": "English",
                                "targetLanguage": "Spanish",
                                "translatedText": "Buenos dias.",
                            }
                        )
                    }
                },
            )

        service = OllamaService(transport=httpx.MockTransport(handler))
        result = await service.translate_text("Good morning.", "Spanish")

        self.assertEqual(result["sourceLanguage"], "English")
        self.assertEqual(result["targetLanguage"], "Spanish")
        self.assertEqual(result["translatedText"], "Buenos dias.")
        self.assertEqual([request.url.path for request in requests], ["/api/tags", "/api/chat"])
        payload = json.loads(requests[-1].content)
        self.assertFalse(payload["stream"])
        self.assertIn("Detect the source language", payload["messages"][1]["content"])

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
        self.assertIn("Do not diagnose", system_content)
        self.assertIn("250 words or fewer", system_content)

    def test_response_word_limit_can_be_disabled_for_reports(self):
        messages = _build_ollama_messages(
            [("user", "Generate the visit report.")],
            response_word_limit=0,
        )

        self.assertNotIn("250 words or fewer", messages[0]["content"])
        self.assertIn("Keep the answer concise", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
