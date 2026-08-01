from abc import ABC, abstractmethod


class LLMService(ABC):
    """Base interface for all language model providers."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        history: list[dict[str, str]],
        prompt: str,
    ) -> str:
        """Generate a response using the supplied prompt and conversation context."""
        raise NotImplementedError
