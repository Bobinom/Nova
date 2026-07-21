from abc import ABC, abstractmethod


class LLMService(ABC):
    """Base interface for all language model providers."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a response for the given prompt."""
        raise NotImplementedError