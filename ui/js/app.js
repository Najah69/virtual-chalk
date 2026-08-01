// Logique de l'assistant en 5 étapes. Appelle app.api_bridge.Api via
// window.pywebview.api (injecté par pywebview au chargement de la fenêtre).

// ui/index.html est chargée via le mini serveur HTTP local de pywebview
// (http://localhost:<port>/..., voir Api.open_editor pour le détail de ce
// mécanisme), mais la vidéo générée vit dans un dossier de sortie
// quelconque (Documents/Virtual-Chalk Videos/...), hors de la racine
// servie par ce serveur — impossible de la référencer par une URL
// relative à celui-ci. Un <video src="file://..."> semblait la solution
// (utilisé un temps), mais WebView2/Chromium REFUSE de charger un
// file:// depuis une page qui n'est pas elle-même file:// — constaté
// empiriquement (video.error.message === "Media load rejected by URL
// safety check"), pas juste un cas d'usage non documenté. Corrigé côté
// Python (app/local_media_server.py) : Api.start_pipeline_from_script/
// rerender_scene/rerender_all renvoient désormais une URL déjà servie
// (http://127.0.0.1:<port>/<jeton>) plutôt qu'un chemin Windows brut à
// convertir ici — voir result.video_url / la valeur de retour directe de
// rerender_scene/rerender_all.

function goToStep(n) {
  document.querySelectorAll(".step").forEach((el) => {
    el.classList.toggle("active", el.dataset.step === String(n));
  });
  document.querySelectorAll(".step-panel").forEach((el) => {
    el.classList.toggle("active", el.dataset.step === String(n));
  });
}

// Navigation libre entre étapes en cliquant directement sur leur onglet
// (barre du haut) — pas seulement via les boutons "Continuer" qui
// n'avancent que d'une étape. Utile notamment pour revenir à l'étape 1
// (prompt initial) après avoir avancé, sans perdre le contenu déjà saisi
// (goToStep ne fait que basculer la classe "active", rien n'est vidé).
// role="button"/tabindex (voir index.html) rendent l'onglet focusable au
// clavier, mais un div role="button" n'active pas Entrée/Espace tout
// seul comme un vrai <button> — géré explicitement ici.
document.querySelectorAll(".step").forEach((el) => {
  el.addEventListener("click", () => goToStep(parseInt(el.dataset.step, 10)));
  el.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter" || evt.key === " ") {
      evt.preventDefault();
      goToStep(parseInt(el.dataset.step, 10));
    }
  });
});

window.onPipelineProgress = function (step, fraction) {
  const label = { script: "Script...", diagram: "Schémas...", voice: "Voix...", render: "Animation...", encode: "Assemblage vidéo..." }[step] || step;
  document.getElementById("progress-label").textContent = label;
  document.getElementById("progress-bar").value = fraction;
};

