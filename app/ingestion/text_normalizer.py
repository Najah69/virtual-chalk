from pathlib import Path
from typing import Any

from app.ingestion.docx_reader import read_docx
from app.ingestion.github import fetch_repo_text
from app.ingestion.pdf_reader import read_pdf
from app.ingestion.url_reader import read_url


def normalize_source(source: dict[str, Any]) -> str:
    """source = {"type": "text"|"file"|"url"|"github", "value": str}"""
    kind = source["type"]
    value = source["value"]

    if kind == "text":
        text = value
    elif kind == "url":
        text = read_url(value)
    elif kind == "github":
        text = fetch_repo_text(value)
    elif kind == "file":
        path = Path(value)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = read_pdf(path)
        elif suffix == ".docx":
            text = read_docx(path)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError(f"Type de source inconnu: {kind}")

    return "\n".join(line.strip() for line in text.splitlines() if line.strip())
