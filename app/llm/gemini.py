from __future__ import annotations

import requests

from app.llm.base import LLMProvider

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiProvider(LLMProvider):
    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        model = self.model or "gemini-2.5-pro"
        response = requests.post(
            GEMINI_URL_TEMPLATE.format(model=model),
            params={"key": self.api_key},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"},
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
