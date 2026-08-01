"""Point cosmétique : le tableau craie a désormais un cadre en bois dessiné
autour de la zone verte (voir app/render/web_template/surfaces/
board_noise.js::buildFramedBoardNoise, calqué sur une photo de référence
fournie par l'utilisateur). Ici : uniquement la conséquence côté Python —
les éléments placés par le LLM doivent rester dans la zone craie, jamais
sous le cadre. BOARD_FRAME_RATIO DOIT rester synchronisé avec
window.BOARD_FRAME_RATIO côté JS (aucun test ne peut vérifier ça depuis
pytest ; voir le script de fumée qui capture un vrai rendu pour la
vérification visuelle)."""

from __future__ import annotations

from app.scenes.schema import (
    BOARD_FRAME_MARGIN_PADDING,
    BOARD_FRAME_RATIO,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    strokes_from_visual_elements,
)


def _expected_margin(canvas_width: float, canvas_height: float) -> float:
    return min(canvas_width, canvas_height) * BOARD_FRAME_RATIO + BOARD_FRAME_MARGIN_PADDING


def test_element_near_corner_is_clamped_clear_of_the_frame():
    elements = [{"type": "icon", "name": "sun", "x": 0, "y": 0}]
    strokes = strokes_from_visual_elements(elements, "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)

    margin = _expected_margin(CANVAS_WIDTH, CANVAS_HEIGHT)
    anchor = strokes[0].points[0]
    assert anchor.x >= margin - 1.0  # tolérance flottante
    assert anchor.y >= margin - 1.0


def test_frame_margin_is_larger_than_the_old_flat_default():
    """Régression : avant l'ajout du cadre, resolve_overlaps utilisait une
    marge fixe de 20px — trop petite pour laisser la place au cadre en
    bois, un élément y aurait été dessiné en partie dessous."""
    margin = _expected_margin(CANVAS_WIDTH, CANVAS_HEIGHT)
    assert margin > 20.0


def test_frame_margin_identical_in_portrait_and_landscape():
    """Les deux orientations partagent la même plus petite dimension
    (1080px), donc la même largeur de cadre en pixels — voir le
    commentaire de BOARD_FRAME_RATIO dans schema.py."""
    from app.scenes.schema import CANVAS_HEIGHT_PORTRAIT, CANVAS_WIDTH_PORTRAIT

    landscape_margin = _expected_margin(CANVAS_WIDTH, CANVAS_HEIGHT)
    portrait_margin = _expected_margin(CANVAS_WIDTH_PORTRAIT, CANVAS_HEIGHT_PORTRAIT)
    assert landscape_margin == portrait_margin
