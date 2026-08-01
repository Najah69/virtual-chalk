from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

import webview

import uuid

from app.edit.nl_commands import _recolor_strokes_for_theme, apply_nl_edit_command
from app.h5p.packager import build_h5p
from app.i18n.translate import translate_project
from app.ingestion.text_normalizer import normalize_source
from app.local_media_server import serve as serve_media
from app.llm.deepseek import DeepSeekProvider
from app.llm.gemini import GeminiProvider
from app.llm.openrouter import OpenRouterProvider
from app.llm.prompts import DEFAULT_VIDEO_PROFILE, VIDEO_PROFILES
from app.paths import UI_DIR
from app.pipeline import GenerationRequest, Pipeline
from app.scenes.project_file import PROJECT_FILE_EXTENSION, load_project_file, save_project_file
from app.scenes.schema import Exercise, Point, Stroke
from app.settings import Settings, get_api_key
from app.tts.base import TTSProvider, VoiceProfile
from app.tts.gemini_tts import GeminiTTSProvider
from app.tts.sapi_local import SapiLocalProvider
from app.tts.voice_profiles import list_voice_profiles

logger = logging.getLogger(__name__)

# Repli utilise quand aucun profil de voix n'a ete choisi dans cette session
# (ex: projet charge depuis un .vchalk sans etre repasse par
# start_pipeline) — gratuit et local, jamais d'appel reseau surprise.
_DEFAULT_VOICE_PROFILE = VoiceProfile(name="Voix Windows par défaut", provider="sapi_local")


