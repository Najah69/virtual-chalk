"""GeminiProvider._complete_with_images (app/llm/gemini.py) : construction
de la requête multimodale pour la boucle d'auto-critique visuelle. Aucun
vrai appel réseau — requests.post est simulé."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

from app.llm.gemini import GeminiProvider


def _fake_response(payload: dict):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
    return resp


def test_complete_with_images_sends_text_and_image_parts():
    provider = GeminiProvider(api_key="fake-key", model="gemini-flash-latest")
    fake_resp = _fake_response({"sufficient": True})

    with patch("app.llm.gemini.requests.post", return_value=fake_resp) as mock_post:
        result = provider.complete_json_with_images("system prompt", "user prompt", [b"jpeg-bytes-1", b"jpeg-bytes-2"])

    assert result == {"sufficient": True}
    call_kwargs = mock_post.call_args.kwargs
    body = call_kwargs["json"]
    assert body["system_instruction"]["parts"][0]["text"] == "system prompt"
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "user prompt"}
    assert len(parts) == 3  # 1 texte + 2 images
    for part, raw in zip(parts[1:], [b"jpeg-bytes-1", b"jpeg-bytes-2"]):
        assert part["inline_data"]["mime_type"] == "image/jpeg"
        assert base64.b64decode(part["inline_data"]["data"]) == raw


def test_complete_with_images_falls_back_to_default_model_when_unset():
    provider = GeminiProvider(api_key="fake-key", model="")
    fake_resp = _fake_response({"sufficient": False})

    with patch("app.llm.gemini.requests.post", return_value=fake_resp) as mock_post:
        provider.complete_json_with_images("sys", "user", [])

    assert "gemini-flash-latest" in mock_post.call_args.args[0]


def test_complete_with_images_passes_api_key_as_query_param():
    provider = GeminiProvider(api_key="my-secret-key", model="gemini-flash-latest")
    fake_resp = _fake_response({"sufficient": True})

    with patch("app.llm.gemini.requests.post", return_value=fake_resp) as mock_post:
        provider.complete_json_with_images("sys", "user", [])

    assert mock_post.call_args.kwargs["params"] == {"key": "my-secret-key"}
