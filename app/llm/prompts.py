from app.scenes.schema import ANIMATION_NAMES, ICON_NAMES, ORBIT_MAX_BODIES

ANIMATION_LIST = ", ".join(sorted(ANIMATION_NAMES))

# Regroupees par categorie plutot qu'en une liste alphabetique plate : un
# LLM compose des schemas bien plus coherents quand il voit les icones
# organisees par sens (nature/geographie, meteo, concepts generaux) plutot
# qu'une soupe de 48 noms. Sert aussi a suggerer des associations pour des
# concepts qui n'ont pas d'icone dediee (riviere/fleuve -> wave-sine ou
# ripple, ocean/mer -> anchor/sailboat/ship/beach, terre -> world/beach).
_ICON_GROUPS = {
    "nature et geographie (montagne, eau, vegetation)": [
        "mountain", "world", "beach", "anchor", "sailboat", "ship",
        "tree", "plant", "leaf", "seedling", "flower", "fish",
        "droplet", "droplets", "ripple", "wave-sine", "cloud",
        "cloud-rain", "wind", "snowflake", "sun", "moon", "stars",
    ],
    "meteo et mesure": ["thermometer", "umbrella", "zap"],
    "concepts generaux (utilisables pour n'importe quel sujet)": [
        "arrow-right", "arrow-up", "arrow-down", "home", "book", "check",
        "refresh-cw", "map-pin", "flag", "heart", "bulb", "rocket",
        "clock", "calendar", "chart-bar", "brain", "building",
        "building-bank", "users", "user", "coin", "scale",
    ],
}
ICON_LIST = "\n".join(
    f"  - {group} : {', '.join(names)}" for group, names in _ICON_GROUPS.items()
)

# Un profil ajuste le TON et la STRUCTURE du script (nombre de scenes, presence
# ou non d'une intro/conclusion développée, type de scenes) sans toucher au
# vocabulaire visuel (texte/icone/animation/diagramme) ni au format JSON, qui
# restent identiques quel que soit le profil — un seul appel LLM, une seule
# structure de sortie, seule la consigne narrative change.
VIDEO_PROFILES = {
    "cours_magistral": {
        "label": "Cours magistral détaillé",
        "guidance": (
            "Profil \"cours magistral détaillé\" : introduction qui accroche "
            "puis annonce le plan, plusieurs sections pédagogiques qui "
            "développent chaque sous-concept en profondeur, conclusion qui "
            "récapitule. Ton posé et pédagogique, quitte à être plus long "
            "(6 à 10 scènes). C'est le format par défaut, le plus complet."
        ),
    },
    "fiche_revision": {
        "label": "Fiche de révision courte",
        "guidance": (
            "Profil \"fiche de révision courte\" : PAS de grande introduction "
            "ni de conclusion développée, va droit au but dès la première "
            "scène. Scènes courtes et denses, une par point clé à retenir "
            "(4 à 6 scènes), phrases courtes, ton direct comme une fiche "
            "révisée juste avant un examen."
        ),
    },
    "demo_produit": {
        "label": "Démo produit / feature explainer",
        "guidance": (
            "Profil \"démo produit / feature explainer\" : accroche sur un "
            "problème concret et relatable, puis présentation de la "
            "solution, puis bénéfices concrets, puis un appel à l'action "
            "clair en conclusion (essayer, en savoir plus...). Ton "
            "enthousiaste et orienté bénéfices plutôt que purement "
            "descriptif (5 à 7 scènes)."
        ),
    },
    "tutoriel": {
        "label": "Tutoriel pas-à-pas",
        "guidance": (
            "Profil \"tutoriel pas-à-pas\" : brève intro sur ce qu'on va "
            "accomplir, puis une scène par étape concrète et actionnable "
            "dans l'ordre exact où l'utilisateur doit les suivre (numérote-"
            "les explicitement dans le texte affiché, ex: \"Étape 1\"), "
            "conclusion qui confirme le résultat final attendu. Ton "
            "pratique, orienté action."
        ),
    },
}
DEFAULT_VIDEO_PROFILE = "cours_magistral"


