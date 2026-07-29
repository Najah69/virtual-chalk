// Logique de l'assistant en 5 étapes. Appelle app.api_bridge.Api via
// window.pywebview.api (injecté par pywebview au chargement de la fenêtre).

function goToStep(n) {
  document.querySelectorAll(".step").forEach((el) => {
    el.classList.toggle("active", el.dataset.step === String(n));
  });
  document.querySelectorAll(".step-panel").forEach((el) => {
    el.classList.toggle("active", el.dataset.step === String(n));
  });
}

window.onPipelineProgress = function (step, fraction) {
  const label = { script: "Script...", voice: "Voix...", render: "Animation...", encode: "Assemblage vidéo..." }[step] || step;
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

document.getElementById("btn-pick-file").addEventListener("click", async () => {
  const path = await window.pywebview.api.pick_file();
  if (path) document.getElementById("source-text").value = `[Fichier sélectionné] ${path}`;
});

document.getElementById("btn-go-step2").addEventListener("click", () => goToStep(2));
document.getElementById("btn-go-step3").addEventListener("click", () => goToStep(3));

document.getElementById("btn-go-step4").addEventListener("click", async () => {
  goToStep(4);
  const source = { type: "text", value: document.getElementById("source-text").value };
  const voiceProfile = document.getElementById("voice-select").value;
  const exportH5p = document.getElementById("export-h5p").checked;
  const result = await window.pywebview.api.start_pipeline(source, voiceProfile, exportH5p);
  document.getElementById("result-video").src = result.video_path;
  goToStep(5);
});

document.getElementById("btn-open-folder").addEventListener("click", () => {
  window.pywebview.api.open_output_folder();
});

window.addEventListener("pywebviewready", () => {
  loadThemeGallery();
  loadVoices();
});
