// Rendu WYSIWYG + édition directe (sélection, glisser, redimensionner,
// ajout, édition de texte inline) de la scène sélectionnée dans
// l'éditeur. Réutilise les mêmes modules que web_template/index.html
// (thème, police manuscrite réelle, icônes, grain craie) pour un aperçu
// fidèle au rendu final — voir Api.open_editor (api_bridge.py) pour la
// raison technique (chargement via http://localhost, pas file://,
// nécessaire pour que ces modules puissent charger leurs ressources
// locales comme dans la fenêtre de rendu).
//
// Contrairement au moteur de capture (qui accumule la craie sans jamais
// effacer, pour un rendu incrémental rapide sur des milliers de frames),
// ce module redessine TOUJOURS l'intégralité du canvas à chaque
// changement : les éléments peuvent être déplacés/supprimés/redimensionnés
// ici, l'hypothèse "jamais effacé" du moteur de capture ne tient plus.
//
// stroke.points reste TOUJOURS la donnée persistée/source de vérité
// (ancre haut-gauche pour icône/animation/image/diagramme, point de
// départ baseline pour texte, tracé vectoriel complet pour "shape") —
// jamais réécrite avec le tracé développé. Le tracé réellement dessiné
// (contours de lettres/icône) est calculé à la volée et mis en cache sur
// le stroke (champs préfixés "_", jamais envoyés à Python, voir
// serializeStrokesForSave).

