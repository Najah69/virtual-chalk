"""Ingestion depuis un dépôt GitHub public : récupère le README (obligatoire)
et quelques fichiers de doc de premier niveau s'ils existent, combinés en un
texte source unique — même format qu'un fichier/URL collé par l'utilisateur,
exploitable directement par Pipeline.run() sans code spécifique en aval.

Volontairement limité à un petit nombre de fichiers de premier niveau (pas
de crawl récursif de tout le dépôt) : reste sobre et rapide, cohérent avec
le principe d'un seul appel LLM en aval — inutile de charger tout un dépôt
si le README + CHANGELOG suffisent à en tirer une vidéo pédagogique."""

from __future__ import annotations

import re

import requests

GITHUB_API = "https://api.github.com"

_README_CANDIDATES = ("README.md", "readme.md", "Readme.md", "README.rst", "README.txt")
_DOC_CANDIDATES = ("docs/README.md", "CHANGELOG.md", "CONTRIBUTING.md")


class GitHubIngestionError(RuntimeError):
    pass


def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """Accepte 'owner/repo' ou une URL github.com complète (avec ou sans
    https://, avec ou sans .git/slash final)."""
    cleaned = repo_url.strip().rstrip("/")
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?$", cleaned)
    if match:
        return match.group(1), match.group(2)
    parts = cleaned.split("/")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    raise GitHubIngestionError(f"URL de dépôt GitHub invalide : {repo_url!r}")


def _fetch_raw_file(owner: str, repo: str, path: str, ref: str) -> str | None:
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    response = requests.get(url, timeout=15)
    return response.text if response.status_code == 200 else None


def _default_branch(owner: str, repo: str) -> str:
    response = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", timeout=15)
    if response.status_code == 404:
        raise GitHubIngestionError(f"Dépôt introuvable ou privé : {owner}/{repo}")
    response.raise_for_status()
    return response.json().get("default_branch") or "main"


def fetch_repo_text(repo_url: str) -> str:
    """Récupère le README (obligatoire, plusieurs orthographes/extensions
    essayées) et quelques fichiers de doc de premier niveau s'ils existent."""
    owner, repo = _parse_owner_repo(repo_url)
    branch = _default_branch(owner, repo)

    readme = None
    for name in _README_CANDIDATES:
        readme = _fetch_raw_file(owner, repo, name, branch)
        if readme:
            break
    if not readme:
        raise GitHubIngestionError(f"Aucun README trouvé pour {owner}/{repo}")

    sections = [f"# Dépôt GitHub : {owner}/{repo}\n\n{readme}"]
    for path in _DOC_CANDIDATES:
        content = _fetch_raw_file(owner, repo, path, branch)
        if content:
            sections.append(f"# {path}\n\n{content}")

    return "\n\n---\n\n".join(sections)
