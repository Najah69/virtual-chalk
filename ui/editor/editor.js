// Écran d'édition post-génération : re-render ciblé par scène (partial_render.py),
// pas de rappel LLM/TTS sauf si le texte de la scène a réellement changé.

let currentProject = null;
let selectedSceneId = null;

function renderSceneList() {
  const list = document.getElementById("scene-list");
  list.innerHTML = currentProject.scenes
    .map(
      (s) =>
        `<div class="scene-item ${s.scene_id === selectedSceneId ? "selected" : ""}" data-id="${s.scene_id}">${s.scene_id}</div>`
    )
    .join("");
  list.querySelectorAll(".scene-item").forEach((el) => {
    el.addEventListener("click", () => selectScene(el.dataset.id));
  });
}

function selectScene(sceneId) {
  selectedSceneId = sceneId;
  const scene = currentProject.scenes.find((s) => s.scene_id === sceneId);
  document.getElementById("prop-text").value = scene.voice_over;
  document.getElementById("prop-duration").value = scene.duration_sec;
  renderSceneList();
  // TODO: dessiner l'aperçu SVG/canvas live de la scène sélectionnée
}

document.getElementById("btn-rerender-scene").addEventListener("click", async () => {
  if (!selectedSceneId) return;
  await window.pywebview.api.rerender_scene(selectedSceneId);
});

document.getElementById("btn-nl-apply").addEventListener("click", async () => {
  const input = document.getElementById("nl-command-input");
  const status = document.getElementById("nl-command-status");
  const commandText = input.value.trim();
  if (!commandText) return;

  status.textContent = "Application en cours...";
  try {
    const result = await window.pywebview.api.apply_edit_command(commandText);
    currentProject = result.project;
    if (result.skipped_actions && result.skipped_actions.length) {
      status.textContent = `Appliqué, mais ${result.skipped_actions.length} action(s) ignorée(s) (voir logs).`;
    } else if (!result.changed_scene_ids.length && !result.theme_changed) {
      status.textContent = "Rien à faire : instruction non comprise ou sans effet.";
    } else {
      status.textContent = "Modifications appliquées et scènes concernées re-rendues.";
    }
    input.value = "";
    // La scene selectionnee peut avoir ete supprimee/deplacee : on retombe
    // sur la premiere scene plutot que de garder un id qui n'existe plus.
    const stillExists = currentProject.scenes.some((s) => s.scene_id === selectedSceneId);
    renderSceneList();
    if (currentProject.scenes.length) {
      selectScene(stillExists ? selectedSceneId : currentProject.scenes[0].scene_id);
    }
  } catch (err) {
    status.textContent = `Erreur : ${err}`;
  }
});

window.addEventListener("pywebviewready", async () => {
  // Le chemin du projet n'est pas passe en query string sur l'URL file://
  // (WebView2 echoue a la resoudre) : demande au bridge Python le projet
  // actuellement charge en memoire (ui/js/app.js -> btn-edit -> open_editor).
  const projectPath = await window.pywebview.api.get_current_project_path();
  if (projectPath) {
    currentProject = await window.pywebview.api.load_project(projectPath);
    if (currentProject.scenes.length) selectScene(currentProject.scenes[0].scene_id);
  }
});