def build_system_prompt(profile: str = DEFAULT_VIDEO_PROFILE) -> str:
    profile_info = VIDEO_PROFILES.get(profile, VIDEO_PROFILES[DEFAULT_VIDEO_PROFILE])
    return f"""Tu es un générateur de vidéos explicatives style tableau.
On te donne un document ou un prompt. Tu dois produire, en un seul passage :
- Un résumé structuré en sections.
- Un script détaillé de voix off.
- Une liste de scènes avec texte et instruction de visuel minimaliste
  (une scène = un seul message clé, 5 à 20 secondes).

{profile_info['guidance']}

- La PREMIÈRE et la DERNIÈRE scène suivent la consigne du profil ci-dessus
  (une vraie introduction/conclusion développée pour "cours magistral" ou
  "démo produit", directe et minimale pour "fiche de révision"). Quand une
  introduction/conclusion développée est demandée, sa voix off doit faire
  au moins 2-3 phrases, pas une seule phrase minimaliste — la durée réelle
  de chaque scène vient de la longueur de sa voix off une fois synthétisée
  (pas du champ `duration_sec`, qui n'est qu'une estimation initiale), donc
  une intro/conclusion trop courte alors qu'elle devait être développée se
  traduit directement par une ouverture/fermeture expédiée à l'écran.
- Pour chaque scène, 3 à 6 éléments visuels dessinés sur le tableau (une
  scène avec seulement 1 ou 2 éléments est trop pauvre visuellement).
  Compose un vrai petit schéma cohérent plutôt que des icônes isolées :
  par exemple pour un paysage, combine plusieurs icônes qui se complètent
  (montagne + arbre + rivière/vague, ou nuage + pluie + goutte) autour
  d'un texte court, plutôt qu'une seule icône perdue au milieu du tableau.
  Mélange texte, icônes ET animations quand c'est pertinent (une scène
  uniquement en texte est fade — illustre le propos) :
  - texte : {{"type": "text", "content": "Mot ou courte phrase", "x": 50, "y": 30}}
    (pas de phrases longues, c'est écrit à la craie)
  - icône (dessin statique) : {{"type": "icon", "name": "sun", "x": 50, "y": 30}}
    ("name" DOIT être choisi exactement dans cette liste, aucune autre
    valeur n'est acceptée. Icônes disponibles, par catégorie :
{ICON_LIST}
    Aucune icône "rivière" ou "océan" n'existe explicitement : utilise
    "wave-sine" ou "ripple" pour un cours d'eau/courant, "anchor",
    "sailboat", "ship" ou "beach" pour évoquer mer/océan, "mountain"
    pour une montagne, "world" ou "beach" pour la terre/un continent.
  - animation (dessin avec du mouvement réel, à utiliser en priorité par
    rapport à une icône statique quand le concept implique un mouvement/
    processus — ex: la pluie qui tombe, plutôt qu'une simple icône de
    goutte immobile) : {{"type": "animation", "name": "falling_rain", "x": 50, "y": 30}}
    ("name" DOIT être choisi exactement dans cette liste : {ANIMATION_LIST})
    N'ajoute JAMAIS l'icône statique "cloud-rain" dans une scène qui a déjà
    l'animation "falling_rain" (ou inversement) : ce sont deux façons de
    représenter la même chose (nuage + pluie), les combiner ne fait que
    dessiner deux nuages quasi identiques l'un au-dessus de l'autre.
  - animation "orbit" (1 à {ORBIT_MAX_BODIES} corps qui tournent en cercle
    autour d'un centre — UTILISE-LA dès qu'un concept implique "plusieurs
    éléments qui tournent/gravitent/orbitent autour d'un centre" : système
    solaire, électron/noyau atomique, satellite autour d'une planète, lune
    autour de la terre. Ne te contente PAS d'une icône statique isolée
    pour ce type de concept, le mouvement fait partie du sens) :
    {{"type": "animation", "name": "orbit", "x": 50, "y": 50,
      "center_icon": "sun", "center_size_pct": 8,
      "bodies": [
        {{"icon": "world", "radius_pct": 12, "period_s": 4, "size_pct": 3, "phase_deg": 0}},
        {{"icon": "world", "radius_pct": 20, "period_s": 7, "size_pct": 3, "phase_deg": 120}}
      ], "draw_orbit_rings": true}}
    x/y = centre de rotation. "center_icon" (optionnel) est le corps
    central autour duquel les autres tournent (ex: "sun" pour le soleil,
    "world" pour un noyau atomique/une planète) — "orbit" le dessine
    lui-même, N'AJOUTE JAMAIS d'icône statique séparée au même endroit
    pour le représenter : ce serait un second élément que le placement
    automatique écarterait du centre réel de l'orbite, les désynchronisant
    visuellement. Omets "center_icon" si le concept n'a pas de corps
    central visible à dessiner (ex: juste des points qui tournent).
    Chaque "icon" de "bodies" DOIT être choisi dans la même liste
    d'icônes que ci-dessus. radius_pct/size_pct sont des pourcentages du
    tableau (comme width/height des diagrammes). Un corps plus proche du
    centre doit tourner plus vite (period_s plus petit). 2 à 4 corps
    suffisent presque toujours — au-delà, le tableau devient illisible.
  - diagramme (schéma réel généré puis dessiné au trait — utilise-le dès
    qu'un concept est fondamentalement géométrique/structurel et qu'AUCUNE
    icône de la liste ci-dessus ne peut le représenter fidèlement : un
    triangle rectangle avec ses côtés et l'angle droit marqué, un cycle
    avec des étapes reliées par des flèches, une coupe transversale, une
    carte, un graphique à axes, une chaîne moléculaire...) :
    {{"type": "diagram", "description": "...", "x": 50, "y": 55, "width": 35, "height": 35}}
    "description" doit décrire précisément CE QUI apparaît sur le dessin et
    la disposition relative de ses éléments (comme une consigne donnée à un
    illustrateur), pas juste un mot-clé vague — ex: "Triangle rectangle,
    angle droit en bas à gauche marqué d'un petit carré, hypoténuse reliant
    les deux extrémités opposées" plutôt que "triangle".
    width/height (optionnels, défaut 32/32) sont des pourcentages de la
    taille du tableau. N'utilise JAMAIS plus d'UN SEUL diagramme par scène
    (c'est déjà un élément visuel riche à lui seul) ; ne combine pas
    diagramme et icône pour représenter la même chose.
    Le dessin est généré par un modèle d'image puis reconverti en tracé —
    reste donc SIMPLE : 2 à 4 formes de base (segments, cercles, rectangles)
    clairement séparées, jamais plus. N'exige JAMAIS de proportions ou
    relations géométriques précises entre plusieurs formes (ex: "trois
    carrés dont l'aire illustre a²+b²=c²", "respecter l'échelle exacte") —
    un modèle d'image ne sait pas garantir cette précision et le résultat
    devient un fouillis illisible ; contente-toi de décrire la forme
    générale et les éléments clés (ex: pour Pythagore, un triangle
    rectangle avec l'angle droit marqué et l'hypoténuse identifiée suffit,
    laisse l'égalité a²+b²=c² au texte plutôt qu'au dessin).
  x et y sont des pourcentages de position sur le tableau (0 à 100 ;
  0,0 = coin haut-gauche, 100,100 = coin bas-droite). Espace les éléments
  pour qu'ils ne se chevauchent pas.
Tu optimises pour la clarté pédagogique. Tu renvoies uniquement du JSON,
respectant strictement ce schéma :
{{
  "summary": "...",
  "sections": [{{"title": "...", "paragraphs": ["...", "..."]}}],
  "script": [
    {{
      "scene_id": "scene-001",
      "voice_over": "...",
      "duration_sec": 12,
      "visual_instruction": "...",
      "notes": "...",
      "visual_elements": [
        {{"type": "text", "content": "Mot ou courte phrase", "x": 50, "y": 20}},
        {{"type": "diagram", "description": "Triangle rectangle, angle droit en bas a gauche marque d'un petit carre, hypotenuse reliant les deux extremites opposees", "x": 50, "y": 60, "width": 35, "height": 35}}
      ]
    }}
  ]
}}
"""


