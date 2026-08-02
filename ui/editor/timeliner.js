// Bande "pellicule" affichée sous l'éditeur (blueprint Timeline + Anime.js,
// voir docs/architecture.md) : vue d'ensemble de toutes les scènes du
// montage (durée relative les unes aux autres, événements mascotte/images
// superposés) — mêmes données que app/scenes/timeline.py::project_to_timeline,
// mais recalculées ici côté client (projectToTimeline ci-dessous mire
// volontairement cette fonction) plutôt que d'aller la chercher via un
// aller-retour Python à chaque rafraîchissement : editor.js garde déjà
// `currentProject` à jour en mémoire après toute édition locale (voix off
// resynthétisée, commande NL appliquée, glisser sur le canvas...), donc
// recalculer ici est instantané et ne peut pas désynchroniser l'affichage.
//
// Tâche 2 : cliquer une scène la sélectionne (réutilise editor.js::selectScene).
// Tâche 3 : glisser un bloc le réordonne, glisser sa poignée de droite le
// raccourcit — les deux persistent via Api.update_timeline (voir editor.js::
// applyTimelineChange), avec un aller-retour optimiste (l'écran se met à
// jour immédiatement pendant le glisser, la confirmation/le vrai état
// arrive du serveur une fois la resynthèse/le re-rendu terminés).

