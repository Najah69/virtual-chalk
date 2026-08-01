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
- **Projet vectoriel éditable** : le fichier projet (`.vchalk`) est la
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

### Mise en page mobile (portrait 1080x1920 vs paysage 1920x1080)

Retour utilisateur : le tableau était toujours en paysage (1920x1080), y
compris pour une vidéo destinée à être lue sur téléphone/réseaux sociaux.
Case "Mise en page mobile" à l'étape 1 de l'assistant (`ui/index.html`,
`#mobile-layout`), **cochée par défaut** — un vrai format vertical
1080x1920 (`Project.mobile_layout`), pas un simple recadrage optique du
paysage.

**Pourquoi décidé à l'étape 1, avant l'appel LLM (comme le profil de
vidéo), contrairement au thème (choisi à l'étape 3)** : les éléments
visuels du LLM sont exprimés en pourcentage (voir plus haut) mais
`strokes_from_visual_elements` les convertit IMMÉDIATEMENT en pixels
absolus, figés dans `Stroke.points` — contrairement à la couleur (simple
attribut recalculable après coup par `_recolor_strokes_for_theme`),
changer l'orientation après génération demanderait de relayouter toute la
scène, pas juste de la retoucher. `GenerationRequest.mobile_layout` (donc
`Pipeline.generate_project` → `LLMProvider.generate_script` →
`Project.from_llm_response`) porte ce choix jusqu'à la conversion
pourcentage → pixel.

**Deux constantes de repli distinctes selon le contexte** (`app/scenes/
schema.py`) :
- `Project.from_llm_response` (nouvelle génération) : défaut
  `mobile_layout=True`, cohérent avec la case cochée par défaut.
- `Project.from_dict` (chargement d'un `.vchalk` existant) : défaut
  `mobile_layout=False` si la clé est absente — un projet enregistré
  avant cette fonctionnalité a ses strokes figés en pixels pour le SEUL
  format qui existait alors (paysage) ; le réinterpréter en portrait par
  défaut le ferait déborder du nouveau cadre plus étroit.

**Propagation dans tout le moteur de rendu**, qui ne connaissait jusqu'ici
que 1920x1080 en dur à plusieurs endroits :
- `app/render/web_template/index.html::loadScene(scene, themeId,
  canvasWidth, canvasHeight)` redimensionne `<canvas id="stage">`
  (attributs `width`/`height`, PAS juste sa taille CSS affichée) avant de
  dessiner le fond — un canvas HTML alloue toujours un backing store de la
  taille de ces attributs, indépendamment de la fenêtre/viewport qui
  l'héberge (la fenêtre de rendu cachée, `main.py`, reste fixe à
  1920x1080 : `canvas.toDataURL()` lit quand même le backing store entier,
  pas seulement la portion visible dans la fenêtre).
- `FrameCapture.render_scene_frames` (`app/render/capture.py`) reçoit
  `canvas_width`/`canvas_height` en paramètres, lus depuis
  `Project.canvas_size` par `partial_render.render_scene` (seul endroit
  où `Project` est encore en scope à ce niveau).
- `ui/editor/editor_canvas.js` : `CANVAS_WIDTH`/`CANVAS_HEIGHT` sont
  passés de constantes à variables (`let`), fixées par
  `setCanvasSize(mobileLayout)` — appelée par `EditorCanvas.loadScene`,
  elle-même appelée par `editor.js::selectScene` avec
  `currentProject.mobile_layout`.
- `Api.insert_image` utilisait par erreur les constantes globales
  `CANVAS_WIDTH`/`CANVAS_HEIGHT` (toujours paysage) pour la conversion
  pourcentage → pixel plutôt que `self._current_project.canvas_size` — un
  projet portrait aurait alors positionné/dimensionné une image insérée
  pour le mauvais cadre. Corrigé au passage.
- `app/edit/nl_commands.py` (`_apply_insert_scene`,
  `_apply_replace_scene_content`) appelaient `strokes_from_visual_elements`
  sans dimensions explicites (repli silencieux sur le paysage) : une
  scène insérée/remplacée par édition NL sur un projet portrait aurait
  été mal mise à l'échelle. Corrigé pour passer `*project.canvas_size`.
- `app/i18n/translate.py::translate_project` réutilise les strokes
  (positions déjà figées) de l'original tels quels — doit donc reporter
  `project.mobile_layout` sur le `Project` traduit plutôt que de retomber
  sur le défaut `True`, sans quoi un projet paysage traduit se
  verrait rendu avec un cadre portrait sans rapport avec ses coordonnées
  réelles.
- `app/render/ffmpeg_wrapper.py`/le reste du moteur JS (surfaces, mascot,
  animations) étaient déjà paramétrés en largeur/hauteur (aucune valeur
  1920/1080 en dur trouvée en dehors des points ci-dessus) — rien à
  changer là.

**Bug corrigé au passage — titre "décalé"** : le LLM choisit x/y en
pourcentage sans garantie de bien centrer son texte d'ouverture, et même
un x=50% correct n'est pas un centrage réel puisque l'ancre d'un texte
est sa ligne de base à GAUCHE (pas son centre). `strokes_from_visual_elements`
traite maintenant le PREMIER texte placé dans la bande du haut du tableau
(`TITLE_TOP_BAND_PCT = 30`, pourcentage de hauteur) comme le titre/
l'accroche de la scène : son ancre est recalculée pour centrer réellement
le texte (`canvas_width/2 - largeur_estimée(texte)/2`, réutilise
`app/render/layout.py::text_width`, déjà utilisé pour les boîtes
englobantes de collision) et marquée `pinned_x` — un nouveau champ que
`resolve_overlaps` respecte : un élément épinglé sur un axe n'est plus
jamais déplacé sur cet axe (seul l'AUTRE élément d'une paire en collision
bouge, du double du déplacement habituel pour compenser). Seul le premier
texte de la bande du haut est traité ainsi (pas tous) : un deuxième texte
qui s'y trouverait aussi (rare) garde sa position normale, pour ne pas
superposer deux textes tous deux forcés au même centre.

`resolve_overlaps`/`_push_apart` avaient aussi une hypothèse implicite
"le tableau est plus large que haut" pour départager un chevauchement
parfaitement symétrique (cas dégénéré, deux éléments à coordonnées
identiques) — plus vraie en portrait. Corrigé pour comparer réellement
`canvas_width`/`canvas_height` (déjà passés en paramètres) plutôt que de
préférer l'axe horizontal inconditionnellement.

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

### Mascotte animée

Personnage optionnel (case "Ajouter une mascotte animée" à l'étape 3 de
l'assistant, ou commande NL Editing "active/désactive la mascotte") qui
apparaît en coin bas-gauche du tableau, réagit brièvement au contenu de
chaque scène, puis disparaît. Contrairement aux animations à stroke
unique (`falling_rain`) qui rejouent la même boucle du début à la fin de
leur fenêtre active, la mascotte enchaîne plusieurs **phases**
successives au sein d'une même scène.

**Schéma** (`app/scenes/schema.py`) : `Scene.mascot_timeline: list[MascotAction]`,
chaque `MascotAction` = `{action_type: "appear"|"wave"|"point"|"idle"|"disappear",
start_sec, end_sec, target_x, target_y}` (target_x/y en pixels canvas,
utilisés uniquement par `"point"`). `Project.mascot_enabled: bool`
reflète l'état courant, pour que l'UI et l'édition NL puissent l'afficher/
le faire évoluer sans avoir à inspecter toutes les scènes.

**Timeline déterministe, jamais générée par le LLM**
(`default_mascot_timeline()`) : la mascotte ne fait que réagir à des
données déjà connues (durée de la scène, premier élément visuel non
textuel déjà positionné par `strokes_from_visual_elements`) — aucun appel
LLM supplémentaire, aucun risque de timeline malformée à valider. Séquence
type : `appear` (0 → ~0.6s) → `wave` (uniquement sur la toute première
scène du projet, salut de bienvenue) ou directement `point` vers le
premier élément non textuel de la scène s'il y en a un → `idle` (le
reste) → `disappear` (dernières ~0.6s). Sur une scène trop courte pour
qu'un geste soit lisible (`MASCOT_MIN_POINT_WINDOW_SEC`), `wave`/`point`
sont simplement omis. `add_mascot_timeline(project)` (re)calcule cette
timeline pour toutes les scènes et met `mascot_enabled = True` ;
`remove_mascot_timeline(project)` vide toutes les timelines et remet
`mascot_enabled = False` — jamais d'état intermédiaire incohérent
(timeline non vide mais mascotte "désactivée") persisté dans le
`.vchalk`.

**Génération initiale** (`Pipeline.run`) : si `GenerationRequest.mascot_enabled`,
`add_mascot_timeline` est appelé après `generate_diagrams` (pas avant) —
un diagramme retiré faute de génération réussie ne doit pas être choisi
comme cible de `"point"`.

**Édition NL** : nouvelle action `toggle_mascot` (`app/edit/prompts.py`,
`app/edit/nl_commands.py::_apply_toggle_mascot`) — no-op si déjà dans
l'état demandé, sinon marque toutes les scènes comme changées (leur
`content_hash` change réellement, voir plus bas) pour que
`Api.apply_edit_command` déclenche `Pipeline.render`.
`_apply_insert_scene` donne aussi une timeline à toute nouvelle scène
insérée si `project.mascot_enabled` (jamais en mode "salut", réservé à la
scène 0 du projet).

