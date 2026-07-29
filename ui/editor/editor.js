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

window.addEventListener("pywebviewready", async () => {
  // Le chemin du projet est transmis par la fenêtre appelante (ui/js/app.js -> btn-edit).
  const params = new URLSearchParams(window.location.search);
  const projectPath = params.get("project");
  if (projectPath) {
    currentProject = await window.pywebview.api.load_project(projectPath);
    if (currentProject.scenes.length) selectScene(currentProject.scenes[0].scene_id);
  }
});
