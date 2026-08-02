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

### Grain et texture du tableau

**Grain à grande échelle** (`_addSoftClouds`, `board_noise.js`) : le
grain de base n'est qu'un bruit fin pixel-par-pixel (`_fineGrain`,
amplitude ±5, non corrélé spatialement — comme de la neige TV), alors
qu'un vrai tableau essuyé au chiffon montre de larges zones plus claires
en arcs (traces de chiffon, grande échelle, organique). Superposé au
grain fin : 10 à 18 dégradés radiaux doux, positionnés/dimensionnés/
pivotés/aplatis aléatoirement, à très faible opacité (0.03-0.08) — un
bruit BASSE fréquence, contrairement au grain fin haute fréquence, donc
beaucoup moins coûteux à compresser en H.264 malgré la couche
supplémentaire. Piège rencontré et corrigé : remplir une ellipse
pivotée/aplatie avec un dégradé radial défini dans l'espace NON
transformé laisse un bord dur visible (le rayon du dégradé, calibré pour
un cercle, dépasse le petit axe de l'ellipse avant de s'estomper à
alpha=0) — corrigé en définissant le dégradé et la forme remplie dans le
même espace transformé (`translate`+`rotate`+`scale`), jamais l'un dans
l'espace canvas brut et l'autre dans un espace déformé. Fonction partagée
(`buildBoardNoise`) par les trois surfaces tableau (`blackboard.js`,
`greenboard.js`, `whiteboard.js`) — seule la couleur de fond passée en
paramètre change.

### Cadre en bois — retiré, remplacé par un choix de couleur noir/vert

Le cadre en bois autour du tableau craie a été retravaillé deux fois
(base unie + bandes de teinte, puis une version complète avec montants en
onglet, veinage directionnel, dégradé et feuillure — voir l'historique
git pour le détail de ces deux itérations) sans jamais atteindre un rendu
jugé satisfaisant par l'utilisateur. Décision explicite : retiré
entièrement (`_drawWoodFrame`/`_miteredSidePath`/`_woodGrainStreaks`/
`_drawChalkSticks`/`buildFramedBoardNoise` supprimés de `board_noise.js`,
`BOARD_FRAME_RATIO` retiré) plutôt que de continuer à itérer dessus. Le
grain de fond (voir ci-dessus) reste inchangé — c'était déjà ce
qu'utilisaient `blackboard.js`/`whiteboard.js`, `greenboard.js` l'utilise
maintenant aussi, juste sans cadre autour.

**Choix noir/vert** (idée pour compenser la perte du cadre, proposée par
l'utilisateur) : `blackboard.js` (fond `#161616`) existait déjà dans le
code mais n'était référencé par aucun thème — code mort en attente,
utilisable directement une fois câblé. Nouveau thème
`chalk_board_black` (`web_template/themes.js`), strictement identique à
`chalk_board` (palette, outil craie, couleurs de texte/mascotte/icônes
sémantiques — dupliquées dans `app/render/theme_registry.py`, à garder
synchronisé avec `themes.js` comme documenté en tête de ce fichier) sauf
la surface (`blackboard` au lieu de `greenboard`). Comme ces mécanismes
sont déjà génériques par `theme_id` (recoloration au changement de
thème, édition NL `set_theme`/`VALID_THEMES`, export...), aucun autre
changement n'a été nécessaire ailleurs dans le pipeline — confirmé
l'intuition de l'utilisateur qu'ajouter cette variante n'affecterait rien
d'autre.

UI (étape 3 "Style et voix", `ui/index.html`/`ui/js/app.js`) : un choix
noir/vert apparaît sous la galerie de thèmes uniquement quand "Tableau
craie" est sélectionné, résolu en `chalk_board_black` au moment de
"Générer la vidéo →" si "Noir" est coché — `chalk_board` (vert) reste
l'id envoyé par défaut, aucune migration nécessaire pour les projets
`.vchalk` existants.

Conséquence côté placement (`app/scenes/schema.py`) : la marge
`resolve_overlaps` qui élargissait l'espace réservé pour ne jamais
dessiner sous le cadre (`BOARD_FRAME_RATIO` + `BOARD_FRAME_MARGIN_PADDING`)
redevient une simple constante plate (`BOARD_EDGE_MARGIN_PX = 20.0`),
identique pour tous les thèmes et les deux orientations — voir
`tests/test_board_edge_margin.py`.

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

### Grammaire de mouvement — "orbit"

Retour utilisateur : sur un sujet qui implique explicitement du mouvement
(le système solaire), le moteur ne dessinait RIEN de pertinent — le LLM
ne choisissait que du texte/des icônes statiques, faute de vocabulaire
adapté. `falling_rain` était la seule animation existante, câblée à la
main pour un seul sujet ; ajouter une animation par sujet ne passe pas à
l'échelle. Premier "verbe" d'une grammaire de mouvement plus générale
(voir les notes de brainstorm) : `orbit`, N corps qui tournent autour
d'un centre, paramétré par le LLM plutôt qu'une animation par sujet —
couvre système solaire, électron/noyau, satellite, lune... avec une
seule fonction JS écrite une fois.

**Schéma** : `Stroke` gagne un champ `params: dict` (vide sauf pour un
verbe paramétré — `falling_rain` n'en a toujours pas besoin, juste
`points[0]`/`width` comme avant). Pour `orbit`, `params` contient
`bodies` (liste de `{icon, radius, size, period_s, phase_deg}`, déjà
résolus en pixels canvas côté Python — voir `_orbit_params_from_element`,
`app/scenes/schema.py`), `draw_orbit_rings`, `center_icon`, `center_size`.
`ORBIT_MAX_BODIES`/`ORBIT_MIN_BODY_SIZE_PX` bornent une sortie LLM non
plausible (trop de corps, corps illisible) — résolu une seule fois ici,
pas laissé au rendu. `points[0]` reste le centre de rotation, même
convention que les autres animations.

**Le piège trouvé en testant réellement, pas en relisant le code** :
la première version demandait au LLM de placer une icône statique
séparée au même x/y que le centre pour représenter le corps central
(ex: "sun"). `resolve_overlaps` ne sait pas que les deux éléments
devraient rester co-localisés — il voit deux boîtes qui se chevauchent
et les écarte, comme il le ferait pour n'importe quelle collision
fortuite. Résultat observé à l'écran (capture canvas, pas une
supposition) : le soleil se retrouvait décalé des anneaux d'orbite qu'il
est censé occuper. Corrigé en faisant dessiner le corps central PAR
`orbit` elle-même (`params.center_icon`/`center_size`, optionnels) —
un seul `Stroke` produit, plus de second élément que le placement
automatique pourrait désynchroniser. Le prompt (`app/llm/prompts.py`)
interdit maintenant explicitement d'ajouter une icône séparée pour le
centre.

**Bbox pour `resolve_overlaps`** (`app/render/layout.py::_bbox`) : les
animations existantes (`falling_rain`) sont ancrées coin haut-gauche
avec une extension asymétrique vers le bas (nuage + gouttes qui
tombent) — une orbite est ancrée à son CENTRE avec une extension
symétrique (un cercle). Les confondre pousserait à tort un centre
d'orbite placé dans la moitié basse du tableau vers le haut au
recadrage, sans collision réelle (bug rencontré et corrigé pendant le
développement, avant même la vérification visuelle ci-dessus). Un champ
`anchor: "center"` sur l'entrée `planned` (voir `strokes_from_visual_elements`)
sélectionne la bonne formule de boîte englobante.

