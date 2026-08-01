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


def text_width(content: str, font_size: float) -> float:
    """Largeur estimée d'un texte pour sa taille de police — exposée
    (pas de préfixe _) car aussi utilisée par
    app/scenes/schema.py::strokes_from_visual_elements pour centrer
    horizontalement un texte "titre" (ancré ligne de base à gauche, donc
    il faut connaître sa largeur pour calculer l'ancre qui le centre)."""
    return max(len(content), 1) * font_size * _CHAR_WIDTH_RATIO


def _bbox(el: dict) -> tuple[float, float, float, float]:
    """Boîte englobante (x0, y0, x1, y1). Les ancrages ne sont pas
    homogènes entre types (texte = ligne de base à gauche, icône/animation
    = coin haut-gauche) — reproduit ici la même convention que
    text_to_path.js / icon_to_path.js / animations.js, pour que la boîte
    corresponde à ce qui est réellement dessiné."""
    x, y, size = el["x"], el["y"], el["size"]
    if el["kind"] == "text":
        w = text_width(el.get("content", ""), size)
        return (x - _PADDING, y - size * 0.8 - _PADDING, x + w + _PADDING, y + size * 0.3 + _PADDING)
    if el["kind"] == "animation":
        h = size * 1.7
        return (x - 14 - _PADDING, y - 14 - _PADDING, x + size + 14 + _PADDING, y + h + 14 + _PADDING)
    if el["kind"] == "diagram":
        h = el.get("height", size)
        return (x - _PADDING, y - _PADDING, x + size + _PADDING, y + h + _PADDING)
    return (x - _PADDING, y - _PADDING, x + size + _PADDING, y + size + _PADDING)


def _push_pair_along_axis(a: dict, b: dict, axis: str, push: float, a_first: bool) -> None:
    """Écarte a/b de `2*push` le long de `axis`, en respectant un éventuel
    élément "épinglé" sur cet axe (`pinned_x`/`pinned_y`, voir
    strokes_from_visual_elements — un texte "titre" en haut du tableau,
    forcé centré horizontalement, ne doit jamais être repoussé par
    resolve_overlaps, seul l'autre élément de la paire bouge, du double du
    déplacement pour que la séparation totale reste la même)."""
    pin_key = f"pinned_{axis}"
    a_pinned = a.get(pin_key, False)
    b_pinned = b.get(pin_key, False)
    if a_pinned and b_pinned:
        return  # cas dégénéré (deux éléments épinglés qui se chevauchent) : non résoluble sur cet axe
    sign = -1 if a_first else 1
    if a_pinned:
        b[axis] -= sign * push * 2
    elif b_pinned:
        a[axis] += sign * push * 2
    else:
        a[axis] += sign * push
        b[axis] -= sign * push


def _push_apart(elements: list[dict], canvas_width: float, canvas_height: float, iterations: int) -> bool:
    """Une passe de poussées pairwise. Retourne True si au moins une
    collision a été traitée (donc si un nouveau passage pourrait encore
    être nécessaire après un recadrage)."""
    # A egalite (cas degenere : deux elements a coordonnees identiques),
    # on privilegie l'axe le long duquel le tableau laisse le plus de
    # marge de manoeuvre pour separer sans buter sur un bord — dépend de
    # l'orientation (paysage 1920x1080 : horizontal : portrait 1080x1920 :
    # vertical), plutôt qu'une hypothèse figée "toujours horizontal".
    prefer_x_on_tie = canvas_width >= canvas_height
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
                push_x = overlap_x <= overlap_y if overlap_x != overlap_y else prefer_x_on_tie
                if push_x:
                    push = overlap_x / 2 + 1
                    _push_pair_along_axis(a, b, "x", push, (ax0 + ax1) <= (bx0 + bx1))
                else:
                    push = overlap_y / 2 + 1
                    _push_pair_along_axis(a, b, "y", push, (ay0 + ay1) <= (by0 + by1))
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
        # Un élément épinglé (voir _push_pair_along_axis) est déjà placé à
        # une position volontairement fixe sur cet axe (ex: texte "titre"
        # centré horizontalement) — le recadrer irait à l'encontre de cette
        # contrainte ; en pratique il est aussi toujours dans le cadre
        # (centré), donc ne pas le recadrer ne casse rien de plus.
        if not el.get("pinned_x", False):
            if x0 < margin:
                el["x"] += margin - x0
                clamped = True
            elif x1 > canvas_width - margin:
                el["x"] -= x1 - (canvas_width - margin)
                clamped = True
        if not el.get("pinned_y", False):
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
    'pinned_x'/'pinned_y' (optionnels, absents = False) empêchent tout
    déplacement de l'élément sur l'axe concerné — voir
    strokes_from_visual_elements, qui épingle horizontalement le texte
    "titre" d'une scène (toujours centré) : seul l'AUTRE élément d'une
    paire en collision est alors repoussé, du double du déplacement usuel.

    Alterne séparation et recadrage dans le cadre du tableau plutôt que de
    faire le recadrage une seule fois à la fin : recadrer un élément déjà
    séparé peut le repousser dans un voisin (repéré en re-testant sur un
    cas de bord — cinq éléments serrés en haut/bas de tableau), d'où le
    besoin de reboucler tant que l'un ou l'autre bouge encore."""
    for _ in range(rounds):
        moved = _push_apart(elements, canvas_width, canvas_height, iterations)
        clamped = _clamp_to_canvas(elements, canvas_width, canvas_height, margin)
        if not moved and not clamped:
            break
