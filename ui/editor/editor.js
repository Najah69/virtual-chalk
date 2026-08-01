// Écran d'édition post-génération : re-render ciblé par scène (partial_render.py),
// pas de rappel LLM/TTS sauf si le texte de la scène a réellement changé
// (voir update_scene_voice_over) ou pour traduire une commande NL.
//
// L'aperçu WYSIWYG (sélection, glisser, redimensionner, ajout, édition de
// texte inline) est géré par editor_canvas.js (window.EditorCanvas) —
// ce fichier orchestre le reste de l'écran (liste des scènes, panneau de
// propriétés contextuel, commande NL, journal) et appelle EditorCanvas
// pour charger/relire l'état visuel de la scène sélectionnée.

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
    case "toggle_mascot":
      return action.enabled ? "Mascotte activée" : "Mascotte désactivée";
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

function findScene(sceneId) {
  return currentProject.scenes.find((s) => s.scene_id === sceneId);
}

function selectScene(sceneId) {
  selectedSceneId = sceneId;
  const scene = findScene(sceneId);
  document.getElementById("prop-voice-over").value = scene.voice_over;
  document.getElementById("prop-duration-display").textContent = scene.duration_sec.toFixed(1);
  document.getElementById("voice-over-status").textContent = "";
  renderSceneList();
  window.EditorCanvas.loadScene(scene, currentProject.theme);
  showElementProperties(null);
}

// --- Panneau de propriétés contextuel (élément sélectionné sur le canvas) --

function showElementProperties(stroke) {
  const section = document.getElementById("element-properties-section");
  if (!stroke) {
    section.style.display = "none";
    return;
  }
  section.style.display = "block";

  const textRow = document.getElementById("element-text-row");
  const colorRow = document.getElementById("element-color-row");
  const kindLabel = document.getElementById("element-kind-label");
  const textArea = document.getElementById("prop-element-text");
  const colorInput = document.getElementById("prop-element-color");

  const kindNames = { text: "texte", icon: "icône", animation: "animation", image: "image", shape: "forme", diagram: "diagramme" };
  kindLabel.textContent = `Type : ${kindNames[stroke.kind] || stroke.kind}`;

  // Le texte n'est librement éditable que pour un vrai stroke "text" —
  // pour une icône/animation, stroke.text est le NOM technique (ex:
  // "sun", "falling_rain"), pas une prose éditable au hasard.
  if (stroke.kind === "text") {
    textRow.style.display = "block";
    textArea.value = stroke.text;
  } else {
    textRow.style.display = "none";
  }

  // La couleur n'a pas de sens pour une image.
  if (stroke.kind === "image") {
    colorRow.style.display = "none";
  } else {
    colorRow.style.display = "block";
    colorInput.value = stroke.color || "#ffffff";
  }
}

document.getElementById("prop-element-text").addEventListener("change", () => {
  const stroke = window.EditorCanvas.getSelectedStroke();
  if (!stroke) return;
  stroke.text = document.getElementById("prop-element-text").value;
  window.EditorCanvas.onStrokeMutated(stroke);
});

document.getElementById("prop-element-color").addEventListener("input", () => {
  const stroke = window.EditorCanvas.getSelectedStroke();
  if (!stroke) return;
  stroke.color = document.getElementById("prop-element-color").value;
  window.EditorCanvas.onStrokeMutated(stroke);
});

document.getElementById("btn-delete-element").addEventListener("click", () => {
  window.EditorCanvas.deleteSelected();
});

document.getElementById("btn-deselect-element").addEventListener("click", () => {
  window.EditorCanvas.selectStroke(null);
});

window.EditorCanvas.setOnSelectionChange((stroke) => showElementProperties(stroke));

// changedSinceRerender : vrai dès qu'un glisser/redimensionnement/ajout/
// suppression/édition inline a modifié la scène affichée — sert juste à
// personnaliser le message des boutons "Re-render", la sauvegarde
// elle-même se fait systématiquement (voir saveCurrentSceneEdits) pour
// ne jamais perdre silencieusement une modification visuelle.
let changedSinceRerender = false;
window.EditorCanvas.setOnSceneChanged(() => { changedSinceRerender = true; });