**Rendu** (`window.ANIMATIONS.orbit`, `animations.js`) : même principe
que `falling_rain` (effacement local depuis `_boardTextureCache`, corps
mis en cache en sprites via `renderIconSprite` — un par corps + un pour
le centre — calculés une seule fois puis repositionnés chaque frame par
simple trigonométrie). Les anneaux-guides sont bon marché (quelques
`ctx.arc()`), redessinés chaque frame sans mise en cache.

Vérifié à trois niveaux, comme le reste du moteur cette session : (1)
séquence de plusieurs frames dans le rendu direct (positions différentes,
soleil resté centré, aucune traînée) ; (2) un vrai appel LLM sur un texte
sur le système solaire — a spontanément utilisé `orbit` dans 2 scènes
sur 7, avec des paramètres cohérents (rayon croissant, période croissante,
comme demandé dans le prompt) sans aucune autre incitation ; (3) pipeline
complet réel (vraie synthèse vocale, vrai rendu, vrai encodage H.264) —
frame extraite du MP4 final, titre bien centré en haut, soleil et
planètes correctement positionnés sur leurs anneaux.

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

### Erreurs ffmpeg opaques (retour utilisateur)

**Piège rencontré (bug, retour utilisateur, capture d'écran)** : un
encodage de scène a échoué avec le message "Command [...] returned
non-zero exit status 3752568763" affiché tel quel dans l'UI — un nombre
sans aucun sens pour l'utilisateur (`encode_scene`/`concat_scenes`
appelaient `subprocess.run(cmd, check=True)` sans capturer stderr ;
`CalledProcessError` ne rapporte que le code de sortie brut). En rejouant
la commande manuellement, stderr révélait la cause réelle : `[vf#0:0]
Error while filtering: Cannot allocate memory` dans le filtre `scale`
(mémoire système épuisée en cours d'encodage — machine à 8 Go de RAM,
moins de 1,5 Go libre au moment du test, plusieurs applications ouvertes
en parallèle). Pas un bug du pipeline vidéo lui-même : une scène de 26 s en
1080×1920 à 30 fps n'a rien d'anormal à encoder.

Correction apportée (`app/render/ffmpeg_wrapper.py`) : `_run()` capture
désormais stderr (`capture_output=True, text=True`) et lève `FFmpegError`
avec les 15 dernières lignes de stderr plutôt que de laisser remonter un
`CalledProcessError` muet — la prochaine panne, quelle qu'en soit la
cause, sera diagnosticable directement depuis le message affiché à
l'utilisateur, sans avoir à rejouer la commande à la main.

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
d'un vocabulaire fixe de 7 actions primitives (`update_scene_duration`,
`set_theme`, `delete_scene`, `move_scene`, `insert_scene`,
`replace_scene_content`, `add_visual_elements`) — jamais de régénération complète du script, pas
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

**Piège rencontré (bug, retour utilisateur)** : une commande du type
"dessine la molécule de sucre + CO2" affichait "Modifications appliquées et
scènes concernées re-rendues" mais ne produisait aucun changement visible
ni de vidéo re-encodée. Deux causes distinctes :
1. `strokes_from_visual_elements` transforme un élément `"type": "diagram"`
   en `Stroke(kind="diagram", points=[ancre])` — un simple point
   d'ancrage, invisible au rendu tant qu'il n'est pas vectorisé par
   `Pipeline.generate_diagrams` (appel Gemini, voir plus haut "Génération
   des diagrammes"). Ce vectorisation n'a lieu QUE dans
   `Pipeline.finish_generation` (génération initiale) — `Api.apply_edit_command`
   ne l'appelait jamais, donc un diagramme ajouté par édition NL restait
   pour toujours un point invisible. Corrigé en appelant
   `pipeline.generate_diagrams(project)` dans `apply_edit_command`, juste
   après résolution des actions et avant le rendu — sans coût quand rien
   n'est en attente (`generate_diagrams` retourne immédiatement dans ce
   cas), donc appelé sans condition à chaque commande plutôt que de
   détecter nous-mêmes si une action a posé un diagramme.
2. `_apply_replace_scene_content` ajoutait systématiquement l'id de la
   scène à `changed_scene_ids`, même quand l'action du LLM ne portait ni
   `voice_over` ni `visual_elements` (LLM ayant mal compris la commande) —
   un no-op se faisait donc passer pour un succès. Corrigé : l'action lève
   maintenant `EditCommandError` (donc journalisée et ignorée, comme tout
   autre échec d'action individuelle) si aucun des deux champs n'est
   présent.

**Piège rencontré (limite architecturale, découverte en corrigeant le bug
ci-dessus)** : une fois les deux bugs corrigés, la MÊME commande
("dessine une molécule de sucre + CO2" sur une scène qui a déjà du
contenu) se traduisait par `{"actions": []}` — "Rien à faire : instruction
non comprise ou sans effet". Cause : `build_scene_context` ne transmet au
LLM qu'un extrait de la voix off, jamais les `visual_elements` actuels
d'une scène ; or `replace_scene_content` REMPLACE tout le contenu visuel.
Le LLM, suivant sa propre consigne de ne jamais inventer une action
approximative, refuse à raison plutôt que de risquer d'effacer un contenu
qu'il ne peut pas voir. Corrigé en ajoutant une 7ᵉ action,
`add_visual_elements` (`scene_index`, `visual_elements`) : AJOUTE aux
strokes déjà présents (`scene.strokes.extend(...)`) sans y toucher — le
prompt indique désormais explicitement au LLM de préférer cette action à
`replace_scene_content` dès que l'instruction demande d'ajouter quelque
chose plutôt que de réécrire toute la scène.

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

### Timeline éditable (TimelineJSON) — Tâche 1

Directive apportée par un document externe (blueprint "Timeliner +
Anime.js") : une timeline visuelle pour voir/réordonner les scènes et les
événements mascotte/images, plutôt que de passer uniquement par la
commande en langage naturel ci-dessus. Intégrée après vérification contre
le schéma réel — le document source suppose une classe `ImageElement`
(inexistante : une image est un `Stroke(kind="image", ...)` comme un
autre) et un `Scene.order`/`index` (inexistant : l'ordre est la position
dans `Project.scenes`) — et deux décisions explicites pour résoudre deux
frictions d'architecture avant d'écrire du code :

**Frictions résolues** :
- *Édition de durée par glisser* : `scene.duration_sec` n'est pas une
  valeur libre, elle est DÉRIVÉE de l'audio réellement synthétisé
  (`Pipeline.resynthesize_scene`, `scene.duration_sec = duration`). La
  faire glisser sans toucher au texte désynchroniserait voix et tableau.
  Décision : réutiliser EXACTEMENT la sémantique déjà existante de la
  commande NL "raccourcis la scène à Xs" (troncature du texte à une fin
  de phrase + durée provisoire, une resynthèse ultérieure fixe la durée
  réelle) — voir `truncate_voice_over_to_duration` ci-dessous, extraite
  de `app/edit/nl_commands.py::_apply_update_scene_duration` pour que les
  deux points d'entrée produisent un résultat identique (vérifié par
  test, pas juste par relecture — voir Tests plus bas), plutôt que deux
  implémentations qui pourraient dériver l'une de l'autre.
- *Déterminisme du rendu* (pour la Tâche 4, Anime.js — pas encore
  commencée) : le rendu final ne tourne jamais en temps réel
  (`FrameCapture.renderAtTime(t)`, un instant exact à la fois). Anime.js
  est prévu en `autoplay: false`, piloté par `.seek(t)` plutôt qu'en
  temps réel, pour garder cette garantie. Décision : Anime.js vient en
  PLUS du moteur d'animation existant (`falling_rain`/`orbit`/mascotte),
  ne les remplace pas.

**`app/scenes/schema.py`** : `truncate_voice_over_to_duration(scene,
target_duration)` — extraite de `nl_commands.py`, désormais partagée.
`VOICE_TRUNCATE_CHARS_PER_SECOND` (15.0 caractères/s, un rythme de parole
approximatif — sans rapport avec `CHARS_PER_SECOND` de
`app/render/timing.py`, qui règle la vitesse du TRACÉ à la craie).

**`app/scenes/timeline.py`** (nouveau, même principe que
`project_file.py` : un module frère de `schema.py` pour un souci
particulier) :
- `project_to_timeline(project) -> dict` — vue dérivée, pas un nouveau
  modèle persisté : `{"scenes": [{scene_id, start, duration}, ...],
  "tracks": {"mascot": [...], "images": [...]}}`. `start` d'une scène est
  sa position ABSOLUE dans le montage final (réutilise
  `Project.scene_start_times`, déjà existante). Chaque entrée
  mascotte/image porte un `index` (position dans `scene.mascot_timeline`/
  `scene.strokes`) pour être retrouvée sans ambiguïté au moment de
  réappliquer — deux phases mascotte peuvent partager le même
  `action_type` (ex: deux `"idle"`), les distinguer par contenu seul
  serait fragile. Volontairement grossier (niveau scène + quelques
  événements, pas de micro-keyframes toutes les 100 ms) — conforme à la
  contrainte du document source.
- **Limite assumée, pas silencieuse** : la piste "images" ne couvre que
  l'apparition (`start_sec`/`end_sec`, le même fondu que le reste du
  moteur) — aucun mécanisme de disparition ni de zoom n'existe pour une
  image déjà posée ("la craie posée ne bouge plus" reste le principe du
  moteur), contrairement à ce qu'envisageait le document source. Ajouter
  ces capacités est un chantier séparé (probablement à rattacher à la
  grammaire de mouvement, pas à la timeline elle-même).