(function () {
  "use strict";

  // Doit rester synchronisé avec CANVAS_WIDTH/HEIGHT et
  // CANVAS_WIDTH/HEIGHT_PORTRAIT dans app/scenes/schema.py. "let" (pas
  // "const") : dépend du projet chargé (Project.mobile_layout, voir
  // setCanvasSize ci-dessous) — un même éditeur peut successivement
  // ouvrir un projet paysage puis un projet portrait.
  const CANVAS_SIZES = {
    landscape: [1920, 1080],
    portrait: [1080, 1920],
  };
  let CANVAS_WIDTH = CANVAS_SIZES.portrait[0];
  let CANVAS_HEIGHT = CANVAS_SIZES.portrait[1];
  const HANDLE_SIZE = 14; // px en espace canvas réel, pas espace écran

  // Doit rester synchronisé avec THEME_TEXT_COLORS dans
  // app/render/theme_registry.py (même logique que window.THEMES dans
  // themes.js, dupliqué ici pour la même raison : Python ne parse pas le
  // JS). Couleur par défaut d'un texte nouvellement ajouté depuis
  // l'éditeur — l'utilisateur peut la changer ensuite via le panneau de
  // propriétés (Phase 2).
  const THEME_TEXT_COLORS = {
    chalk_board: ["#ffffff", "#ffe66d"],
    whiteboard_marker: ["#1a1a1a", "#1f5fd1"],
  };
  function defaultTextColorForTheme(themeId) {
    const colors = THEME_TEXT_COLORS[themeId] || THEME_TEXT_COLORS.chalk_board;
    return colors[0];
  }

  const canvas = document.getElementById("preview-canvas");
  const container = canvas.parentElement;
  const ctx = canvas.getContext("2d");
  canvas.width = CANVAS_WIDTH;
  canvas.height = CANVAS_HEIGHT;

  // Taille CSS du canvas calculée explicitement en JS à partir des
  // dimensions RÉELLEMENT mesurées du conteneur (container.clientWidth/
  // Height), plutôt que via max-width:100% en CSS : un canvas avec des
  // attributs width/height à 1920x1080 a une taille CSS intrinsèque de
  // 1920x1080 par défaut, et dans un conteneur flex imbriqué
  // (.canvas-preview, lui-même flex:1 d'un parent flex), cette taille
  // intrinsèque peut empêcher le conteneur de se réduire correctement
  // (le point d'ancrage min-width:0 ne suffit pas toujours selon la
  // profondeur d'imbrication) — constaté à l'écran : le panneau de
  // propriétés poussé hors de la fenêtre. Mesurer et fixer la taille en
  // pixels explicitement lève toute ambiguïté.
  function resizeCanvasToContainer() {
    const availW = Math.max(50, container.clientWidth - 24);
    const availH = Math.max(50, container.clientHeight - 24);
    const scale = Math.min(availW / CANVAS_WIDTH, availH / CANVAS_HEIGHT);
    canvas.style.width = `${Math.floor(CANVAS_WIDTH * scale)}px`;
    canvas.style.height = `${Math.floor(CANVAS_HEIGHT * scale)}px`;
  }

  // Applique l'orientation du projet chargé (voir Project.mobile_layout,
  // relayé par editor.js) — change le backing store réel du canvas
  // (attributs width/height, PAS juste sa taille CSS affichée), donc doit
  // être appelé avant tout redraw() pour ce projet. Change canvas.width/
  // height efface aussi le contenu existant (comportement natif du
  // canvas), sans effet ici puisque loadScene() redessine juste après.
  function setCanvasSize(mobileLayout) {
    const [w, h] = mobileLayout ? CANVAS_SIZES.portrait : CANVAS_SIZES.landscape;
    CANVAS_WIDTH = w;
    CANVAS_HEIGHT = h;
    canvas.width = CANVAS_WIDTH;
    canvas.height = CANVAS_HEIGHT;
    resizeCanvasToContainer();
  }
  window.addEventListener("resize", resizeCanvasToContainer);
  resizeCanvasToContainer();

  let editorScene = null;
  let editorTheme = null;
  let editorThemeId = null;
  let selectedStroke = null;

  let onSelectionChange = null;
  let onSceneChanged = null;

  // --- Cache dérivé par stroke (jamais persisté) ------------------------

  function invalidateStrokeRenderCache(stroke) {
    delete stroke._drawPoints;
    delete stroke._chalkDabs;
    stroke._lastDrawnCount = 0;
  }

  // Points réellement dessinables pour un stroke texte/icône, calculés à
  // partir de son ancre (stroke.points[0]) — jamais stockés dans
  // stroke.points lui-même. "shape" a déjà son tracé complet dans
  // stroke.points (diagramme déjà vectorisé), retourné tel quel.
  function getDrawPoints(stroke) {
    if (stroke._drawPoints) return stroke._drawPoints;
    if (stroke.kind === "text" && stroke.text) {
      const anchor = stroke.points[0];
      stroke._drawPoints = window.textToPaths(stroke.text, anchor.x, anchor.y, stroke.width);
    } else if (stroke.kind === "icon" && stroke.text) {
      const anchor = stroke.points[0];
      stroke._drawPoints = window.iconToPoints(stroke.text, anchor.x, anchor.y, stroke.width);
    } else {
      stroke._drawPoints = stroke.points;
    }
    return stroke._drawPoints;
  }

  // Boîte englobante en espace canvas réel (1920x1080) — utilisée pour la
  // sélection (hit-test), le surlignage, et le placement des poignées.
  function boundingBoxOf(stroke) {
    if (stroke.kind === "image" || stroke.kind === "diagram") {
      const a = stroke.points[0];
      return { x: a.x, y: a.y, w: stroke.width, h: stroke.height || stroke.width };
    }
    if (stroke.kind === "icon" || stroke.kind === "animation") {
      const a = stroke.points[0];
      return { x: a.x, y: a.y, w: stroke.width, h: stroke.width };
    }
    const pts = getDrawPoints(stroke);
    if (!pts || !pts.length) {
      const a = stroke.points[0];
      return { x: a.x - 5, y: a.y - 5, w: 10, h: 10 };
    }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of pts) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
    if (minX === Infinity) {
      const a = stroke.points[0];
      return { x: a.x - 5, y: a.y - 5, w: 10, h: 10 };
    }
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  // --- Dessin -------------------------------------------------------------

  function drawStrokeFull(stroke) {
    if (stroke.kind === "image") {
      if (stroke._imageEl && stroke._imageReady !== false) {
        const a = stroke.points[0];
        ctx.drawImage(stroke._imageEl, a.x, a.y, stroke.width, stroke.height);
      }
      return;
    }
    if (stroke.kind === "animation") {
      const fn = window.ANIMATIONS && window.ANIMATIONS[stroke.text];
      if (fn) {
        const boardTexture = window._boardTextureCache[editorTheme.surface] || null;
        // Image statique représentative (pas d'horloge dans l'éditeur) :
        // t fixe plutôt qu'une vraie boucle animée.
        fn(ctx, stroke, 0.5, boardTexture, editorTheme.tool);
      }
      return;
    }
    // text / icon / shape / diagram (déjà vectorisé) : même outil craie/
    // feutre que le rendu final. stroke.points est échangé TEMPORAIREMENT
    // contre le tracé développé (ancre -> vrais contours) le temps de cet
    // appel synchrone, puis restauré aussitôt après — jamais réécrit de
    // façon persistante (voir en-tête de fichier). _chalkDabs (le grain,
    // coûteux à calculer) reste en cache sur le stroke entre deux
    // redessins ; _lastDrawnCount, lui, DOIT repartir de 0 à chaque
    // redessin puisque le canvas entier est effacé à chaque fois
    // (redraw()) — sans ça, chalk.js croit que ce grain a déjà été tracé
    // sur un canvas maintenant vide et ne redessine rien.
    const drawTool = window.TOOLS[editorTheme.tool];
    const originalPoints = stroke.points;
    stroke.points = getDrawPoints(stroke);
    stroke._lastDrawnCount = 0;
    drawTool(ctx, stroke, 1);
    stroke.points = originalPoints;
  }

  function drawSelectionOverlay(stroke) {
    const box = boundingBoxOf(stroke);
    ctx.save();
    ctx.strokeStyle = "#2f7bff";
    ctx.lineWidth = 3;
    ctx.setLineDash([10, 6]);
    ctx.strokeRect(box.x - 6, box.y - 6, box.w + 12, box.h + 12);
    ctx.setLineDash([]);
    if (isResizable(stroke)) {
      ctx.fillStyle = "#2f7bff";
      for (const h of handlePositions(box)) {
        ctx.fillRect(h.x - HANDLE_SIZE / 2, h.y - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
      }
    }
    ctx.restore();
  }

  function redraw() {
    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    if (!editorScene || !editorTheme) return;
    window.SURFACES[editorTheme.surface](ctx, CANVAS_WIDTH, CANVAS_HEIGHT);
    for (const stroke of editorScene.strokes || []) {
      drawStrokeFull(stroke);
    }
    if (selectedStroke) drawSelectionOverlay(selectedStroke);
  }

  // --- Poignées de redimensionnement --------------------------------------

  function isResizable(stroke) {
    return stroke.kind === "image" || stroke.kind === "icon" ||
      stroke.kind === "diagram" || stroke.kind === "animation";
  }

  // 4 coins, dans l'ordre : haut-gauche, haut-droit, bas-droit, bas-gauche.
  function handlePositions(box) {
    return [
      { corner: "nw", x: box.x, y: box.y },
      { corner: "ne", x: box.x + box.w, y: box.y },
      { corner: "se", x: box.x + box.w, y: box.y + box.h },
      { corner: "sw", x: box.x, y: box.y + box.h },
    ];
  }

  function handleAtPoint(stroke, x, y) {
    if (!isResizable(stroke)) return null;
    const box = boundingBoxOf(stroke);
    for (const h of handlePositions(box)) {
      if (Math.abs(x - h.x) <= HANDLE_SIZE && Math.abs(y - h.y) <= HANDLE_SIZE) return h.corner;
    }
    return null;
  }

  // --- Hit-testing ---------------------------------------------------------

  function strokeAtPoint(x, y) {
    const strokes = (editorScene && editorScene.strokes) || [];
    // Dernier posé = dessiné par-dessus = prioritaire à la sélection.
    for (let i = strokes.length - 1; i >= 0; i--) {
      const box = boundingBoxOf(strokes[i]);
      if (x >= box.x - 6 && x <= box.x + box.w + 6 && y >= box.y - 6 && y <= box.y + box.h + 6) {
        return strokes[i];
      }
    }
    return null;
  }

  // --- Coordonnées écran -> espace canvas réel (1920x1080) ---------------

  function canvasSpaceFromEvent(evt) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = CANVAS_WIDTH / rect.width;
    const scaleY = CANVAS_HEIGHT / rect.height;
    return { x: (evt.clientX - rect.left) * scaleX, y: (evt.clientY - rect.top) * scaleY };
  }

  // --- État d'interaction souris -------------------------------------------

  let dragState = null; // { mode: "move" | "resize", stroke, corner, startX, startY, orig }
  let placingKind = null; // "text" | "image" | "icon" | "library" en attente de placement (voir startPlacingNew*)
  let pendingImageData = null;
  let pendingIconName = null;
  let pendingLibraryAsset = null; // Tâche 6 : LibraryAsset en attente de placement

  function selectStroke(stroke) {
    selectedStroke = stroke;
    redraw();
    if (onSelectionChange) onSelectionChange(stroke);
  }

  function notifySceneChanged() {
    if (onSceneChanged) onSceneChanged();
  }

  canvas.addEventListener("mousedown", (evt) => {
    const pt = canvasSpaceFromEvent(evt);

    if (placingKind === "text") {
      const stroke = _addTextStrokeAt(pt.x, pt.y, "Nouveau texte");
      placingKind = null;
      canvas.style.cursor = "default";
      selectStroke(stroke);
      notifySceneChanged();
      return;
    }
    if (placingKind === "image") {
      const stroke = _addImageStrokeAt(pt.x, pt.y, pendingImageData);
      placingKind = null;
      pendingImageData = null;
      canvas.style.cursor = "default";
      selectStroke(stroke);
      notifySceneChanged();
      return;
    }
    if (placingKind === "icon") {
      const stroke = _addIconStrokeAt(pt.x, pt.y, pendingIconName);
      placingKind = null;
      pendingIconName = null;
      canvas.style.cursor = "default";
      selectStroke(stroke);
      notifySceneChanged();
      return;
    }
    if (placingKind === "library") {
      const stroke = _addLibraryAssetStrokeAt(pt.x, pt.y, pendingLibraryAsset);
      placingKind = null;
      pendingLibraryAsset = null;
      canvas.style.cursor = "default";
      selectStroke(stroke);
      notifySceneChanged();
      return;
    }

    if (selectedStroke) {
      const corner = handleAtPoint(selectedStroke, pt.x, pt.y);
      if (corner) {
        dragState = {
          mode: "resize", stroke: selectedStroke, corner, startX: pt.x, startY: pt.y,
          orig: { ...boundingBoxOf(selectedStroke) },
        };
        return;
      }
    }

    const hit = strokeAtPoint(pt.x, pt.y);
    if (hit) {
      selectStroke(hit);
      dragState = { mode: "move", stroke: hit, startX: pt.x, startY: pt.y };
    } else {
      selectStroke(null);
    }
  });

  window.addEventListener("mousemove", (evt) => {
    if (!dragState) return;
    const pt = canvasSpaceFromEvent(evt);
    const dx = pt.x - dragState.startX;
    const dy = pt.y - dragState.startY;

    if (dragState.mode === "move") {
      moveStroke(dragState.stroke, dx, dy);
      dragState.startX = pt.x;
      dragState.startY = pt.y;
      redraw();
    } else if (dragState.mode === "resize") {
      resizeStroke(dragState.stroke, dragState.corner, dragState.orig, dx, dy);
      redraw();
    }
  });

  window.addEventListener("mouseup", () => {
    if (dragState) {
      dragState = null;
      notifySceneChanged();
    }
  });

  canvas.addEventListener("dblclick", (evt) => {
    const pt = canvasSpaceFromEvent(evt);
    const hit = strokeAtPoint(pt.x, pt.y);
    if (hit && hit.kind === "text") {
      selectStroke(hit);
      beginInlineTextEdit(hit);
    }
  });

  // --- Édition de texte inline (Phase 5) -----------------------------------
  //
  // Le canvas ne peut pas éditer du texte nativement : on superpose un
  // <textarea> HTML positionné exactement sur la boîte englobante de
  // l'élément (conversion espace canvas réel -> espace écran, inverse de
  // canvasSpaceFromEvent), pré-rempli avec le texte actuel. Validé sur
  // Entrée ou perte de focus ; Échap annule. Le stroke original reste cadré
  // sur son ancre (points[0]) — seul stroke.text change, la position ne
  // bouge pas même si la nouvelle longueur de texte change la largeur
  // réelle du tracé.
  let activeInlineEditor = null;

  function beginInlineTextEdit(stroke) {
    if (activeInlineEditor) commitInlineTextEdit();

    const rect = canvas.getBoundingClientRect();
    const scaleX = rect.width / CANVAS_WIDTH;
    const scaleY = rect.height / CANVAS_HEIGHT;
    const box = boundingBoxOf(stroke);

    const textarea = document.createElement("textarea");
    textarea.value = stroke.text;
    textarea.style.position = "fixed";
    textarea.style.left = `${rect.left + (box.x - 10) * scaleX}px`;
    textarea.style.top = `${rect.top + (box.y - 10) * scaleY}px`;
    textarea.style.width = `${Math.max(80, (box.w + 20) * scaleX)}px`;
    textarea.style.height = `${Math.max(30, (box.h + 20) * scaleY)}px`;
    textarea.style.font = "16px sans-serif";
    textarea.style.color = stroke.color;
    textarea.style.background = "rgba(255,255,255,0.95)";
    textarea.style.border = "2px solid #2f7bff";
    textarea.style.zIndex = "1000";
    textarea.style.resize = "none";
    textarea.style.padding = "2px 4px";

    textarea.addEventListener("keydown", (evt) => {
      if (evt.key === "Enter" && !evt.shiftKey) {
        evt.preventDefault();
        commitInlineTextEdit();
      } else if (evt.key === "Escape") {
        evt.preventDefault();
        cancelInlineTextEdit();
      }
    });
    textarea.addEventListener("blur", () => commitInlineTextEdit());

    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    activeInlineEditor = { textarea, stroke };
  }

  function commitInlineTextEdit() {
    if (!activeInlineEditor) return;
    const { textarea, stroke } = activeInlineEditor;
    activeInlineEditor = null; // avant removeChild : blur ne doit pas re-déclencher un commit
    const newText = textarea.value.trim();
    textarea.remove();
    if (newText && newText !== stroke.text) {
      stroke.text = newText;
      invalidateStrokeRenderCache(stroke);
      redraw();
      notifySceneChanged();
    } else {
      redraw();
    }
  }

  function cancelInlineTextEdit() {
    if (!activeInlineEditor) return;
    const { textarea } = activeInlineEditor;
    activeInlineEditor = null;
    textarea.remove();
  }

  // --- Manipulation des strokes --------------------------------------------

  function moveStroke(stroke, dx, dy) {
    if (stroke.kind === "shape") {
      for (const p of stroke.points) { p.x += dx; p.y += dy; }
    } else {
      stroke.points[0].x += dx;
      stroke.points[0].y += dy;
    }
    invalidateStrokeRenderCache(stroke);
  }

  const MIN_SIZE = 20;

  function resizeStroke(stroke, corner, orig, dx, dy) {
    let { x, y, w, h } = orig;
    if (corner === "se") { w = orig.w + dx; h = orig.h + dy; }
    else if (corner === "sw") { x = orig.x + dx; w = orig.w - dx; h = orig.h + dy; }
    else if (corner === "ne") { y = orig.y + dy; w = orig.w + dx; h = orig.h - dy; }
    else if (corner === "nw") { x = orig.x + dx; y = orig.y + dy; w = orig.w - dx; h = orig.h - dy; }

    w = Math.max(MIN_SIZE, w);
    h = Math.max(MIN_SIZE, h);

    stroke.points[0].x = x;
    stroke.points[0].y = y;
    stroke.width = w;
    if (stroke.kind === "image" || stroke.kind === "diagram") {
      stroke.height = h;
    }
    invalidateStrokeRenderCache(stroke);
  }

  function _addTextStrokeAt(x, y, text) {
    const stroke = {
      points: [{ x, y }],
      color: defaultTextColorForTheme(editorThemeId),
      width: 90.0,
      kind: "text",
      text: text,
      height: 0.0,
      start_sec: 0.0,
      end_sec: 0.0,
      image_data: "",
    };
    editorScene.strokes.push(stroke);
    return stroke;
  }

  function _addImageStrokeAt(x, y, dataUri) {
    const stroke = {
      points: [{ x, y }],
      color: "",
      width: 400.0,
      kind: "image",
      text: "",
      height: 240.0,
      start_sec: 0.0,
      end_sec: 0.0,
      image_data: dataUri,
    };
    stroke._imageReady = false;
    const img = new Image();
    img.onload = () => { stroke._imageReady = true; redraw(); };
    img.onerror = () => { stroke._imageReady = true; };
    img.src = dataUri;
    stroke._imageEl = img;
    editorScene.strokes.push(stroke);
    return stroke;
  }

  // Doit rester synchronisé avec ICON_SIZE dans app/scenes/schema.py.
  const ICON_SIZE = 220.0;

  function _addIconStrokeAt(x, y, iconName) {
    const palette = (editorTheme && editorTheme.palette) || ["#ffffff"];
    const stroke = {
      points: [{ x, y }],
      color: palette[0],
      width: ICON_SIZE,
      kind: "icon",
      text: iconName,
      height: 0.0,
      start_sec: 0.0,
      end_sec: 0.0,
      image_data: "",
    };
    editorScene.strokes.push(stroke);
    return stroke;
  }

  // Doit rester cohérent avec ICON_SIZE : même taille par défaut qu'un
  // icône (220px de large), pas de raison qu'un élément de bibliothèque
  // apparaisse visuellement plus petit/grand. La hauteur suit l'aspect
  // natif de l'élément enregistré (voir asset.native_height), jamais
  // déformée. Contrairement à icon/image/diagram, "shape" n'est PAS
  // redimensionnable après coup (voir isResizable ci-dessous — pas de
  // notion de "largeur" séparée du tracé lui-même pour ce kind) : cette
  // taille de placement est donc définitive, même limitation que pour
  // n'importe quel autre stroke "shape" déjà vectorisé (diagramme généré
  // par le LLM par exemple), pas une régression introduite ici.
  const LIBRARY_DEFAULT_WIDTH = 220.0;

  function _addLibraryAssetStrokeAt(x, y, asset) {
    const scale = LIBRARY_DEFAULT_WIDTH / window.Library.LIBRARY_NATIVE_WIDTH;
    const points = window.Library.assetToPoints(asset, x, y, LIBRARY_DEFAULT_WIDTH);
    const stroke = {
      points, color: asset.color, width: LIBRARY_DEFAULT_WIDTH,
      kind: asset.kind, text: "", height: asset.native_height * scale,
      start_sec: 0.0, end_sec: 0.0, image_data: "",
    };
    editorScene.strokes.push(stroke);
    return stroke;
  }

  function deleteSelected() {
    if (!selectedStroke || !editorScene) return;
    const idx = editorScene.strokes.indexOf(selectedStroke);
    if (idx === -1) return;
    editorScene.strokes.splice(idx, 1);
    selectedStroke = null;
    redraw();
    if (onSelectionChange) onSelectionChange(null);
    notifySceneChanged();
  }

  // --- API publique ---------------------------------------------------------

  window.EditorCanvas = {
    loadScene(scene, themeId, mobileLayout) {
      setCanvasSize(mobileLayout);
      editorScene = scene;
      editorThemeId = themeId;
      editorTheme = window.getTheme(themeId);
      selectedStroke = null;
      for (const stroke of editorScene.strokes || []) {
        invalidateStrokeRenderCache(stroke);
        if (stroke.kind === "image" && stroke.image_data) {
          stroke._imageReady = false;
          const img = new Image();
          img.onload = () => { stroke._imageReady = true; redraw(); };
          img.onerror = () => { stroke._imageReady = true; };
          img.src = stroke.image_data;
          stroke._imageEl = img;
        }
      }
      redraw();
    },

    redraw,

    getScene() {
      return editorScene;
    },

    getSelectedStroke() {
      return selectedStroke;
    },

    selectStroke,

    deleteSelected,

    // Place le prochain clic sur le canvas comme position d'un nouvel
    // élément texte/image (voir Phase 4 — bouton "Ajouter du texte"/
    // "Insérer une image").
    startPlacingNewText() {
      placingKind = "text";
      canvas.style.cursor = "crosshair";
    },
    startPlacingNewImage(dataUri) {
      placingKind = "image";
      pendingImageData = dataUri;
      canvas.style.cursor = "crosshair";
    },
    // Bibliothèque d'icônes (voir editor.js) : nom parmi
    // Object.keys(window.ICON_PATHS), déjà chargé via icon_paths.js.
    startPlacingNewIcon(iconName) {
      placingKind = "icon";
      pendingIconName = iconName;
      canvas.style.cursor = "crosshair";
    },
    // Bibliothèque personnelle (Tâche 6, voir editor.js/library.js) : asset
    // = un LibraryAsset renvoyé par Api.list_library_assets.
    startPlacingNewLibraryAsset(asset) {
      placingKind = "library";
      pendingLibraryAsset = asset;
      canvas.style.cursor = "crosshair";
    },
    cancelPlacing() {
      placingKind = null;
      pendingImageData = null;
      pendingIconName = null;
      pendingLibraryAsset = null;
      canvas.style.cursor = "default";
    },

    // Dessine une icône à taille de vignette sur un canvas fourni par
    // l'appelant (bibliothèque d'icônes, editor.js) — même outil
    // craie/feutre que le canvas principal, pour un aperçu fidèle.
    drawIconThumbnail(targetCanvas, iconName, themeId) {
      const thumbCtx = targetCanvas.getContext("2d");
      const theme = window.getTheme(themeId);
      const size = Math.min(targetCanvas.width, targetCanvas.height) * 0.7;
      const x = (targetCanvas.width - size) / 2;
      const y = (targetCanvas.height - size) / 2;
      const points = window.iconToPoints(iconName, x, y, size);
      const stroke = { points, color: (theme.palette && theme.palette[0]) || "#333", width: size, kind: "icon", text: iconName, _lastDrawnCount: 0 };
      thumbCtx.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
      window.TOOLS[theme.tool](thumbCtx, stroke, 1);
    },

    // Bibliothèque personnelle (Tâche 6) : même principe que
    // drawIconThumbnail, mais à partir d'un LibraryAsset (points déjà
    // normalisés, voir library.js::assetToPoints) plutôt qu'un nom
    // d'icône du socle fixe. Centré verticalement en tenant compte de
    // l'aspect natif réel (asset.native_height, peut différer de la
    // largeur — un tracé n'est pas forcément carré comme une icône).
    drawLibraryAssetThumbnail(targetCanvas, asset, themeId) {
      const thumbCtx = targetCanvas.getContext("2d");
      const theme = window.getTheme(themeId);
      const size = Math.min(targetCanvas.width, targetCanvas.height) * 0.7;
      const actualHeight = size * (asset.native_height / window.Library.LIBRARY_NATIVE_WIDTH);
      const x = (targetCanvas.width - size) / 2;
      const y = (targetCanvas.height - actualHeight) / 2;
      const points = window.Library.assetToPoints(asset, x, y, size);
      const stroke = { points, color: asset.color || (theme.palette && theme.palette[0]) || "#333", width: size, kind: asset.kind, _lastDrawnCount: 0 };
      thumbCtx.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
      window.TOOLS[theme.tool](thumbCtx, stroke, 1);
    },

    // Bibliothèque personnelle (Tâche 6) : renvoie {kind, color, points,
    // bbox} pour le stroke actuellement sélectionné, ou null s'il n'est
    // pas éligible (voir LIBRARY_ELIGIBLE_KINDS côté Python — seul "shape"
    // est accepté, un texte/icône/image a une ancre séparée de son
    // contenu dessiné, incompatible avec ce stockage normalisé). bbox
    // recalculée ici (pas stroke.width/height, pas fiables pour "shape",
    // voir boundingBoxOf) pour que la normalisation côté Python parte
    // d'une boîte englobante réelle du tracé.
    getSelectedStrokeForLibrary() {
      if (!selectedStroke || selectedStroke.kind !== "shape") return null;
      const box = boundingBoxOf(selectedStroke);
      return {
        kind: selectedStroke.kind,
        color: selectedStroke.color,
        points: selectedStroke.points.map((p) => ({ x: p.x, y: p.y, penUp: !!p.penUp })),
        bbox: { x: box.x, y: box.y, w: box.w, h: box.h },
      };
    },

    // Notifie le changement (texte édité, couleur changée...) et
    // redessine — utilisé par le panneau de propriétés (editor.js).
    onStrokeMutated(stroke) {
      invalidateStrokeRenderCache(stroke);
      redraw();
      notifySceneChanged();
    },

    boundingBoxOf,

    setOnSelectionChange(cb) { onSelectionChange = cb; },
    setOnSceneChanged(cb) { onSceneChanged = cb; },

    // Renvoie les strokes de la scène courante dans le format attendu par
    // Api.update_scene_strokes — dépouillés de tout champ de cache "_..."
    // (jamais persisté, voir en-tête de fichier).
    serializeStrokesForSave() {
      if (!editorScene) return [];
      return editorScene.strokes.map((s) => ({
        points: s.points.map((p) => ({ x: p.x, y: p.y, penUp: !!p.penUp })),
        color: s.color,
        width: s.width,
        kind: s.kind,
        text: s.text || "",
        height: s.height || 0.0,
        start_sec: s.start_sec || 0.0,
        end_sec: s.end_sec || 0.0,
        image_data: s.image_data || "",
        // Paramètres d'un verbe de la grammaire de mouvement (ex: "orbit",
        // voir animations.js) — l'éditeur n'a pas encore d'interface pour
        // les MODIFIER (pas de panneau de propriétés pour les éléments
        // animés), mais doit au moins les préserver telles quelles à
        // chaque sauvegarde, plutôt que les perdre silencieusement dès
        // qu'un autre élément de la même scène est édité.
        params: s.params || {},
      }));
    },
  };
})();
