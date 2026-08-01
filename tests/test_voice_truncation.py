"""app/scenes/schema.py::truncate_voice_over_to_duration — extrait de
app/edit/nl_commands.py (commande NL "raccourcis la scène à Xs") lors de
l'ajout de la timeline éditable (app/scenes/timeline.py), pour que les
deux points d'entrée partagent EXACTEMENT la même heuristique plutôt que
deux implémentations qui pourraient dériver l'une de l'autre. Aucune
couverture n'existait pour cette heuristique avant ce partage — comblée
ici."""

from __future__ import annotations

from app.scenes.schema import Scene, truncate_voice_over_to_duration


def _make_scene(voice_over: str) -> Scene:
    return Scene(scene_id="s0", voice_over=voice_over, duration_sec=10.0, visual_instruction="")


def test_truncate_cuts_at_a_sentence_boundary_when_one_exists():
    scene = _make_scene("Première phrase courte. Deuxième phrase qui rallonge beaucoup le texte total.")
    truncate_voice_over_to_duration(scene, target_duration=2.0)  # budget ~30 caracteres
    assert scene.voice_over == "Première phrase courte."
    assert scene.duration_sec == 2.0


def test_truncate_falls_back_to_ellipsis_without_a_sentence_boundary():
    scene = _make_scene("un long texte sans aucune ponctuation de fin de phrase qui depasse le budget alloue")
    truncate_voice_over_to_duration(scene, target_duration=1.0)  # budget = max(20, int(1.0*15)) = 20 caracteres
    assert scene.voice_over.endswith("…")
    assert len(scene.voice_over) <= 21  # 20 caracteres + le caractere ellipse


def test_truncate_leaves_short_text_unchanged():
    scene = _make_scene("Court.")
    truncate_voice_over_to_duration(scene, target_duration=10.0)
    assert scene.voice_over == "Court."


def test_truncate_always_sets_duration_even_when_text_is_untouched():
    scene = _make_scene("Court.")
    truncate_voice_over_to_duration(scene, target_duration=3.0)
    assert scene.duration_sec == 3.0  # provisoire : une resynthese ulterieure fixera la duree reelle


def test_truncate_never_produces_an_empty_budget():
    scene = _make_scene("Un texte de longueur normale pour une scene explicative typique.")
    truncate_voice_over_to_duration(scene, target_duration=0.0)
    assert len(scene.voice_over) >= 20  # plancher de securite (max(20, ...) dans l'implementation)
