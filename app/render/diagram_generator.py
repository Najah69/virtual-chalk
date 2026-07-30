"""Genere un vrai schema visuel (triangle, cycle, carte, coupe...) a partir
d'une description en langage naturel, pour les scenes ou du texte/icones
seuls ne suffisent pas a montrer quelque chose visuellement.

Principe : au lieu de demander au LLM de script des coordonnees precises
(peu fiable, et il faudrait ajouter un nouveau primitive a chaque nouveau
type de forme rencontre), on delegue le "quoi dessiner" a un modele de
generation d'image (qui genere n'importe quel sujet, dans n'importe quel
domaine, sans jamais avoir besoin d'etre etendu), puis on vectorise l'image
obtenue en contours et on la fait rejouer par le moteur de trace existant
(app/render/web_template/tools/chalk.js), qui sait deja animer n'importe
quelle liste de points."""

from __future__ import annotations

import base64
import logging
from io import BytesIO

import cv2
import numpy as np
import requests
from PIL import Image

from app.scenes.schema import Point

logger = logging.getLogger(__name__)

GEMINI_IMAGE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
)

# Lignes fines demandees explicitement : un trait epais se vectorise en deux
# contours paralleles proches (bord interieur + exterieur), un trait fin
# reduit cet ecart au point qu'il devient imperceptible une fois texture par
# le grain craie/feutre.
_DIAGRAM_IMAGE_PROMPT = (
    "Minimalist black and white line drawing, thin clean outlines only, "
    "no shading, no gradients, no color, no fill, no background texture, "
    "plain flat white background, like a simple textbook diagram sketch. "
    "Do NOT include any text, letters, numbers or labels in the image — "
    "geometry/shapes only, labels are added separately afterwards. "
    "Subject: {description}"
)

# Epaisseur de trait pour le rendu (chalk.js/marker_veleda.js), sans rapport
# avec la taille du cadre de placement (Stroke.width/height la portent
# temporairement le temps de la vectorisation, voir Pipeline.generate_diagrams
# qui remet cette valeur en place une fois les points resolus) : meme ordre
# de grandeur que le trait de texte/icone (~14-16px) pour un poids visuel
# coherent avec le reste du tableau.
DIAGRAM_LINE_WIDTH = 14.0

MAX_POINTS_PER_DIAGRAM = 500
_MIN_CONTOUR_POINTS = 3
_MIN_CONTOUR_ARC_LEN = 20.0


class DiagramGenerationError(RuntimeError):
    pass


def generate_diagram_image(description: str, api_key: str) -> bytes:
    """Demande a Gemini une image de diagramme (dessin au trait, pas une
    photo) et retourne les octets PNG bruts. Leve DiagramGenerationError si
    la reponse ne contient pas d'image (cle invalide, contenu refuse,
    reponse texte seule...)."""
    prompt = _DIAGRAM_IMAGE_PROMPT.format(description=description)
    response = requests.post(
        GEMINI_IMAGE_URL,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    for part in data["candidates"][0]["content"]["parts"]:
        inline = part.get("inlineData")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise DiagramGenerationError(f"Aucune image renvoyee par Gemini pour : {description!r}")


def _largest_contours(gray: np.ndarray, max_points: int) -> list[np.ndarray]:
    """Detecte les contours du dessin au trait et les simplifie (Douglas-
    Peucker) pour ne garder que les sommets significatifs plutot que des
    centaines de points quasi-colineaires le long de chaque segment.
    Trie par longueur decroissante et plafonne le nombre total de points
    (perf du rendu incremental cote JS, proportionnel au nombre de points)."""
    edges = cv2.Canny(gray, 60, 160)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.arcLength(c, False) >= _MIN_CONTOUR_ARC_LEN]
    contours.sort(key=lambda c: cv2.arcLength(c, False), reverse=True)

    simplified = []
    total = 0
    for c in contours:
        epsilon = 0.003 * cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, epsilon, False)
        pts = approx.reshape(-1, 2)
        if len(pts) < _MIN_CONTOUR_POINTS:
            continue
        if simplified and total + len(pts) > max_points:
            break
        simplified.append(pts)
        total += len(pts)
    return simplified


def vectorize_diagram(png_bytes: bytes, anchor_x: float, anchor_y: float,
                       width_px: float, height_px: float) -> list[Point]:
    """Convertit une image de diagramme en une liste de points positionnes
    dans le cadre (anchor_x, anchor_y, coin haut-gauche + largeur/hauteur)
    reserve sur le tableau, memes coordonnees canvas que les autres strokes.
    Chaque contour distinct devient un sous-trace (premier point marque
    penUp=True) pour que le moteur de trace ne relie pas des traits
    disjoints (ex: les 3 cotes d'un triangle) par une ligne parasite."""
    image = Image.open(BytesIO(png_bytes)).convert("L")
    gray = np.array(image)

    contours = _largest_contours(gray, MAX_POINTS_PER_DIAGRAM)
    if not contours:
        return []

    # Le dessin genere ne remplit pas forcement tout le cadre demande a
    # Gemini : on recadre sur la boite englobante reelle des contours
    # plutot que sur l'image entiere, pour que le diagramme occupe bien
    # tout l'espace reserve au lieu d'etre minuscule au centre.
    all_pts = np.vstack(contours)
    bx0, by0 = all_pts.min(axis=0)
    bx1, by1 = all_pts.max(axis=0)
    src_w = max(bx1 - bx0, 1)
    src_h = max(by1 - by0, 1)
    scale = min(width_px / src_w, height_px / src_h)
    # Centre le dessin dans le cadre reserve (son ratio largeur/hauteur ne
    # correspond pas forcement exactement a celui du cadre demande).
    offset_x = anchor_x + (width_px - src_w * scale) / 2.0
    offset_y = anchor_y + (height_px - src_h * scale) / 2.0

    points: list[Point] = []
    for contour in contours:
        for i, (px, py) in enumerate(contour):
            x = offset_x + (px - bx0) * scale
            y = offset_y + (py - by0) * scale
            points.append(Point(x=float(x), y=float(y), penUp=(i == 0)))
    return points


def generate_diagram_points(description: str, api_key: str, anchor_x: float, anchor_y: float,
                             width_px: float, height_px: float) -> list[Point]:
    """Bout en bout : description -> image -> contours positionnes. Les
    erreurs (reseau, cle invalide, vectorisation vide) sont laissees a
    l'appelant (app/pipeline.py), qui decide de degrader gracieusement
    plutot que de faire echouer toute la generation de video pour un seul
    schema manque."""
    image_bytes = generate_diagram_image(description, api_key)
    return vectorize_diagram(image_bytes, anchor_x, anchor_y, width_px, height_px)
