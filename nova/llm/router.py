from __future__ import annotations

from typing import Any

from nova.core.settings import SettingsManager
from nova.llm.openai import CloudBrainError, OpenAIService
from nova.llm.service import LLMService


class BrainRouter(LLMService):
    VALID_MODES = {"local", "hybrid", "cloud"}

    def __init__(self, settings: SettingsManager, local: LLMService,
                 cloud: OpenAIService) -> None:
        self.settings = settings
        self.local = local
        self.cloud = cloud
        self.last_provider = "local"

    def set_mode(self, mode: str) -> None:
        cleaned = mode.strip().lower()
        if cleaned not in self.VALID_MODES:
            raise ValueError(f"Unsupported brain mode: {mode}")
        self.settings.set("brain.mode", cleaned)

    def configure(self, api_key: str) -> None:
        if api_key.strip():
            self.cloud.keychain.set(api_key)
        if not self.cloud.configured():
            raise ValueError("Enter an OpenAI API key first.")
        self.set_mode("hybrid")

    def status(self) -> dict[str, Any]:
        mode = str(self.settings.get("brain.mode", "hybrid"))
        configured = self.cloud.configured()
        return {
            "mode": mode,
            "cloud_configured": configured,
            "cloud_model": self.cloud.model,
            "local_model": getattr(self.local, "model", "local"),
            "effective_provider": (
                "openai" if mode != "local" and configured else "ollama"
            ),
            "last_provider": self.last_provider,
        }

    def generate(self, system_prompt: str, history: list[dict[str, str]],
                 prompt: str) -> str:
        mode = str(self.settings.get("brain.mode", "hybrid")).lower()
        if mode == "local":
            self.last_provider = "ollama"
            return self.local.generate(system_prompt, history, prompt)
        try:
            result = self.cloud.generate(system_prompt, history, prompt)
            self.last_provider = "openai"
            return result
        except CloudBrainError as exc:
            if mode == "cloud":
                self.last_provider = "openai-error"
                return str(exc)
            self.last_provider = "ollama-fallback"
            return self.local.generate(system_prompt, history, prompt)
