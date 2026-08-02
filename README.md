# Virtual-Chalk

Application Windows autonome qui transforme un document, un prompt, une URL ou un dépôt GitHub public en vidéo
explicative animée façon tableau (craie ou feutre) — dessin progressif, voix off synthétisée, export `.h5p`
optionnel pour Moodle. Écrite en Python (moteur, LLM/TTS, rendu) + JS/Canvas (moteur de tracé), packagée en un
seul `.exe` via PyInstaller + Inno Setup.

Voir [`docs/architecture.md`](docs/architecture.md) pour le détail des décisions de conception et l'historique
des correctifs — ce README couvre l'installation et l'utilisation, l'architecture couvre le "pourquoi".

## Fonctionnalités

**Génération**
- Source : texte collé, fichier (PDF/DOCX/MD/TXT), URL, ou dépôt GitHub public (angle "architecture",
  "installation" ou "changelog")
- 4 profils de vidéo : cours magistral détaillé, fiche de révision courte, démo produit, tutoriel pas-à-pas
- Un seul appel LLM produit résumé + script + scènes + éléments visuels (texte, icônes, animations, diagrammes)
- Étape de révision du script (avant la synthèse vocale/le rendu, coûteux) : relire et éditer le texte de
  chaque scène avant de lancer la suite
- Mise en page mobile (case cochée par défaut) : format vertical 1080×1920 natif pour téléphone/réseaux
  sociaux, ou format paysage 1920×1080 plein cadre
- Deux thèmes : tableau craie (vert, cadre en bois) et tableau blanc + feutres
- Bibliothèque de ~50 icônes vectorisées (nature, météo, concepts généraux), choisies et positionnées
  automatiquement par le LLM, avec résolution des chevauchements
- Diagrammes générés à la demande (schéma → image → vectorisation en tracé) pour les concepts
  géométriques/structurels qu'aucune icône ne peut représenter
- Grammaire de mouvement pour les animations générées par le LLM (pluie qui tombe, orbites qui tournent...) —
  le vocabulaire s'enrichit verbe par verbe, contrainte à un rendu déterministe (jamais de temps réel)
- Mascotte animée optionnelle qui salue, pointe les éléments et accompagne la scène ; ses transitions
  d'apparition/disparition et le fondu des images insérées suivent une courbe d'accélération naturelle
  (Anime.js, utilisé uniquement comme bibliothèque d'easing pure)
- Voix : voix Windows locale (SAPI, gratuite, hors-ligne) ou voix Gemini (cloud)

**Édition post-génération**
- Éditeur visuel WYSIWYG : glisser/redimensionner/ajouter/supprimer texte, icônes, images ; édition de texte
  en place ; bibliothèque d'icônes à vignettes ; lecteur vidéo intégré ; re-rendu ciblé par scène ou complet
  (cache par empreinte de contenu — ne ré-encode que ce qui a changé)
- Bande de montage (timeline) sous le canvas : vue d'ensemble des scènes (durée relative, pistes
  mascotte/image), glisser un bloc pour réordonner les scènes ou tirer son bord droit pour la raccourcir
  (voix off retronquée et resynthétisée automatiquement)
- Édition par commande en langage naturel ("raccourcis la scène 3 à 10s", "change le thème", "supprime la
  scène 2", "ajoute une mascotte"...)
- Insertion d'images (bitmap/vecteur) directement sur le tableau
- Ouverture d'un projet existant (`.vchalk`, associé à l'application à l'installation)

**Export**
- Export multilingue (français → anglais), voix et durées recalculées
- Export `.h5p` (vidéo interactive Moodle) avec bookmarks automatiques par scène et exercices : QCM, vrai/faux,
  texte à trous, glisser les mots

## Installation (utilisateur)

1. Télécharger `virtual-chalk-setup.exe` depuis les [releases GitHub](../../releases) et l'exécuter
   (installateur 64 bits, Windows 10/11 — installe aussi l'association de fichiers `.vchalk`).
2. Configurer au moins une clé API LLM (aucune interface de réglage pour ça pour l'instant — voir
   [Configuration des clés API](#configuration-des-clés-api) ci-dessous).
3. Lancer Virtual-Chalk, coller un texte ou choisir une source, générer.

### Configuration des clés API

Les clés sont stockées dans le trousseau Windows (Gestionnaire d'identifiants), jamais en clair sur disque.
Aucun écran de réglages ne permet encore de les saisir directement — à faire une fois, depuis une invite
PowerShell, avec Python installé (ou depuis l'environnement de dev, voir plus bas) :

```powershell
python -c "import keyring; keyring.set_password('virtual-chalk', 'openrouter', 'VOTRE_CLE_API')"
```

Fournisseurs reconnus : `openrouter` (script), `gemini` (script, diagrammes, voix Gemini optionnelle),
`deepseek` (script). Le fournisseur actif se choisit dans Réglages → Fournisseur LLM (`app/settings.py`) ;
seule sa clé est nécessaire. Repli pour Gemini uniquement : variable d'environnement système
`Gemini_Key_Virtual-Chalk`, utilisée si aucune clé n'est trouvée dans le trousseau.

Sans clé configurée pour le fournisseur actif, la génération échoue à l'appel LLM (message d'erreur explicite,
pas de blocage silencieux).

## Développement

Prérequis : Python 3.12+, [ffmpeg](https://ffmpeg.org/) dans le `PATH` (rendu vidéo/audio), Windows (le rendu
s'appuie sur WebView2/pywebview et SAPI, spécifiques à la plateforme).

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

### Tests

```powershell
pytest
```

Suite de tests pure (aucun vrai appel réseau/LLM/TTS ni rendu ffmpeg/capture d'écran réel — voir la section
Tests de [`docs/architecture.md`](docs/architecture.md#tests) pour le détail de ce que couvre chaque fichier).

## Build (.exe + installateur)

```powershell
pyinstaller build/pyinstaller.spec
```

Produit `dist/virtual-chalk/`. Puis, avec [Inno Setup](https://jrsoftware.org/isinfo.php) installé :

```powershell
ISCC.exe build/installer.iss
```

Produit `build/Output/virtual-chalk-setup.exe`. La version de l'installateur se règle dans
`build/installer.iss` (`MyAppVersion`).

## Structure du projet

```
app/                  moteur Python : ingestion, LLM, TTS, rendu, H5P, pipeline
  render/
    web_template/      moteur de rendu Canvas/JS (thèmes, outils craie/feutre, icônes, animations)
ui/                    interface pywebview (assistant 5 étapes + éditeur WYSIWYG)
tests/                 suite pytest (logique métier pure, pas de vrai réseau/rendu)
build/                 spec PyInstaller + script Inno Setup
docs/architecture.md   décisions de conception, historique des correctifs
```

## Fichiers projet (`.vchalk`)

Un projet généré (script, scènes, tracés, voix off, exercices) se sauvegarde en `.vchalk` — associé à
l'application à l'installation, double-clic pour rouvrir directement dans l'éditeur. Dossier de sortie par
défaut : `Documents\Virtual-Chalk Videos\{titre}\{langue}\`.
