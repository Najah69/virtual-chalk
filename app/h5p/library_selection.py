# N'embarque dans le .h5p que ce qui sert réellement au projet : le socle
# Interactive Video est toujours nécessaire, chaque type d'exercice ajoute
# ses propres dépendances seulement si utilisé (évite de gonfler un export
# vidéo-seule avec les 4 types d'exercices à chaque fois).
CORE_LIBRARIES = [
    "H5P.InteractiveVideo-1.28",
    "FontAwesome-4.5",
    "jQuery.ui-1.10",
    "H5P.Video-1.6",
    "H5P.DragNBar-1.5",
    "H5P.DragNDrop-1.1",
    "H5P.DragNResize-1.2",
    "H5P.FontIcons-1.0",
    "H5P.Components-1.0",
]

EXERCISE_LIBRARIES = {
    "true_false": ["H5P.TrueFalse-1.8", "H5P.JoubelUI-1.3", "H5P.Question-1.5", "H5P.Transition-1.0"],
    "multi_choice": ["H5P.MultiChoice-1.16", "H5P.JoubelUI-1.3", "H5P.Question-1.5", "H5P.Transition-1.0"],
    "blanks": ["H5P.Blanks-1.14", "H5P.JoubelUI-1.3", "H5P.Question-1.5", "H5P.Transition-1.0", "H5P.TextUtilities-1.3"],
    "drag_text": ["H5P.DragText-1.10", "H5P.JoubelUI-1.3", "H5P.Question-1.5", "H5P.Transition-1.0", "H5P.Components-1.0"],
}


def libraries_for_project(exercise_types: set[str]) -> list[str]:
    folders = set(CORE_LIBRARIES)
    for exercise_type in exercise_types:
        folders.update(EXERCISE_LIBRARIES.get(exercise_type, []))
    return sorted(folders)
