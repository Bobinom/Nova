import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from nova.core.settings import SettingsManager
from nova.llm.openai import CloudBrainError, OpenAIService
from nova.llm.router import BrainRouter


class FakeKeychain:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLocal:
    model = "local-test"

    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, history, prompt):
        self.calls.append((system_prompt, history, prompt))
        return "local answer"


class CloudBrainTests(unittest.TestCase):
    @patch("nova.llm.openai.requests.post")
    def test_responses_api_request_and_output_parsing(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "Cloud answer"}],
            }]
        }
        post.return_value = response
        service = OpenAIService(FakeKeychain("secret"), model="test-model")

        result = service.generate(
            "system", [{"role": "user", "content": "Earlier"}], "Hello"
        )

        self.assertEqual(result, "Cloud answer")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "test-model")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["input"][-1]["content"], "Hello")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer secret"
        )

    def test_missing_key_is_a_safe_cloud_error(self):
        with self.assertRaisesRegex(CloudBrainError, "not connected"):
            OpenAIService(FakeKeychain()).generate("system", [], "Hello")

    def test_hybrid_falls_back_to_local_when_cloud_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings.load()
            local = FakeLocal()
            cloud = OpenAIService(FakeKeychain("secret"))
            router = BrainRouter(settings, local, cloud)
            with patch(
                "nova.llm.openai.requests.post",
                side_effect=requests.ConnectionError("offline"),
            ):
                result = router.generate("system", [], "Hello")

            self.assertEqual(result, "local answer")
            self.assertEqual(router.status()["last_provider"], "ollama-fallback")

    def test_cloud_mode_does_not_silently_use_local(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings.load()
            settings.set("brain.mode", "cloud")
            local = FakeLocal()
            router = BrainRouter(settings, local, OpenAIService(FakeKeychain()))

            result = router.generate("system", [], "Hello")

            self.assertIn("not connected", result)
            self.assertEqual(local.calls, [])

    def test_configure_stores_key_and_selects_hybrid(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsManager(Path(directory) / "settings.json")
            settings.load()
            keychain = FakeKeychain()
            router = BrainRouter(settings, FakeLocal(), OpenAIService(keychain))

            router.configure("new-secret")

            self.assertEqual(keychain.value, "new-secret")
            self.assertEqual(settings.get("brain.mode"), "hybrid")
            self.assertNotIn("secret", str(router.status()))


if __name__ == "__main__":
    unittest.main()
