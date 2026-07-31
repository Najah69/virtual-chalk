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


def _raise_for_rate_limit_or_error(response: requests.Response, context: str) -> None:
    """Transforme un statut HTTP d'erreur en GitHubIngestionError lisible
    plutôt que de laisser fuir une requests.HTTPError brute — 403/429
    signifient très souvent une limite de requêtes GitHub API atteinte
    (anonyme : 60 requêtes/heure), un message générique "erreur HTTP"
    serait trompeur pour l'utilisateur final."""
    if response.status_code in (403, 429):
        raise GitHubIngestionError(
            f"Limite de requêtes GitHub atteinte (statut {response.status_code}) en "
            f"{context} — réessayez dans quelques minutes."
        )
    if response.status_code >= 400:
        raise GitHubIngestionError(f"Erreur GitHub (statut {response.status_code}) en {context}.")


def _fetch_raw_file(owner: str, repo: str, path: str, ref: str) -> str | None:
    """Retourne le contenu du fichier, ou None si absent (404 — cas normal,
    l'appelant essaie le candidat suivant). Toute autre erreur (réseau,
    timeout, limite de requêtes) est une vraie panne, pas une simple
    absence de fichier : elle remonte en GitHubIngestionError plutôt que
    d'être confondue avec un "aucun README trouvé" silencieux."""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as exc:
        raise GitHubIngestionError(f"Impossible de contacter GitHub pour récupérer {path!r} : {exc}") from exc
    if response.status_code == 404:
        return None
    _raise_for_rate_limit_or_error(response, context=f"la récupération de {path!r}")
    return response.text


def _default_branch(owner: str, repo: str) -> str:
    try:
        response = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", timeout=15)
    except requests.RequestException as exc:
        raise GitHubIngestionError(f"Impossible de contacter l'API GitHub pour {owner}/{repo} : {exc}") from exc
    if response.status_code == 404:
        raise GitHubIngestionError(f"Dépôt introuvable ou privé : {owner}/{repo}")
    _raise_for_rate_limit_or_error(response, context=f"la lecture des informations de {owner}/{repo}")
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
