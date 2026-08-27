"""Groq provider using Groq's OpenAI-compatible chat API."""
import re

import httpx

from app.config import get_settings
from app.providers.llm.base import LLMProvider

settings = get_settings()


class GroqProvider(LLMProvider):
    def __init__(self):
        if not settings.GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file -- "
                "never hard-code it in source."
            )
        self.api_key = settings.GROQ_API_KEY
        self.base_url = settings.GROQ_API_BASE
        self.model = settings.GROQ_MODEL

    async def generate(self, system_prompt: str, user_message: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": settings.MAX_OUTPUT_TOKENS,
            "reasoning_format": "hidden",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Groq API request failed: {exc}") from exc

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # Keep model reasoning out of the response if the API returns it anyway.
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        content = content.replace("**", "")
        return content.strip()