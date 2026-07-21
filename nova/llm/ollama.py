from __future__ import annotations

from typing import Any

import requests

from nova.llm.service import LLMService


class OllamaService(LLMService):
    """Language model service backed by a local Ollama server."""

    def __init__(
        self,
        *,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        prompt = prompt.strip()

        if not prompt:
            return "Please give me something to respond to."

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.ConnectionError:
            return (
                "I couldn't connect to Ollama. "
                "Make sure Ollama is running on this computer."
            )
        except requests.Timeout:
            return "Ollama took too long to respond."
        except requests.RequestException as exc:
            return f"Ollama request failed: {exc}"

        try:
            data: dict[str, Any] = response.json()
        except ValueError:
            return "Ollama returned an invalid response."

        generated_text = data.get("response")

        if not isinstance(generated_text, str) or not generated_text.strip():
            error = data.get("error")

            if isinstance(error, str) and error.strip():
                return f"Ollama error: {error}"

            return "Ollama returned an empty response."

        return generated_text.strip()