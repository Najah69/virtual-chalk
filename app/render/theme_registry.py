# Doit rester synchronisé avec app/render/web_template/themes.js (même
# mapping thème -> outil et mêmes palettes, dupliqué ici car Python ne
# parse pas le JS).
THEME_TOOLS = {
    "chalk_board": "chalk",
    # Même outil/palette/couleurs que chalk_board — variante "noir" du
    # tableau craie (voir web_template/themes.js), seule la couleur de
    # fond diffère.
    "chalk_board_black": "chalk",
    "whiteboard_marker": "marker_veleda",
}

THEME_PALETTES = {
    "chalk_board": ["#ffffff", "#ffe66d", "#ff6b6b", "#6bd4ff", "#8fe388", "#ff9ecb", "#ffa94d", "#c2a878"],
    "chalk_board_black": ["#ffffff", "#ffe66d", "#ff6b6b", "#6bd4ff", "#8fe388", "#ff9ecb", "#ffa94d", "#c2a878"],
    "whiteboard_marker": ["#1a1a1a", "#1f5fd1", "#e0313b", "#1f9e56", "#f2a900", "#8a5a2b"],
}

# Categorie semantique de certaines icones : permet de choisir une couleur
# coherente avec ce qu'elles representent (eau = bleu, vegetation = vert,
# terre/montagne = brun...) plutot que la simple rotation de palette.
# Les icones absentes de cette table (concepts generiques : fleche, coeur,
# horloge, utilisateur...) n'ont pas de couleur "juste" evidente et
# gardent donc la rotation de palette classique.
ICON_SEMANTIC_CATEGORY = {
    "droplet": "water", "cloud-rain": "water", "droplets": "water",
    "ripple": "water", "wave-sine": "water", "fish": "water",
    "anchor": "water", "sailboat": "water", "ship": "water", "umbrella": "water",
    "cloud": "sky", "wind": "sky", "snowflake": "sky", "moon": "sky", "stars": "sky",
    "sun": "sun", "thermometer": "sun", "zap": "sun", "bulb": "sun",
    "tree": "vegetation", "plant": "vegetation", "leaf": "vegetation",
    "seedling": "vegetation", "flower": "vegetation",
    "mountain": "earth", "world": "earth", "beach": "earth",
    "building": "earth", "building-bank": "earth",
    # Animations (namespace distinct des icones, voir ANIMATION_NAMES) :
    # meme table, memes categories, pour eviter qu'une pluie qui tombe soit
    # coloree au hasard (jaune) au lieu du bleu utilise pour le reste de
    # l'eau (goutte, nuage de pluie...) presente dans la meme scene.
    "falling_rain": "water",
}

THEME_SEMANTIC_COLORS = {
    "chalk_board": {
        "water": "#6bd4ff", "sky": "#ffffff", "sun": "#ffe66d",
        "vegetation": "#8fe388", "earth": "#c2a878",
    },
    "chalk_board_black": {
        "water": "#6bd4ff", "sky": "#ffffff", "sun": "#ffe66d",
        "vegetation": "#8fe388", "earth": "#c2a878",
    },
    "whiteboard_marker": {
        "water": "#1f5fd1", "sky": "#1a1a1a", "sun": "#f2a900",
        "vegetation": "#1f9e56", "earth": "#8a5a2b",
    },
}

# Couleurs de texte "sûres" (contraste garanti avec le fond du thème),
# utilisées pour les strokes de kind "text" au lieu de la rotation de
# palette complète — celle-ci contient des teintes pensées pour des
# icônes/formes ponctuelles, pas pour du texte à lire en continu (ex: le
# jaune ou le rose de chalk_board restent lisibles sur fond vert craie,
# mais sont moins confortables à lire qu'un blanc/craie classique). Un
# minimum de variation (2 couleurs) évite un rendu trop monotone quand
# plusieurs textes apparaissent dans la même scène.
THEME_TEXT_COLORS = {
    "chalk_board": ["#ffffff", "#ffe66d"],
    "chalk_board_black": ["#ffffff", "#ffe66d"],
    "whiteboard_marker": ["#1a1a1a", "#1f5fd1"],
}


def tool_for_theme(theme_id: str) -> str:
    return THEME_TOOLS.get(theme_id, "chalk")


def palette_for_theme(theme_id: str) -> list[str]:
    return THEME_PALETTES.get(theme_id, THEME_PALETTES["chalk_board"])


def text_color_for_theme(theme_id: str, index: int = 0) -> str:
    """Couleur à utiliser pour un stroke de kind "text" dans ce thème —
    toujours l'une des quelques couleurs "sûres" de THEME_TEXT_COLORS
    (jamais la palette cyclique complète, réservée aux icônes/diagrammes/
    animations). `index` fait juste alterner entre les couleurs sûres
    pour éviter un aplat visuel monotone quand plusieurs textes
    coexistent dans une scène."""
    colors = THEME_TEXT_COLORS.get(theme_id, THEME_TEXT_COLORS["chalk_board"])
    return colors[index % len(colors)]


def semantic_color_for_icon(icon_name: str, theme_id: str) -> str | None:
    """Couleur "juste" pour une icone (eau=bleu, vegetation=vert...), ou
    None si l'icone est un concept generique sans couleur evidente — dans
    ce cas l'appelant doit retomber sur la rotation de palette."""
    category = ICON_SEMANTIC_CATEGORY.get(icon_name)
    if category is None:
        return None
    theme_colors = THEME_SEMANTIC_COLORS.get(theme_id, THEME_SEMANTIC_COLORS["chalk_board"])
    return theme_colors.get(category)