- `timeline_to_project(timeline, project) -> TimelineApplyResult` —
  applique EN PLACE (même `Project`, pas une copie — même convention que
  `apply_nl_edit_command`). `TimelineApplyResult` (`reordered`,
  `changed_scene_ids`, `voice_changed_scene_ids`) ne déclenche JAMAIS
  elle-même de resynthèse/rendu — aucun appel LLM/TTS/rendu dans ce
  module, l'orchestration revient à un futur `Api.update_timeline`
  (Tâche 3, pas encore écrite). `scene_id`/`index` inconnus ou périmés
  (timeline affichée avant un changement fait par ailleurs) sont ignorés
  silencieusement plutôt que de lever une exception ; un réordonnancement
  n'est appliqué que si l'ensemble des `scene_id` référencés correspond
  EXACTEMENT à celui du projet (jamais de scène qui disparaît
  silencieusement parce qu'absente d'un JSON partiel/périmé).

**Bug trouvé en écrivant les tests, pas en relisant le code** : la
première version marquait une scène "changée" dès qu'une entrée
mascotte/image était traitée avec succès, même si les valeurs reçues
étaient IDENTIQUES aux valeurs actuelles — cassant l'idempotence attendue
d'un aller-retour `project_to_timeline` → `timeline_to_project` sans
aucune édition (un test dédié l'a détecté immédiatement : la scène
apparaissait à tort dans `changed_scene_ids`). Corrigé en ne marquant
"changé" que lorsqu'au moins une valeur diffère réellement de l'état
actuel — même principe que la comparaison à tolérance déjà utilisée pour
la durée (`_DURATION_EPSILON_SEC`).

### Composant Timeliner (éditeur) — Tâche 2

`ui/editor/timeliner.js` (`window.Timeliner`) : bande "pellicule" affichée
sous le canvas de l'éditeur (`ui/editor/editor.html`, panneau
`.timeliner-panel`) — un bloc par scène, largeur proportionnelle à sa
durée (`flex-grow` = `duration_sec`, pas de calcul de pourcentage manuel),
avec les événements mascotte/images superposés en petits traits colorés à
l'intérieur de chaque bloc.

- **Lecture seule pour l'instant** : cliquer un bloc sélectionne la scène
  (réutilise `editor.js::selectScene`, donc synchronisé avec la liste de
  scènes à gauche et le canvas) — réordonner/redimensionner par glisser
  n'est pas câblé ici. Décision explicite : construire l'interaction de
  glisser maintenant, sans persistance réelle derrière (Tâche 3, l'API
  `Api.update_timeline`, n'existe pas encore), aurait donné une édition
  qui semble fonctionner puis se perd silencieusement au prochain
  re-rendu/rechargement — pire que ne pas l'avoir. Le glisser arrive avec
  la Tâche 3, pour que les deux soient livrés ensemble.
- **`projectToTimeline(project)` recalculée côté client**, volontairement
  distincte de l'appel à `project_to_timeline` (Python, Tâche 1) plutôt
  que d'ajouter un aller-retour réseau : `editor.js` garde déjà
  `currentProject` à jour en mémoire après toute édition locale (voix off
  resynthétisée, commande NL appliquée...), donc recalculer la vue
  timeline à partir de cet état est instantané et ne peut pas se
  désynchroniser — contrairement à un appel Python qui obligerait à
  rafraîchir après chaque mutation locale pour rester exact. Les deux
  implémentations restent volontairement simples (une somme cumulée de
  durées + deux `map`), le risque de divergence est faible comparé au coût
  d'un aller-retour à chaque frappe/sélection.
- **`refreshTimeliner()`** appelée à chaque changement de sélection de
  scène (couvre le chargement initial et un changement de scène), après
  la sauvegarde de la voix off (la durée change), et après l'application
  d'une commande NL (structure du projet potentiellement changée,
  y compris le cas où toutes les scènes sont supprimées — `selectScene`
  n'étant alors jamais rappelée, ce cas est traité explicitement).
- Vérifié par un harnais pywebview réel (projet `.vchalk` à 8 scènes,
  26 actions mascotte, 1 image) : nombre de blocs/tics conforme aux
  données du projet, largeurs `flex-grow` conformes aux durées réelles,
  clic sur un bloc met à jour la sélection dans le bandeau, la liste de
  scènes ET le canvas en une seule fois — captures d'écran à l'appui.

### Persistance du glisser — Tâche 3

`Api.update_timeline(timeline)` (`app/api_bridge.py`) : orchestre les
effets de bord que `timeline_to_project` (Tâche 1) ne fait jamais
elle-même — même séparation que `apply_edit_command` pour une commande NL.
Resynthétise UNIQUEMENT les scènes que `voice_changed_scene_ids` désigne,
puis un seul appel à `Pipeline.render` (qui retrouve tout seul quoi
re-rendre via le hash de contenu) si `changed_scene_ids` OU `reordered` est
non-vide — un simple réordonnancement sans contenu modifié ne touche le
hash d'aucune scène mais doit quand même redéclencher la concaténation
finale pour refléter le nouvel ordre. Sauvegarde toujours le projet, même
si rien n'a changé (round-trip sans édition, voir Tâche 1).

`ui/editor/timeliner.js` gagne le glisser réel, câblé à cette API via
`editor.js::applyTimelineChange` :

- **Réordonner** : glisser un bloc — un seuil de 4px distingue un glisser
  d'un simple clic (`dragState.dragging`, posé sur `mousedown`/`mousemove`/
  `mouseup` au niveau module, même schéma que `editor_canvas.js::dragState`).
  La position cible est recalculée à chaque `mousemove` à partir d'un ratio
  px/seconde fixé au début du glisser (largeur de la piste ÷ durée totale
  du montage) — pas de nouvelle mesure DOM à chaque frame. Le bloc déplacé
  suit l'ordre recalculé (classe `.dragging`, opacité réduite) ; au relâché,
  si l'ordre a réellement changé, le nouveau `TimelineJSON` est envoyé à
  `Api.update_timeline`.
