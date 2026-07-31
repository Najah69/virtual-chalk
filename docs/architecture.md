# Virtual-Chalk — Architecture

Application Windows autonome (un seul .exe) qui transforme un document ou un
prompt en vidéo explicative animée façon tableau (craie ou feutre), avec export
optionnel `.h5p` pour Moodle. Aucune architecture client/serveur : tout tourne
en local dans un seul processus.

## Principes directeurs

- **Autonomie** : un seul exécutable, pas de service externe à installer.
  Les seuls appels réseau sont volontaires (LLM cloud, TTS cloud optionnel).
- **Sobriété** : un seul appel LLM par génération de script, aucune édition
  dans l'UI ne consomme de tokens, re-rendu partiel scène par scène plutôt
  que tout régénérer.
- **Projet vectoriel éditable** : le fichier projet (`.golpoproj`) est la
  source de vérité (scènes, tracés vectoriels, timings). Le MP4 est un
  artefact toujours régénérable, pas la donnée maîtresse.
- **UX simple** : assistant linéaire en 5 étapes pour un utilisateur non
  technique ; un écran Réglages séparé pour la configuration avancée.

## Stack

- **UI + moteur de rendu** : pywebview (WebView2 natif Windows) pour la
  fenêtre principale ET pour la capture offscreen du rendu — un seul stack
  HTML/CSS/JS pour les deux usages.
- **Backend** : Python (orchestration, appels API, fichiers).
- **Vidéo** : FFmpeg embarqué en binaire statique (`resources/ffmpeg/`).

## Rendu déterministe (horloge virtuelle)

Le rendu ne capture pas en temps réel (risque de perte de frames sur machine
modeste). Python pilote une horloge virtuelle : pour chaque frame `t = n/fps`,
il demande au JS de dessiner l'état exact à cet instant, capture l'image,
répète. Ça garantit une synchro audio/vidéo parfaite indépendamment de la
vitesse de la machine.

## Thèmes = Surface + Outil

Le moteur de rendu sépare deux briques indépendantes et combinables :

- **Surface** (`render/web_template/surfaces/`) : fond du support
  (`blackboard.js`, `greenboard.js`, `whiteboard.js`).
- **Outil** (`render/web_template/tools/`) : technique de trait
  (`chalk.js` — tampon-texture grainé ; `marker_veleda.js` — trait lisse
  opaque façon feutre effaçable).

Chaque outil implémente la même interface `drawStroke(ctx, path, color,
width, progress)`, chaque surface `drawSurface(ctx, width, height)`. Ajouter
un futur thème = ajouter un module, sans toucher au reste du moteur.

Thème par défaut : tableau craie (vert/noir). Deuxième thème disponible dès
le v1 : tableau blanc + feutres Veleda.

Le texte manuscrit est converti en tracés vectoriels (contours de glyphes,
`text_to_path.js`) puis dessiné avec le même moteur d'outil que les formes
libres — cohérence visuelle totale entre texte et dessin.

Ce qui est stocké/éditable reste vectoriel (liste de points, couleur,
épaisseur) ; la texture (grain craie, brillance feutre) est une fonction
pure appliquée au rendu, jamais figée dans les données.

### Texture craie et séquencement (v1)

Le trait de craie est un nuage de petits points ("stipple") tamponnés le
long du tracé (`tools/chalk.js`), précalculé une fois par stroke et mis en
cache dessus (`stroke._chalkDabs`) — recalculer avec `Math.random()` à
chaque frame ferait scintiller la portion déjà tracée d'une image à
l'autre, la craie posée ne doit pas changer d'aspect. Le bruit du fond de
tableau (`surfaces/board_noise.js`) est mis en cache de la même façon.

Chaque dab est en réalité un tas de points dispersés aléatoirement autour
du tracé (rayon = `penWidth * jitterFactor`) : au-delà d'un certain rayon,
cette dispersion éloigne trop les points du contour de lettre réel et
floute la forme au lieu de simplement la texturer — repéré sur du texte
en minuscules cursives (les traits de liaison entre lettres, plus fins,
sont plus sensibles à ce flou que les formes/icônes). `jitterFactor` est
donc plus resserré pour le texte (0.22) que pour formes/icônes (0.4), qui
n'ont pas ce problème de lisibilité fine. Vérifié en rendant du texte
représentatif à travers la même chaîne de compression H.264 que la
production (crf 18, `yuv420p` limited-range) plutôt qu'en jugeant sur une
image brute non compressée — voir `marker_veleda.js` pour comparaison :
le feutre dessine un trait plein lisse (`ctx.stroke()`), donc ce problème
de dispersion ne le concerne pas.

### Texte manuscrit (contours réels)