class Api:
    """Pont exposé au JS de l'assistant (ui/js/app.js) via pywebview."""

    def __init__(self):
        self.settings = Settings.load()
        self._current_project = None
        self._current_project_dir: Path | None = None
        # Chemin exact du fichier .vchalk chargé (voir load_project) —
        # distinct de _current_project_dir (le dossier, utilisé pour la
        # sauvegarde/le rendu, toujours "project.vchalk" par convention
        # pour un projet généré). Un fichier ouvert via "Ouvrir un projet"
        # peut avoir n'importe quel nom/emplacement ; reconstruire son
        # chemin en devinant "{dir}/project.vchalk" (ancien comportement
        # de get_current_project_path) échouait silencieusement dès que
        # ce n'était pas le cas.
        self._current_project_path: Path | None = None
        self._current_video_path: Path | None = None
        self._current_voice_profile: VoiceProfile | None = None
        # Script généré à l'étape "2. Script" (Api.generate_script) en
        # attente de révision/édition par l'utilisateur avant de lancer la
        # suite (diagrammes, voix, rendu — coûteux) — voir
        # start_pipeline_from_script. None tant que l'étape 2 n'a pas
        # encore produit de script pour cette session.
        self._pending_script_project = None

    def pick_file(self) -> str | None:
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Documents (*.pdf;*.docx;*.md;*.txt)", "Tous les fichiers (*.*)"),
        )
        return result[0] if result else None

    def pick_output_folder(self) -> str | None:
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

    def pick_project_file(self) -> str | None:
        """Sélectionne un fichier projet existant (voir PROJECT_FILE_EXTENSION)
        à ouvrir dans l'éditeur — voir open_project_file, qui fait le
        chargement + l'ouverture de la fenêtre Éditeur en une fois.

        Le libellé du filtre ne doit contenir NI tiret NI aucun caractère
        hors [A-Za-z0-9_ ] avant la parenthèse : pywebview le valide côté
        Python avec la regex util.py::parse_file_type, `^([\\w ]+)\\(...`,
        qui n'autorise ni "-" ni accents dans le libellé — "Projets
        Virtual-Chalk (...)" (tiret) lève une ValueError non rattrapée
        avant même l'ouverture de la boîte de dialogue, sans aucun retour
        visible côté UI (bug rencontré et corrigé ici : le bouton
        "Ouvrir un projet" ne faisait alors littéralement rien)."""
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=(f"Fichiers projet (*{PROJECT_FILE_EXTENSION})", "Tous les fichiers (*.*)"),
        )
        return result[0] if result else None

    def pick_and_encode_image(self) -> dict[str, Any] | None:
        """Sélectionne une image (bitmap ou vecteur) et la retourne déjà
        encodée en data URI (base64) — la lecture/l'encodage se font ici,
        côté Python (I/O fichier normale, aucune restriction), plutôt que
        de faire lire un chemin de fichier arbitraire par le JS de
        l'éditeur (page chargée en file://, fetch()/XHR d'un autre file://
        n'est pas fiable sous Chromium). None si l'utilisateur annule."""
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Images (*.png;*.jpg;*.jpeg;*.gif;*.webp;*.svg)", "Tous les fichiers (*.*)"),
        )
        if not result:
            return None
        path = Path(result[0])
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"name": path.name, "data_uri": f"data:{mime_type};base64,{encoded}"}

    def get_settings(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self.settings)

    def save_settings(self, data: dict[str, Any]) -> None:
        self.settings = Settings(**{**self.settings.__dict__, **data})
        self.settings.save()

    def list_voice_profiles(self) -> list[dict[str, Any]]:
        return [p.__dict__ for p in list_voice_profiles()]

    def list_video_profiles(self) -> list[dict[str, Any]]:
        return [{"key": key, "label": info["label"]} for key, info in VIDEO_PROFILES.items()]

    LLM_PROVIDERS = {
        "gemini": GeminiProvider,
        "openrouter": OpenRouterProvider,
        "deepseek": DeepSeekProvider,
    }

    def _build_tts(self, voice_profile: VoiceProfile | None) -> TTSProvider:
        if voice_profile and voice_profile.provider == "gemini_tts":
            return GeminiTTSProvider(api_key=get_api_key("gemini") or "")
        return SapiLocalProvider()

    def _build_pipeline(self, voice_profile: VoiceProfile | None = None) -> Pipeline:
        provider_key = get_api_key(self.settings.llm_provider) or ""
        provider_cls = self.LLM_PROVIDERS.get(self.settings.llm_provider, OpenRouterProvider)
        llm = provider_cls(api_key=provider_key, model=self.settings.llm_model)
        tts = self._build_tts(voice_profile)
        return Pipeline(llm=llm, tts=tts, output_dir=Path(self.settings.default_output_dir),
                         diagram_api_key=get_api_key("gemini"))

    @staticmethod
    def _resolve_voice_profile(voice_profile_name: str) -> VoiceProfile:
        """Repli explicite sur un profil valide si `voice_profile_name` ne
        correspond à aucun profil connu (liste de voix système changée
        entre-temps, valeur périmée envoyée par l'UI...) plutôt que de
        laisser None se propager jusqu'à TTSProvider.synthesize — les
        providers actuels tolèrent déjà None en pratique, mais ce repli
        évite une dégradation SILENCIEUSE (l'utilisateur a choisi une voix
        précise, il doit obtenir un profil réel, pas juste "ce qui ne
        plante pas")."""
        profile = next((p for p in list_voice_profiles() if p.name == voice_profile_name), None)
        if profile is None:
            logger.warning(
                "Profil de voix %r introuvable, repli sur le profil par défaut", voice_profile_name,
            )
            return _DEFAULT_VOICE_PROFILE
        return profile

    def generate_script(self, source: dict[str, Any], script_profile: str = DEFAULT_VIDEO_PROFILE,
                         github_content_kind: str | None = None, mobile_layout: bool = True) -> dict[str, Any]:
        """Étape "2. Script" de l'assistant : ne fait QUE l'appel LLM de
        génération du script (Pipeline.generate_project), sans diagrammes/
        voix/rendu — pour laisser l'utilisateur relire/éditer le texte
        (voix off de chaque scène) avant de lancer la suite, coûteuse.
        Le thème n'est pas encore choisi à ce stade (étape 3) : les
        strokes sont générés avec un thème provisoire ("chalk_board") et
        recolorés si besoin dans start_pipeline_from_script, une fois le
        vrai thème connu (même mécanisme que set_theme en édition NL, voir
        _recolor_strokes_for_theme). `mobile_layout` (case "mise en page
        mobile" de l'étape 1), lui, est déjà définitif à cet instant : les
        strokes sont figés en pixels absolus pour cette orientation dès
        ce seul appel LLM, contrairement au thème (voir Project.mobile_layout)."""
        text = normalize_source(source)
        pipeline = self._build_pipeline(_DEFAULT_VOICE_PROFILE)
        content_kind = github_content_kind if source.get("type") == "github" else None
        request = GenerationRequest(
            source_text=text, voice_profile=_DEFAULT_VOICE_PROFILE, theme="chalk_board",
            script_profile=script_profile, github_content_kind=content_kind, mobile_layout=mobile_layout,
        )
        project = pipeline.generate_project(request)
        self._pending_script_project = project
        return project.to_dict()

    def start_pipeline_from_script(self, edited_scenes: list[dict[str, Any]], voice_profile_name: str,
                                    export_h5p: bool, theme: str = "chalk_board",
                                    mascot_enabled: bool = False) -> dict[str, Any]:
        """Termine la génération à partir du script produit par
        generate_script, en réappliquant les éditions textuelles faites à
        l'étape 2 (voix off par scène — `edited_scenes` : liste de
        {scene_id, voice_over})."""
        if not self._pending_script_project:
            raise RuntimeError("Aucun script en attente — repassez par l'étape 1")
        project = self._pending_script_project

        for scene_data in edited_scenes:
            scene = project.find_scene(scene_data["scene_id"])
            if scene is not None:
                scene.voice_over = scene_data["voice_over"]

        if theme != project.theme:
            project.theme = theme
            _recolor_strokes_for_theme(project, theme)

        profile = self._resolve_voice_profile(voice_profile_name)
        pipeline = self._build_pipeline(profile)

        def on_progress(step: str, fraction: float) -> None:
            # Best-effort : un pépin transitoire du pont JS (observé en
            # pratique : "window.onPipelineProgress is not a function" sous
            # WebView2 pendant un rendu chargé en appels evaluate_js
            # concurrents sur la fenêtre de rendu cachée) ne doit jamais
            # faire échouer toute la génération (déjà payée en TTS/rendu) —
            # seule la barre de progression en pâtit, pas le résultat final.
            try:
                webview.windows[0].evaluate_js(
                    f"window.onPipelineProgress({step!r}, {fraction})"
                )
            except Exception:
                logger.warning("Échec de la mise à jour de la barre de progression (%s, %s)", step, fraction)

        request = GenerationRequest(
            source_text="", voice_profile=profile, theme=theme,
            export_h5p=export_h5p, mascot_enabled=mascot_enabled,
        )
        result = pipeline.finish_generation(project, request, on_progress=on_progress)
        self._current_project = result.project
        self._current_project_dir = result.project_dir
        self._current_video_path = result.video_path
        self._current_voice_profile = profile
        self._pending_script_project = None
        return {
            "video_path": str(result.video_path),
            # URL servie via app/local_media_server.py, pas un chemin
            # brut converti en file:// côté JS (toFileUri) : un
            # <video src="file://..."> est refusé par WebView2/Chromium
            # quand la page qui l'affiche est elle-même servie en
            # http:// (ui/index.html, voir Api.open_editor) — constaté
            # empiriquement ("Media load rejected by URL safety check").
            "video_url": serve_media(result.video_path),
            "h5p_path": str(result.h5p_path) if result.h5p_path else None,
        }

    def scene_start_times(self) -> dict[str, float]:
        if not self._current_project:
            return {}
        return self._current_project.scene_start_times()

    def list_exercises(self) -> list[dict[str, Any]]:
        if not self._current_project:
            return []
        return [ex.__dict__ for ex in self._current_project.exercises]

    def add_exercise(self, exercise_type: str, time_sec: float, title: str, payload: dict[str, Any]) -> str:
        exercise_id = str(uuid.uuid4())
        self._current_project.exercises.append(
            Exercise(exercise_id=exercise_id, exercise_type=exercise_type,
                     time_sec=time_sec, title=title, payload=payload)
        )
        return exercise_id

    def remove_exercise(self, exercise_id: str) -> None:
        self._current_project.exercises = [
            ex for ex in self._current_project.exercises if ex.exercise_id != exercise_id
        ]

    def export_h5p_now(self) -> str:
        """Ré-exporte le .h5p avec les exercices actuels, sans re-rendre la
        vidéo (déjà générée) — ajouter un exercice ne coûte donc aucun
        appel LLM/TTS ni re-rendu."""
        from app.h5p.bookmarks import generate_bookmarks
        from app.h5p.interactions import build_interaction

        if not self._current_project or not self._current_project_dir:
            raise RuntimeError("Aucun projet à exporter")
        project = self._current_project
        bookmarks = generate_bookmarks(project.scenes)
        interactions = [build_interaction(ex) for ex in project.exercises]
        exercise_types = {ex.exercise_type for ex in project.exercises}
        h5p_path = self._current_project_dir / f"{project.slug}.h5p"
        build_h5p(self._current_video_path, bookmarks, h5p_path,
                  interactions=interactions, exercise_types=exercise_types)
        return str(h5p_path)

    def open_output_folder(self) -> None:
        import subprocess
        folder = str(self._current_project_dir) if self._current_project_dir else self.settings.default_output_dir
        subprocess.Popen(["explorer", folder])

    def load_project(self, path: str) -> dict[str, Any]:
        project = load_project_file(Path(path))
        self._current_project = project
        self._current_project_path = Path(path)
        self._current_project_dir = Path(path).parent
        # Nommée d'après le slug depuis cette tâche (voir Pipeline.render) ;
        # repli sur l'ancien nom générique "video.mp4" pour les projets
        # générés avant ce changement.
        named_video = self._current_project_dir / f"{project.slug}.mp4"
        legacy_video = self._current_project_dir / "video.mp4"
        if named_video.exists():
            self._current_video_path = named_video
        elif legacy_video.exists():
            self._current_video_path = legacy_video
        else:
            self._current_video_path = None
        return project.to_dict()

    def _current_project_save_path(self) -> Path:
        """Où sauvegarder le projet courant après une édition — le fichier
        exact qui a été ouvert (_current_project_path, voir load_project)
        s'il est connu, sinon l'emplacement canonique "project{EXT}" utilisé
        par une génération fraîche (start_pipeline_from_script ne renseigne
        jamais _current_project_path, voir get_current_project_path). Sans ça, un
        projet ouvert sous un autre nom que "project{EXT}" verrait ses
        éditions sauvegardées dans un tout autre fichier que celui ouvert."""
        if self._current_project_path:
            return self._current_project_path
        return self._current_project_dir / f"project{PROJECT_FILE_EXTENSION}"

    def open_project_file(self, path: str) -> None:
        """Charge un fichier projet existant puis ouvre directement la
        fenêtre Éditeur dessus — combine load_project + open_editor en un
        seul appel pour le bouton "Ouvrir un projet" de l'assistant et
        pour le lancement de l'exe via association de fichier (voir
        main.py, qui appelle cette méthode si un chemin est passé en
        argument au lancement)."""
        self.load_project(path)
        self.open_editor()

    def update_scene_voice_over(self, scene_id: str, voice_over: str) -> dict[str, Any]:
        """Met à jour le texte de la voix off d'une scène et resynthétise
        l'audio correspondant (Pipeline.resynthesize_scene, qui recalcule
        au passage scene.duration_sec à partir de la durée réelle du
        nouvel audio — la durée n'est donc jamais éditable directement
        dans le panneau de propriétés, juste affichée). Pas de re-rendu
        visuel immédiat : editor.js enchaîne ensuite update_scene_strokes
        + rerender_scene comme pour toute autre édition, pour ne payer
        qu'un seul re-rendu même si plusieurs propriétés ont changé."""
        if not self._current_project:
            raise RuntimeError("Aucun projet à éditer")
        scene = self._current_project.find_scene(scene_id)
        if scene is None:
            raise ValueError(f"Scène introuvable : {scene_id!r}")
        scene.voice_over = voice_over
        pipeline = self._build_pipeline(self._current_voice_profile)
        voice_profile = self._current_voice_profile or _DEFAULT_VOICE_PROFILE
        pipeline.resynthesize_scene(scene, voice_profile)
        return {"duration_sec": scene.duration_sec}

    def rerender_scene(self, scene_id: str) -> str:
        """Re-rend une scène puis sauvegarde le projet — cette sauvegarde
        manquait jusqu'ici (bug préexistant trouvé en construisant
        l'éditeur WYSIWYG) : la vidéo se mettait à jour mais le
        `.vchalk` restait périmé, donc toute édition visuelle
        (voir update_scene_strokes) semblait perdue à la réouverture du
        projet alors qu'elle était bien dans la vidéo déjà rendue."""
        if not self._current_project or not self._current_project_dir:
            raise RuntimeError("Aucun projet à re-rendre")
        pipeline = self._build_pipeline(self._current_voice_profile)
        video_path = pipeline.rerender_scene(self._current_project, scene_id, self._current_project_dir)
        self._current_video_path = video_path
        save_project_file(self._current_project, self._current_project_save_path())
        # URL servie (voir start_pipeline_from_script pour le pourquoi),
        # pas le chemin brut : editor.js l'assigne directement à
        # <video id="rerender-preview">.src.
        return serve_media(video_path)

    def rerender_all(self) -> str:
        """Ré-encode le montage final en ne re-rendant que les scènes
        dont le contenu a réellement changé (Pipeline.render ->
        render_all, basé sur content_hash) — contrairement à un appel
        répété de rerender_scene sur chaque scène, qui forcerait un
        ré-encodage inconditionnel de tout le projet à chaque clic sur
        "Re-render tout"."""
        if not self._current_project or not self._current_project_dir:
            raise RuntimeError("Aucun projet à re-rendre")
        pipeline = self._build_pipeline(self._current_voice_profile)
        video_path = pipeline.render(self._current_project, self._current_project_dir)
        self._current_video_path = video_path
        save_project_file(self._current_project, self._current_project_save_path())
        return serve_media(video_path)

    def update_scene_strokes(self, scene_id: str, strokes: list[dict[str, Any]]) -> None:
        """Remplace l'ensemble des strokes d'une scène par l'état édité
        côté éditeur WYSIWYG (ui/editor/editor_canvas.js) — glisser,
        redimensionner, ajouter/supprimer un élément, éditer un texte ne
        mutent que l'état JS local (aucun aller-retour réseau à chaque
        pixel de déplacement) ; cette méthode persiste cet état côté
        Python juste avant un re-rendu (voir editor.js, appelée juste
        avant rerender_scene). Ne sauvegarde pas le projet elle-même —
        rerender_scene s'en charge juste après, une fois la vidéo à jour."""
        if not self._current_project:
            raise RuntimeError("Aucun projet à éditer")
        scene = self._current_project.find_scene(scene_id)
        if scene is None:
            raise ValueError(f"Scène introuvable : {scene_id!r}")
        scene.strokes = [
            Stroke(
                points=[Point(p["x"], p["y"], p.get("penUp", False)) for p in s["points"]],
                color=s["color"], width=s["width"], kind=s.get("kind", "shape"),
                text=s.get("text", ""), height=s.get("height", 0.0),
                start_sec=s.get("start_sec", 0.0), end_sec=s.get("end_sec", 0.0),
                image_data=s.get("image_data", ""),
            )
            for s in strokes
        ]

    def insert_image(self, scene_id: str, image_data: str, x_pct: float, y_pct: float,
                      width_pct: float, height_pct: float) -> dict[str, Any]:
        """Ajoute un stroke kind="image" à la scène ciblée puis re-rend
        immédiatement (comme apply_edit_command) pour que le résultat soit
        visible sans action supplémentaire. `image_data` est déjà un data
        URI base64 fourni par editor.js (jamais un chemin de fichier — voir
        Stroke.image_data pour la raison : canvas "tainted" par un file://
        étranger à web_template/index.html). x_pct/y_pct/width_pct/
        height_pct sont en pourcentage du tableau, même convention que les
        éléments visuels générés par le LLM (strokes_from_visual_elements)."""
        if not self._current_project or not self._current_project_dir:
            raise RuntimeError("Aucun projet à éditer")
        scene = self._current_project.find_scene(scene_id)
        if scene is None:
            raise ValueError(f"Scène introuvable : {scene_id!r}")

        # Dimensions du PROJET courant (portrait ou paysage, voir
        # Project.mobile_layout), pas les constantes globales CANVAS_WIDTH/
        # HEIGHT (paysage uniquement) — un pourcentage doit s'appliquer au
        # cadre réellement utilisé par ce projet.
        canvas_width, canvas_height = self._current_project.canvas_size
        x = (x_pct / 100.0) * canvas_width
        y = (y_pct / 100.0) * canvas_height
        width = (width_pct / 100.0) * canvas_width
        height = (height_pct / 100.0) * canvas_height
        scene.strokes.append(Stroke(
            points=[Point(x, y)], color="", width=width, height=height,
            kind="image", image_data=image_data,
        ))

        video_path = self.rerender_scene(scene_id)
        save_project_file(self._current_project, self._current_project_save_path())
        return {"project": self._current_project.to_dict(), "video_path": video_path}

    def open_editor(self) -> None:
        """Ouvre l'écran Éditeur (ui/editor/) dans une nouvelle fenêtre.
        Le projet à charger n'est pas passé en query string sur l'URL
        (WebView2 échoue à la résoudre — testé, ERR_FILE_NOT_FOUND) mais
        lu par editor.js via get_current_project_path() une fois la
        fenêtre prête, comme le reste des échanges JS<->Python.

        URL passée comme chemin brut (pas .as_uri()/file://) — comme la
        fenêtre principale et la fenêtre de rendu dans main.py : pywebview
        ne sert via son mini serveur HTTP local que les URLs "locales"
        (ni http(s)://, ni file://, voir webview.util.is_local_url), et
        c'est ce mode qui permet à editor.html d'inclure les mêmes
        modules de rendu que web_template/index.html (text_to_path.js,
        icon_to_path.js...) pour un aperçu WYSIWYG fidèle — ces modules
        chargent des ressources locales (police, icônes) via des requêtes
        qui échouent silencieusement en file:// mais fonctionnent
        normalement en http://localhost:<port>/... (même origine que le
        reste de l'app, aucune restriction cross-scheme)."""
        if not self._current_project:
            raise RuntimeError("Aucun projet à éditer")
        editor_url = UI_DIR / "editor" / "editor.html"
        webview.create_window("Virtual-Chalk — Éditeur", url=str(editor_url), js_api=self, width=1200, height=760)

    def get_current_project_path(self) -> str | None:
        """Chemin du .vchalk à recharger côté editor.js (voir sa gestion de
        pywebviewready). Préfère le chemin exact suivi depuis
        load_project (_current_project_path) — nécessaire dès que le
        fichier ouvert ne s'appelle pas "project{EXT}" (voir
        Api.open_project_file) — sinon reconstruit le chemin canonique
        "{dossier}/project{EXT}", correct pour un projet fraîchement
        généré par start_pipeline_from_script (toujours sauvegardé à cet
        emplacement, voir Pipeline.finish_generation) mais qui n'a jamais
        mis à jour _current_project_path."""
        if self._current_project_path:
            return str(self._current_project_path)
        if not self._current_project_dir:
            return None
        return str(self._current_project_dir / f"project{PROJECT_FILE_EXTENSION}")

    def export_translated(self, target_lang: str) -> dict[str, Any]:
        """Traduit le projet courant (app/i18n/translate.py) puis
        re-synthétise la voix et re-rend entièrement dans la langue cible
        — les icônes/animations/diagrammes ne sont pas régénérés (géométrie
        indépendante de la langue). Écrit dans un sous-dossier de langue
        SIBLING (`{dossier du projet}/{target_lang}/`, même dossier de
        projet que l'original, ex: `.../mon-projet/en/`) plutôt que dans un
        nouveau dossier basé sur le titre traduit — la version française
        d'origine n'est jamais modifiée."""
        if not self._current_project or not self._current_project_dir:
            raise RuntimeError("Aucun projet à traduire")

        pipeline = self._build_pipeline(self._current_voice_profile)
        voice_profile = self._current_voice_profile or _DEFAULT_VOICE_PROFILE

        translated = translate_project(self._current_project, target_lang, pipeline.llm)
        pipeline.synthesize_voices(translated, voice_profile)

        out_dir = self._current_project_dir.parent / target_lang
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = pipeline.render(translated, out_dir)
        h5p_path = pipeline.export_h5p(translated, video_path, out_dir)
        save_project_file(translated, out_dir / f"project{PROJECT_FILE_EXTENSION}")

        return {
            "title": translated.title,
            "video_path": str(video_path),
            "h5p_path": str(h5p_path),
        }

    def apply_edit_command(self, command_text: str) -> dict[str, Any]:
        """Traduit et applique une instruction d'édition en langage naturel
        (app/edit/nl_commands.py), puis ne re-synthétise que les scènes
        dont la voix a réellement changé. Le rendu final passe par
        Pipeline.render (basé sur le hash de contenu de chaque scène) plutôt
        que de décider nous-mêmes quelles scènes re-rendre : un changement
        de thème recolore désormais aussi les strokes existants
        (voir _recolor_strokes_for_theme), donc leur hash change comme
        n'importe quelle autre édition — render() retrouve tout seul quoi
        re-rendre et réutilise le cache pour le reste."""
        if not self._current_project or not self._current_project_dir:
            raise RuntimeError("Aucun projet à éditer")

        pipeline = self._build_pipeline(self._current_voice_profile)
        result = apply_nl_edit_command(self._current_project, command_text, pipeline.llm)
        self._current_project = result.project

        if result.error:
            # Traduction commande -> JSON impossible (voir LLMJsonError) :
            # le Project n'a pas bouge, rien a re-synthetiser/re-rendre.
            return {
                "project": self._current_project.to_dict(),
                "changed_scene_ids": [],
                "theme_changed": False,
                "applied_actions": [],
                "skipped_actions": result.skipped_actions,
                "error": result.error,
            }

        voice_profile = self._current_voice_profile or _DEFAULT_VOICE_PROFILE
        for scene_id in result.voice_changed_scene_ids:
            # Le scene_id peut ne plus exister si une action ulterieure de
            # la meme commande a supprime cette scene (ex: "raccourcis la
            # scene 2 et supprime-la ensuite") — find_scene ne leve jamais
            # de StopIteration, contrairement a un next() non garde.
            scene = self._current_project.find_scene(scene_id)
            if scene is None:
                logger.warning("Scène %s introuvable pour la re-synthèse (ignorée)", scene_id)
                continue
            pipeline.resynthesize_scene(scene, voice_profile)

        if result.changed_scene_ids or result.theme_changed:
            self._current_video_path = pipeline.render(self._current_project, self._current_project_dir)

        save_project_file(self._current_project, self._current_project_save_path())

        return {
            "project": self._current_project.to_dict(),
            "changed_scene_ids": result.changed_scene_ids,
            "theme_changed": result.theme_changed,
            "applied_actions": result.applied_actions,
            "skipped_actions": result.skipped_actions,
            "error": None,
        }
