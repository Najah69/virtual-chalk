from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

import webview

import uuid

from app.edit.nl_commands import apply_nl_edit_command
from app.h5p.packager import build_h5p
from app.i18n.translate import translate_project
from app.ingestion.text_normalizer import normalize_source
from app.llm.deepseek import DeepSeekProvider
from app.llm.gemini import GeminiProvider
from app.llm.openrouter import OpenRouterProvider
from app.llm.prompts import DEFAULT_VIDEO_PROFILE, VIDEO_PROFILES
from app.paths import UI_DIR
from app.pipeline import GenerationRequest, Pipeline
from app.scenes.project_file import PROJECT_FILE_EXTENSION, load_project_file, save_project_file
from app.scenes.schema import CANVAS_HEIGHT, CANVAS_WIDTH, Exercise, Point, Stroke
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

    def start_pipeline(self, source: dict[str, Any], voice_profile_name: str, export_h5p: bool,
                        theme: str = "chalk_board", script_profile: str = DEFAULT_VIDEO_PROFILE,
                        github_content_kind: str | None = None, mascot_enabled: bool = False) -> dict[str, Any]:
        text = normalize_source(source)
        profile = next((p for p in list_voice_profiles() if p.name == voice_profile_name), None)
        if profile is None:
            # voice_profile_name ne correspond a aucun profil connu (liste
            # de voix systeme changee entre-temps, valeur perimee envoyee
            # par l'UI...) : repli explicite sur un profil valide plutot
            # que de laisser None se propager jusqu'a TTSProvider.synthesize
            # — les providers actuels tolerent deja None en pratique, mais
            # ce repli evite une degradation SILENCIEUSE (l'utilisateur a
            # choisi une voix precise, il doit obtenir un profil reel, pas
            # juste "ce qui ne plante pas").
            logger.warning(
                "Profil de voix %r introuvable, repli sur le profil par défaut", voice_profile_name,
            )
            profile = _DEFAULT_VOICE_PROFILE
        pipeline = self._build_pipeline(profile)
        content_kind = github_content_kind if source.get("type") == "github" else None

        def on_progress(step: str, fraction: float) -> None:
            webview.windows[0].evaluate_js(
                f"window.onPipelineProgress({step!r}, {fraction})"
            )

        request = GenerationRequest(
            source_text=text, voice_profile=profile, theme=theme, script_profile=script_profile,
            github_content_kind=content_kind, export_h5p=export_h5p, mascot_enabled=mascot_enabled,
        )
        result = pipeline.run(request, on_progress=on_progress)
        self._current_project = result.project
        self._current_project_dir = result.project_dir
        self._current_video_path = result.video_path
        self._current_voice_profile = profile
        return {
            "video_path": str(result.video_path),
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
        h5p_path = self._current_project_dir / "video.h5p"
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
        existing_video = self._current_project_dir / "video.mp4"
        self._current_video_path = existing_video if existing_video.exists() else None
        return project.to_dict()

    def _current_project_save_path(self) -> Path:
        """Où sauvegarder le projet courant après une édition — le fichier
        exact qui a été ouvert (_current_project_path, voir load_project)
        s'il est connu, sinon l'emplacement canonique "project{EXT}" utilisé
        par une génération fraîche (start_pipeline ne renseigne jamais
        _current_project_path, voir get_current_project_path). Sans ça, un
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

    def rerender_scene(self, scene_id: str) -> str:
        if not self._current_project or not self._current_project_dir:
            raise RuntimeError("Aucun projet à re-rendre")
        pipeline = self._build_pipeline(self._current_voice_profile)
        video_path = pipeline.rerender_scene(self._current_project, scene_id, self._current_project_dir)
        self._current_video_path = video_path
        return str(video_path)

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

        x = (x_pct / 100.0) * CANVAS_WIDTH
        y = (y_pct / 100.0) * CANVAS_HEIGHT
        width = (width_pct / 100.0) * CANVAS_WIDTH
        height = (height_pct / 100.0) * CANVAS_HEIGHT
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
        file:// (WebView2 échoue à la résoudre — testé, ERR_FILE_NOT_FOUND)
        mais lu par editor.js via get_current_project_path() une fois la
        fenêtre prête, comme le reste des échanges JS<->Python."""
        if not self._current_project:
            raise RuntimeError("Aucun projet à éditer")
        editor_url = UI_DIR / "editor" / "editor.html"
        webview.create_window("Virtual-Chalk — Éditeur", url=editor_url.as_uri(), js_api=self, width=1200, height=760)

    def get_current_project_path(self) -> str | None:
        """Chemin du .vchalk à recharger côté editor.js (voir sa gestion de
        pywebviewready). Préfère le chemin exact suivi depuis
        load_project (_current_project_path) — nécessaire dès que le
        fichier ouvert ne s'appelle pas "project{EXT}" (voir
        Api.open_project_file) — sinon reconstruit le chemin canonique
        "{dossier}/project{EXT}", correct pour un projet fraîchement
        généré par start_pipeline (toujours sauvegardé à cet emplacement,
        voir Pipeline.run) mais qui n'a jamais mis à jour
        _current_project_path."""
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
