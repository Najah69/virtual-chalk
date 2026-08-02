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

// Numérotée "Scène N" (position dans currentProject.scenes, même
// convention que les blocs de la timeline, voir timeliner.js) plutôt que
// le scene_id technique ("scene-001") — Tâche 5 (UX enseignants non-pro) :
// un identifiant interne n'a pas de sens pour quelqu'un qui n'a jamais lu
// le code, "Scène 1" si.
function renderSceneList() {
  const list = document.getElementById("scene-list");
  list.innerHTML = currentProject.scenes
    .map(
      (s, i) =>
        `<div class="scene-item ${s.scene_id === selectedSceneId ? "selected" : ""}" data-id="${s.scene_id}">Scène ${i + 1}</div>`
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
  window.EditorCanvas.loadScene(scene, currentProject.theme, currentProject.mobile_layout);
  showElementProperties(null);
  refreshTimeliner();
}

// Vue d'ensemble du montage sous le canvas (voir timeliner.js) — rappelée
// après tout ce qui peut changer la durée d'une scène (voix off
// resynthétisée), la structure du projet (commande NL) ou l'ordre/la durée
// via glisser (applyTimelineChange ci-dessous), en plus de chaque
// changement de sélection dans selectScene ci-dessus.
function refreshTimeliner() {
  if (!currentProject) return;
  const container = document.getElementById("timeliner-container");
  window.Timeliner.render(container, currentProject, selectedSceneId, {
    onSceneClick: selectScene,
    onTimelineChange: (payload) => {
      if (!timelinerBusy) applyTimelineChange(payload);
    },
  });
}

// timelinerBusy : un seul Api.update_timeline en vol à la fois — un
// deuxième glisser pendant qu'une resynthèse/un re-rendu est en cours
// enverrait un TimelineJSON basé sur un `currentProject` déjà périmé (voir
// applyTimelineChange, qui remplace currentProject une fois la réponse
// arrivée). #timeliner-container.busy (CSS) bloque aussi les événements
// souris pendant ce délai, en plus de ce garde-fou côté JS.
let timelinerBusy = false;

// Persiste un glisser (réordonnancement ou raccourcissement, voir
// timeliner.js) via Api.update_timeline (Tâche 3) — même schéma que
// saveCurrentSceneEdits + rerender_scene : l'édition locale (déjà visible
// à l'écran de façon optimiste pendant le glisser) n'est réellement actée
// côté projet qu'une fois la resynthèse/le re-rendu terminés côté Python.
async function applyTimelineChange(timelinePayload) {
  const status = document.getElementById("timeliner-status");
  const container = document.getElementById("timeliner-container");
  timelinerBusy = true;
  container.classList.add("busy");
  status.className = "timeliner-status";
  status.textContent = "Mise à jour du montage en cours (resynthèse/re-rendu si nécessaire)...";
  try {
    const result = await window.pywebview.api.update_timeline(timelinePayload);
    currentProject = result.project;
    status.textContent = result.changed_scene_ids.length || result.reordered
      ? "Montage mis à jour."
      : "";
    renderSceneList();
    // selectScene rafraîchit aussi le canvas (si la durée/le contenu de la
    // scène sélectionnée a changé) et la timeliner en une fois ; si la
    // scène sélectionnée n'existe plus (ne devrait pas arriver ici, aucune
    // action de update_timeline ne supprime de scène, mais reste défensif
    // comme le reste de l'éditeur), on retombe sur un simple rafraîchissement.
    if (selectedSceneId && currentProject.scenes.some((s) => s.scene_id === selectedSceneId)) {
      selectScene(selectedSceneId);
    } else {
      refreshTimeliner();
    }
  } catch (err) {
    status.className = "timeliner-status error";
    status.textContent = `Erreur : ${err}`;
    // currentProject n'a pas bougé (l'échec est survenu côté Python avant
    // toute réponse) : un simple rafraîchissement suffit à annuler l'état
    // optimiste affiché pendant le glisser.
    refreshTimeliner();
  } finally {
    timelinerBusy = false;
    container.classList.remove("busy");
  }
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

  // Bibliothèque personnelle (Tâche 6) : seul "shape" est éligible (un
  // tracé déjà entièrement vectorisé — un diagramme généré en fait partie
  // une fois résolu, voir app/pipeline.py) — même restriction que côté
  // Python (LIBRARY_ELIGIBLE_KINDS), vérifiée ici aussi pour ne montrer le
  // bouton que quand il a une chance de fonctionner.
  const saveToLibraryRow = document.getElementById("save-to-library-row");
  saveToLibraryRow.style.display = stroke.kind === "shape" ? "block" : "none";
  document.getElementById("library-save-status").textContent = "";
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
    refreshTimeliner();
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

// --- Bibliothèque d'icônes (style craie, vignettes) --------------------------
//
// Les icônes existent depuis le début du projet (ICON_NAMES côté Python,
// tracés précalculés dans icon_paths.js côté JS — déjà utilisées par la
// génération LLM) mais n'étaient jamais montrées visuellement nulle
// part : impossible de savoir ce qui était disponible sans lire le code.
// Chaque vignette est dessinée une seule fois au premier affichage avec
// le même moteur craie/feutre que le canvas principal
// (EditorCanvas.drawIconThumbnail), pour un aperçu fidèle, pas une icône
// générique.
let iconLibraryBuilt = false;

function buildIconLibrary() {
  if (iconLibraryBuilt) return;
  const library = document.getElementById("icon-library");
  const iconNames = Object.keys(window.ICON_PATHS || {}).sort();
  library.innerHTML = "";
  for (const name of iconNames) {
    const swatch = document.createElement("div");
    swatch.className = "icon-swatch";
    const canvas = document.createElement("canvas");
    canvas.width = 96;
    canvas.height = 96;
    const label = document.createElement("span");
    label.textContent = name;
    swatch.appendChild(canvas);
    swatch.appendChild(label);
    swatch.addEventListener("click", () => {
      if (!selectedSceneId) return;
      window.EditorCanvas.startPlacingNewIcon(name);
      document.getElementById("image-insert-status").textContent =
        `Icône "${name}" — cliquez sur le tableau pour la placer.`;
    });
    library.appendChild(swatch);
    window.EditorCanvas.drawIconThumbnail(canvas, name, currentProject ? currentProject.theme : "chalk_board");
  }
  iconLibraryBuilt = true;
}

document.getElementById("btn-toggle-icons").addEventListener("click", () => {
  const library = document.getElementById("icon-library");
  const showing = library.style.display !== "none";
  if (showing) {
    library.style.display = "none";
  } else {
    buildIconLibrary();
    library.style.display = "grid";
  }
});

// --- Bibliothèque personnelle (Tâche 6) --------------------------------------
//
// Section "Mes éléments" à côté du socle d'icônes fixe, même mécanisme de
// vignette (EditorCanvas.drawLibraryAssetThumbnail) et de placement par clic
// (startPlacingNewLibraryAsset). Stockage GLOBAL côté Python (pas par
// projet) : reconstruite à chaque ouverture (pas de cache "déjà construit"
// comme buildIconLibrary, qui elle ne change jamais) pour refléter tout de
// suite un ajout/une suppression faite dans la même session.

document.getElementById("btn-save-to-library").addEventListener("click", async () => {
  const status = document.getElementById("library-save-status");
  const payload = window.EditorCanvas.getSelectedStrokeForLibrary();
  if (!payload) {
    status.textContent = "Cet élément ne peut pas être enregistré.";
    return;
  }
  const name = document.getElementById("library-asset-name").value.trim();
  status.textContent = "Enregistrement...";
  try {
    await window.pywebview.api.save_library_asset(name, payload.kind, payload.color, payload.points, payload.bbox);
    document.getElementById("library-asset-name").value = "";
    status.textContent = "Enregistré dans « Mes éléments ».";
    myLibraryStale = true;
  } catch (err) {
    status.textContent = `Erreur : ${err}`;
  }
});

// true après un ajout/une suppression : force buildMyLibrary à refaire
// l'appel réseau au prochain affichage plutôt que de garder une liste
// périmée si la section était déjà ouverte avant l'édition.
let myLibraryStale = true;

async function buildMyLibrary() {
  const library = document.getElementById("my-library");
  const assets = await window.pywebview.api.list_library_assets();
  library.innerHTML = "";
  if (!assets.length) {
    library.innerHTML = '<div class="empty-hint">Aucun élément enregistré pour l\'instant — sélectionnez une forme sur le tableau puis « Enregistrer dans ma bibliothèque ».</div>';
    myLibraryStale = false;
    return;
  }
  for (const asset of assets) {
    const swatch = document.createElement("div");
    swatch.className = "icon-swatch";
    const canvas = document.createElement("canvas");
    canvas.width = 96;
    canvas.height = 96;
    const label = document.createElement("span");
    label.textContent = asset.name;
    const del = document.createElement("span");
    del.className = "swatch-delete";
    del.textContent = "×";
    del.title = "Supprimer cet élément";
    del.addEventListener("click", async (evt) => {
      evt.stopPropagation();
      await window.pywebview.api.delete_library_asset(asset.asset_id);
      myLibraryStale = true;
      buildMyLibrary();
    });
    swatch.appendChild(canvas);
    swatch.appendChild(label);
    swatch.appendChild(del);
    swatch.addEventListener("click", () => {
      if (!selectedSceneId) return;
      window.EditorCanvas.startPlacingNewLibraryAsset(asset);
      document.getElementById("image-insert-status").textContent =
        `« ${asset.name} » — cliquez sur le tableau pour la placer.`;
    });
    library.appendChild(swatch);
    window.EditorCanvas.drawLibraryAssetThumbnail(canvas, asset, currentProject ? currentProject.theme : "chalk_board");
  }
  myLibraryStale = false;
}

document.getElementById("btn-toggle-library").addEventListener("click", async () => {
  const library = document.getElementById("my-library");
  const showing = library.style.display !== "none";
  if (showing) {
    library.style.display = "none";
  } else {
    library.style.display = "grid";
    if (myLibraryStale) await buildMyLibrary();
  }
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

// Un re-rendu prend facilement 10s à plusieurs minutes (ré-encodage
// ffmpeg réel, voir Pipeline.render) : avant ce correctif, le seul
// retour visible était un petit texte gris discret pendant que les deux
// boutons restaient cliquables comme s'ils ne faisaient rien — un
// utilisateur n'avait aucun moyen de savoir qu'un re-rendu était
// réellement en cours, ni de voir le résultat sans quitter l'éditeur.
// Les deux boutons sont maintenant désactivés pendant l'opération, le
// statut est visuellement marqué (couleur + gras), et le résultat
// s'affiche directement dans un lecteur vidéo intégré au panneau, sans
// avoir à ouvrir le dossier.
function setRerenderBusy(busy, message) {
  const status = document.getElementById("rerender-status");
  const sceneBtn = document.getElementById("btn-rerender-scene");
  const allBtn = document.getElementById("btn-rerender-all");
  sceneBtn.disabled = busy;
  allBtn.disabled = busy;
  status.textContent = message;
  status.className = `rerender-status ${busy ? "busy" : ""}`;
}

function showRerenderResult(success, message, videoUrl) {
  const status = document.getElementById("rerender-status");
  status.textContent = message;
  status.className = `rerender-status ${success ? "ok" : "error"}`;
  if (success && videoUrl) {
    const preview = document.getElementById("rerender-preview");
    // videoUrl est déjà une URL servie par Api.rerender_scene/rerender_all
    // (app/local_media_server.py) — un <video src="file://..."> est
    // refusé par WebView2/Chromium depuis une page http:// (constaté
    // empiriquement, voir ui/js/app.js pour le détail).
    preview.src = videoUrl;
    preview.style.display = "block";
  }
}

document.getElementById("btn-rerender-scene").addEventListener("click", async () => {
  if (!selectedSceneId) return;
  setRerenderBusy(true, "Re-rendu de la scène en cours (peut prendre jusqu'à quelques minutes)...");
  try {
    await saveCurrentSceneEdits();
    const videoUrl = await window.pywebview.api.rerender_scene(selectedSceneId);
    showRerenderResult(true, "Scène re-rendue — vidéo à jour ci-dessous.", videoUrl);
  } catch (err) {
    showRerenderResult(false, `Erreur : ${err}`, null);
  } finally {
    document.getElementById("btn-rerender-scene").disabled = false;
    document.getElementById("btn-rerender-all").disabled = false;
  }
});

document.getElementById("btn-rerender-all").addEventListener("click", async () => {
  setRerenderBusy(true, "Re-rendu en cours (seules les scènes modifiées sont ré-encodées)...");
  try {
    if (selectedSceneId) await saveCurrentSceneEdits();
    const videoUrl = await window.pywebview.api.rerender_all();
    showRerenderResult(true, "Montage final à jour — vidéo ci-dessous.", videoUrl);
  } catch (err) {
    showRerenderResult(false, `Erreur : ${err}`, null);
  } finally {
    document.getElementById("btn-rerender-scene").disabled = false;
    document.getElementById("btn-rerender-all").disabled = false;
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
    } else {
      // Toutes les scenes ont ete supprimees par la commande : selectScene
      // (qui rafraichit aussi la timeline) n'est jamais appelee dans ce cas.
      selectedSceneId = null;
      refreshTimeliner();
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
