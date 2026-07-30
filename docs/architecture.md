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

## Export H5P (finalité du projet, pas une extension)

`h5p/packager.py` construit `h5p.json` + `content/content.json` autour du
MP4 rendu, avec les librairies `H5P.InteractiveVideo` embarquées une fois
pour toutes en local (`resources/h5p_libraries/`, aucun téléchargement à
l'export). `h5p/bookmarks.py` génère automatiquement un bookmark par scène
(titre + timestamp) pour qu'un utilisateur lambda obtienne une vidéo
interactive utilisable sans configuration manuelle.

## Édition post-génération

Écran Éditeur (`ui/editor/`) : liste des scènes, aperçu canvas live de la
scène sélectionnée, panneau de propriétés (texte, couleur, position,
durée). Bouton "re-render cette scène" vs "re-render tout" —
`render/partial_render.py` ne régénère que ce qui a changé (et ne rappelle
le TTS que si le texte a changé).

## Arborescence

```
app/
  main.py, api_bridge.py, pipeline.py, settings.py
  ingestion/      pdf_reader.py, docx_reader.py, url_reader.py, text_normalizer.py
  llm/            base.py, openrouter.py, gemini.py, prompts.py
  tts/            base.py, sapi_local.py, cloud_providers.py, voice_profiles.py
  scenes/         schema.py, project_store.py, project_file.py
  render/         capture.py, ffmpeg_wrapper.py, partial_render.py
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

## Reporté (pas dans le v1)

- Interactions H5P avancées au-delà des bookmarks auto (pause, question) —
  extension naturelle de l'éditeur de scène plus tard.
- Providers LLM/TTS/thèmes supplémentaires au-delà de ceux listés —
  l'abstraction est prête, ajouter un provider = une classe de plus.
