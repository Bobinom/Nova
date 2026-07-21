import unittest
from unittest.mock import Mock, patch

import requests

from nova.llm.ollama import OllamaService


class OllamaServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = OllamaService(model="test-model", timeout=5)

    @patch("nova.llm.ollama.requests.post")
    def test_chat_request_message_order_and_response(self, post):
        response = Mock()
        response.json.return_value = {"message": {"content": "  Answer  "}}
        post.return_value = response

        result = self.service.generate(
            "System instructions",
            [
                {"role": "user", "content": "Prior question"},
                {"role": "assistant", "content": "Prior answer"},
                {"role": "user", "content": "Current question"},
            ],
            "Current question",
        )

        self.assertEqual(result, "Answer")
        post.assert_called_once_with(
            "http://localhost:11434/api/chat",
            json={
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "System instructions"},
                    {"role": "user", "content": "Prior question"},
                    {"role": "assistant", "content": "Prior answer"},
                    {"role": "user", "content": "Current question"},
                ],
                "stream": False,
            },
            timeout=5,
        )
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(
            sum(message["content"] == "Current question" for message in messages),
            1,
        )

    @patch("nova.llm.ollama.requests.post")
    def test_unsupported_history_role_is_normalized(self, post):
        response = Mock()
        response.json.return_value = {"message": {"content": "Answer"}}
        post.return_value = response

        self.service.generate(
            "System",
            [{"role": "tool", "content": "Tool output"}],
            "Question",
        )

        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(messages[1], {"role": "user", "content": "Tool output"})

    @patch("nova.llm.ollama.requests.post")
    def test_connection_error(self, post):
        post.side_effect = requests.ConnectionError()
        result = self.service.generate("System", [], "Question")
        self.assertIn("couldn't connect", result)

    @patch("nova.llm.ollama.requests.post")
    def test_timeout(self, post):
        post.side_effect = requests.Timeout()
        result = self.service.generate("System", [], "Question")
        self.assertEqual(result, "Ollama took too long to respond.")

    @patch("nova.llm.ollama.requests.post")
    def test_http_error(self, post):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("500 error")
        post.return_value = response
        result = self.service.generate("System", [], "Question")
        self.assertEqual(result, "Ollama request failed: 500 error")

    @patch("nova.llm.ollama.requests.post")
    def test_malformed_json(self, post):
        response = Mock()
        response.json.side_effect = ValueError()
        post.return_value = response
        result = self.service.generate("System", [], "Question")
        self.assertEqual(result, "Ollama returned an invalid response.")

    @patch("nova.llm.ollama.requests.post")
    def test_unexpected_json_shape(self, post):
        response = Mock()
        response.json.return_value = []
        post.return_value = response
        result = self.service.generate("System", [], "Question")
        self.assertEqual(result, "Ollama returned an invalid response.")

    @patch("nova.llm.ollama.requests.post")
    def test_ollama_error(self, post):
        response = Mock()
        response.json.return_value = {"error": "model unavailable"}
        post.return_value = response
        result = self.service.generate("System", [], "Question")
        self.assertEqual(result, "Ollama error: model unavailable")

    @patch("nova.llm.ollama.requests.post")
    def test_empty_response(self, post):
        response = Mock()
        response.json.return_value = {"message": {"content": "  "}}
        post.return_value = response
        result = self.service.generate("System", [], "Question")
        self.assertEqual(result, "Ollama returned an empty response.")


if __name__ == "__main__":
    unittest.main()