**Cache de rendu** : `_hash_scene` (`app/render/partial_render.py`) inclut
maintenant `scene.mascot_timeline` dans le hash — sans ça, activer/
désactiver la mascotte ne changerait le hash d'aucune scène et
`render_all` ignorerait silencieusement le besoin de re-rendu (même piège
que celui corrigé pour `set_theme`, voir plus haut).

**Rendu JS** (`app/render/web_template/mascot.js`) : position d'ancrage
FIXE (coin bas-gauche, `MASCOT_ANCHOR_FRACTION`) — seule la pose interne
bouge (bras, yeux, échelle d'apparition/disparition), ce qui borne une
fois pour toutes la région à effacer/redessiner à chaque frame (même
technique que les animations : restaurer depuis
`window._boardTextureCache`), y compris pour `"point"` où le bras s'étend
vers une cible potentiellement lointaine (`MASCOT_POINT_REACH` plafonne
la portée dessinée, donc la région à effacer). Personnage entièrement
tracé au canvas (cercle, yeux, bras — pas de sprite bitmap importé),
couleur dédiée par thème (`MASCOT_COLORS`, distincte des couleurs de
texte pour rester visuellement identifiable). `window.drawMascot` n'est
appelé que pour les scènes dont `mascot_timeline` est non vide — aucun
coût supplémentaire sur les scènes/projets sans mascotte.

**Limite v1 assumée** : l'emplacement du coin bas-gauche n'est pas exclu
de `resolve_overlaps` — un élément visuel placé par le LLM à cet endroit
précis pourrait occasionnellement se retrouver recouvert par la mascotte
à chaque frame où elle est active. Considéré rare en pratique (coin
extrême, éléments plutôt distribués vers le centre par le prompt de
génération) et cohérent avec la limite déjà assumée pour l'export
multilingue (repositionnement non recalculé) ; à corriger plus tard en
réservant explicitement cette zone dans `resolve_overlaps` si ça s'avère
gênant en usage réel.

**Vérifié de bout en bout sur l'exe packagé** (pas seulement en test
unitaire) : cycle complet désactivation → réactivation de la mascotte via
`toggle_mascot` (commande NL "désactive/active la mascotte animée sur
toutes les scènes") sur un vrai projet de 8 scènes déjà généré, avec une
image insérée entre les deux (voir section suivante) pour confirmer que
les deux fonctionnalités cohabitent sans se marcher dessus. Dans les deux
sens, `Api.apply_edit_command` régénère bien la vidéo finale (mtime de
`video.mp4` changé, `mascot_enabled` correctement mis à jour), et une
frame extraite après coup montre la mascotte réellement absente/présente
selon le sens du basculement. Réactiver la mascotte sur 8 scènes prend
environ 232s (ré-encodage complet de chaque scène + concat) — un premier
essai avait semblé bloqué après plusieurs minutes sans activité ffmpeg
visible, mais un second essai a confirmé qu'il s'agissait simplement du
temps normal de l'appel LLM + du rendu, pas d'un blocage réel.

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

### Insertion d'images (bitmap/vecteur)

Depuis l'éditeur (`ui/editor/`), bouton "Insérer une image" : sélectionne
un fichier (PNG/JPG/GIF/WEBP/SVG), le place sur la scène sélectionnée via
des champs numériques x/y/largeur/hauteur en pourcentage (pas de glisser-
déposer — l'éditeur n'a pas encore de rendu live par élément dans
`canvas-preview`, TODO préexistant, non construit ici pour rester dans le
périmètre de cette tâche), puis re-rend immédiatement la scène.

**`Stroke.kind = "image"`** réutilise le reste du modèle existant :
`points[0]` = ancre haut-gauche (même convention que icône/diagramme),
`width`/`height` = taille d'affichage en pixels canvas, nouveau champ
`image_data` = l'image encodée en **data URI base64** (bitmap ou SVG, même
mécanisme pour les deux). Aucun nouveau champ sur `Scene`/`Project` : le
cache de rendu (`content_hash`), la sérialisation (`to_dict`/`from_dict`)
et le `.vchalk` fonctionnent donc sans modification particulière — au
passage, la reconstruction manuelle de `Stroke` dans `Project.from_dict`
oubliait déjà `height` avant cette tâche (bug préexistant, corrigé ici en
même temps que l'ajout d'`image_data` puisque les deux touchent la même
ligne).

