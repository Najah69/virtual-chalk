"""Tâche #6 : format vertical 1080x1920 (Project.mobile_layout, coché par
défaut à l'étape 1 de l'assistant) vs paysage 1920x1080 historique, et
correction du titre "décalé" (recentrage + épinglage horizontal du
premier texte placé en haut du tableau, voir strokes_from_visual_elements/
app/render/layout.py::resolve_overlaps). Aucun vrai rendu/LLM ici."""

from __future__ import annotations

from app.render.layout import resolve_overlaps
from app.scenes.schema import (
    CANVAS_HEIGHT,
    CANVAS_HEIGHT_PORTRAIT,
    CANVAS_WIDTH,
    CANVAS_WIDTH_PORTRAIT,
    Project,
    canvas_dimensions,
    strokes_from_visual_elements,
)


def test_canvas_dimensions_portrait_vs_landscape():
    assert canvas_dimensions(True) == (CANVAS_WIDTH_PORTRAIT, CANVAS_HEIGHT_PORTRAIT)
    assert canvas_dimensions(False) == (CANVAS_WIDTH, CANVAS_HEIGHT)
    # Portrait est bien plus haut que large (vraie vidéo verticale), pas
    # juste les mêmes dimensions permutées par accident.
    assert CANVAS_WIDTH_PORTRAIT < CANVAS_HEIGHT_PORTRAIT


def test_project_canvas_size_follows_mobile_layout():
    portrait = Project(title="t", summary="s", sections=[], scenes=[], mobile_layout=True)
    landscape = Project(title="t", summary="s", sections=[], scenes=[], mobile_layout=False)
    assert portrait.canvas_size == (CANVAS_WIDTH_PORTRAIT, CANVAS_HEIGHT_PORTRAIT)
    assert landscape.canvas_size == (CANVAS_WIDTH, CANVAS_HEIGHT)


def test_project_from_dict_defaults_to_landscape_for_legacy_files_without_the_field():
    """Un .vchalk enregistré avant cette fonctionnalité n'a pas la clé
    "mobile_layout" — ses strokes ont été figés en pixels absolus pour le
    SEUL format qui existait alors (paysage). Le réinterpréter en portrait
    par défaut le ferait déborder du nouveau cadre plus étroit."""
    legacy_data = Project(title="t", summary="s", sections=[], scenes=[]).to_dict()
    del legacy_data["mobile_layout"]

    restored = Project.from_dict(legacy_data)

    assert restored.mobile_layout is False


def test_project_from_dict_respects_explicit_mobile_layout():
    data = Project(title="t", summary="s", sections=[], scenes=[], mobile_layout=True).to_dict()
    restored = Project.from_dict(data)
    assert restored.mobile_layout is True


def test_project_from_llm_response_defaults_to_mobile_layout_true():
    """Contrairement à from_dict (repli paysage pour la compatibilité
    ascendante), une NOUVELLE génération doit suivre le défaut de la case
    à cocher de l'étape 1 ("cochée par défaut" — voir ui/index.html)."""
    project = Project.from_llm_response({"summary": "s", "sections": [], "script": []})
    assert project.mobile_layout is True
    assert project.canvas_size == (CANVAS_WIDTH_PORTRAIT, CANVAS_HEIGHT_PORTRAIT)


def test_strokes_from_visual_elements_scales_to_given_canvas_size():
    elements = [{"type": "text", "content": "Bonjour", "x": 50, "y": 80}]
    strokes = strokes_from_visual_elements(elements, "chalk_board", canvas_width=1000, canvas_height=2000)
    # y=80% n'est pas dans la bande "titre" (TITLE_TOP_BAND_PCT=30) : x
    # n'est donc pas recentré, juste mis à l'échelle du canvas fourni.
    assert strokes[0].points[0].y == 0.80 * 2000