async function loadThemeGallery() {
  const gallery = document.getElementById("theme-gallery");
  const themes = [
    { id: "chalk_board", label: "Tableau craie" },
    { id: "whiteboard_marker", label: "Tableau blanc + feutres" },
  ];
  gallery.innerHTML = themes
    .map((t) => `<div class="theme-card" data-theme="${t.id}">${t.label}</div>`)
    .join("");
  gallery.querySelectorAll(".theme-card").forEach((card) => {
    card.addEventListener("click", () => {
      gallery.querySelectorAll(".theme-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
    });
  });
  gallery.querySelector(".theme-card").classList.add("selected");
}

async function loadVoices() {
  const select = document.getElementById("voice-select");
  const profiles = await window.pywebview.api.list_voice_profiles();
  select.innerHTML = profiles.map((p) => `<option value="${p.name}">${p.name}</option>`).join("");
}

async function loadVideoProfiles() {
  const select = document.getElementById("video-profile-select");
  const profiles = await window.pywebview.api.list_video_profiles();
  select.innerHTML = profiles.map((p) => `<option value="${p.key}">${p.label}</option>`).join("");
}

let pickedFilePath = null;

document.getElementById("btn-pick-file").addEventListener("click", async () => {
  const path = await window.pywebview.api.pick_file();
  if (path) {
    pickedFilePath = path;
    document.getElementById("picked-file-label").textContent = `Fichier sélectionné : ${path}`;
  }
});

// "Ouvrir un projet..." : sélectionne un fichier projet existant (.vchalk)
// et ouvre directement l'éditeur dessus (Api.open_project_file combine
// chargement + ouverture de fenêtre), sans passer par l'assistant.
document.getElementById("btn-open-project").addEventListener("click", async () => {
  const path = await window.pywebview.api.pick_project_file();
  if (path) {
    await window.pywebview.api.open_project_file(path);
  }
});

// Determine la source a envoyer au pipeline selon ce que l'utilisateur a
// rempli, par ordre de priorite (fichier choisi > URL GitHub > URL simple >
// texte colle) — avant ce correctif, seul le texte colle etait jamais
// transmis (fichier/URL etaient ignores silencieusement).
function resolveSource() {
  if (pickedFilePath) return { type: "file", value: pickedFilePath };
  const githubUrl = document.getElementById("source-github").value.trim();
  if (githubUrl) return { type: "github", value: githubUrl };
  const url = document.getElementById("source-url").value.trim();
  if (url) return { type: "url", value: url };
  return { type: "text", value: document.getElementById("source-text").value };
}

// --- Étape 1 -> 2 : génère le script (seul appel LLM coûteux avant la
// révision) puis affiche une zone de texte éditable par scène. Rien n'est
// encore synthétisé/rendu à ce stade — voir Api.generate_script /
// Pipeline.generate_project (docs/architecture.md).
function renderScriptEditor(project) {
  const container = document.getElementById("scenes-editor");
  container.innerHTML = project.scenes
    .map(
      (scene, i) => `
        <div class="scene-script-item" data-scene-id="${scene.scene_id}">
          <h4>Scène ${i + 1}</h4>
          <textarea rows="3" class="scene-voice-over">${scene.voice_over}</textarea>
        </div>`
    )
    .join("");
}

document.getElementById("btn-go-step2").addEventListener("click", async () => {
  const btn = document.getElementById("btn-go-step2");
  const errorBox = document.getElementById("step1-error");
  errorBox.style.display = "none";
  btn.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = "Génération du script...";
  try {
    const source = resolveSource();
    const videoProfile = document.getElementById("video-profile-select").value;
    const githubContentKind = document.getElementById("github-content-kind").value;
    const mobileLayout = document.getElementById("mobile-layout").checked;
    const project = await window.pywebview.api.generate_script(source, videoProfile, githubContentKind, mobileLayout);
    renderScriptEditor(project);
    goToStep(2);
  } catch (err) {
    errorBox.textContent = `Erreur : ${err}`;
    errorBox.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
});

document.getElementById("btn-go-step3").addEventListener("click", () => goToStep(3));

let lastVideoPath = null;
let lastVideoUrl = null;

// --- Étape 3 -> 4/5 : reprend le script en attente (édité à l'étape 2) et
// termine la génération (diagrammes, voix, rendu, export) — voir
// Api.start_pipeline_from_script.
document.getElementById("btn-go-step4").addEventListener("click", async () => {
  goToStep(4);
  const errorBox = document.getElementById("generation-error");
  const errorBackBtn = document.getElementById("btn-generation-error-back");
  errorBox.style.display = "none";
  errorBackBtn.style.display = "none";
  document.getElementById("progress-bar").style.display = "block";

  const editedScenes = Array.from(document.querySelectorAll("#scenes-editor .scene-script-item")).map((el) => ({
    scene_id: el.dataset.sceneId,
    voice_over: el.querySelector(".scene-voice-over").value,
  }));
  const voiceProfile = document.getElementById("voice-select").value;
  const exportH5p = document.getElementById("export-h5p").checked;
  const theme = document.querySelector(".theme-card.selected")?.dataset.theme || "chalk_board";
  const mascotEnabled = document.getElementById("mascot-enabled").checked;
  try {
    const result = await window.pywebview.api.start_pipeline_from_script(
      editedScenes, voiceProfile, exportH5p, theme, mascotEnabled
    );
    lastVideoPath = result.video_path;
    lastVideoUrl = result.video_url;
    document.getElementById("result-video").src = result.video_url;
    goToStep(5);
  } catch (err) {
    // Sans ce rattrapage, une erreur (ex: SAPI qui ne répond plus, voir
    // app/tts/sapi_local.py::SYNTHESIS_TIMEOUT_SEC) laissait la barre de
    // progression figée indéfiniment, sans aucun message — la promesse
    // rejetée n'était gérée nulle part, silencieusement.
    document.getElementById("progress-bar").style.display = "none";
    errorBox.textContent = `Erreur : ${err}`;
    errorBox.style.display = "block";
    errorBackBtn.style.display = "inline-block";
  }
});

document.getElementById("btn-generation-error-back").addEventListener("click", () => goToStep(3));

document.getElementById("btn-open-folder").addEventListener("click", () => {
  window.pywebview.api.open_output_folder();
});

document.getElementById("btn-edit").addEventListener("click", () => {
  window.pywebview.api.open_editor();
});

document.getElementById("btn-export-en").addEventListener("click", async () => {
  const btn = document.getElementById("btn-export-en");
  const status = document.getElementById("export-en-status");
  btn.disabled = true;
  status.textContent = " Traduction et re-génération en cours (peut prendre quelques minutes)...";
  try {
    const result = await window.pywebview.api.export_translated("en");
    status.textContent = ` Exporté : ${result.video_path}`;
  } catch (err) {
    status.textContent = ` Erreur : ${err}`;
  } finally {
    btn.disabled = false;
  }
});

// --- Étape 6 : exercices (mode simple) ---

document.getElementById("btn-go-step6").addEventListener("click", async () => {
  document.getElementById("exercise-video").src = lastVideoUrl || "";
  await refreshExerciseList();
  goToStep(6);
});

document.getElementById("exercise-type").addEventListener("change", (e) => {
  document.querySelectorAll(".exercise-type-fields").forEach((el) => (el.style.display = "none"));
  document.getElementById(`exercise-fields-${e.target.value}`).style.display = "block";
});

document.getElementById("btn-use-current-time").addEventListener("click", () => {
  const video = document.getElementById("exercise-video");
  document.getElementById("exercise-time").value = video.currentTime.toFixed(1);
});

function addAnswerRow(text = "", correct = false) {
  const row = document.createElement("div");
  row.className = "mc-answer-row";
  row.style.marginTop = "6px";
  row.innerHTML = `
    <input type="text" class="mc-answer-text" value="${text}" placeholder="Réponse" style="width:60%" />
    <label><input type="checkbox" class="mc-answer-correct" ${correct ? "checked" : ""} /> Correcte</label>
    <button type="button" class="secondary btn-remove-answer">✕</button>
  `;
  row.querySelector(".btn-remove-answer").addEventListener("click", () => row.remove());
  document.getElementById("mc-answers").appendChild(row);
}

document.getElementById("btn-add-answer").addEventListener("click", () => addAnswerRow());
addAnswerRow();
addAnswerRow();

function buildExercisePayload(type) {
  if (type === "true_false") {
    return {
      question: document.getElementById("tf-question").value,
      correct: document.querySelector('input[name="tf-correct"]:checked').value === "true",
    };
  }
  if (type === "multi_choice") {
    const answers = Array.from(document.querySelectorAll("#mc-answers .mc-answer-row")).map((row) => [
      row.querySelector(".mc-answer-text").value,
      row.querySelector(".mc-answer-correct").checked,
    ]);
    return { question: document.getElementById("mc-question").value, answers };
  }
  if (type === "blanks") {
    return {
      instruction: document.getElementById("blanks-instruction").value,
      sentence: document.getElementById("blanks-sentence").value,
    };
  }
  if (type === "drag_text") {
    return {
      instruction: document.getElementById("dt-instruction").value,
      text: document.getElementById("dt-text").value,
    };
  }
}

document.getElementById("btn-add-exercise").addEventListener("click", async () => {
  const type = document.getElementById("exercise-type").value;
  const title = document.getElementById("exercise-title").value || "Exercice";
  const time = parseFloat(document.getElementById("exercise-time").value || "0");
  const payload = buildExercisePayload(type);

  await window.pywebview.api.add_exercise(type, time, title, payload);
  document.getElementById("exercise-title").value = "";
  await refreshExerciseList();
});

const EXERCISE_TYPE_LABELS = {
  true_false: "Vrai / Faux",
  multi_choice: "QCM",
  blanks: "Texte à trous",
  drag_text: "Glisser les mots",
};

async function refreshExerciseList() {
  const exercises = await window.pywebview.api.list_exercises();
  const list = document.getElementById("exercise-list");
  list.innerHTML = exercises
    .map(
      (ex) =>
        `<li>${ex.time_sec.toFixed(1)}s — [${EXERCISE_TYPE_LABELS[ex.exercise_type]}] ${ex.title} ` +
        `<button type="button" class="secondary btn-remove-exercise" data-id="${ex.exercise_id}">Supprimer</button></li>`
    )
    .join("");
  list.querySelectorAll(".btn-remove-exercise").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await window.pywebview.api.remove_exercise(btn.dataset.id);
      await refreshExerciseList();
    });
  });
}

