# Doit rester synchronisé avec app/render/web_template/themes.js (même
# mapping thème -> outil et mêmes palettes, dupliqué ici car Python ne
# parse pas le JS).
THEME_TOOLS = {
    "chalk_board": "chalk",
    "whiteboard_marker": "marker_veleda",
}

THEME_PALETTES = {
    "chalk_board": ["#ffffff", "#ffe66d", "#ff6b6b", "#6bd4ff", "#8fe388", "#ff9ecb", "#ffa94d", "#c2a878"],
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
    "whiteboard_marker": {
        "water": "#1f5fd1", "sky": "#1a1a1a", "sun": "#f2a900",
        "vegetation": "#1f9e56", "earth": "#8a5a2b",
    },
}


def tool_for_theme(theme_id: str) -> str:
    return THEME_TOOLS.get(theme_id, "chalk")


def palette_for_theme(theme_id: str) -> list[str]:
    return THEME_PALETTES.get(theme_id, THEME_PALETTES["chalk_board"])


def semantic_color_for_icon(icon_name: str, theme_id: str) -> str | None:
    """Couleur "juste" pour une icone (eau=bleu, vegetation=vert...), ou
    None si l'icone est un concept generique sans couleur evidente — dans
    ce cas l'appelant doit retomber sur la rotation de palette."""
    category = ICON_SEMANTIC_CATEGORY.get(icon_name)
    if category is None:
        return None
    theme_colors = THEME_SEMANTIC_COLORS.get(theme_id, THEME_SEMANTIC_COLORS["chalk_board"])
    return theme_colors.get(category)