**Pourquoi base64 et pas un chemin de fichier** (décision prise avant
d'écrire le code, vérifiée empiriquement) : la fenêtre de rendu charge
`web_template/index.html` en `file://`, et capture chaque frame via
`canvas.toDataURL()` (voir `capture.py`). Dessiner sur ce canvas une image
chargée depuis un **autre** `file://` le rend "tainted" (Chromium traite
chaque `file://` comme une origine distincte) : `toDataURL()` lèverait
alors une `SecurityError`, cassant la capture de **toutes** les frames
suivantes — pas seulement celles avec une image. Une image encodée en
data URI reste same-origin pour le canvas, donc sans ce risque. La
lecture du fichier et l'encodage base64 se font côté Python
(`Api.pick_and_encode_image`, I/O sans restriction) plutôt que par le JS
de l'éditeur (page `file://`, `fetch()` d'un autre `file://` non fiable
sous Chromium — non plus testé mais écarté par prudence au profit d'une
solution déjà connue pour marcher).

**Décodage asynchrone, capture bloquante** : même un data URI n'est pas
décodé de façon garantie synchrone par le navigateur (vérifié
empiriquement : `evaluate_js` de pywebview ne résout pas correctement une
Promise renvoyée par une fonction JS `async`, donc `window.loadScene` ne
peut pas simplement `await` le décodage et laisser Python attendre le
retour). À la place, `loadScene` lance le décodage en fire-and-forget
(`Image.onload`) et expose `window.allImagesReady()` ; `FrameCapture`
(`capture.py::_wait_for_images_ready`) fait un petit nombre
d'aller-retours `evaluate_js` en attendant `true` (quelques millisecondes
en pratique pour une image déjà en mémoire, testé), avec un timeout de
sécurité de 5s pour ne jamais bloquer indéfiniment. No-op immédiat pour
toute scène sans stroke "image".