- **Raccourcir** : glisser la poignée à droite d'un bloc (`.timeliner-
  resize-handle`) — ratio px/seconde propre à CE bloc (sa largeur réelle ÷
  sa durée), affichage live de la durée cible dans une bulle
  (`.timeliner-resize-tooltip`). En dessous de 0.1s de delta, traité comme
  un geste accidentel et annulé sans appel API.
- **Rallonger explicitement bloqué** (`Math.min(originalDuration, ...)`
  dans `handleResizeMove`) : `truncate_voice_over_to_duration` (Tâche 1) ne
  sait que raccourcir un texte, jamais l'étirer — glisser vers la droite
  n'aurait aucun effet réel une fois la scène resynthétisée (le texte
  inchangé produirait à peu près la même durée), donc autant ne pas
  laisser croire que le geste fait quelque chose.
- **État "busy"** (`timelinerBusy` + classe CSS `.busy` sur
  `#timeliner-container`, qui coupe `pointer-events`) : un seul
  `Api.update_timeline` en vol à la fois — la resynthèse/le re-rendu réels
  peuvent prendre plusieurs dizaines de secondes, un deuxième glisser
  pendant ce délai enverrait un `TimelineJSON` basé sur un `currentProject`
  déjà périmé.
- Vérifié par un harnais pywebview réel avec de vrais glissers simulés
  (`dispatchEvent` mousedown/mousemove/mouseup, comme `editor_wysiwyg_test.py`
  cette session) sur le projet `.vchalk` à 8 scènes : réordonnancement
  confirmé identique côté DOM et côté `Api._current_project`, raccourcissement
  confirmé avec une VRAIE resynthèse SAPI (durée mesurée avant/après, pas
  simulée), tentative de rallongement confirmée sans effet. Piège rencontré
  en écrivant ce test (pas un bug produit) : `evaluate_js` pour lire un
  état DOM pendant qu'un `Api.update_timeline` synchrone est en vol côté
  pont pywebview s'est avéré peu fiable (le polling ne voyait jamais l'état
  "terminé" alors que le rendu Python avait bien fini) — corrigé en
  sondant l'état Python directement (`api._current_project`, accessible
  dans le même process de test) plutôt que le DOM.

### Anime.js — Tâche 4

Premier usage réel d'Anime.js dans le moteur, conforme à la décision actée
plus haut (additif, portée limitée au fondu/easing, jamais son moteur
temps réel). `app/render/web_template/anime.min.js` (v3.2.2, vendue
localement — même convention que `opentype.min.js`, aucune dépendance
réseau au rendu, embarquée automatiquement dans l'installateur via le
`Datas` du spec PyInstaller qui inclut tout le dossier `web_template`).

- **`motion_easing.js`** (`window.easedProgress(linearProgress, easingName)`) :
  wrapper autour de `anime.easing(name)` — Anime.js utilisé UNIQUEMENT
  comme bibliothèque d'easing pur (une fonction mathématique
  `progress -> progress`), jamais `anime({...})`/`autoplay`/
  `requestAnimationFrame`. Résultat toujours ramené à `[0, 1]` :
  certaines courbes nommées (`easeOutElastic`, `easeOutBack`...) dépassent
  momentanément cet intervalle, ce qui casserait silencieusement
  `ctx.globalAlpha` (la spec Canvas ignore une valeur hors `[0,1]` et
  GARDE l'ancienne au lieu de lever une erreur — un fondu piloté par une
  courbe qui dépasse 1 se figerait au lieu de continuer). D'où le choix de
  courbes non dépassantes (`easeOutCubic`/`easeInCubic`) pour ce premier
  usage.
- **Deux emplacements touchés**, tous les deux dans `renderAtTime`
  (`index.html`) — le seul point d'entrée du rendu réellement déterministe
  (jamais l'éditeur WYSIWYG, `ui/editor/editor_canvas.js`, qui affiche
  l'état complet d'une scène sans notion de progression temporelle, donc
  hors sujet ici) :
  - Fondu d'apparition d'une image (`stroke.kind === "image"`) :
    `easeOutCubic` au lieu d'un `globalAlpha = progress` linéaire.
  - Poses mascotte `appear`/`disappear` (`mascot.js`) : `easeOutCubic`/
    `easeInCubic` sur l'alpha ET l'échelle (même valeur eased pour les
    deux, cohérence visuelle) au lieu d'une interpolation linéaire.
    `idle`/`wave`/`point` restent inchangées (pas de transition à easer,
    juste une pose continue).