def test_strokes_from_visual_elements_centers_and_pins_top_text_as_title():
    elements = [{"type": "text", "content": "Titre", "x": 5, "y": 15}]
    strokes = strokes_from_visual_elements(elements, "chalk_board", canvas_width=1920, canvas_height=1080)

    stroke = strokes[0]
    # L'ancre texte est en ligne de base à GAUCHE (pas le centre) : le
    # texte est visuellement centré quand ancre + largeur/2 == canvas/2.
    from app.render.layout import text_width
    from app.scenes.schema import TEXT_STROKE_WIDTH
    estimated_center = stroke.points[0].x + text_width("Titre", TEXT_STROKE_WIDTH) / 2.0
    assert abs(estimated_center - 1920 / 2.0) < 1.0


def test_only_the_first_top_text_is_treated_as_title():
    elements = [
        {"type": "text", "content": "Premier", "x": 5, "y": 10},
        {"type": "text", "content": "Second", "x": 90, "y": 12},
    ]
    strokes = strokes_from_visual_elements(elements, "chalk_board", canvas_width=1920, canvas_height=1080)

    from app.render.layout import text_width
    from app.scenes.schema import TEXT_STROKE_WIDTH
    first_center = strokes[0].points[0].x + text_width("Premier", TEXT_STROKE_WIDTH) / 2.0
    assert abs(first_center - 1920 / 2.0) < 1.0
    # Le second texte, lui, garde une position dérivée de son x/y d'origine
    # (90%), pas recentrée sur le milieu du tableau.
    assert strokes[1].points[0].x > 1920 / 2.0


def test_title_text_not_centered_when_below_top_band():
    elements = [{"type": "text", "content": "Pas un titre", "x": 5, "y": 60}]
    strokes = strokes_from_visual_elements(elements, "chalk_board", canvas_width=1920, canvas_height=1080)
    # y=60% est sous TITLE_TOP_BAND_PCT (30) : x reste dérivé du
    # pourcentage d'origine (5%), pas recentré.
    assert strokes[0].points[0].x == (5.0 / 100.0) * 1920


def test_resolve_overlaps_never_moves_pinned_x_element_horizontally():
    elements = [
        {"kind": "text", "x": 960.0, "y": 100.0, "size": 90.0, "content": "Titre", "pinned_x": True},
        {"kind": "icon", "x": 950.0, "y": 105.0, "size": 220.0, "content": "", "name": "sun"},
    ]
    resolve_overlaps(elements, 1920, 1080)

    assert elements[0]["x"] == 960.0  # l'élément épinglé n'a pas bougé sur x
    # La collision a bien été résolue (les deux boîtes ne se chevauchent plus).
    ax0, ay0 = elements[0]["x"] - 16, elements[0]["y"] - 90.0 * 0.8 - 16
    ax1 = elements[0]["x"] + 90.0 * len("Titre") * 0.6 + 16
    bx0 = elements[1]["x"] - 14 - 16
    bx1 = elements[1]["x"] + 220.0 + 14 + 16
    assert ax1 <= bx0 or bx1 <= ax0 or elements[1]["y"] != 105.0


def test_resolve_overlaps_tie_break_prefers_wider_axis():
    # Deux éléments identiques (chevauchement égal en x et en y) : en
    # paysage (plus large que haut), on doit préférer écarter le long de
    # l'axe horizontal ; en portrait (plus haut que large), le vertical.
    landscape_elements = [
        {"kind": "icon", "x": 500.0, "y": 500.0, "size": 100.0, "content": "", "name": "sun"},
        {"kind": "icon", "x": 500.0, "y": 500.0, "size": 100.0, "content": "", "name": "sun"},
    ]
    resolve_overlaps(landscape_elements, 1920, 1080)
    assert landscape_elements[0]["x"] != landscape_elements[1]["x"]

    portrait_elements = [
        {"kind": "icon", "x": 500.0, "y": 500.0, "size": 100.0, "content": "", "name": "sun"},
        {"kind": "icon", "x": 500.0, "y": 500.0, "size": 100.0, "content": "", "name": "sun"},
    ]
    resolve_overlaps(portrait_elements, 1080, 1920)
    assert portrait_elements[0]["y"] != portrait_elements[1]["y"]