`text_to_path.js` extrait les vrais contours de lettres via **opentype.js**
(vendorisé en `opentype.min.js`, bundle navigateur) appliqués à une police
manuscrite libre (**Caveat**, licence OFL, `fonts/Caveat.ttf` +
`fonts/OFL.txt`). Les commandes de tracé (M/L/C/Q/Z, avec courbes de
Bézier) sont aplaties en points, avec un marqueur `penUp` entre chaque
sous-tracé (lettres séparées, boucles fermées d'un "o"/"e"...) pour que le
moteur de tampon craie ne relie pas ces sous-tracés par un trait parasite
— `chalkPrecompute` et `marker_veleda.js` respectent ce marqueur.

Le champ `Stroke.width` a un double sens selon `kind` : taille de police
pour le texte (positionnement/échelle), épaisseur de trait réelle pour les
formes — les outils appliquent un facteur réducteur (`width * 0.16` pour
la craie comme pour le feutre) afin que le trait de lettre reste fin.

`TEXT_STROKE_WIDTH` (`app/scenes/schema.py`) est la taille de police
utilisée pour tout le texte, tous thèmes confondus — augmentée de 56 à 90
(retour utilisateur : trop petit par rapport à la taille du tableau).
Choisie après comparaison visuelle de plusieurs tailles (56 à 110) sur les
deux thèmes : au-delà d'environ 100-110, le trait du feutre (qui s'épaissit
proportionnellement, même facteur `* 0.16`) devient assez épais pour que
les lettres commencent à se fondre entre elles.

La police est chargée en XHR synchrone au chargement de la page de rendu
(page servie par le mini-serveur HTTP local de pywebview, pas `file://` —
`overrideMimeType('text/plain; charset=x-user-defined')` est nécessaire
car `responseType` ne peut pas être fixé sur une requête XHR synchrone).
Repli sur un simple segment si le chargement échoue.

### Icônes (illustrations)

Le LLM ne génère pas que du texte : chaque scène mélange texte et icônes
(`visual_elements` de type `"icon"`, `name` choisi dans un vocabulaire fixe
— voir `ICON_NAMES` dans `app/scenes/schema.py`, dupliqué dans le prompt
système `app/llm/prompts.py`). Une icône hors vocabulaire est simplement
ignorée plutôt que de faire planter le rendu.

Les tracés viennent de **Feather Icons** (MIT, 16 icônes de base) et
**Tabler Icons** (MIT, `@tabler/icons`, 32 icônes ajoutées ensuite pour la
nature/géographie et des concepts généraux — voir plus bas), convertis une
fois pour toutes en points (même format que les contours de police :
commandes M/L/C/Z aplaties, marqueur `penUp` entre sous-tracés) via un
script Node utilisant `svgpath` pour gérer les commandes d'arc SVG (`A`,
présentes dans plusieurs icônes) — voir `icon_paths.js` (généré, ne pas
éditer à la main) et `icon_to_path.js` (mise à l'échelle/position au
rendu, viewBox natif 24×24). Pour ajouter une icône : reproduire la
procédure de conversion avec le nom voulu, copier le résultat dans
`icon_paths.js`, et ajouter le nom à `ICON_NAMES` (Python) et à la liste
du prompt.

**Piège du convertisseur** (script Node de conversion, pas dans le repo
Python) : une lettre de commande SVG normalisée par `svgpath` peut être
suivie de plusieurs jeux de paramètres chaînés (répétition implicite de la
même commande — `unarc()` transforme souvent un arc en 2-3 courbes C
consécutives sous une seule lettre). Ne lire que le premier jeu tronque la
forme silencieusement ; il faut boucler sur tous les jeux de paramètres
d'un même token. `H`/`V` (ligne horizontale/verticale) ne sont pas non
plus converties par `svgpath` et doivent être gérées à la main (converties
en `L` via la position courante suivie manuellement). Vérifié en rendant
les 16 icônes une par une après coup — plusieurs (nuage, goutte,
thermomètre...) avaient une forme silencieusement déformée avant ce
correctif, alors que d'autres (maison, flèches) avaient l'air correctes
par coïncidence malgré le même bug.

Chaque tracé d'une scène a son propre `start_sec`/`end_sec`, calculés côté
Python (`app/render/timing.py`, répartition proportionnelle à la longueur
du tracé) et simplement lus par le JS — les tracés s'écrivent l'un après
l'autre (comme un vrai geste), pas tous en fondu simultané.

**Vocabulaire étendu (Tabler Icons)** — retour utilisateur : vocabulaire
initial (16 icônes Feather, surtout météo/UI) jugé "rachitique, sans
ambition", avec absence totale de rivière/fleuve/océan/mer/terre/montagne.
Ajout de 32 icônes **Tabler Icons** (MIT, `@tabler/icons`, bien plus
large que Feather) via le même pipeline de conversion, `ICON_NAMES` passe
de 16 à 48 noms. Le script de conversion lit maintenant deux répertoires
sources (`FEATHER_ICONS/FEATHER_DIR` + `TABLER_ICONS/TABLER_DIR`) au lieu
d'un seul.

**Piège Tabler #1** : chaque SVG Tabler démarre par un
`<path stroke="none" d="M0 0h24v24H0z" fill="none"/>` — un cadre de
délimitation invisible pour l'alignement, pas un tracé à dessiner. Sans
filtrage chaque icône héritait d'un rectangle parasite ; corrigé en
sautant tout `<path>` dont `stroke="none"`.

**Piège #2 (touchait déjà Feather, découvert seulement maintenant)** :
même bug de "jeu de paramètres chaînés" documenté plus haut pour `C`,
mais qui affectait en fait aussi certaines icônes Feather avant même
l'ajout de Tabler — reconfirmé par une re-vérification individuelle des
16 icônes Feather après restructuration du script (aucune régression).