- **Vérifié par un harnais pywebview réel** contre le VRAI render surface
  (`web_template/index.html`, celui utilisé par `FrameCapture`) : valeurs
  d'easing lues en conditions réelles dans le navigateur (`easeOutCubic(0.5)
  = 0.875`, `easeInCubic(0.5) = 0.125`, exact), puis une scène synthétique
  (image + mascotte) échantillonnée pixel par pixel à plusieurs instants —
  la trajectoire de fondu mesurée suit bien la courbe eased théorique
  (`0.15 -> 0.386`, `0.5 -> 0.875`, `0.85 -> 0.997`), pas une droite.
  Régression confirmée nulle sur le VRAI pipeline (`Api.rerender_scene`,
  encodage ffmpeg réel) avec les nouveaux scripts chargés.
- **Piège rencontré en écrivant ce test** (pas un bug produit) : échantillonner
  le pixel à des instants espacés SANS recharger la scène entre deux
  empile plusieurs dessins semi-transparents les uns sur les autres — le
  moteur "accumule, n'efface jamais" (voir plus haut) fonctionne
  correctement sur des frames RÉELLES très rapprochées (1/30s), mais de
  grands sauts de test faussent la lecture en cumulant l'opacité de
  plusieurs passages. Corrigé en rechargeant la scène avant chaque
  échantillon isolé.

### UX enseignants non-pro — Tâche 5

Dernière tâche du blueprint : polish, sans changement de comportement,
sur la Timeliner (Tâches 2-3) — le public cible n'est jamais le
développeur qui l'a construite (un professeur qui n'a jamais lu le code,
voir aussi la carte "Cohérence de style, personnage, humour" côté
brainstorming, jamais approfondie mais dans le même esprit).

- **Labels clairs** : `scene_id` technique (`"scene-001"`) ne fuite plus
  nulle part dans l'UI visible — remplacé par "Scène N" (position dans
  `Project.scenes`, même numérotation que les blocs de la timeline) à la
  fois dans la liste de scènes à gauche (`editor.js::renderSceneList`) et
  dans l'infobulle des blocs de la timeline. Le vocabulaire technique des
  actions mascotte (`action_type` : `"appear"`, `"wave"`...) est traduit
  pour l'infobulle (`MASCOT_ACTION_LABELS_FR`, `timeliner.js`) plutôt que
  montré tel quel.
- **Couleurs sobres** : les 5 couleurs par `action_type` mascotte
  (`MASCOT_ACTION_COLORS`) réduites à UNE seule couleur pour toute la
  piste mascotte, une autre pour la piste image — un professeur n'a pas
  besoin de distinguer "wave" de "point" au premier coup d'œil sur une
  bande de quelques millimètres, seulement de voir "il se passe quelque
  chose ici" ; le détail reste dans l'infobulle au survol. Légende à deux
  entrées ajoutée sous l'en-tête "Montage" pour nommer ces deux couleurs.
- **Doc courte, en contexte** : une ligne d'aide directement dans l'en-tête
  du panneau ("Glissez un bloc pour changer l'ordre des scènes ; tirez son
  bord droit pour la raccourcir") plutôt qu'un document séparé — ce public
  ne lira jamais `docs/architecture.md`. Poignée de redimensionnement
  redessinée avec un repère visuel à trois traits (au lieu d'une simple
  bande sans indice) pour qu'elle se découvre sans dépendre d'un survol.
- Aucun changement de comportement (glisser/API `update_timeline`
  inchangés) : vérifié par un harnais pywebview réel — labels "Scène N"
  partout, légende et aide présentes, infobulles sans vocabulaire anglais
  technique, et sélection par clic toujours fonctionnelle après le
  changement de libellés. Piège rencontré en écrivant ce test (pas un bug
  produit) : `timeliner.js` n'écoute pas l'événement `"click"` mais
  `mousedown`+`mouseup` (pour distinguer un clic d'un glisser, voir Tâche
  3) — un `dispatchEvent("click")` simulé dans le test ne déclenchait donc
  jamais la sélection ; corrigé en simulant la vraie séquence d'événements.

## Bibliothèque personnelle — Tâche 6

Sixième tâche, hors blueprint Timeline (issue du brainstorming "champ des
possibles" du début de session — voir la carte "Bibliothèque personnelle"
de la feuille de route). Trois décisions actées avant d'écrire ce code :
**portée globale** (comme les profils de voix — disponible dans tous les
projets futurs, jamais embarquée dans un `.vchalk`), **statique pour
l'instant** (les presets animés, ex. "mon orbite à 3 corps", dépendent d'un
panneau de propriétés pour éléments animés qui n'existe pas encore — phase
séparée), et **aucune connaissance du LLM** (purement manuel via l'éditeur,
pas de suggestion automatique à la génération). Cette dernière décision a
depuis été nuancée par la pré-génération par lot décrite plus bas — voir
"Pré-génération de schémas vers la bibliothèque".

- **`app/library/asset_library.py`** : `LibraryAsset` (dataclass), stocké
  en JSON dans `config_dir()/asset_library.json` (même répertoire que
  `Settings`, voir `app/settings.py`). Un seul kind éligible :
  **`"shape"`** — c'est la représentation FINALE d'un tracé déjà
  vectorisé (un diagramme généré passe en `kind="shape"` une fois résolu,
  voir `Pipeline.finish_generation`/`app/pipeline.py`, "diagram" n'étant
  qu'un kind transitoire avant résolution) ; c'est aussi le seul kind dont
  TOUS les points bougent ensemble lors d'un déplacement dans l'éditeur
  (`editor_canvas.js::moveStroke`) — un icône/texte/image a une ancre
  séparée de son contenu dessiné, incompatible avec un stockage normalisé
  replaçable à toute taille.
- **Normalisation** (`normalize_points`) : même convention que les icônes
  (`icon_to_path.js::iconToPoints`, viewBox natif de largeur fixe
  `LIBRARY_NATIVE_WIDTH = 24`) — un point stocké se replace via
  `x_placé = x_ancre + x_natif * (taille_cible / 24)`. La largeur native
  est fixée une fois pour toutes ; seule la hauteur native varie pour
  préserver l'aspect d'origine (jamais de déformation à la réutilisation,
  y compris en portrait).
- **`Api.list_library_assets`/`save_library_asset`/`delete_library_asset`**
  (`app/api_bridge.py`) : orchestration mince — toute la logique
  (normalisation, validation du kind, persistance) vit dans
  `asset_library.py`, testable sans pywebview.
- **`ui/editor/library.js`** (nouveau, mêmes conventions que
  `timeliner.js`) : `window.Library.assetToPoints(asset, x, y, size)`,
  formule inverse de la normalisation Python — aucune persistance côté JS,
  uniquement la conversion géométrique.
- **`ui/editor/editor_canvas.js`** : `drawLibraryAssetThumbnail` (même
  principe que `drawIconThumbnail`, mais à partir de points déjà
  normalisés plutôt qu'un nom d'icône du socle fixe — centré verticalement
  en tenant compte de l'aspect natif réel, pas forcément carré comme une
  icône), `startPlacingNewLibraryAsset`/`_addLibraryAssetStrokeAt` (place
  un preset comme un stroke `"shape"` ORDINAIRE, points entièrement
  développés à la taille choisie — pas de nouveau kind de stroke, pas de
  référence différée comme pour les icônes, donc AUCUN changement requis
  dans le pipeline de rendu/`resolve_overlaps`/le reste du moteur),
  `getSelectedStrokeForLibrary` (renvoie `{kind, color, points, bbox}` du
  stroke sélectionné, ou `null` s'il n'est pas éligible).
- **UX** : section "Mes éléments" dans la grille de vignettes de l'éditeur,
  à côté du socle d'icônes (`#my-library`, même style que `#icon-library`)
  — reconstruite à chaque ouverture (pas de cache "déjà construit" comme
  pour le socle fixe, qui lui ne change jamais) pour refléter tout de
  suite un ajout/une suppression fait dans la même session. Bouton
  "Enregistrer dans ma bibliothèque" dans le panneau de propriétés,
  visible uniquement pour un stroke `"shape"` sélectionné. Suppression par
  un petit bouton "×" sur chaque vignette.
