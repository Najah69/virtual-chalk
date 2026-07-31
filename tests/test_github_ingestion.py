"""Tâche E : robustesse de app/ingestion/github.py — aucun vrai appel
réseau ici, requests.get est entièrement simulé."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from app.ingestion import github


def _response(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def test_parse_owner_repo_accepts_short_form_and_full_url():
    assert github._parse_owner_repo("owner/repo") == ("owner", "repo")
    assert github._parse_owner_repo("https://github.com/owner/repo") == ("owner", "repo")
    assert github._parse_owner_repo("https://github.com/owner/repo.git") == ("owner", "repo")
    assert github._parse_owner_repo("git@github.com:owner/repo.git") == ("owner", "repo")


def test_parse_owner_repo_rejects_invalid_url():
    with pytest.raises(github.GitHubIngestionError):
        github._parse_owner_repo("not-a-valid-repo-reference")


def test_fetch_repo_text_happy_path(monkeypatch):
    def fake_get(url, timeout=15):
        if "api.github.com" in url:
            return _response(200, json_data={"default_branch": "main"})
        if url.endswith("/README.md"):
            return _response(200, text="# Mon projet\n\nContenu.")
        return _response(404)

    monkeypatch.setattr(github.requests, "get", fake_get)
    text = github.fetch_repo_text("owner/repo")
    assert "Mon projet" in text
    assert "owner/repo" in text


def test_fetch_repo_text_missing_readme_raises_clear_error(monkeypatch):
    def fake_get(url, timeout=15):
        if "api.github.com" in url:
            return _response(200, json_data={"default_branch": "main"})
        return _response(404)

    monkeypatch.setattr(github.requests, "get", fake_get)
    with pytest.raises(github.GitHubIngestionError, match="Aucun README"):
        github.fetch_repo_text("owner/repo")


def test_fetch_repo_text_repo_not_found_404_on_repo_lookup(monkeypatch):
    monkeypatch.setattr(github.requests, "get", lambda url, timeout=15: _response(404))
    with pytest.raises(github.GitHubIngestionError, match="introuvable"):
        github.fetch_repo_text("owner/repo")


@pytest.mark.parametrize("status_code", [403, 429])
def test_fetch_repo_text_rate_limit_raises_clear_error(monkeypatch, status_code):
    monkeypatch.setattr(github.requests, "get", lambda url, timeout=15: _response(status_code))
    with pytest.raises(github.GitHubIngestionError, match="Limite de requêtes"):
        github.fetch_repo_text("owner/repo")


def test_fetch_repo_text_network_error_raises_ingestion_error_not_raw_exception(monkeypatch):
    def fake_get(url, timeout=15):
        raise requests.exceptions.ConnectTimeout("boom")

    monkeypatch.setattr(github.requests, "get", fake_get)
    with pytest.raises(github.GitHubIngestionError):
        github.fetch_repo_text("owner/repo")


def test_fetch_repo_text_includes_optional_doc_files_when_present(monkeypatch):
    def fake_get(url, timeout=15):
        if "api.github.com" in url:
            return _response(200, json_data={"default_branch": "main"})
        if url.endswith("/README.md"):
            return _response(200, text="# Projet")
        if url.endswith("/CHANGELOG.md"):
            return _response(200, text="## v1.0")
        return _response(404)

    monkeypatch.setattr(github.requests, "get", fake_get)
    text = github.fetch_repo_text("owner/repo")
    assert "Projet" in text
    assert "v1.0" in text
