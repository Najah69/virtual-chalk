"""Résolution de collisions entre éléments visuels d'une scène.

Le prompt LLM demande d'espacer les éléments, mais le LLM choisit x/y en
pourcentage sans connaître les dimensions réelles (largeur du texte selon
son contenu, empreinte d'une icône/animation) — rien ne garantissait donc
qu'un texte ne recouvre pas une icône ou une animation. Un professeur qui
écrit/dessine réellement au tableau ne fait jamais ça : il laisse
implicitement de la place. On calcule ici une boîte englobante
approximative par élément et on les écarte itérativement si elles se
chevauchent, en poussant du minimum nécessaire plutôt qu'en refaisant tout
le placement — l'intention de composition du LLM (voir prompts.py) est
conservée, seules les collisions sont corrigées.
"""

from __future__ import annotations

# Largeur moyenne d'un caractère de la police manuscrite (Caveat), en
# fraction de la taille de police — du même ordre que le repli utilisé
# par text_to_path.js quand la police ne charge pas (0.55), légèrement
# augmenté car ici il vaut mieux surestimer que sous-estimer : une boîte
# trop large pousse un peu plus que nécessaire, une boîte trop étroite
# laisserait deux tracés se toucher.
_CHAR_WIDTH_RATIO = 0.6
_PADDING = 16.0


def _text_width(content: str, font_size: float) -> float:
    return max(len(content), 1) * font_size * _CHAR_WIDTH_RATIO


def _bbox(el: dict) -> tuple[float, float, float, float]:
    """Boîte englobante (x0, y0, x1, y1). Les ancrages ne sont pas
    homogènes entre types (texte = ligne de base à gauche, icône/animation
    = coin haut-gauche) — reproduit ici la même convention que
    text_to_path.js / icon_to_path.js / animations.js, pour que la boîte
    corresponde à ce qui est réellement dessiné."""
    x, y, size = el["x"], el["y"], el["size"]
    if el["kind"] == "text":
        w = _text_width(el.get("content", ""), size)
        return (x - _PADDING, y - size * 0.8 - _PADDING, x + w + _PADDING, y + size * 0.3 + _PADDING)
    if el["kind"] == "animation":
        h = size * 1.7
        return (x - 14 - _PADDING, y - 14 - _PADDING, x + size + 14 + _PADDING, y + h + 14 + _PADDING)
    if el["kind"] == "diagram":
        h = el.get("height", size)
        return (x - _PADDING, y - _PADDING, x + size + _PADDING, y + h + _PADDING)
    return (x - _PADDING, y - _PADDING, x + size + _PADDING, y + size + _PADDING)


def _push_apart(elements: list[dict], iterations: int) -> bool:
    """Une passe de poussées pairwise. Retourne True si au moins une
    collision a été traitée (donc si un nouveau passage pourrait encore
    être nécessaire après un recadrage)."""
    any_moved = False
    for _ in range(iterations):
        moved = False
        for i in range(len(elements)):
            for j in range(i + 1, len(elements)):
                a, b = elements[i], elements[j]
                ax0, ay0, ax1, ay1 = _bbox(a)
                bx0, by0, bx1, by1 = _bbox(b)
                overlap_x = min(ax1, bx1) - max(ax0, bx0)
                overlap_y = min(ay1, by1) - max(ay0, by0)
                if overlap_x <= 0 or overlap_y <= 0:
                    continue
                moved = True
                # A egalite (cas degenere : deux elements a coordonnees
                # identiques), on privilegie l'axe horizontal : le tableau
                # est plus large que haut (1920x1080), donc plus de marge
                # de manoeuvre pour separer sans buter sur un bord.
                if overlap_x <= overlap_y:
                    push = overlap_x / 2 + 1
                    if (ax0 + ax1) <= (bx0 + bx1):
                        a["x"] -= push
                        b["x"] += push
                    else:
                        a["x"] += push
                        b["x"] -= push
                else:
                    push = overlap_y / 2 + 1
                    if (ay0 + ay1) <= (by0 + by1):
                        a["y"] -= push
                        b["y"] += push
                    else:
                        a["y"] += push
                        b["y"] -= push
        if moved:
            any_moved = True
        else:
            break
    return any_moved


def _clamp_to_canvas(elements: list[dict], canvas_width: float, canvas_height: float, margin: float) -> bool:
    """Replaque dans le cadre du tableau les éléments qui en dépassent.
    Retourne True si un élément a dû être déplacé (un recadrage peut
    réintroduire une collision entre éléments déjà séparés, d'où le besoin
    de repasser une passe de séparation ensuite)."""
    clamped = False
    for el in elements:
        x0, y0, x1, y1 = _bbox(el)
        if x0 < margin:
            el["x"] += margin - x0
            clamped = True
        elif x1 > canvas_width - margin:
            el["x"] -= x1 - (canvas_width - margin)
            clamped = True
        if y0 < margin:
            el["y"] += margin - y0
            clamped = True
        elif y1 > canvas_height - margin:
            el["y"] -= y1 - (canvas_height - margin)
            clamped = True
    return clamped


def resolve_overlaps(elements: list[dict], canvas_width: float, canvas_height: float,
                      margin: float = 20.0, iterations: int = 30, rounds: int = 6) -> None:
    """Écarte en place (modifie 'x'/'y') les éléments dont la boîte
    englobante se chevauche, par petites poussées itératives le long de
    l'axe qui demande le moins de déplacement pour désamorcer chaque
    collision. `elements` : liste de dicts avec au moins 'x', 'y', 'size',
    'kind' ('text'/'icon'/'animation'), et 'content' pour le texte.

    Alterne séparation et recadrage dans le cadre du tableau plutôt que de
    faire le recadrage une seule fois à la fin : recadrer un élément déjà
    séparé peut le repousser dans un voisin (repéré en re-testant sur un
    cas de bord — cinq éléments serrés en haut/bas de tableau), d'où le
    besoin de reboucler tant que l'un ou l'autre bouge encore."""
    for _ in range(rounds):
        moved = _push_apart(elements, iterations)
        clamped = _clamp_to_canvas(elements, canvas_width, canvas_height, margin)
        if not moved and not clamped:
            break
