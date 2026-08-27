"""
Abstract interface every LLM provider must implement.

The agent layer depends ONLY on this interface, never on a concrete
provider — swapping LLM_PROVIDER in the environment should require
zero changes above this file.
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, system_prompt: str, user_message: str) -> str:
        """
        Generate a response given a system prompt and user message.

        Phase 1 keeps this simple (no tool calling yet — that's added
        in Phase 2's ToolRegistry work). The system prompt is where
        Phase 1 injects grounded database facts as context.
        """
        raise NotImplementedError
