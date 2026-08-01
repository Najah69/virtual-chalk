from __future__ import annotations

import mimetypes
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Sert les vidéos générées (hors de l'arborescence de l'app, voir
# app/settings.py::default_output_dir) à un <video> de l'UI. ui/index.html
# et ui/editor/editor.html sont chargées via le mini serveur HTTP local de
# pywebview (http://localhost:<port>/..., voir Api.open_editor) : un
# <video src="file://...">, lui, est REFUSÉ par WebView2/Chromium quand la
# page qui l'affiche n'est pas elle-même file:// — constaté empiriquement
# (video.error.message == "Media load rejected by URL safety check"),
# alors qu'un <img>/<video> cross-ORIGIN http(s) classique ne l'est pas.
# --allow-file-access-from-files (webview.settings["ALLOW_FILE_URLS"])
# NE RÉSOUT PAS ce cas précis (vérifié) : ce flag ne lève que les
# restrictions file://->file://, pas http://->file://.
#
# Un second petit serveur HTTP local (pas le serveur de pywebview lui-même
# — son root_path est calculé une seule fois comme le plus petit ancêtre
# commun des fenêtres locales, donc limité à l'arborescence de l'app ;
# Program Files n'est pas inscriptible sans élévation, donc "y copier la
# vidéo" n'est pas une option fiable une fois installé) sert UNIQUEMENT
# les chemins explicitement enregistrés via serve() — jamais un dossier
# entier — pour ne jamais exposer autre chose que ce que l'app a
# elle-même généré, même si le serveur n'écoute que sur 127.0.0.1 (donc
# déjà inaccessible depuis le réseau).

_registry: dict[str, Path] = {}
_registry_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None
_port: int | None = None
_start_lock = threading.Lock()

_CHUNK_SIZE = 1024 * 1024


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """"bytes=start-end" ou "bytes=start-" (fin omise = fin de fichier) —
    seule la forme à un seul intervalle est gérée (largement suffisante
    pour un <video>, qui ne demande jamais de multipart/byteranges)."""
    _, _, range_spec = range_header.partition("=")
    start_str, _, end_str = range_spec.partition("-")
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    return start, min(end, file_size - 1)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - signature imposée par BaseHTTPRequestHandler
        pass  # pas de bruit console (app packagée sans console, voir capture.py pour la même raison)

    def do_GET(self) -> None:
        token = self.path.lstrip("/").split("?", 1)[0]
        with _registry_lock:
            path = _registry.get(token)
        if path is None or not path.exists():
            self.send_error(404)
            return

        file_size = path.stat().st_size
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        range_header = self.headers.get("Range")

        if range_header:
            start, end = _parse_range(range_header, file_size)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(end - start + 1))
        else:
            # Un <video> commence quasi toujours par une requête Range
            # (voir ci-dessus), mais répondre correctement même sans
            # Range évite de dépendre de ce détail d'implémentation du
            # navigateur.
            start, end = 0, file_size - 1
            self.send_response(200)
            self.send_header("Content-Length", str(file_size))

        self.send_header("Content-Type", mime_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    # Le lecteur vidéo a coupé la connexion (seek, page
                    # fermée...) — pas une erreur serveur, rien à logger.
                    break
                remaining -= len(chunk)

    def do_HEAD(self) -> None:
        token = self.path.lstrip("/").split("?", 1)[0]
        with _registry_lock:
            path = _registry.get(token)
        if path is None or not path.exists():
            self.send_error(404)
            return
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()


def _ensure_started() -> int:
    global _server, _port
    with _start_lock:
        if _server is None:
            _server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            _port = _server.server_address[1]
            threading.Thread(target=_server.serve_forever, daemon=True).start()
        return _port


def serve(path: Path) -> str:
    """Enregistre `path` et renvoie son URL servie
    (http://127.0.0.1:<port>/<jeton>) — jeton aléatoire (pas le nom de
    fichier) : évite toute collision entre deux appels et ne révèle pas
    l'arborescence réelle du disque à qui intercepterait l'URL. Le
    serveur démarre paresseusement au premier appel (pas de coût au
    lancement de l'app pour les sessions qui ne regardent jamais de
    vidéo dans l'UI, ex: génération suivie uniquement de l'ouverture du
    dossier de sortie)."""
    port = _ensure_started()
    token = uuid.uuid4().hex
    with _registry_lock:
        _registry[token] = Path(path)
    return f"http://127.0.0.1:{port}/{token}"
