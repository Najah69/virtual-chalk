"""Marge de sécurité entre un élément placé par le LLM et le bord du
tableau (voir app/scenes/schema.py::BOARD_EDGE_MARGIN_PX). Remplace
l'ancien test_board_frame.py : le cadre en bois qui justifiait une marge
élargie a été retiré (retour utilisateur, voir docs/architecture.md) —
il ne reste qu'une marge fixe, identique pour tous les thèmes et les deux
orientations."""

from __future__ import annotations

from app.scenes.schema import (
    BOARD_EDGE_MARGIN_PX,
    CANVAS_HEIGHT,
    CANVAS_HEIGHT_PORTRAIT,
    CANVAS_WIDTH,
    CANVAS_WIDTH_PORTRAIT,
    strokes_from_visual_elements,
)


def test_element_near_corner_is_clamped_clear_of_the_edge():
    elements = [{"type": "icon", "name": "sun", "x": 0, "y": 0}]
    strokes = strokes_from_visual_elements(elements, "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT)

    anchor = strokes[0].points[0]
    assert anchor.x >= BOARD_EDGE_MARGIN_PX - 1.0  # tolérance flottante
    assert anchor.y >= BOARD_EDGE_MARGIN_PX - 1.0


def test_edge_margin_is_a_flat_constant_independent_of_orientation():
    """La marge ne dépend plus de la dimension du canvas (elle dépendait
    de BOARD_FRAME_RATIO * plus petite dimension avant le retrait du
    cadre) — un même élément proche du coin doit être repoussé de
    exactement la même distance en portrait et en paysage."""
    landscape = strokes_from_visual_elements(
        [{"type": "icon", "name": "sun", "x": 0, "y": 0}], "chalk_board", CANVAS_WIDTH, CANVAS_HEIGHT,
    )
    portrait = strokes_from_visual_elements(
        [{"type": "icon", "name": "sun", "x": 0, "y": 0}], "chalk_board",
        CANVAS_WIDTH_PORTRAIT, CANVAS_HEIGHT_PORTRAIT,
    )
    assert landscape[0].points[0].x == portrait[0].points[0].x
    assert landscape[0].points[0].y == portrait[0].points[0].y