// --- Propriétés de scène (voix off) ----------------------------------------

document.getElementById("btn-save-voice-over").addEventListener("click", async () => {
  if (!selectedSceneId) return;
  const status = document.getElementById("voice-over-status");
  const newText = document.getElementById("prop-voice-over").value;
  const scene = findScene(selectedSceneId);
  if (newText === scene.voice_over) {
    status.textContent = "Aucun changement.";
    return;
  }
  status.textContent = "Resynthèse de la voix en cours...";
  try {
    const result = await window.pywebview.api.update_scene_voice_over(selectedSceneId, newText);
    scene.voice_over = newText;
    scene.duration_sec = result.duration_sec;
    document.getElementById("prop-duration-display").textContent = scene.duration_sec.toFixed(1);
    status.textContent = "Voix mise à jour — pensez à re-render la scène pour voir/entendre le résultat.";
    changedSinceRerender = true;
  } catch (err) {
    status.textContent = `Erreur : ${err}`;
  }
});

// --- Ajout d'éléments (Phase 4) ---------------------------------------------

document.getElementById("btn-add-text").addEventListener("click", () => {
  if (!selectedSceneId) return;
  window.EditorCanvas.startPlacingNewText();
  document.getElementById("image-insert-status").textContent = "Cliquez sur le tableau pour placer le texte.";
});

let pickedImageDataUri = null;

document.getElementById("btn-pick-image").addEventListener("click", async () => {
  if (!selectedSceneId) return;
  const status = document.getElementById("image-insert-status");
  status.textContent = "";
  const picked = await window.pywebview.api.pick_and_encode_image();
  if (!picked) return;
  pickedImageDataUri = picked.data_uri;
  window.EditorCanvas.startPlacingNewImage(picked.data_uri);
  status.textContent = `"${picked.name}" — cliquez sur le tableau pour la placer (coin haut-gauche), redimensionnable ensuite.`;
});

// --- Sauvegarde des éditions visuelles + re-render --------------------------

// Envoie l'état actuel des strokes (édités côté canvas) à Python avant
// tout re-rendu — sans ça, un glisser/redimensionnement/ajout/suppression
// resterait local au JS et n'apparaîtrait jamais dans la vidéo.
async function saveCurrentSceneEdits() {
  if (!selectedSceneId) return;
  const strokes = window.EditorCanvas.serializeStrokesForSave();
  await window.pywebview.api.update_scene_strokes(selectedSceneId, strokes);
  const scene = findScene(selectedSceneId);
  scene.strokes = strokes;
  changedSinceRerender = false;
}

document.getElementById("btn-rerender-scene").addEventListener("click", async () => {
  if (!selectedSceneId) return;
  const status = document.getElementById("image-insert-status");
  status.textContent = "Re-rendu en cours...";
  try {
    await saveCurrentSceneEdits();
    await window.pywebview.api.rerender_scene(selectedSceneId);
    status.textContent = "Scène re-rendue.";
  } catch (err) {
    status.textContent = `Erreur : ${err}`;
  }
});

document.getElementById("btn-rerender-all").addEventListener("click", async () => {
  const status = document.getElementById("image-insert-status");
  status.textContent = "Re-rendu en cours (seules les scènes modifiées sont ré-encodées)...";
  try {
    if (selectedSceneId) await saveCurrentSceneEdits();
    await window.pywebview.api.rerender_all();
    status.textContent = "Montage final à jour.";
  } catch (err) {
    status.textContent = `Erreur : ${err}`;
  }
});

// --- Édition en langage naturel ---------------------------------------------

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
  // Le chemin du projet n'est pas passe en query string sur l'URL
  // (WebView2 echoue a la resoudre) : demande au bridge Python le projet
  // actuellement charge en memoire (ui/js/app.js -> btn-edit -> open_editor).
  const projectPath = await window.pywebview.api.get_current_project_path();
  if (projectPath) {
    currentProject = await window.pywebview.api.load_project(projectPath);
    if (currentProject.scenes.length) selectScene(currentProject.scenes[0].scene_id);
  }
});
