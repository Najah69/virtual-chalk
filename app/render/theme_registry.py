# Doit rester synchronisé avec app/render/web_template/themes.js (même
# mapping thème -> outil, dupliqué ici car Python ne parse pas le JS).
THEME_TOOLS = {
    "chalk_board": "chalk",
    "whiteboard_marker": "marker_veleda",
}


def tool_for_theme(theme_id: str) -> str:
    return THEME_TOOLS.get(theme_id, "chalk")