- **Limitation assumée, pas cachée** : un preset placé n'est PAS
  redimensionnable après coup — même limitation que n'importe quel autre
  stroke `"shape"` déjà vectorisé (un diagramme généré par le LLM, par
  exemple), pas une régression introduite ici. La taille de placement par
  défaut (`LIBRARY_DEFAULT_WIDTH = 220px`, même largeur qu'un icône) est
  donc définitive.
- **Vérifié** par un harnais pywebview réel (bibliothèque personnelle réelle
  de l'utilisateur sauvegardée/restaurée autour du test, jamais polluée) :
  sélection d'un vrai stroke `"shape"` existant dans un projet, bouton
  d'enregistrement visible seulement pour ce kind, sauvegarde persistée et
  relue depuis le disque, vignette réelle affichée dans "Mes éléments",
  placement sur une AUTRE scène produisant un stroke `"shape"` avec
  exactement le même nombre de points que l'original, puis suppression
  bout en bout. Complété par 9 tests unitaires (`tests/test_asset_library.py`)
  sur la normalisation (aller-retour pixel exact) et la persistance
  (kind non éligible rejeté, nom vide replié sur "Sans titre",
  suppression ciblée).

### Pré-génération de schémas vers la bibliothèque

Idée utilisateur (discussion sur comment enrichir automatiquement le
résultat sans laisser le LLM écrire du nouveau code de rendu — rejeté :
problème de sécurité/fiabilité d'exécuter du code généré, alors que le
pipeline de diagrammes existant couvre déjà tout schéma STATIQUE quel que
soit le sujet, sans jamais avoir besoin d'un "vocabulaire" pré-défini).
Étape 1 de l'assistant, entièrement optionnelle : avant même de lancer le
script, un appel LLM analyse le texte source et propose une liste de
schémas pertinents pour ce thème (ex: "molécule de sucre", "graphique
simplifié du krach de 1929"), que l'utilisateur relit, décoche
éventuellement, puis confirme — chaque schéma retenu est alors généré/
vectorisé et déposé dans la Bibliothèque personnelle (section précédente),
prêt à être replacé sur n'importe quelle scène, y compris dans un futur
projet sur le même thème.

Flux volontairement **à deux temps** (proposer puis confirmer
explicitement), jamais une génération automatique en un clic : chaque
schéma coûte un vrai appel Gemini Image, même philosophie que l'auto-
critique visuelle plus bas (jamais activé sans décision explicite de
l'utilisateur, pour ne jamais dépenser des appels API à son insu).

- **`app/library/diagram_suggestions.py`** (nouveau) : `suggest_diagram_topics(llm, source_text)`, un seul appel `llm.complete_json` (même
  pattern que `apply_nl_edit_command`), plafonné à `MAX_SUGGESTIONS = 6`
  pour borner le coût de la passe de génération qui suit. Réutilise le LLM
  de script déjà configuré par l'utilisateur (pas nécessairement Gemini) —
  seule la vectorisation qui suit exige Gemini, exactement comme pour un
  diagramme en scène. Dégradation silencieuse (liste vide) sur
  `LLMJsonError`, jamais d'exception : ce n'est qu'une aide optionnelle.
- **`Pipeline.generate_library_diagrams`** (`app/pipeline.py`) : pour
  chaque description retenue, appelle `generate_diagram_points` (même
  fonction que pour un diagramme de scène) avec un cadre de placement
  neutre fixe — sans incidence sur le résultat stocké, seule la boîte
  englobante RÉELLE des points obtenus compte une fois passée à
  `asset_library.add_asset`, qui normalise à partir de cette boîte.
  Couleur fixée sur la palette craie (thème provisoire, même logique que
  `generate_script` avant que le vrai thème ne soit choisi à l'étape 3).
  Dégradation gracieuse PAR description (même logique que
  `generate_diagrams`) : un échec individuel ne doit jamais interrompre le
  reste du lot déjà payé en appels Gemini — renvoie le compte d'ajouts
  réussis et d'échecs plutôt qu'une exception globale.
- **`Api.suggest_library_diagrams`/`pregenerate_library_diagrams`**
  (`app/api_bridge.py`) : la suggestion réutilise le même format `source`
  que `generate_script` (`{"type": ..., "value": ...}`) pour proposer sur
  exactement le même contenu (texte collé, fichier, URL, GitHub) que celui
  qui sera utilisé pour le script.
- **UX** (étape 1, `ui/index.html`/`ui/js/app.js`) : bouton "Suggérer des
  schémas" → liste à cocher (tout coché par défaut) → bouton "Générer et
  ajouter à ma bibliothèque" actif seulement une fois des suggestions
  affichées. Bloc entièrement indépendant du bouton "Générer le script →" :
  n'interfère jamais avec le flux normal, avec ou sans passage par cette
  pré-génération.

## Boucle d'auto-critique visuelle

Proposition explicite de l'utilisateur, pas issue du blueprint Timeline :
après avoir constaté qu'une vidéo générée manquait d'illustration malgré
un texte de qualité, la demande était que l'IA REGARDE elle-même la vidéo
produite, juge les manques par rapport au script, et itère sur le moteur
de rendu jusqu'à ce que l'illustration soit jugée suffisante. Deux
décisions actées avant d'écrire ce code : **optionnelle** (case à cocher,
jamais activée par défaut) et **plafonnée à 2 itérations** — chaque
itération coûte un vrai appel LLM vision et une capture par scène encore
jugée insuffisante, en plus du coût de génération normal.

**Décision d'architecture clé : la boucle tourne AVANT le premier rendu
réel, pas après.** Une scène peut être jugée par le modèle à partir de
simples captures canvas (`FrameCapture.capture_frames_at`, nouveau —
`window.renderFrames(t, 1, FPS)` réutilisé avec `count=1` pour un instant
arbitraire) sans avoir besoin d'un encodage ffmpeg complet : ces captures
lisent l'état EN MÉMOIRE du `Scene` courant via la même fenêtre de rendu
que le vrai pipeline. Conséquence : les éléments ajoutés par la critique
sont déjà présents dans le TOUT PREMIER encodage vidéo — pas de cycle
"encoder → critiquer → ré-encoder" qui gaspillerait le premier rendu.
Ordre dans `Pipeline.finish_generation` : diagrammes → mascotte → voix →
**critique** → rendu → sauvegarde → export H5P.

- **`app/critique/visual_critique.py`** : `run_critique_loop(llm, project,
  capture, on_progress)` — pour chaque scène encore "en attente", capture
  2 images (à 35 % et 75 % de sa durée, ni pile au début où une transition
  peut être en cours, ni pile à la fin) et appelle
  `analyze_scene_illustration`. Une scène jugée "suffisante" n'est PLUS
  JAMAIS ré-analysée aux itérations suivantes (coût déjà justifié une
  fois) ; une scène "insuffisante" reçoit les `missing_elements` proposés
  (convertis en `Stroke` via `strokes_from_visual_elements`, le même
  chemin que la génération initiale) et reste "en attente" pour la
  prochaine itération, jusqu'à convergence ou `MAX_CRITIQUE_ITERATIONS`.
- **Vocabulaire JSON partagé avec la génération initiale** : le prompt de
  critique (`CRITIQUE_SYSTEM_PROMPT`) réutilise `ICON_LIST`/`ANIMATION_LIST`
  /`ORBIT_MAX_BODIES` de `app/llm/prompts.py` — les éléments proposés
  doivent être exploitables tels quels par `strokes_from_visual_elements`,
  pas un format parallèle inventé pour l'occasion.
- **Nouvelle capacité LLM : `complete_json_with_images`** (`app/llm/base.py`)
  — variante multimodale de `complete_json`, PAS une méthode abstraite
  (contrairement à `_complete`) : la vision n'est pas disponible sur tous
  les fournisseurs (OpenRouter/DeepSeek génériques n'ont pas d'API image
  uniforme), le repli par défaut lève `NotImplementedError` plutôt qu'un
  `TypeError` bas niveau. `GeminiProvider._complete_with_images` l'implémente
  (payload `contents[].parts[]` avec des parts `inline_data`
  `image/jpeg` en plus du texte). `Pipeline.run_visual_critique` utilise
  TOUJOURS Gemini pour cette analyse (`self.diagram_api_key`),
  indépendamment du fournisseur choisi pour le script — même logique que
  `generate_diagrams`, la clé Gemini est de toute façon déjà requise pour
  les diagrammes.
- **Dégradation gracieuse à chaque niveau** : pas de clé Gemini configurée
  → la boucle entière est ignorée (log, pas d'exception) ; le fournisseur
  ne supporte pas la vision ou renvoie un JSON inexploitable → la scène
  concernée est traitée comme "suffisante" (repli vers le comportement
  d'avant cette fonctionnalité) plutôt que de faire échouer une génération
  déjà payée en TTS.
- **Limitation assumée, pas cachée** : les éléments ajoutés par une
  itération ne passent PAS par un `resolve_overlaps` conscient du contenu
  déjà placé (par la génération initiale OU par une itération précédente)
  — `strokes_from_visual_elements` ne résout les chevauchements qu'ENTRE
  les éléments d'un même appel. La seule protection est l'instruction
  donnée au modèle de choisir un emplacement visiblement libre sur les
  images fournies — observé en pratique (voir Vérifié ci-dessous) : des
  éléments ajoutés à deux itérations différentes peuvent se retrouver
  visuellement proches/superposés, le modèle ne "voyant" pas parfaitement
  ce qu'une itération précédente vient d'ajouter au même endroit.
- **UI** : case à cocher "Améliorer automatiquement les scènes peu
  illustrées" à l'étape 3 de l'assistant (`ui/index.html`), à côté des
  cases existantes (export H5P, mascotte) — jamais cochée par défaut.
  Nouveau step de progression `"critique"` dans `onPipelineProgress`
  (`ui/js/app.js`).

**Vérifié avec de VRAIS appels Gemini** (pas seulement des doubles de
test) : une scène délibérément pauvre (un seul texte, sans icône ni
schéma) capturée via une vraie fenêtre de rendu, envoyée à Gemini —
verdict réel `sufficient=false` avec un raisonnement cohérent
("le tableau est totalement vide et ne présente aucune illustration du
soleil, des océans ou du phénomène d'évaporation") et des éléments
proposés pertinents et bien formés (icônes `sun`/`wave-sine`/`arrow-up`,
texte "Évaporation", coordonnées dans `[0,100]`). Boucle complète
exécutée avec ce vrai modèle jusqu'au plafond de 2 itérations : la scène
passe de 1 à 8 strokes, capture d'écran finale confirmant un tableau
réellement illustré (soleil + gouttes d'eau) là où il n'y avait qu'un
titre — y compris le léger chevauchement entre itérations mentionné
ci-dessus, observé sur cette même capture. Complété par 24 tests
unitaires (`test_visual_critique.py`, `test_llm_base.py`,
`test_gemini_provider.py`, `test_frame_capture.py`) sur l'orchestration
de la boucle (convergence, plafond, scènes déjà suffisantes jamais
ré-analysées), le parsing JSON multimodal, la construction de la requête
Gemini, et la capture de frames à des instants arbitraires — aucun de ces
tests n'effectue de vrai appel réseau, contrairement à la vérification
ci-dessus.

### Correction de mise en page du texte (retour utilisateur)

Retour explicite après la première version : "problèmes fréquents de mise
en page des textes" à intégrer dans la MÊME boucle, avec auto-correction à
chaque itération — pas une passe séparée. Jusque-là, la critique ne
pouvait qu'AJOUTER des éléments ; elle ne pouvait rien dire ni rien faire
sur un élément déjà présent, y compris quand celui-ci débordait du cadre
ou en chevauchait un autre.

- **Le modèle juge désormais DEUX choses par appel** (`CRITIQUE_SYSTEM_PROMPT`) :
  l'illustration est-elle suffisante (comme avant), ET la mise en page du
  texte est-elle propre (chevauchement, dépassement du cadre, texte trop
  long pour rester lisible) — cherché ACTIVEMENT, pas seulement en repli.
  Un seul appel/une seule réponse JSON pour les deux, pas deux passes
  séparées : le modèle voit le même contenu de toute façon.
- **`_describe_current_elements`** : liste compacte et INDEXÉE des strokes
  actuels de la scène (index, kind, x/y en %, contenu texte ou nom
  d'icône), donnée en plus des images dans le prompt utilisateur — sans
  elle, le modèle peut dire "il y a un problème" mais jamais désigner
  PRÉCISÉMENT quel élément corriger (une image seule ne permet que
  d'ajouter, jamais de référencer un élément existant par un identifiant
  stable).
- **`layout_fixes`** (nouveau champ du verdict, à côté de `missing_elements`) :
  chaque correction cible un stroke EXISTANT par son `stroke_index` :
  - `move` (repositionner) et `shorten_text` (raccourcir le contenu) —
    **réservés au texte** (`_TEXT_ONLY_FIX_ACTIONS`) : un icône/diagramme/
    image a une taille FIXE choisie à la génération, jamais variable
    ailleurs dans le moteur — introduire un déplacement/redimensionnement
    pour ces kinds ici créerait un axe de variation inédit, hors de la
    demande explicite ("mise en page des TEXTES").
  - `remove` — disponible pour n'importe quel kind (opération toujours
    bien définie, utile si le modèle juge un élément entièrement
    redondant/cassé).
  `apply_layout_fixes` (`app/critique/visual_critique.py`) les applique :
  défensif par construction (index hors limites, action incompatible avec
  le kind ciblé, champs manquants → ignorés silencieusement, jamais
  d'exception) ; les suppressions sont appliquées EN DERNIER par index
  DÉCROISSANT pour ne jamais décaler l'index d'une correction suivante
  dans le même lot.
- **Une scène avec des `layout_fixes` appliqués reste "en attente"** pour
  l'itération suivante, exactement comme une scène avec des
  `missing_elements` ajoutés — c'est ce qui permet la "auto-correction à
  chaque loop" demandée : le modèle voit le résultat RÉEL de sa propre
  correction précédente et peut la rattraper si elle a mal tourné (ex: un
  texte déplacé qui chevauche maintenant autre chose), plutôt qu'un
  correctif "à l'aveugle" appliqué une seule fois sans vérification.

**Vérifié avec un VRAI appel Gemini** sur une scène construite avec deux
textes délibérément superposés (même ancre à quelques pixels près) — le
modèle a détecté À LA FOIS le chevauchement/l'illisibilité ET l'absence
totale d'illustration en un seul verdict ("le texte est illisible et
écrasé sur le bord droit du tableau, et la scène manque totalement
d'éléments visuels"), proposant dans la MÊME réponse deux `layout_fixes`
(déplacer chaque texte vers une position distincte, sans chevauchement) et
5 `missing_elements` formant une séquence cohérente (soleil → flèche →
plante → flèche → éclair, pour illustrer la photosynthèse). Les
corrections appliquées ont réellement séparé les deux textes (capture
avant/après) — confirmé pixel par pixel via les nouvelles coordonnées des
strokes, pas seulement par lecture du JSON renvoyé. Complété par 12 tests
unitaires supplémentaires (`apply_layout_fixes` : déplacement,
raccourcissement refusé si pas réellement plus court, suppressions
multiples sans décalage d'index, action ignorée sur un kind non éligible,
index hors limites, entrées malformées ; `run_critique_loop` : une scène
avec seulement des `layout_fixes` reste en attente ; `analyze_scene_illustration` :
liste d'éléments indexée bien transmise dans le prompt).

## Identité visuelle (icône, splash-screen, installateur)

Retour utilisateur : les icônes de l'app étaient génériques (celle du
bootloader PyInstaller, jamais personnalisée — `icon=None` dans
`build/pyinstaller.spec`). Deux images fournies par l'utilisateur,
dérivées en plusieurs formats via un script ponctuel (pas un module de
l'app, exécuté une fois — voir `resources/branding/`) :

- **`resources/branding/app_icon.ico`** (depuis `icone-Virtual-Chalk-3.png`,
  carrée) : multi-résolution (16 à 256px, un seul fichier .ico via
  `Image.save(..., sizes=[...])` de Pillow, qui génère toutes les tailles
  en une fois). Référencée à TROIS endroits qui doivent chacun leur propre
  copie de cette icône (Windows ne propage pas automatiquement l'icône
  d'un exe à un autre) :
  - `build/pyinstaller.spec` (`EXE(..., icon=...)`) — icône de
    `virtual-chalk.exe` : barre des tâches, raccourcis Bureau/Menu
    Démarrer (`build/installer.iss` les pointe vers l'exe, pas vers un
    fichier .ico séparé, donc ils héritent de celle-ci), et icône des
    fichiers `.vchalk` associés (`VirtualChalkProject\DefaultIcon`,
    `{app}\{#MyAppExeName},0` — index 0 = l'icône embarquée dans l'exe).
  - `build/installer.iss` (`SetupIconFile`) — icône du PROGRAMME
    D'INSTALLATION lui-même (`virtual-chalk-setup.exe`), distincte de
    celle de l'app installée.
  - `webview.start(..., icon=...)` (`app/main.py`) — best-effort pour les
    backends pywebview qui ne récupèrent pas l'icône directement depuis
    les ressources de l'exe (sans effet nuisible sur EdgeChromium/Windows,
    qui la lit déjà depuis l'exe).
- **Bannière `Pub-Virtual-Chalk-2.png`** (carrée), réutilisée à DEUX
  endroits distincts avec la même image source :
  - **Splash-screen** (`ui/splash.html` + `ui/img/splash.png`, redimensionnée
    à 640×640 — inutile de charger le PNG source à pleine résolution pour
    une fenêtre qui ne fait que quelques centaines de pixels) : nouvelle
    fenêtre pywebview SANS chrome (`frameless=True`), créée EN PREMIER
    dans `main()`, pendant que la fenêtre principale est construite
    CACHÉE (`hidden=True`). `_reveal_windows` (thread lancé par
    `webview.start(func, ...)`, même mécanisme que tous les harnais de
    test de cette session) attend `SPLASH_MIN_DISPLAY_SEC` (1,8s — délai
    ARTIFICIEL : rien de lourd ne charge avant que la fenêtre principale
    soit prête, sans lui le splash ne serait quasiment jamais vu) puis
    détruit le splash et révèle la fenêtre principale — SAUF si un projet
    a été ouvert directement par association de fichier (`.vchalk`), auquel
    cas `Api.open_project_file` a déjà fait apparaître sa propre fenêtre
    Éditeur et révéler EN PLUS l'assistant vide n'aurait aucun intérêt.
  - **Assistant Inno Setup** (`WizardImageFile`/`WizardSmallImageFile`,
    `build/installer.iss`) : Inno attend des proportions PORTRAIT
    (164×314 pour la grande image, 55×58 pour la petite) très différentes
    du carré source — `letterbox()` (dans le script de génération) la
    redimensionne pour tenir ENTIÈREMENT dans ces dimensions sans
    déformation ni recadrage, puis la centre sur un fond de la couleur du
    coin de l'image source ELLE-MÊME (déjà un fond sombre uni sur les deux
    images fournies), pour que la bande ajoutée soit invisible plutôt
    qu'une bordure disgracieuse d'une autre couleur. Variantes 2x
    (328×628, 110×116) fournies pour le haut-DPI — Inno Setup 6 choisit
    automatiquement dans une liste séparée par des virgules.
    `WizardImageStretch=no` : ces images sont déjà à la bonne taille,
    ne jamais les étirer.

**Vérifié** : les trois références à `app_icon.ico` compilent/s'assemblent
sans erreur (build PyInstaller + build Inno Setup réels, pas juste une
lecture du script) ; pour le splash, un harnais pywebview réel confirme
que `<img>` charge et décode réellement l'image (`naturalWidth`/
`naturalHeight` > 0, pas seulement présente dans le DOM), capture les
PIXELS RÉELS affichés (dessinés dans un canvas hors-écran puis
`toDataURL()` — preuve visuelle, pas une simple assertion de dimensions),
et confirme la bascule complète : le splash est bien détruit
(`splash not in webview.windows`) et la fenêtre principale bien révélée
(son DOM répond, l'étape 1 de l'assistant y est présente) après le délai
minimal.

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
- `test_board_edge_margin.py` — la marge de sécurité entre un élément
  placé par le LLM et le bord du tableau (`BOARD_EDGE_MARGIN_PX`) est bien
  appliquée par `resolve_overlaps`, et reste identique en portrait et en
  paysage (constante plate depuis le retrait du cadre en bois, voir
  "Cadre en bois — retiré").
- `test_orbit_animation.py` — premier verbe de la grammaire de mouvement :
  résolution pourcentage → pixels des corps et du centre, bornes de
  sécurité (nombre de corps, taille minimale), icônes inconnues filtrées
  sans faire échouer tout le stroke, `orbit` sans corps valide entièrement
  ignoré, boîte englobante correcte (ancre centrée, pas coin haut-gauche),
  et surtout la régression du corps central qui se désynchronisait des
  anneaux (voir plus haut) — `orbit` ne produit désormais qu'un seul
  `Stroke`, plus de second élément que `resolve_overlaps` pourrait
  écarter. Persistance de `Stroke.params` à travers `Project.to_dict`/
  `from_dict`, un `.vchalk` pré-existant sans ce champ, et le round-trip
  éditeur (`Api.update_scene_strokes`). Le mouvement réel frame par frame
  et l'usage spontané par un vrai LLM sont vérifiés séparément (scripts de
  fumée, pas reproductibles en pytest pur).
- `test_timeline.py` — Tâche 1 de la timeline éditable :
  `project_to_timeline`/`timeline_to_project`, `start` absolu correct par
  scène, index mascotte/image sans ambiguïté, réordonnancement défensif
  (refusé si l'ensemble des `scene_id` ne correspond pas exactement),
  troncature de durée identique à la commande NL équivalente (comparaison
  directe des deux chemins, pas juste une relecture), et surtout
  l'idempotence d'un aller-retour sans édition (`changed_scene_ids`
  vide) — a immédiatement débusqué un vrai bug (scène marquée "changée"
  à tort par des entrées mascotte/image identiques à l'existant, voir
  plus haut).
- `test_voice_truncation.py` — `truncate_voice_over_to_duration` (extraite
  de la commande NL lors du partage avec la timeline) : coupure à une fin
  de phrase, repli en ellipse sans ponctuation, texte déjà court laissé
  intact, plancher de caractères minimal. Aucune couverture n'existait
  pour cette heuristique avant ce partage — comblée à cette occasion.
- `test_nl_commands.py` (complété) — `update_scene_duration` bout en
  bout via `apply_nl_edit_command`, et preuve que la commande NL et
  `timeline_to_project` produisent un résultat identique pour le même
  texte/la même durée cible.
- `test_api_bridge_update_timeline.py` — Tâche 3 : `Api.update_timeline`
  (`Pipeline` entièrement simulé) — un réordonnancement seul re-rend mais
  ne resynthétise jamais, un changement de durée resynthétise ET re-rend,
  un round-trip sans édition ne fait ni l'un ni l'autre (mais sauvegarde
  quand même), et le dict `project` retourné reflète la VRAIE durée issue
  de la resynthèse simulée (pas la valeur provisoire posée par
  `truncate_voice_over_to_duration`). Le glisser réel (réordonner/
  raccourcir/tentative de rallonger, avec une vraie resynthèse SAPI et un
  vrai re-rendu ffmpeg) est vérifié séparément par un harnais pywebview
  avec `dispatchEvent` simulé — voir la section Timeline éditable plus haut.
- `test_asset_library.py` — Tâche 6 : `normalize_points` (le coin
  haut-gauche de la bbox retombe sur l'origine, la largeur se ramène à
  `LIBRARY_NATIVE_WIDTH`, `pen_up` préservé, aller-retour placé/normalisé
  qui retombe EXACTEMENT sur la position pixel d'origine), et
  `add_asset`/`load_library`/`remove_asset` (kind non éligible rejeté,
  persistance/rechargement réel via `tmp_path`, nom vide replié sur "Sans
  titre", suppression ciblée). Le flux complet (sélection d'un vrai stroke
  `"shape"`, sauvegarde, vignette, placement sur une autre scène,
  suppression) est vérifié séparément par un harnais pywebview réel — voir
  la section Bibliothèque personnelle plus haut.

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