Il n'existe pas d'icône "rivière" ni "océan" dédiée dans Tabler sous ces
noms exacts : le prompt système (`app/llm/prompts.py`) indique
explicitement au LLM de réutiliser `wave-sine`/`ripple` pour un cours
d'eau, `anchor`/`sailboat`/`ship`/`beach` pour évoquer mer/océan, plutôt
que de laisser le LLM deviner ou halluciner un nom hors vocabulaire (qui
serait silencieusement ignoré, voir plus haut).

Les 48 icônes ont été revérifiées **individuellement** en rendant des
grilles de 10 à la fois (`diag_icon_batch.py`, script paramétré par liste
de noms + chemin de sortie) avant de considérer le vocabulaire validé —
même discipline que pour le lot de 16 initial, condition sine qua non
avant de toucher au reste du pipeline.

**Couleurs sémantiques** — au lieu de faire tourner une palette générique
(`palette[i % len(palette)]`, sans rapport avec ce que l'icône représente),
`app/render/theme_registry.py` définit maintenant `ICON_SEMANTIC_CATEGORY`
(icône → catégorie : eau, ciel, soleil, végétation, terre) et
`THEME_SEMANTIC_COLORS` (catégorie → couleur, par thème). Les icônes hors
table (concepts génériques : flèche, cœur, horloge, utilisateur...) n'ont
pas de couleur "juste" évidente et gardent la rotation de palette
classique. `semantic_color_for_icon(name, theme)` retourne `None` dans ce
cas ; l'appelant (`schema.py`) retombe alors sur `palette[i % len(palette)]`.
Deux couleurs (terre brune, pour chalk_board et whiteboard_marker) ont été
ajoutées aux palettes de thème pour permettre ce mapping — elles entrent
aussi dans la rotation classique, ce qui ajoute au passage de la variété.

**Hiérarchie de recoloration par kind de stroke** — la palette cyclique
(`palette[i % len(palette)]`) convient à des icônes/formes ponctuelles
mais pas à du texte lu en continu : certaines couleurs de palette restent
techniquement lisibles sur le fond du thème sans être confortables à lire
(ex: le rose ou le jaune vif de chalk_board). `THEME_TEXT_COLORS` dans
`app/render/theme_registry.py` définit donc, par thème, une courte liste
de couleurs "sûres" dédiées au texte (`["#ffffff", "#ffe66d"]` pour
chalk_board, `["#1a1a1a", "#1f5fd1"]` pour whiteboard_marker), exposée via
`text_color_for_theme(theme_id, index)`. La règle de recoloration
appliquée uniformément par `strokes_from_visual_elements` (génération
initiale) et `_recolor_strokes_for_theme` (`app/edit/nl_commands.py`,
appelé par `set_theme`) est :

- `kind == "text"` → `text_color_for_theme`, avec un compteur dédié
  (indépendant de l'index global des éléments) pour alterner entre les
  couleurs sûres sans dépendre de ce qui a été placé avant dans la scène.
- `kind in ("icon", "animation")` → couleur sémantique si connue, sinon
  repli sur la palette cyclique (inchangé).
- `kind in ("shape", "diagram")` → palette cyclique (dessin libre ou
  diagramme déjà vectorisé, la couleur y est purement décorative).

### Disposition (éviter les chevauchements texte/dessin)

Retour utilisateur : le texte peut empiéter sur une icône ou une
animation — un professeur qui écrit/dessine réellement au tableau ne fait
jamais ça, il laisse implicitement de la place. Le prompt système demande
bien au LLM d'espacer les éléments, mais celui-ci choisit x/y en
pourcentage sans connaître les dimensions réelles de ce qu'il place : la
largeur d'un texte dépend de son contenu, l'emprise d'une icône/animation
de sa taille — rien ne garantissait donc l'absence de chevauchement.

`app/render/layout.py` (`resolve_overlaps`) calcule une boîte englobante
approximative par élément — les ancrages ne sont pas homogènes entre
types (texte = ligne de base à gauche comme `opentype.getPath`, icône =
coin haut-gauche, animation = coin haut-gauche mais avec une hauteur
`size * 1.7` pour couvrir l'excursion verticale des gouttes qui tombent,
voir `animations.js`) — puis écarte itérativement toute paire dont les
boîtes se chevauchent, en poussant du minimum nécessaire le long de l'axe
qui coûte le moins de déplacement. Appelé depuis
`_strokes_from_visual_elements` (`app/scenes/schema.py`) juste avant de
figer les `Stroke`, donc en aval du choix de position du LLM : son
intention de composition (voir prompts.py) est conservée, seules les
collisions sont corrigées.

Recadrer un élément dans les limites du tableau après coup peut le
repousser dans un voisin déjà séparé (repéré sur un cas de test avec
plusieurs éléments serrés en haut de tableau) : `resolve_overlaps`
alterne donc plusieurs rounds de [séparation par paires] puis
[recadrage], plutôt qu'un recadrage final unique. Un cas dégénéré
(plusieurs éléments à coordonnées exactement identiques, ce qui ne
devrait plus arriver en pratique — voir la consigne anti-doublon
icône/animation ci-dessus) peut ne pas converger à zéro chevauchement ;
des positions réalistes issues du LLM convergent proprement en quelques
itérations.

### Animations (mouvement réel)

Contrairement au texte/icônes (révélés progressivement puis figés pour
toujours), certains éléments ont un vrai mouvement — ex: `falling_rain`
(nuage + gouttes qui tombent en boucle). `Stroke.kind = "animation"`,
vocabulaire fixe dans `ANIMATION_NAMES` (`app/scenes/schema.py`), même
mécanisme de validation que les icônes.

Le reste du moteur ne touche jamais au canvas une fois quelque chose
dessiné (juste accumulé, jamais effacé — c'est ce qui permet le rendu
incrémental rapide). Une animation a besoin de faire l'inverse : ses
éléments bougent, donc chaque frame doit "effacer" sa propre zone avant de
la redessiner. Elle le fait en redessinant depuis
`window._boardTextureCache[surface]` (voir `surfaces/board_noise.js`,
qui expose maintenant ce cache), jamais en vidant tout le canvas — pour ne
jamais toucher au reste du tableau déjà tracé ailleurs.

Une fois sa fenêtre `end_sec` dépassée, l'animation est appelée une
dernière fois puis marquée `_frozen` (voir `index.html`) : elle cesse
alors d'être touchée pour le reste de la scène, cohérent avec le principe
"la craie posée ne bouge plus" — et ça évite qu'elle continue à effacer
sa zone indéfiniment si un élément plus tardif venait à s'y superposer.

La partie statique d'une animation (ex: le contour du nuage) est
pré-rendue une seule fois en sprite offscreen (`icon_sprite.js`,
réutilise le moteur craie/feutre existant) plutôt que recalculée à chaque
frame — seuls les éléments qui bougent (les gouttes) sont redessinés.

Vérifié avec une séquence de plusieurs frames dans la fenêtre active (pas
une seule image, qui ne peut jamais prouver un mouvement) : positions des
gouttes différentes d'une frame à l'autre, gel correct après `end_sec`,
et absence d'interférence avec un texte positionné ailleurs et apparu
après le gel.

### Diagrammes générés (image → vectorisation)

Texte/icônes/animations ne suffisent pas à représenter un concept
fondamentalement géométrique ou structurel (ex: un triangle rectangle pour
le théorème de Pythagore). Plutôt que d'ajouter une primitive de forme par
type de schéma rencontré (approche qui demanderait une itération de
développeur à chaque nouveau domaine), `app/render/diagram_generator.py`
délègue le "quoi dessiner" à un modèle de génération d'image (Gemini,
`gemini-2.5-flash-image`), qui sait dessiner n'importe quel sujet dans
n'importe quel domaine sans jamais avoir besoin d'être étendu :

1. Le LLM du script pose un élément `{"type": "diagram", "description": "...", "x", "y", "width", "height"}`
   dans `visual_elements` (au plus un par scène — voir consigne dans
   `app/llm/prompts.py`, qui demande une description simple, 2 à 4 formes
   de base, jamais de proportions exactes entre plusieurs formes : un
   modèle d'image ne peut pas garantir cette précision).
2. `app/scenes/schema.py::strokes_from_visual_elements` crée un `Stroke`
   temporaire `kind="diagram"` dont `points` ne contient qu'un point
   d'ancrage et `width`/`height` portent la taille du cadre réservé sur le
   tableau (pas une épaisseur de trait — double sens temporaire, corrigé à
   l'étape suivante).
3. `Pipeline.generate_diagrams()` résout chaque stroke "diagram" : appelle
   `generate_diagram_image()` (prompt forçant un style ligne fine N&B sans
   texte/légende), puis `vectorize_diagram()` (OpenCV : Canny →
   `findContours` → `approxPolyDP` pour limiter les points → recadrage sur
   la bbox réelle des contours) pour obtenir une liste de `Point`
   positionnés dans le cadre réservé, un sous-tracé par contour disjoint
   (`penUp=True` en tête de chaque contour). Le stroke bascule alors en
   `kind="shape"` et `width` est remis à `DIAGRAM_LINE_WIDTH` (épaisseur de
   trait réelle, plus la taille du cadre) — sans ce reset, le moteur de
   rendu tente de tracer un trait aussi épais que le cadre entier
   (retour utilisateur : rendu comme un nuage de points diffus au lieu
   d'un dessin nettement reconnaissable).
4. Le stroke `"shape"` résultant est ensuite dessiné par `chalk.js`/
   `marker_veleda.js` exactement comme n'importe quel autre tracé
   multi-points — **aucune modification du moteur de rendu JS n'a été
   nécessaire**, il savait déjà animer une liste de points arbitraire.

**Robustesse** (générateur d'image non déterministe — un résultat peut
être fragmenté ou contenir un résidu de texte malgré la consigne) :
`_largest_contours` écarte les contours dont la longueur est minuscule par
rapport au plus grand contour du même dessin (`_MIN_RELATIVE_ARC_LEN`,
filtre les résidus de texte/artefacts sans dépendre de l'échelle absolue
de l'image) ; si le résultat reste trop fragmenté après filtrage
(`_MAX_PLAUSIBLE_CONTOURS`, plus de 8 contours distincts — un schéma
simple en compte rarement davantage), `generate_diagram_points()` retente
une seule génération et garde le résultat le moins fragmenté des deux.
Sans clé API Gemini, en cas d'erreur réseau, ou si la vectorisation ne
produit aucun contour exploitable, le diagramme est simplement retiré de
la scène (`Pipeline.generate_diagrams`, `try/except` par diagramme) plutôt
que de faire échouer toute la génération vidéo pour un seul schéma manqué.

### Sons de craie

`app/render/chalk_audio.py` synthétise un pool de tapotements de craie
(bruit filtré + enveloppe, procédural — aucun enregistrement réel
disponible localement) et construit une piste audio dédiée par scène, avec
un tapotement choisi aléatoirement à chaque déclenchement pour éviter la
répétition, positionné au début de chaque tracé puis périodiquement pour
les tracés longs. Cette piste est mixée sous la voix off au moment de
l'encodage (`ffmpeg_wrapper.encode_scene`, filtre `amix` avec volume
réduit sur la piste craie) — uniquement pour le thème craie, pas pour le
thème feutre (`theme_registry.py`). Remplacer les sons synthétisés par de
vrais enregistrements ne demande aucun changement de code (voir
`resources/chalk_sounds/README.txt`).

## Fournisseurs pluggables (LLM / TTS)

Même pattern d'abstraction pour les deux :

- `llm/base.py` : interface `LLMProvider.generate_script(text)`.
  Implémentations prévues : OpenRouter, Gemini Pro. Un seul appel par script.
- `tts/base.py` : interface `TTSProvider.synthesize(text, voice_profile)`.
  Par défaut historique : voix locale Windows (SAPI5 / pyttsx3), gratuite
  et hors-ligne — mais qualité jugée insuffisante par l'utilisateur une
  fois le reste (visuel, texte, timing) mis au niveau attendu. Profils de
  voix sauvegardés (`tts/voice_profiles.py`) réutilisables entre projets.
  Clonage de voix = uniquement via provider cloud (impossible correctement
  en local sur machine modeste), option opt-in explicite.

### Voix Gemini (cloud, payant, voix par défaut actuelle)

`tts/gemini_tts.py` (`GeminiTTSProvider`) appelle le même endpoint
`generateContent` que la génération de script (`llm/gemini.py`), avec
`generationConfig.responseModalities: ["AUDIO"]` et
`speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`. Une seule clé
API Gemini sert donc aux deux usages (script + voix). La langue n'est pas
un paramètre explicite : le modèle la détecte depuis le texte envoyé, la
même voix ("Sulafat" par défaut, choisie pour son caractère "Warm"/
chaleureux adapté à un ton d'enseignant) fonctionne donc pour du français
comme n'importe quelle autre langue.

L'API renvoie du PCM brut 24kHz mono 16 bits en base64 (`candidates[0]
.content.parts[0].inlineData.data`), pas un fichier conteneur — il faut
reconstruire un WAV soi-même (`wave.open` en écriture) pour que
`wave.open` en lecture (mesure de la durée réelle dans
`Pipeline.synthesize_voices`) et ffmpeg puissent le lire ensuite.

**Dispatch du provider TTS** : `api_bridge.py::_build_tts` choisit
`GeminiTTSProvider` ou `SapiLocalProvider` selon `VoiceProfile.provider`
("gemini_tts" ou "sapi_local") — corrige au passage un oubli antérieur où
`_build_pipeline` construisait toujours `SapiLocalProvider()` en dur, sans
jamais regarder le profil sélectionné par l'utilisateur dans l'assistant.

**Clé API** : stockée dans le trousseau Windows (`settings.get_api_key
("gemini")`, chemin normal) avec repli sur la variable d'environnement
utilisateur persistante `Gemini_Key_Virtual-Chalk` si le trousseau est
vide — l'utilisateur tient les deux à jour en parallèle.

OpenRouter propose aussi un endpoint TTS (`/api/v1/audio/speech`,
compatible OpenAI Audio Speech) avec des voix Google/OpenAI/Mistral — non
retenu ici : le crédit payant a été alloué spécifiquement sur la clé
Gemini, et l'appel direct à l'API Gemini évite un intermédiaire.

## Rythme de l'intro/conclusion (pas un bug de rendu)

Retour utilisateur : "on dirait que tout le début de la vidéo a été tronqué,
et même une partie de la fin" — après vérification approfondie (durée du
conteneur, intégrité de l'audio, contenu image à l'ouverture/fermeture),
aucune frame ni aucun son n'est réellement coupé. Le vrai problème :
absence d'introduction/conclusion — la scène d'ouverture enchaînait
directement sur un fait technique, la scène de clôture ajoutait un dernier
fait à la hâte, sans accroche ni récapitulatif — d'où l'impression de
précipitation.

Point clé à ne pas oublier en travaillant sur le timing des scènes : le
champ `duration_sec` produit par le LLM (`app/llm/prompts.py`) n'est
qu'une estimation initiale, écrasée par la durée réelle de l'audio
synthétisé dans `Pipeline.synthesize_voices` (`app/pipeline.py`) avant le
rendu. La durée effective d'une scène à l'écran vient donc entièrement de
la longueur de sa voix off une fois synthétisée — une scène d'intro/
conclusion trop courte en texte est nécessairement expédiée à l'écran,
quel que soit le `duration_sec` demandé. Le prompt système exige donc
explicitement 2-3 phrases pour la première scène (accroche + annonce du
sujet) et la dernière (récapitulatif + phrase de clôture), plutôt que le
message clé unique attendu des scènes intermédiaires.

## Profils de vidéo

`app/llm/prompts.py::VIDEO_PROFILES` (`cours_magistral`, `fiche_revision`,
`demo_produit`, `tutoriel`) ajuste le **ton et la structure** du script
(nombre de scènes, présence ou non d'une intro/conclusion développée,
type de scènes) sans toucher au vocabulaire visuel ni au format JSON de
sortie — un seul appel LLM, une seule structure de sortie, seule la
consigne narrative change. `SYSTEM_PROMPT` (constante figée) est devenu
`build_system_prompt(script_profile)` pour permettre cette
paramétrisation ; `LLMProvider.generate_script()` accepte `script_profile`
(voir `GenerationRequest` plus bas). Sélectionné dans l'assistant UX à
l'étape 3 (`ui/index.html`, `#video-profile-select`), à côté du thème et
de la voix.

Vérifié en opposant `cours_magistral` et `fiche_revision` sur le même
sujet : 8 scènes de 250-350 caractères avec accroche/conclusion contre 5
scènes de 110-135 caractères, directes, sans intro, avec étapes numérotées
explicitement pour `tutoriel`.

## Connecteur GitHub

`app/ingestion/github.py::fetch_repo_text()` récupère le README
(obligatoire, plusieurs orthographes/extensions essayées) et quelques
fichiers de doc de premier niveau (`CHANGELOG.md`, `CONTRIBUTING.md`,
`docs/README.md`) d'un dépôt public, à partir d'une URL `github.com` ou de
la forme `owner/repo` — volontairement limité à ces fichiers de premier
niveau plutôt qu'un crawl récursif de tout le dépôt, pour rester sobre et
rapide. Branché dans `normalize_source` comme un type de source de plus
(`text`/`file`/`url`/`github`), donc `Pipeline.run()` n'a besoin d'aucun
code spécifique en aval.

Le contenu brut d'un dépôt (README/CHANGELOG) ne dit pas lui-même sous
quel angle le présenter, contrairement à un texte déjà rédigé pour un
lecteur humain : `github_content_kind` (`architecture` / `installation` /
`changelog`, choisi dans l'assistant à côté de l'URL du dépôt) ajoute une
consigne d'angle au prompt utilisateur (`build_user_prompt`,
`GITHUB_CONTENT_KINDS`) — même mécanisme que les profils de vidéo, une
seule consigne textuelle en plus, aucun nouveau format de données.

## API interne (`GenerationRequest`)

`Pipeline.run()`/`generate_project()` ont grossi au fil des ajouts
(thème, profil, angle GitHub...) jusqu'à une signature à 6-7 paramètres
mélangeant obligatoires et optionnels sans regroupement logique.
`GenerationRequest` (dataclass, `app/pipeline.py`) regroupe les
paramètres d'une génération initiale (`source_text`, `voice_profile`,
`theme`, `script_profile`, `github_content_kind`, `export_h5p`) en un seul
objet passé à `Pipeline.run(request, on_progress=...)` — un seul endroit à
étendre pour une future option plutôt que de rallonger la signature à
chaque étape. Les étapes suivantes du pipeline (`generate_diagrams`,
`synthesize_voices`, `render`, `export_h5p`, `rerender_scene`,
`resynthesize_scene`) continuent de prendre le `Project` (ou une `Scene`)
directement : elles n'ont pas besoin des paramètres d'entrée de la
génération initiale, seulement de son résultat — regroupement volontaire
limité à l'entrée du pipeline, pas une convention forcée partout.

## Export H5P (finalité du projet, pas une extension)

`h5p/packager.py` construit `h5p.json` + `content/content.json` autour du
MP4 rendu, avec les librairies `H5P.InteractiveVideo` embarquées une fois
pour toutes en local (`resources/h5p_libraries/`, aucun téléchargement à
l'export). `h5p/bookmarks.py` génère automatiquement un bookmark par scène
(titre + timestamp) pour qu'un utilisateur lambda obtienne une vidéo
interactive utilisable sans configuration manuelle.

## Organisation des fichiers de sortie

Un dossier par projet, un sous-dossier par langue à l'intérieur —
`{réglages.default_output_dir}/{slug}/{lang}/` (`fr` par défaut, `en` pour
une traduction) contenant `video.mp4`, `video.h5p`, `project.golpoproj` et
un sous-dossier `scenes/{scene_id}.mp4` (cache par scène, voir plus bas).
`Pipeline.project_dir(slug, lang)` calcule/crée ce chemin ; toutes les
autres méthodes (`render`, `export_h5p`, `rerender_scene`) reçoivent ce
répertoire en paramètre plutôt que de le recalculer chacune de leur côté.
Une traduction (`Api.export_translated`) écrit dans un sous-dossier de
langue **frère** du dossier de la langue source (même dossier de projet,
`.../{slug}/en/`) plutôt que dans un nouveau dossier dérivé du titre
traduit — la version source n'est jamais modifiée.

**Cache de rendu par scène et reconstruction du montage final** :
`render_scene`/`render_all` (`app/render/partial_render.py`) écrivaient
auparavant chaque scène dans un fichier temporaire jetable
(`tempfile.mktemp`), et `render_all` ne retournait que les scènes dont le
hash avait changé — recombiner ça dans un montage "final" après un
re-rendu partiel aurait donc silencieusement perdu toutes les scènes
inchangées. Chaque scène est maintenant rendue dans un emplacement stable
(`{project_dir}/scenes/{scene_id}.mp4`) réutilisé comme cache ;
`render_all` retourne toujours le chemin de **toutes** les scènes (en
cache ou fraîchement rendues), donc le montage final reste complet.
`Pipeline.rerender_scene` force le re-rendu d'une scène puis reconstruit
la vidéo finale complète à partir de ce cache — avant ce correctif, le
clip re-rendu n'était jamais réintégré au montage, qui restait donc
périmé après une édition ciblée.

## Édition post-génération

Écran Éditeur (`ui/editor/`) : liste des scènes, aperçu canvas live de la
scène sélectionnée, panneau de propriétés (texte, couleur, position,
durée). Bouton "re-render cette scène" vs "re-render tout" —
`render/partial_render.py` ne régénère que ce qui a changé (et ne rappelle
le TTS que si le texte a changé).

### Édition par langage naturel (NL Editing)

Une barre de commande sous l'éditeur (`editor.js`) accepte une instruction
en français libre ("raccourcis la scène 3 à 15 secondes", "remplace le
thème par tableau blanc feutres", "supprime la dernière scène si elle ne
contient qu'une conclusion répétitive"...). `app/edit/nl_commands.py`
traduit cette instruction en une liste d'actions JSON structurées via **un
seul appel LLM** (`EDIT_SYSTEM_PROMPT`, `app/edit/prompts.py`), à partir
d'un vocabulaire fixe de 6 actions primitives (`update_scene_duration`,
`set_theme`, `delete_scene`, `move_scene`, `insert_scene`,
`replace_scene_content`) — jamais de régénération complète du script, pas
de deuxième appel LLM même pour `insert_scene` (le contenu de la nouvelle
scène est généré dans ce même appel de traduction).

Le LLM reçoit un résumé compact des scènes existantes (index + extrait de
la voix off, pas le script complet) pour résoudre lui-même les références
par contenu ("la scène sur X", "la dernière scène") et évaluer les
conditions ("supprime SI...") — une instruction ambiguë ou hors périmètre
produit une liste d'actions vide plutôt qu'une action inventée.
`apply_nl_edit_command` applique ensuite chaque action déterministiquement
au `Project` ; une action individuelle invalide (index hors limites,
thème inconnu) est journalisée et ignorée sans interrompre les autres.

`Api.apply_edit_command` (`api_bridge.py`) orchestre la suite : ne
re-synthétise (`Pipeline.resynthesize_scene`, scindée de
`synthesize_voices` pour ne traiter qu'une scène) que les scènes dont la
voix a changé, puis appelle `Pipeline.render` une seule fois — basé sur le
hash de contenu de chaque scène, il retrouve tout seul ce qui a réellement
changé et réutilise le cache pour le reste (voir "Organisation des
fichiers de sortie" plus haut), pas besoin de décider manuellement
"toutes les scènes vs seulement les modifiées". `set_theme` recolore
d'ailleurs maintenant les strokes existants avec la palette du nouveau
thème (`_recolor_strokes_for_theme`) — sans ça, un stroke coloré blanc
pour le tableau craie restait blanc après passage au tableau blanc feutre
(texte invisible sur fond blanc), et surtout son hash ne changeait pas
donc `render` l'aurait ignoré. Le `.golpoproj` est re-sauvegardé après coup.

**Piège rencontré** : passer le chemin du `.golpoproj` à éditer en query
string sur l'URL `file://...editor.html?project=...` échoue silencieusement
sous WebView2 (`ERR_FILE_NOT_FOUND`) — corrigé en passant ce chemin par le
pont JS↔Python existant (`Api.get_current_project_path()`, lu par
`editor.js` une fois `pywebviewready` déclenché) plutôt que par l'URL.

## Arborescence

```
app/
  main.py, api_bridge.py, pipeline.py, settings.py, paths.py
  edit/           nl_commands.py, prompts.py (édition par langage naturel)
  i18n/           translate.py (export multilingue)
  ingestion/      pdf_reader.py, docx_reader.py, url_reader.py, github.py, text_normalizer.py
  llm/            base.py, openrouter.py, gemini.py, prompts.py
  tts/            base.py, sapi_local.py, cloud_providers.py, voice_profiles.py
  scenes/         schema.py, project_store.py, project_file.py
  render/         capture.py, ffmpeg_wrapper.py, partial_render.py, diagram_generator.py
    web_template/ index.html, themes.js, text_to_path.js
      surfaces/   blackboard.js, greenboard.js, whiteboard.js
      tools/      chalk.js, marker_veleda.js
    assets/       board_textures/, chalk_textures/
  h5p/            packager.py, bookmarks.py
ui/               index.html (assistant 5 étapes), css/, js/
  editor/         éditeur post-génération
resources/        ffmpeg/, h5p_libraries/
build/            pyinstaller.spec, installer.iss
```

## Export multilingue (FR → EN)

`app/i18n/translate.py::translate_project()` traduit un `Project` déjà
généré vers une autre langue en **un seul appel LLM** : titre, résumé,
voix off de chaque scène, texte affiché à la craie (`Stroke.text` pour
`kind="text"`), et champs texte des exercices. Les icônes/animations/
diagrammes (déjà résolus en tracé vectoriel, indépendants de la langue)
sont copiés tels quels — jamais régénérés, ce qui éviterait un appel
Gemini image-gen supplémentaire et produirait un dessin visuellement
différent de la version source.

`Api.export_translated(target_lang)` (bouton "Exporter aussi en anglais"
sur l'écran Résultat, déclenché après validation de la version française)
enchaîne : traduction → `Pipeline.synthesize_voices()` (re-synthèse
complète dans la langue cible — la voix Gemini détecte la langue depuis
le texte, aucun paramètre de langue explicite nécessaire côté TTS) →
`Pipeline.render()` (re-rendu complet, les durées de scène changent avec
la nouvelle voix) → `Pipeline.export_h5p()`. Fichiers de sortie nommés
d'après le slug du titre traduit (`{slug-en}.mp4`/`.h5p`/`.golpoproj`),
jamais de collision avec la version française qui reste inchangée.

**Limite v1 assumée** : le texte traduit garde exactement la position de
l'original (pas de recalcul d'anti-chevauchement `resolve_overlaps`) — un
texte sensiblement plus long/court dans la langue cible peut
occasionnellement chevaucher un élément voisin. Défaut cosmétique accepté
pour rester simple ; correction possible via une commande NL Editing
(`app/edit/nl_commands.py`) si ça s'avère gênant en pratique. Vérifié de
bout en bout sur un projet réel (6 scènes, thème feutre) : traduction
correcte, vidéo et .h5p produits, version française d'origine intacte.

**Arabe explicitement reporté** : nécessiterait l'écriture de droite à
gauche (le moteur de texte actuel — `text_to_path.js` + police Caveat —
suppose du latin gauche-à-droite) et une police manuscrite arabe avec
shaping contextuel (opentype.js le supporte en théorie si la police a les
bonnes tables GSUB, non vérifié) — un sous-chantier à part entière plutôt
qu'une simple langue de plus.

## Tests

`tests/` (pytest, `pytest.ini` à la racine) couvre la logique métier pure
plutôt que l'UI ou le rendu vidéo réel — aucun test n'effectue de vrai
appel réseau/LLM/TTS ni de vrai rendu ffmpeg/capture d'écran :

- `test_llm_base.py` — robustesse de `LLMProvider.complete_json` (JSON
  pur, JSON entouré de texte parasite, réponse inexploitable →
  `LLMJsonError`).
- `test_nl_commands.py` — résolution sûre de `scene_id`/index dans
  l'édition NL (`Project.find_scene`, action inconnue/index hors limites
  ignorés sans casser la commande), et hiérarchie de recoloration par
  kind de stroke (`_recolor_strokes_for_theme`).
- `test_translate.py` — `translate_project` ne mute jamais le `Project`
  source, propage `LLMJsonError` sans construire de résultat partiel.
- `test_github_ingestion.py` — `app/ingestion/github.py` : parsing
  d'URL, README manquant, dépôt introuvable (404), limite de requêtes
  (403/429), erreur réseau — toutes simulées via un `requests.get` factice.
- `test_render_cache.py` — logique de cache de `render_all`
  (`app/render/partial_render.py`) : ne re-rend que les scènes dont le
  `content_hash` a changé ou dont le fichier caché a disparu, mais
  retourne toujours le chemin de **toutes** les scènes dans l'ordre —
  verrouille le bug historique corrigé pendant cette session (scènes
  inchangées silencieusement absentes du montage final). `render_scene`
  y est entièrement simulé (pas de vraie capture/encodage).
- `test_api_bridge_voice_fallback.py` — `Api.start_pipeline` retombe sur
  `_DEFAULT_VOICE_PROFILE` si `voice_profile_name` ne correspond à aucun
  profil connu, plutôt que de laisser `None` se propager. `Pipeline.run`
  y est entièrement simulé.

`tests/conftest.py` fournit `FakeLLMProvider` (sous-classe de
`LLMProvider` qui rejoue une liste de réponses brutes préparées à
l'avance au lieu d'appeler un vrai modèle), réutilisé par les tests LLM/
NL editing/traduction. Lancer la suite : `pytest` depuis la racine du
dépôt (nécessite `pip install -r requirements.txt`, `pytest` y est listé
en dépendance de dev).

## Reporté

- Interactions H5P avancées au-delà des bookmarks auto (pause, question) —
  extension naturelle de l'éditeur de scène plus tard.
- Providers LLM/TTS/thèmes supplémentaires au-delà de ceux listés —
  l'abstraction est prête, ajouter un provider = une classe de plus.
- Connecteurs "workflow" au-delà de GitHub (Jira, Calendar...) —
  l'architecture reste extensible (un module `ingestion` par source, une
  interface commune vers `source_text`), aucun besoin identifié pour
  l'instant au-delà de GitHub.
- Export en arabe (voir ci-dessus).
- Mode brouillon (voix SAPI gratuite) → finalisation (voix Gemini) :
  écarté — le changement de voix implique des durées différentes donc un
  re-rendu complet, jugé pas assez rentable par rapport à la simplicité de
  choisir directement la voix voulue dès le départ.
