// Écran d'édition post-génération : re-render ciblé par scène (partial_render.py),
// pas de rappel LLM/TTS sauf si le texte de la scène a réellement changé.

let currentProject = null;
let selectedSceneId = null;
// Journal des commandes d'édition NL de la session courante (pas persisté
// entre deux ouvertures de l'éditeur) : donne une trace visible de ce qui
// a réellement été fait, indispensable dès qu'une instruction ambiguë est
// silencieusement traduite en "zéro action" ou qu'une action individuelle
// est ignorée au milieu d'une commande à plusieurs actions.
const nlEditJournal = [];

// Décrit une action appliquée en une ligne lisible, sans dépendre du
// format JSON brut renvoyé par le LLM (voir app/edit/prompts.py pour le
// vocabulaire d'actions).
function describeAction(action) {
  switch (action.action) {
    case "update_scene_duration":
      return `Scène ${action.scene_index} : durée limitée à ${action.max_duration}s`;
    case "set_theme":
      return `Thème changé pour "${action.theme}"`;
    case "delete_scene":
      return `Scène ${action.scene_index} supprimée`;
    case "move_scene":
      return `Scène ${action.scene_index} déplacée en position ${action.to_index}`;
    case "insert_scene":
      return `Nouvelle scène insérée avant la position ${action.before_index}`;
    case "replace_scene_content":
      return `Contenu de la scène ${action.scene_index} remplacé`;
    default:
      return `Action "${action.action}" inconnue`;
  }
}

function renderJournal() {
  const container = document.getElementById("nl-edit-journal");
  if (!nlEditJournal.length) {
    container.innerHTML = '<div class="journal-empty">Aucune commande d\'édition appliquée pour l\'instant.</div>';
    return;
  }
  // Plus récent en premier.
  container.innerHTML = nlEditJournal
    .slice()
    .reverse()
    .map((entry) => {
      const time = entry.timestamp.toLocaleTimeString("fr-FR");
      const actionsList = entry.appliedActions.length
        ? `<ul class="journal-actions">${entry.appliedActions.map((a) => `<li>${describeAction(a)}</li>`).join("")}</ul>`
        : "";
      return `
        <div class="journal-entry">
          <span class="journal-time">${time}</span><span class="journal-command">"${entry.command}"</span>
          <div class="journal-summary ${entry.statusClass}">${entry.summary}</div>
          ${actionsList}
        </div>`;
    })
    .join("");
}

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

// Image en attente d'insertion (choisie mais pas encore ajoutée à une
// scène) : {name, data_uri}, déjà lue et encodée en base64 côté Python
// (voir Api.pick_and_encode_image) — jamais un chemin de fichier, cf.
// Stroke.image_data pour la raison (canvas "tainted" en file://).
let pickedImage = null;

document.getElementById("btn-pick-image").addEventListener("click", async () => {
  const status = document.getElementById("image-insert-status");
  status.textContent = "";
  const picked = await window.pywebview.api.pick_and_encode_image();
  if (!picked) return;
  pickedImage = picked;
  document.getElementById("image-picked-name").textContent = picked.name;
  document.getElementById("btn-insert-image").disabled = false;
});

document.getElementById("btn-insert-image").addEventListener("click", async () => {
  const status = document.getElementById("image-insert-status");
  if (!selectedSceneId || !pickedImage) return;

  const xPct = parseFloat(document.getElementById("image-x-pct").value) || 0;
  const yPct = parseFloat(document.getElementById("image-y-pct").value) || 0;
  const widthPct = parseFloat(document.getElementById("image-width-pct").value) || 25;
  const heightPct = parseFloat(document.getElementById("image-height-pct").value) || 25;

  status.textContent = "Insertion et re-rendu en cours...";
  try {
    const result = await window.pywebview.api.insert_image(
      selectedSceneId, pickedImage.data_uri, xPct, yPct, widthPct, heightPct
    );
    currentProject = result.project;
    status.textContent = "Image insérée et scène re-rendue.";
    pickedImage = null;
    document.getElementById("image-picked-name").textContent = "";
    document.getElementById("btn-insert-image").disabled = true;
  } catch (err) {
    status.textContent = `Erreur : ${err}`;
  }
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

    const appliedActions = result.applied_actions || [];
    const skippedActions = result.skipped_actions || [];
    let summary;
    let statusClass;
    if (result.error) {
      summary = `Erreur : ${result.error}`;
      statusClass = "error";
    } else if (skippedActions.length) {
      summary = `${appliedActions.length} action(s) appliquée(s), ${skippedActions.length} ignorée(s) (voir logs).`;
      statusClass = "partial";
    } else if (!result.changed_scene_ids.length && !result.theme_changed) {
      summary = "Rien à faire : instruction non comprise ou sans effet.";
      statusClass = "partial";
    } else {
      summary = "Modifications appliquées et scènes concernées re-rendues.";
      statusClass = "ok";
    }
    status.textContent = summary;

    nlEditJournal.push({
      command: commandText,
      timestamp: new Date(),
      summary,
      statusClass,
      appliedActions,
    });
    renderJournal();

    input.value = "";
    // La scene selectionnee peut avoir ete supprimee/deplacee : on retombe
    // sur la premiere scene plutot que de garder un id qui n'existe plus.
    const stillExists = currentProject.scenes.some((s) => s.scene_id === selectedSceneId);
    renderSceneList();
    if (currentProject.scenes.length) {
      selectScene(stillExists ? selectedSceneId : currentProject.scenes[0].scene_id);
    }
  } catch (err) {
    const summary = `Erreur : ${err}`;
    status.textContent = summary;
    nlEditJournal.push({
      command: commandText,
      timestamp: new Date(),
      summary,
      statusClass: "error",
      appliedActions: [],
    });
    renderJournal();
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
