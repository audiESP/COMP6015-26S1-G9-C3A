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
                    json={"models": [{"name": "llama3:latest", "capabilities": ["completion"]}]},
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
        self.assertEqual(payload["model"], "llama3:latest")
        self.assertTrue(payload["stream"])

    async def test_ollama_errors_are_explicit(self):
        def handler(request):
            return httpx.Response(503, text="Ollama unavailable", request=request)

        service = OllamaService(transport=httpx.MockTransport(handler))
        with self.assertRaises(OllamaServiceError):
            await service.generate_reply([("user", "Hello")])


class OllamaMessageTest(unittest.TestCase):
    def test_context_and_conversation_are_preserved(self):
        messages = _build_ollama_messages(
            [("user", "What should happen next?")],
            patient=SimpleNamespace(name="Jane", medications=["Warfarin"]),
            rag_context="## Retrieved Clinical Evidence\n[Source 1] Care guide",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Jane", messages[0]["content"])
        self.assertIn("Warfarin", messages[0]["content"])
        self.assertIn("[Source 1]", messages[0]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "What should happen next?"})


if __name__ == "__main__":
    unittest.main()