**Rendu** (`web_template/index.html::renderAtTime`) : pas de tracé
progressif possible pour un bitmap (contrairement au texte/icônes) —
simple fondu d'apparition (`globalAlpha`) puis figé une fois `end_sec`
dépassé, même principe `_frozen` que les animations. `timing.py` n'a eu
besoin d'aucune modification : un stroke "image" n'a qu'un point
(l'ancre), donc `_path_length` retombe déjà sur son minimum
(`MIN_DRAW_SECONDS`), un comportement de repli générique déjà correct
pour ce cas.

**H5P** : aucune modification nécessaire — l'image est déjà gravée dans
les pixels de la vidéo MP4 rendue avant `export_h5p`, comme les
diagrammes vectorisés.

Vérifié de bout en bout avec le vrai pipeline de capture (`FrameCapture`
piloté directement, pas seulement `evaluate_js` isolé) : image affichée à
la bonne position/taille à côté d'une icône dans la même scène, aucune
`SecurityError` sur les 180 frames capturées.

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
l'étape 1 (`ui/index.html`, `#video-profile-select`) — déplacé de
l'étape 3 pour être connu avant l'appel LLM de génération du script (voir
"Révision du script (étape 2)" plus bas, qui dépend de ce profil dès le
premier appel à `Api.generate_script`).

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
objet passé à `Pipeline.run(request, on_progress=...)` (ou, depuis la
révision du script ci-dessous, à `generate_project()` puis
`finish_generation()` séparément) — un seul endroit à étendre pour une
future option plutôt que de rallonger la signature à chaque étape. Les
étapes suivantes du pipeline (`generate_diagrams`, `synthesize_voices`,
`render`, `export_h5p`, `rerender_scene`, `resynthesize_scene`)
continuent de prendre le `Project` (ou une `Scene`) directement : elles
n'ont pas besoin des paramètres d'entrée de la génération initiale,
seulement de son résultat — regroupement volontaire limité à l'entrée du
pipeline, pas une convention forcée partout.

## Révision du script (étape 2 de l'assistant)

Avant ce correctif, l'assistant enchaînait script → diagrammes → voix →
rendu en un seul appel bloquant (`Pipeline.run`) : impossible de relire ou
corriger le texte généré par le LLM avant de payer la synthèse vocale et
le rendu, qui utilisent ce texte tel quel. `Pipeline.run()` a été scindé
en deux :

- `generate_project(request, on_progress)` : ne fait que l'appel LLM de
  génération du script (`llm.generate_script`) et retourne le `Project`
  brut (scènes + strokes, sans audio/vidéo).
- `finish_generation(project, request, on_progress)` : reprend un
  `Project` déjà produit et termine tout le reste (diagrammes, mascotte,
  synthèse vocale, rendu, sauvegarde `.vchalk`, export H5P). `request`
  n'y est relu que pour `voice_profile`/`theme`/`export_h5p`/
  `mascot_enabled` — `source_text`/`script_profile`/`github_content_kind`
  ont déjà été consommés par `generate_project` et ne sont pas repassés
  (voir signature : `source_text=""` côté appelant, `Api.
  start_pipeline_from_script`). `Pipeline.run()` reste disponible et
  appelle simplement les deux à la suite, pour tout appelant qui n'a pas
  besoin de l'étape de révision (aucun aujourd'hui, gardé pour ne pas
  casser un usage direct de `Pipeline` hors `Api`).

Côté `Api` (`app/api_bridge.py`), deux méthodes remplacent l'ancien
`start_pipeline` unique :

- `generate_script(source, script_profile, github_content_kind)` : appelle
  `generate_project`, stocke le résultat dans `self._pending_script_project`
  (état de session — un seul script "en attente" à la fois, écrasé par un
  nouvel appel), et retourne `project.to_dict()` au JS pour affichage. Le
  thème n'est pas encore connu à ce stade (choisi à l'étape 3 suivante) :
  les strokes sont générés avec un thème provisoire (`"chalk_board"`) et
  recolorés après coup si l'utilisateur choisit un autre thème (même
  mécanisme que `set_theme` en édition NL, voir `_recolor_strokes_for_theme`).
- `start_pipeline_from_script(edited_scenes, voice_profile_name, export_h5p,
  theme, mascot_enabled)` : reprend `_pending_script_project` (erreur
  explicite si absent — l'utilisateur a sauté l'étape 2, ou rafraîchi la
  page), réapplique les éditions textuelles faites à l'étape 2
  (`edited_scenes` : liste de `{scene_id, voice_over}`), recolore les
  strokes si le thème a changé depuis l'étape 2, puis appelle
  `finish_generation`. Vide `_pending_script_project` en sortie (script
  consommé).

Côté UI (`ui/index.html`/`ui/js/app.js`) : l'étape 2 ("Script généré")
affiche une `<textarea>` par scène (`renderScriptEditor`), pré-remplie
avec `voice_over`, éditable librement — ces valeurs sont relues au clic
sur "Générer la vidéo →" (étape 3→4) et envoyées telles quelles à
`start_pipeline_from_script`. Le bouton "Générer le script →" (étape 1→2)
se désactive et affiche un libellé de progression pendant l'appel LLM
(aucune barre de progression : un seul appel, généralement quelques
secondes).

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
une traduction) contenant `{slug}.mp4`, `{slug}.h5p`, `project.vchalk` et
un sous-dossier `scenes/{scene_id}.mp4` (cache par scène, voir plus bas).
Le nom du fichier vidéo/h5p lui-même reprend le slug du projet (pas
"video.mp4"/"video.h5p" génériques comme avant — un fichier isolé de son
dossier, partagé ou déplacé, doit rester identifiable). `Api.load_project`
cherche ce nom, et se replie sur l'ancien nom générique "video.mp4" pour
les projets générés avant ce changement. `Pipeline.project_dir(slug, lang)`
calcule/crée ce chemin ; toutes les autres méthodes (`render`,
`export_h5p`, `rerender_scene`) reçoivent ce répertoire en paramètre
plutôt que de le recalculer chacune de leur côté.
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

