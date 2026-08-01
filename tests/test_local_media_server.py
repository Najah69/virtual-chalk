"""Tâche : lecteur vidéo intégré toujours cassé après le premier correctif
(toFileUri) — <video src="file://..."> est refusé par WebView2/Chromium
quand la page qui l'affiche est servie en http:// (ce qui est le cas de
ui/index.html/editor.html, voir Api.open_editor), constaté empiriquement
via video.error.message == "Media load rejected by URL safety check".
app/local_media_server.py sert donc les vidéos via un second petit
serveur HTTP local dédié plutôt que file://. Ici : tests Python purs
(parsing Range, enregistrement/URL) ; la lecture réelle dans un <video>
est vérifiée séparément via un script de fumée qui pilote une vraie
fenêtre webview (non reproductible dans la suite pytest)."""

from __future__ import annotations

import urllib.request

from app.local_media_server import _parse_range, serve


def test_parse_range_full_spec():
    assert _parse_range("bytes=100-199", file_size=1000) == (100, 199)


def test_parse_range_open_ended():
    assert _parse_range("bytes=500-", file_size=1000) == (500, 999)


def test_parse_range_end_clamped_to_file_size():
    assert _parse_range("bytes=0-99999", file_size=1000) == (0, 999)


def test_serve_returns_distinct_urls_for_distinct_calls(tmp_path):
    f1 = tmp_path / "a.mp4"
    f1.write_bytes(b"fake video a")
    f2 = tmp_path / "b.mp4"
    f2.write_bytes(b"fake video b")

    url1 = serve(f1)
    url2 = serve(f2)

    assert url1 != url2
    assert url1.startswith("http://127.0.0.1:")
    assert url2.startswith("http://127.0.0.1:")


def test_served_file_is_actually_reachable_over_http(tmp_path):
    content = b"fake video bytes for a real HTTP round trip"
    f = tmp_path / "video.mp4"
    f.write_bytes(content)

    url = serve(f)

    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200
        assert resp.read() == content


def test_served_file_supports_range_requests(tmp_path):
    content = b"0123456789" * 100  # 1000 octets
    f = tmp_path / "video.mp4"
    f.write_bytes(content)

    url = serve(f)

    req = urllib.request.Request(url, headers={"Range": "bytes=10-19"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 206
        assert resp.read() == content[10:20]
        assert resp.headers["Content-Range"] == "bytes 10-19/1000"


def test_unknown_token_returns_404(tmp_path):
    # Force le démarrage du serveur (via un premier appel réel) pour
    # obtenir un port valide sans dupliquer la logique interne.
    f = tmp_path / "video.mp4"
    f.write_bytes(b"x")
    base_url = serve(f)
    server_root = base_url.rsplit("/", 1)[0]

    try:
        urllib.request.urlopen(f"{server_root}/does-not-exist", timeout=5)
        raise AssertionError("expected HTTPError 404")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