document.getElementById("btn-export-h5p-now").addEventListener("click", async () => {
  const status = document.getElementById("export-h5p-status");
  status.textContent = " Export en cours...";
  const path = await window.pywebview.api.export_h5p_now();
  status.textContent = ` Exporté : ${path}`;
});

document.getElementById("btn-settings").addEventListener("click", async () => {
  const settings = await window.pywebview.api.get_settings();
  document.getElementById("set-llm-provider").value = settings.llm_provider;
  document.getElementById("set-llm-model").value = settings.llm_model;
  document.getElementById("set-default-theme").value = settings.default_theme;
  document.getElementById("set-output-dir").value = settings.default_output_dir;
  document.getElementById("set-export-h5p").checked = settings.export_h5p_by_default;
  document.getElementById("settings-overlay").classList.add("open");
});

document.getElementById("btn-settings-cancel").addEventListener("click", () => {
  document.getElementById("settings-overlay").classList.remove("open");
});

document.getElementById("btn-pick-output-dir").addEventListener("click", async () => {
  const path = await window.pywebview.api.pick_output_folder();
  if (path) document.getElementById("set-output-dir").value = path;
});

document.getElementById("btn-settings-save").addEventListener("click", async () => {
  await window.pywebview.api.save_settings({
    llm_provider: document.getElementById("set-llm-provider").value,
    llm_model: document.getElementById("set-llm-model").value,
    default_theme: document.getElementById("set-default-theme").value,
    default_output_dir: document.getElementById("set-output-dir").value,
    export_h5p_by_default: document.getElementById("set-export-h5p").checked,
  });
  document.getElementById("settings-overlay").classList.remove("open");
});

window.addEventListener("pywebviewready", () => {
  loadThemeGallery();
  loadVoices();
  loadVideoProfiles();
});
