# Doit rester synchronisé avec app/render/web_template/themes.js (même
# mapping thème -> outil et mêmes palettes, dupliqué ici car Python ne
# parse pas le JS).
THEME_TOOLS = {
    "chalk_board": "chalk",
    "whiteboard_marker": "marker_veleda",
}

THEME_PALETTES = {
    "chalk_board": ["#ffffff", "#ffe66d", "#ff6b6b", "#6bd4ff", "#8fe388", "#ff9ecb", "#ffa94d"],
    "whiteboard_marker": ["#1a1a1a", "#1f5fd1", "#e0313b", "#1f9e56", "#f2a900"],
}


def tool_for_theme(theme_id: str) -> str:
    return THEME_TOOLS.get(theme_id, "chalk")


def palette_for_theme(theme_id: str) -> list[str]:
    return THEME_PALETTES.get(theme_id, THEME_PALETTES["chalk_board"])