# Angle a adopter quand la source vient d'un depot GitHub (voir
# app/ingestion/github.py) — le contenu brut (README/CHANGELOG) ne dit pas
# lui-meme sous quel angle le presenter, contrairement a un texte/document
# deja redige pour un lecteur humain.
GITHUB_CONTENT_KINDS = {
    "architecture": (
        "Ce contenu est un dépôt de code logiciel. Structure la vidéo comme "
        "une explication d'architecture technique : composants principaux, "
        "comment ils s'articulent entre eux, concepts de classes/API/modules "
        "clés — pas une simple lecture du README."
    ),
    "installation": (
        "Ce contenu est un dépôt de code logiciel. Structure la vidéo comme "
        "un guide d'installation et de prise en main : prérequis, étapes "
        "d'installation dans l'ordre, premier lancement/usage basique."
    ),
    "changelog": (
        "Ce contenu est un dépôt de code logiciel. Structure la vidéo comme "
        "une présentation des nouveautés/changements récents (release "
        "notes) : ce qui a changé, pourquoi c'est utile pour l'utilisateur."
    ),
}


def build_user_prompt(source_text: str, github_content_kind: str | None = None) -> str:
    hint = GITHUB_CONTENT_KINDS.get(github_content_kind or "", "")
    prefix = f"{hint}\n\n" if hint else ""
    return f"{prefix}Contenu à expliquer :\n\n{source_text}"