**Bug corrigé — lecteur vidéo intégré (étapes 5/6 de l'assistant, et
aperçu de re-rendu de l'éditeur)** : `Api.start_pipeline_from_script`
renvoyait un chemin Windows brut (ex: `C:\Users\...\video.mp4`), et
`ui/js/app.js` l'assignait directement à `<video>.src` — pas une URL
valide, le navigateur échoue silencieusement à charger le média (aucune
erreur visible, juste "Impossible de lire les fichiers multimédias" côté
accessibilité).

Premier correctif tenté (**incorrect, corrigé depuis**) : convertir en URI
`file://` côté JS (`toFileUri()`) avant assignation, sur l'hypothèse
qu'un `<video>`/`<img>` peut afficher un fichier `file://` même depuis
une page `http://`. **Faux en pratique** : `ui/index.html`/`ui/editor/
editor.html` sont servies via le mini serveur HTTP local de pywebview
(`http://localhost:<port>/...`, voir plus bas "Éditeur visuel WYSIWYG"),
et WebView2/Chromium **refuse** de charger un `<video src="file://...">`
depuis une page qui n'est pas elle-même `file://` — vérifié
empiriquement (`video.error.message === "Media load rejected by URL
safety check"`, `video.error.code === 4`), pas juste un détail non
documenté. Ce premier correctif faisait passer les vérifications
superficielles (le `.src` assigné était syntaxiquement valide, l'appel
Python ne levait aucune exception) mais n'avait jamais été vérifié par
une vraie lecture — les contrôles du lecteur s'affichaient, mais rien ne
se jouait. `webview.settings["ALLOW_FILE_URLS"]` (`--allow-file-access-
from-files`) ne résout PAS ce cas non plus (vérifié) : ce flag ne lève
que les restrictions file://→file://, pas http://→file://.

Correctif définitif : `app/local_media_server.py`, un second petit
serveur HTTP local dédié (`http.server.ThreadingHTTPServer`, port
aléatoire sur `127.0.0.1`), avec support des requêtes `Range` (206
Partial Content — nécessaire pour que le lecteur puisse chercher dans la
vidéo, pas juste la lire séquentiellement). `serve(path)` enregistre un
chemin sous un jeton aléatoire (pas le nom de fichier — évite toute
collision et ne révèle pas l'arborescence réelle du disque) et renvoie
son URL (`http://127.0.0.1:<port>/<jeton>`) ; démarre paresseusement au
premier appel. Ne sert **que** les chemins explicitement enregistrés par
l'app (jamais un dossier entier) — même si le serveur n'écoute que sur
127.0.0.1 (donc déjà inaccessible depuis le réseau), pas de raison
d'exposer plus que ce que l'app a elle-même généré. `Api.
start_pipeline_from_script` (champ `video_url`, en plus de `video_path`
qui reste le chemin brut pour l'affichage/"Ouvrir le dossier"), `Api.
rerender_scene`/`Api.rerender_all` (valeur de retour, remplace
directement l'ancien chemin brut) l'utilisent tous les trois ; `toFileUri()`
a été retiré des deux fichiers JS.

Pourquoi une DEUXIÈME instance de serveur local plutôt que d'étendre
celui de pywebview (déjà utilisé pour `ui/index.html` elle-même) : sa
racine (`server.root_path`) est calculée une seule fois comme le plus
petit ancêtre commun des URLs locales passées à `webview.start()`
(limité à l'arborescence de l'app), et sa route `bottle.static_file`
refuse tout chemin en dehors de cette racine (protection anti-traversal)
— la vidéo générée vit dans le dossier de sortie choisi par
l'utilisateur, hors de cette arborescence. La copier dans l'arborescence
de l'app pour la rendre servable n'est pas fiable une fois installée
(`Program Files` n'est pas inscriptible sans élévation) ; pywebview
n'expose par ailleurs aucun point d'extension pour ajouter une route
supplémentaire à son propre serveur.

## Édition post-génération

Écran Éditeur (`ui/editor/`) : liste des scènes, aperçu WYSIWYG interactif
de la scène sélectionnée (voir "Éditeur visuel WYSIWYG" ci-dessous),
panneau de propriétés contextuel (scène si rien n'est sélectionné,
élément si un stroke est sélectionné sur le canvas). Bouton "Re-render
cette scène" vs "Re-render tout" — `render/partial_render.py` ne
régénère que ce qui a changé (et ne rappelle le TTS que si le texte de la
voix off a changé, voir "Propriétés de scène" ci-dessous).

### Éditeur visuel WYSIWYG

**Constat de départ** : jusqu'ici, l'écran Éditeur était une façade — le
canvas était vide (jamais câblé, `// TODO` resté tel quel depuis le début
de ce chantier), le panneau de propriétés n'exposait que 3 champs au
niveau de la scène (et aucun n'était réellement sauvegardé nulle part),
et il n'existait aucune notion de "sélectionner un élément visuel".
Seules l'édition en langage naturel et les boutons Re-render
fonctionnaient réellement.

**Décision d'architecture** : `ui/editor/editor_canvas.js` réutilise les
**mêmes modules que web_template/index.html** (`themes.js`,
`surfaces/*.js`, `tools/chalk.js`/`marker_veleda.js`, `text_to_path.js`,
`icon_paths.js`, `icon_to_path.js`, `animations.js`) plutôt qu'un second
moteur de rendu simplifié — chaque outil est appelé avec `progress=1`
(trait déjà entièrement tracé, sans l'animation d'écriture) pour un
aperçu fidèle au rendu final (police manuscrite réelle, icônes, grain
craie/feutre). Contrairement au moteur de capture (qui accumule la craie
sans jamais effacer, pour un rendu incrémental rapide sur des milliers de
frames), ce module redessine l'intégralité du canvas à chaque
changement : les éléments peuvent être déplacés/supprimés/redimensionnés
ici, l'hypothèse "jamais effacé" ne tient plus.

**Deux prérequis techniques découverts en construisant cette
réutilisation**, tous deux corrigés :

1. `Api.open_editor()` chargeait `editor.html` via `.as_uri()` (URL
   `file://...`). `web_template/index.html` (fenêtre de rendu) est
   chargée via un chemin brut, ce que pywebview traite différemment :
   toute URL locale qui n'est NI `http(s)://` NI `file://`
   (`webview.util.is_local_url`) déclenche son mini serveur HTTP local
   (`http://localhost:<port>/...`, racine = `base_dir()`, voir
   `app/paths.py`) — permettant les requêtes locales (XHR synchrone pour
   charger la police manuscrite, voir point 2) qui échouent en `file://`.
   `open_editor()` charge donc maintenant `editor.html` de la même façon
   (chemin brut), ce qui active ce même serveur pour la fenêtre Éditeur.
2. `text_to_path.js` chargeait la police manuscrite via une URL
   *relative* (`"fonts/Caveat.ttf"`), qui se résout par rapport à la
   **page** qui inclut le script, pas au fichier `.js` lui-même — correct
   depuis `web_template/index.html` (`fonts/` est un sous-dossier de ce
   même répertoire) mais pointerait vers `ui/editor/fonts/...`
   (inexistant) une fois ce script inclus depuis `editor.html`. Corrigé
   en un chemin absolu (`/app/render/web_template/fonts/Caveat.ttf`),
   résolu depuis la racine du serveur local quelle que soit la page
   appelante.

**Modèle de données** : `stroke.points` reste TOUJOURS la donnée
persistée/source de vérité (ancre haut-gauche pour icône/animation/
image/diagramme, point de départ baseline pour texte, tracé vectoriel
complet déjà résolu pour "shape") — jamais réécrite avec le tracé
développé. Le tracé réellement dessinable (contours de lettres/icône) est
calculé à la volée et mis en cache sur le stroke dans des champs préfixés
`_` (`_drawPoints`, `_chalkDabs`...), jamais envoyés à Python
(`EditorCanvas.serializeStrokesForSave()` les dépouille explicitement).

**Interaction** (souris sur le canvas, aucune bibliothèque externe) :
- **Sélection** : hit-test par boîte englobante (calculée depuis les
  points réellement dessinables pour texte/forme, depuis `width`/
  `height` pour icône/animation/image/diagramme) au clic ; le dernier
  élément posé (dessiné par-dessus) est prioritaire.
- **Déplacement** : glisser un élément sélectionné translate son ancre
  (ou tous ses points pour "shape", qui n'a pas d'ancre unique).
- **Redimensionnement** (Phase 3) : 4 poignées aux coins, uniquement
  pour les kinds à taille explicite (image, icône, animation,
  diagramme) — ajuste `width`/`height` et l'ancre selon le coin tiré.
- **Ajout** (Phase 4) : "+ Texte"/"+ Image..."/"+ Icône..." arment un mode
  "placement" (`startPlacingNewText`/`startPlacingNewImage`/
  `startPlacingNewIcon`) — le prochain clic sur le canvas pose le nouvel
  élément à cet endroit (coin haut-gauche pour une image/icône,
  redimensionnable ensuite comme n'importe quel autre élément).
- **Édition de texte inline** (Phase 5) : double-clic sur un texte
  superpose un `<textarea>` HTML positionné exactement sur sa boîte
  englobante (conversion espace canvas réel ↔ espace écran) ; validé sur
  Entrée/perte de focus, annulé sur Échap.
- **Suppression** : bouton dédié dans le panneau de propriétés (élément
  sélectionné), pas de racourci clavier pour éviter une suppression
  accidentelle en tapant dans un champ de texte adjacent.

**Bibliothèque d'icônes** (retour utilisateur : "je sais que tu utilises
une bibliothèque de sprites stylisés à la craie, je veux pouvoir la voir
et les insérer") — les 48 icônes existaient depuis le tout début du
projet (`ICON_NAMES` côté Python, tracés précalculés dans
`icon_paths.js`/`window.ICON_PATHS` côté JS, déjà utilisées par la
génération LLM) mais n'avaient jamais été montrées visuellement nulle
part. Bouton "+ Icône..." affiche une grille de vignettes
(`buildIconLibrary`, `editor.js`) — une par clé de `window.ICON_PATHS`
(pas besoin de dupliquer `ICON_NAMES` en JS), chacune dessinée une seule
fois avec le même outil craie/feutre que le canvas principal
(`EditorCanvas.drawIconThumbnail`, réutilise `iconToPoints`/
`window.TOOLS[...]`) pour un aperçu fidèle plutôt qu'une icône
générique. Clic sur une vignette → mode placement, identique à "+ Texte"/
"+ Image".

**Persistance** : chaque manipulation ne mute que l'état JS local et
redessine — aucun aller-retour réseau à chaque pixel de glissé/
redimensionnement. `Api.update_scene_strokes(scene_id, strokes)`
(nouveau) remplace l'ensemble des strokes d'une scène ; appelé par
`editor.js` juste avant `rerender_scene`/`rerender_all`, jamais en
continu, pour ne payer qu'un seul re-rendu même après plusieurs
manipulations. Reconstruit les `Stroke`/`Point` à partir du JSON reçu
(même schéma que `Project.from_dict`).

**Bug préexistant trouvé et corrigé au passage** : `Api.rerender_scene`
ne sauvegardait jamais le `.vchalk` — la vidéo se mettait à jour mais le
fichier projet restait périmé, donc toute édition (visuelle ou via NL)
semblait perdue à la réouverture du projet alors qu'elle était bien dans
la vidéo déjà rendue. `rerender_scene`/`rerender_all` (nouveau, voir
ci-dessous) sauvegardent désormais systématiquement après re-rendu, via
`_current_project_save_path()` (déjà utilisé par `apply_edit_command`/
`insert_image` — respecte le chemin exact du fichier ouvert, voir section
"Ouvrir un projet existant").

**"Re-render tout"** appelait auparavant... en fait n'appelait rien du
tout (bouton présent dans le HTML, jamais câblé). `Api.rerender_all()`
(nouveau) appelle `Pipeline.render()` directement plutôt que de boucler
sur `rerender_scene` pour chaque scène : `render_all` (basé sur
`content_hash`) décide lui-même quelles scènes ré-encoder, réutilisant le
cache pour les autres — un `rerender_scene` par scène forcerait un
ré-encodage inconditionnel de tout le projet à chaque clic.

**Retour utilisateur : "le bouton Re-render ne fait rien"** — en réalité
il fonctionnait (confirmé en cliquant le vrai bouton via automatisation :
le re-rendu se déclenchait bien, produisait le bon fichier), mais rien ne
le rendait visible : un re-rendu prend facilement 10s à plusieurs minutes
(ré-encodage ffmpeg réel), et le seul retour était un petit texte gris
discret pendant que les boutons restaient cliquables comme s'ils ne
faisaient rien — combiné au lecteur vidéo cassé (voir plus haut),
l'utilisateur n'avait aucun moyen de constater qu'un re-rendu avait
réellement eu lieu. `editor.js::setRerenderBusy`/`showRerenderResult`
désactivent maintenant les deux boutons pendant l'opération (statut
visuellement marqué, couleur + gras) et affichent le résultat dans un
`<video>` intégré au panneau (`#rerender-preview`, servi via
`app/local_media_server.py` — voir plus haut "Bug corrigé — lecteur
vidéo intégré") — plus besoin de quitter l'éditeur pour constater le
résultat.

**Propriétés de scène** (voix off) : `prop-duration` est maintenant un
affichage en lecture seule (la durée est dérivée de l'audio synthétisé,
l'éditer directement n'aurait pas de sens — utiliser la commande NL
"raccourcis la scène à Xs" pour ça). Éditer la voix off et cliquer
"Enregistrer" appelle `Api.update_scene_voice_over` (nouveau), qui
resynthétise réellement l'audio (`Pipeline.resynthesize_scene`, déjà
utilisé par l'édition NL) et met à jour la durée affichée — pas de
re-rendu visuel immédiat, laissé aux boutons Re-render habituels.

**Vérifié de bout en bout sur l'exe packagé**, en pilotant l'application
réelle (deux fenêtres comme `main.py`) et en simulant des événements DOM
de souris (`dispatchEvent(new MouseEvent(...))`, jamais le curseur OS
réel) sur le canvas de l'éditeur : sélection, glisser, édition de texte
inline (avec commit visible dans le texte du stroke), ajout de texte,
suppression, ajout + redimensionnement d'image (poignées visibles et
fonctionnelles à l'écran), puis `update_scene_strokes` + `rerender_scene`
réels — le texte édité et déplacé apparaît bien dans la vidéo finale
re-rendue, et l'état édité est correctement rechargé dans une session
complètement séparée (persistance confirmée, pas seulement en mémoire).

### Ouvrir un projet existant

Deux façons d'arriver à l'éditeur sur un projet déjà généré, sans repasser
par l'assistant :

- **Bouton "Ouvrir un projet..."** (barre du haut, `ui/index.html`) :
  `Api.pick_project_file()` (sélecteur de fichier filtré sur
  `PROJECT_FILE_EXTENSION`) puis `Api.open_project_file(path)`, qui
  combine `load_project` (charge le `.vchalk`, restaure aussi
  `_current_video_path` s'il existe déjà un `video.mp4` à côté) et
  `open_editor` en un seul appel.
- **Association de fichier** : double-clic sur un `.vchalk` dans
  l'Explorateur lance `virtual-chalk.exe "chemin\vers\le\fichier.vchalk"`
  — Windows passe le chemin en premier argument. `app/main.py` lit
  `sys.argv[1]` au démarrage et appelle `Api.open_project_file` dessus
  avant `webview.start()` si l'extension correspond, pour ouvrir
  directement l'éditeur (la fenêtre assistant reste quand même créée en
  arrière-plan, comme pour un `open_editor()` classique). L'association
  Windows -> `virtual-chalk.exe` elle-même est enregistrée par
  l'installeur (`build/installer.iss`, section `[Registry]`, ProgID
  `VirtualChalkProject`) ; Windows 10/11 exige malgré tout un choix
  explicite de l'utilisateur ("Ouvrir avec" → "Toujours utiliser") pour
  qu'une extension déjà associée à autre chose bascule vers
  Virtual-Chalk — l'installeur ne fait que proposer le programme.

**Bug corrigé au passage** : avant cette fonctionnalité, il n'existait
tout simplement aucun moyen de rouvrir un `.vchalk` existant — ni menu
dans l'assistant, ni prise en compte de `sys.argv` par `main.py` (associer
manuellement l'extension à l'exe ne faisait donc rien : Windows lançait
bien le programme, mais avec le chemin du fichier silencieusement ignoré).

**Deuxième bug trouvé en testant cette fonctionnalité** :
`Api.get_current_project_path()` (lu par `editor.js` au démarrage pour
recharger le projet) reconstruisait un chemin deviné
`"{dossier}/project{EXT}"` au lieu de retenir le chemin réellement ouvert
— correct par coïncidence pour un projet fraîchement généré (toujours
sauvegardé sous ce nom exact par `Pipeline.run`), mais silencieusement
faux dès qu'un `.vchalk` est ouvert sous un autre nom (renommé par
l'utilisateur, reçu de quelqu'un d'autre...) : `editor.js` rechargeait
alors un fichier inexistant et la liste des scènes restait vide sans
message d'erreur. Corrigé en ajoutant `Api._current_project_path`
(chemin exact suivi depuis `load_project`), utilisé en priorité par
`get_current_project_path()` et par la sauvegarde après édition
(`_current_project_save_path()`, utilisé par `apply_edit_command` et
`insert_image`) — sans quoi les éditions d'un projet ouvert sous un nom
personnalisé auraient été silencieusement écrites dans un tout nouveau
`project{EXT}` à côté plutôt que dans le fichier réellement ouvert.
`start_pipeline_from_script` ne renseigne toujours pas ce champ (aucun besoin, son
projet est toujours sauvegardé à l'emplacement canonique), donc le repli
sur le nom deviné reste utilisé — et reste correct — dans ce cas précis.

**Troisième bug trouvé en testant cette fonctionnalité, plus sévère** : le
bouton "Ouvrir un projet..." ne faisait littéralement rien au clic —
aucune boîte de dialogue, aucune erreur visible. Cause : pywebview valide
côté Python le libellé de chaque filtre de fichier avec une regex
(`webview.util.parse_file_type`, `^([\w ]+)\(...`) qui n'autorise ni
tiret ni accent avant la parenthèse. Le libellé initial, "Projets
Virtual-Chalk (\*.vchalk)" (tiret), levait donc une `ValueError` **avant
même l'ouverture de la fenêtre native**, dans `Api.pick_project_file()` —
exception non rattrapée côté `editor.js`/`app.js` (aucun try/catch sur
l'appel), donc silencieuse pour l'utilisateur. Corrigé en renommant le
libellé en "Fichiers projet" (aucun caractère hors `[A-Za-z0-9_ ]`) ; les
deux autres filtres du projet (`pick_file`, `pick_and_encode_image`)
n'avaient par chance jamais eu de tiret/accent dans leur libellé. Test de
non-régression : `tests/test_open_project.py` fait valider les
`file_types` réellement passés par le vrai parseur de pywebview plutôt
que de dupliquer sa regex.

### Navigation libre entre étapes de l'assistant

La barre d'onglets (`ui/index.html`, `.steps-nav .step`) ne faisait que
refléter l'étape courante (`goToStep` bascule juste la classe `active`) —
aucun moyen de revenir en arrière, notamment à l'étape 1 pour modifier le
texte/prompt initial une fois qu'on a avancé. Chaque onglet a maintenant
`role="button" tabindex="0"` (accessible au clavier, Entrée/Espace gérés
explicitement dans `app.js` puisqu'un `<div role="button">` ne réagit pas
nativement aux touches contrairement à un vrai `<button>`) et un
gestionnaire de clic appelant directement `goToStep(n)`. Navigation
libre dans les deux sens, sans restriction — tous les panneaux
(`.step-panel`) coexistent déjà dans le DOM en permanence, donc revenir
en arrière ou sauter en avant ne perd ni ne recalcule rien (`goToStep` ne
fait toujours que basculer une classe CSS).

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
donc `render` l'aurait ignoré. Le `.vchalk` est re-sauvegardé après coup.

**Piège rencontré** : passer le chemin du `.vchalk` à éditer en query
string sur l'URL `file://...editor.html?project=...` échoue silencieusement
sous WebView2 (`ERR_FILE_NOT_FOUND`) — corrigé en passant ce chemin par le
pont JS↔Python existant (`Api.get_current_project_path()`, lu par
`editor.js` une fois `pywebviewready` déclenché) plutôt que par l'URL.

**Journal des commandes** — le seul retour visible après une commande
était une ligne de statut éphémère (`#nl-command-status`), écrasée par la
commande suivante : impossible de vérifier après coup ce qu'une
instruction ambiguë avait réellement fait, ou de retrouver la trace d'une
action ignorée au milieu d'une commande à plusieurs actions. `editor.js`
maintient maintenant `nlEditJournal`, un historique en mémoire (côté
client, pas persisté dans le `.vchalk` — vidé à la fermeture de
l'éditeur) de chaque commande envoyée : horodatage, texte de la commande,
résumé du résultat (succès / partiel — actions ignorées ou instruction
sans effet / erreur de traduction LLM), et le détail lisible de chaque
action réellement appliquée (`describeAction`, un texte par type d'action
du vocabulaire de `app/edit/prompts.py`). Affiché dans un panneau
`#nl-edit-journal` sous la barre de commande, plus récent en premier.
Nécessitait d'exposer `applied_actions` (déjà présent côté
`EditResult` mais jusque-là absent du dict JSON renvoyé par
`Api.apply_edit_command`) en plus de `skipped_actions`.

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
    web_template/ index.html, themes.js, text_to_path.js, animations.js, mascot.js
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
d'après le slug du titre traduit (`{slug-en}.mp4`/`.h5p`/`.vchalk`),
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
- `test_api_bridge_voice_fallback.py` — `Api.start_pipeline_from_script`
  retombe sur `_DEFAULT_VOICE_PROFILE` si `voice_profile_name` ne
  correspond à aucun profil connu, plutôt que de laisser `None` se
  propager ; vérifie aussi qu'il refuse de s'exécuter sans script en
  attente (`_pending_script_project`) et qu'il réapplique les éditions
  textuelles faites à l'étape 2. `Pipeline.finish_generation` y est
  entièrement simulé.
- `test_mobile_layout.py` — format portrait vs paysage
  (`Project.mobile_layout`/`canvas_dimensions`) : défauts distincts selon
  le contexte (`from_llm_response` vs `from_dict`, voir plus haut),
  centrage/épinglage du texte "titre" par `strokes_from_visual_elements`,
  et respect de `pinned_x`/préférence d'axe selon l'orientation par
  `resolve_overlaps` (`app/render/layout.py`).
- `test_local_media_server.py` — `app/local_media_server.py` : parsing
  d'en-tête `Range` (spec complète, ouverte, bornée au-delà de la taille
  du fichier), URLs distinctes par appel, et un vrai aller-retour HTTP
  (`urllib.request`) confirmant qu'un fichier enregistré est
  effectivement accessible (200 complet, 206 partiel) — la seule vraie
  "vérification de lecture vidéo" faisable en pytest pur ; la lecture
  réelle dans un `<video>` d'une vraie fenêtre webview est vérifiée
  séparément via un script de fumée (non reproductible ici).
- `test_editor_wysiwyg.py` (mis à jour) — `rerender_scene`/`rerender_all`
  renvoient désormais une URL servie (`http://127.0.0.1:...`) plutôt que
  le chemin brut, cohérent avec le correctif ci-dessus.

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
