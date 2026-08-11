from __future__ import annotations

import shutil
import subprocess
from typing import Any, Protocol

import requests

from nova.llm.service import LLMService


class CredentialStore(Protocol):
    def get(self) -> str | None: ...
    def set(self, value: str) -> None: ...


class OpenAIKeychain:
    """Store Nova's OpenAI API key in macOS Keychain."""

    service = "com.bobinom.nova.openai"
    account = "api-key"

    def get(self) -> str | None:
        security = shutil.which("security")
        if security is None:
            return None
        try:
            completed = subprocess.run(
                [security, "find-generic-password", "-s", self.service,
                 "-a", self.account, "-w"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        value = completed.stdout.strip()
        return value if completed.returncode == 0 and value else None

    def set(self, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("An OpenAI API key is required.")
        security = shutil.which("security")
        if security is None:
            raise RuntimeError("macOS Keychain is unavailable.")
        try:
            subprocess.run(
                [security, "add-generic-password", "-U", "-s", self.service,
                 "-a", self.account, "-w", cleaned],
                capture_output=True, text=True, timeout=10, check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("Could not save the OpenAI key in Keychain.") from exc


class CloudBrainError(RuntimeError):
    pass


class OpenAIService(LLMService):
    """OpenAI Responses API conversational provider."""

    def __init__(
        self,
        keychain: CredentialStore,
        *,
        model: str = "gpt-5.4-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 45.0,
    ) -> None:
        self.keychain = keychain
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def configured(self) -> bool:
        return bool(self.keychain.get())

    def generate(
        self,
        system_prompt: str,
        history: list[dict[str, str]],
        prompt: str,
    ) -> str:
        key = self.keychain.get()
        if not key:
            raise CloudBrainError("OpenAI is not connected in Nova Settings.")
        input_messages: list[dict[str, Any]] = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", turn.get("text", "")).strip()
            if role in {"user", "assistant"} and content:
                input_messages.append({"role": role, "content": content})
        if (input_messages and input_messages[-1]["role"] == "user"
                and input_messages[-1]["content"] == prompt.strip()):
            input_messages.pop()
        input_messages.append({"role": "user", "content": prompt.strip()})
        try:
            response = requests.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "instructions": system_prompt,
                    "input": input_messages,
                    "reasoning": {"effort": "low"},
                    "max_output_tokens": 1200,
                    "store": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise CloudBrainError("OpenAI took too long to respond.") from exc
        except requests.RequestException as exc:
            raise CloudBrainError(f"OpenAI request failed: {exc}") from exc
        except ValueError as exc:
            raise CloudBrainError("OpenAI returned an invalid response.") from exc
        text = self._output_text(data)
        if not text:
            raise CloudBrainError("OpenAI returned an empty response.")
        return text

    @staticmethod
    def _output_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        parts: list[str] = []
        for item in data.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    value = content.get("text")
                    if isinstance(value, str):
                        parts.append(value)
        return "\n".join(parts).strip()
