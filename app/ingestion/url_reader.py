import requests
import trafilatura


def read_url(url: str) -> str:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    extracted = trafilatura.extract(response.text)
    return extracted or ""
