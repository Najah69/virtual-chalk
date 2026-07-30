from __future__ import annotations

import requests

from app.llm.base import LLMProvider

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekProvider(LLMProvider):
    def _complete(self, system_prompt: str, user_prompt: str) -> str:
        response = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model or "deepseek-chat",
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