(function () {
  "use strict";

  // Plancher UI pour le raccourcissement par glisser — évite une scène
  // dégénérée (quelques dixièmes de seconde). Rallonger par glisser n'est
  // PAS supporté (voir clamp dans handleResizeMove ci-dessous) : la
  // troncature de texte (truncate_voice_over_to_duration, Tâche 1) ne sait
  // que raccourcir, donc allonger n'aurait aucun effet réel une fois la
  // scène resynthétisée — décision actée dans docs/architecture.md,
  // section Timeline éditable.
  const MIN_SCENE_DURATION_SEC = 2.0;
  // En-dessous de ce déplacement (px), un mousedown+mouseup sur un bloc est
  // traité comme un clic (sélection), pas un glisser — un tremblement de
  // souris ne doit jamais être interprété comme une tentative de réordonnancement.
  const DRAG_THRESHOLD_PX = 4;
  // En-dessous de ce delta (s), un glisser de la poignée de redimension est
  // traité comme un geste accidentel et annulé sans appel API.
  const MIN_DURATION_CHANGE_SEC = 0.1;

  // Tâche 5 (UX enseignants non-pro) : une seule couleur sobre par piste
  // (mascotte / image) plutôt qu'une couleur différente par action_type —
  // un professeur n'a pas besoin de distinguer "wave" de "point" au premier
  // coup d'œil sur une bande de quelques millimètres de large, seulement de
  // voir "il se passe quelque chose ici". Le détail (quelle action, quels
  // instants) reste disponible dans l'infobulle au survol.
  const MASCOT_TICK_COLOR = "#6a94c7";
  const IMAGE_TICK_COLOR = "#c9a15a";

  // Vocabulaire technique (action_type, voir default_mascot_timeline dans
  // app/scenes/schema.py) traduit pour l'infobulle — jamais montré tel
  // quel à un utilisateur non développeur.
  const MASCOT_ACTION_LABELS_FR = {
    appear: "apparaît", disappear: "disparaît", idle: "attend",
    wave: "salue", point: "montre quelque chose", exit: "quitte l'écran",
  };

  function projectToTimeline(project) {
    let cursor = 0.0;
    const scenes = [];
    const mascotTrack = [];
    const imagesTrack = [];
    for (const scene of project.scenes) {
      scenes.push({ scene_id: scene.scene_id, start: cursor, duration: scene.duration_sec });
      (scene.mascot_timeline || []).forEach((action, i) => {
        mascotTrack.push({
          scene_id: scene.scene_id, index: i,
          start: action.start_sec, end: action.end_sec, action: action.action_type,
        });
      });
      (scene.strokes || []).forEach((stroke, i) => {
        if (stroke.kind === "image") {
          imagesTrack.push({ scene_id: scene.scene_id, index: i, start: stroke.start_sec, end: stroke.end_sec });
        }
      });
      cursor += scene.duration_sec;
    }
    return { scenes, tracks: { mascot: mascotTrack, images: imagesTrack }, total_duration: cursor };
  }

  function formatSeconds(value) {
    return `${value.toFixed(1)}s`;
  }

  function buildSceneBlock(sceneEntry, index, timeline, isSelected, isDragging) {
    const block = document.createElement("div");
    block.className = `timeliner-scene${isSelected ? " selected" : ""}${isDragging ? " dragging" : ""}`;
    // flex-grow proportionnel à la durée : chaque bloc occupe une part de la
    // largeur totale égale à sa part de la durée totale du montage, sans
    // calcul manuel de pourcentage ni dépendance à la largeur du conteneur.
    block.style.flexGrow = String(Math.max(sceneEntry.duration, 0.1));
    block.title = `Scène ${index + 1} — ${formatSeconds(sceneEntry.duration)}`;
    block.dataset.sceneId = sceneEntry.scene_id;

    const label = document.createElement("span");
    label.className = "timeliner-scene-label";
    label.textContent = String(index + 1);
    block.appendChild(label);

    const eventsRow = document.createElement("div");
    eventsRow.className = "timeliner-events";
    // Les timestamps mascotte/image sont relatifs au DÉBUT DE LA SCÈNE (même
    // convention que Stroke.start_sec/end_sec) — se positionnent donc en
    // pourcentage de la durée de CETTE scène, pas de la durée totale du
    // montage, ce qui reste correct quelle que soit la largeur réelle du
    // bloc (fixée par flex-grow ci-dessus).
    const duration = Math.max(sceneEntry.duration, 0.001);

    timeline.tracks.mascot
      .filter((m) => m.scene_id === sceneEntry.scene_id)
      .forEach((m) => {
        const tick = document.createElement("div");
        tick.className = "timeliner-tick timeliner-tick-mascot";
        tick.style.left = `${(m.start / duration) * 100}%`;
        tick.style.width = `${Math.max(((m.end - m.start) / duration) * 100, 1.5)}%`;
        tick.style.background = MASCOT_TICK_COLOR;
        const label = MASCOT_ACTION_LABELS_FR[m.action] || "fait quelque chose";
        tick.title = `Mascotte : ${label} (${formatSeconds(m.start)} → ${formatSeconds(m.end)})`;
        eventsRow.appendChild(tick);
      });

    timeline.tracks.images
      .filter((im) => im.scene_id === sceneEntry.scene_id)
      .forEach((im) => {
        const tick = document.createElement("div");
        tick.className = "timeliner-tick timeliner-tick-image";
        tick.style.left = `${(im.start / duration) * 100}%`;
        tick.style.width = `${Math.max(((im.end - im.start) / duration) * 100, 1.5)}%`;
        tick.style.background = IMAGE_TICK_COLOR;
        tick.title = `Image (${formatSeconds(im.start)} → ${formatSeconds(im.end)})`;
        eventsRow.appendChild(tick);
      });

    block.appendChild(eventsRow);

    const handle = document.createElement("div");
    handle.className = "timeliner-resize-handle";
    handle.title = "Glisser pour raccourcir la scène";
    block.appendChild(handle);

    return block;
  }

  // --- Glisser : état module-level (un seul glisser possible à la fois,
  // même schéma que editor_canvas.js::dragState) — les gestionnaires
  // mousemove/mouseup sont posés une seule fois sur `window` (pas à chaque
  // rendu) et lisent cet état, qui porte tout ce dont ils ont besoin
  // (fermetures de la scène en cours de glisser capturées au mousedown).

  let dragState = null;

  function handleReorderMove(evt) {
    const state = dragState;
    if (!state.dragging) {
      if (Math.abs(evt.clientX - state.startClientX) < DRAG_THRESHOLD_PX) return;
      state.dragging = true;
    }
    const trackRect = state.track.getBoundingClientRect();
    const pointerX = evt.clientX - trackRect.left;
    const others = state.initialOrder.filter((id) => id !== state.sceneId);
    let cumulative = 0;
    let targetIndex = others.length;
    for (let i = 0; i < others.length; i++) {
      const width = state.byId[others[i]].duration * state.pxPerSecond;
      if (pointerX < cumulative + width / 2) {
        targetIndex = i;
        break;
      }
      cumulative += width;
    }
    const newOrder = others.slice();
    newOrder.splice(targetIndex, 0, state.sceneId);
    state.currentOrder = newOrder;
    state.renderBlocks(newOrder, state.sceneId);
  }

  function finishReorder() {
    const state = dragState;
    if (!state.dragging) {
      // Pas de déplacement significatif : un simple clic de sélection.
      state.handlers.onSceneClick(state.sceneId);
      return;
    }
    if (state.currentOrder.join("|") !== state.initialOrder.join("|")) {
      state.handlers.onTimelineChange({
        scenes: state.currentOrder.map((id) => ({ scene_id: id, duration: state.byId[id].duration })),
        tracks: state.timeline.tracks,
      });
    } else {
      // Ramené à sa place d'origine : redessine sans la classe "dragging".
      state.renderBlocks(state.initialOrder, null);
    }
  }

  function handleResizeMove(evt) {
    const state = dragState;
    const dx = evt.clientX - state.startClientX;
    const deltaSec = dx / state.pxPerSecond;
    // Rallonger (deltaSec > 0) est explicitement bloqué (clampé à la durée
    // d'origine) — voir le commentaire sur MIN_SCENE_DURATION_SEC en tête
    // de fichier.
    const newDuration = Math.min(state.originalDuration, Math.max(MIN_SCENE_DURATION_SEC, state.originalDuration + deltaSec));
    state.newDuration = newDuration;
    state.block.style.flexGrow = String(Math.max(newDuration, 0.1));
    state.label.textContent = formatSeconds(newDuration);
  }

  function finishResize() {
    const state = dragState;
    state.label.remove();
    if (Math.abs(state.newDuration - state.originalDuration) < MIN_DURATION_CHANGE_SEC) {
      state.renderBlocks(state.order, null);
      return;
    }
    state.handlers.onTimelineChange({
      scenes: state.order.map((id) => ({
        scene_id: id,
        duration: id === state.sceneId ? state.newDuration : state.byId[id].duration,
      })),
      tracks: state.timeline.tracks,
    });
  }

  window.addEventListener("mousemove", (evt) => {
    if (!dragState) return;
    if (dragState.type === "reorder") handleReorderMove(evt);
    else if (dragState.type === "resize") handleResizeMove(evt);
  });

  window.addEventListener("mouseup", () => {
    if (!dragState) return;
    if (dragState.type === "reorder") finishReorder();
    else if (dragState.type === "resize") finishResize();
    dragState = null;
  });

  function render(container, project, selectedSceneId, handlers) {
    const timeline = projectToTimeline(project);
    container.innerHTML = "";
    if (!timeline.scenes.length) {
      container.innerHTML = '<div class="timeliner-empty">Aucune scène.</div>';
      return;
    }
    const byId = {};
    timeline.scenes.forEach((s) => { byId[s.scene_id] = s; });
    const initialOrder = timeline.scenes.map((s) => s.scene_id);

    const track = document.createElement("div");
    track.className = "timeliner-track";
    container.appendChild(track);

    function renderBlocks(order, draggingId) {
      track.innerHTML = "";
      order.forEach((sceneId, index) => {
        const sceneEntry = byId[sceneId];
        const block = buildSceneBlock(sceneEntry, index, timeline, sceneId === selectedSceneId, sceneId === draggingId);
        track.appendChild(block);

        block.addEventListener("mousedown", (evt) => {
          dragState = {
            type: "reorder", sceneId, startClientX: evt.clientX, dragging: false,
            initialOrder: order.slice(), currentOrder: order.slice(),
            pxPerSecond: track.getBoundingClientRect().width / Math.max(timeline.total_duration, 0.001),
            byId, timeline, track, handlers, renderBlocks,
          };
        });

        const handle = block.querySelector(".timeliner-resize-handle");
        handle.addEventListener("mousedown", (evt) => {
          evt.stopPropagation();
          evt.preventDefault();
          const rect = block.getBoundingClientRect();
          const pxPerSecond = rect.width / Math.max(sceneEntry.duration, 0.001);
          const label = document.createElement("div");
          label.className = "timeliner-resize-tooltip";
          label.textContent = formatSeconds(sceneEntry.duration);
          block.appendChild(label);
          dragState = {
            type: "resize", sceneId, startClientX: evt.clientX,
            originalDuration: sceneEntry.duration, newDuration: sceneEntry.duration,
            pxPerSecond, block, label, order: order.slice(), byId, timeline, handlers, renderBlocks,
          };
        });
      });
    }

    renderBlocks(initialOrder, null);
  }

  window.Timeliner = { render, projectToTimeline };
})();
