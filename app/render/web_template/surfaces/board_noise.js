// Utilitaire partagé par les surfaces "tableau" : génère une texture de
// grain, mise en cache dans window._boardTextureCache (accessible aussi
// par le système d'animation — voir animations.js — pour "effacer"
// localement une zone en la redessinant depuis ce cache, sans toucher au
// reste du tableau déjà tracé). La clé de cache DOIT rester le nom exact
// de la surface (ex: "greenboard", voir themes.js) : c'est cette même
// clé que index.html relit pour l'effacement local des animations —
// changer la fonction qui construit la texture (grain plat vs. cadre en
// bois, voir buildFramedBoardNoise) ne doit jamais changer la clé.
window._boardTextureCache = {};

window.getCachedBoardTexture = function getCachedBoardTexture(key, width, height, baseColor, builder) {
  const cached = window._boardTextureCache[key];
  if (cached && cached.width === width && cached.height === height) return cached;
  const build = builder || window.buildBoardNoise;
  const canvas = build(width, height, baseColor);
  window._boardTextureCache[key] = canvas;
  return canvas;
};

function _fineGrain(ctx, width, height, amplitude) {
  // Amplitude volontairement faible : un grain trop marqué consomme du
  // débit vidéo (bruit haute fréquence coûteux à compresser en H.264) au
  // détriment de la lisibilité du texte à la craie, qui doit rester la
  // priorité visuelle.
  const imageData = ctx.getImageData(0, 0, width, height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const grain = (Math.random() - 0.5) * amplitude;
    data[i] = Math.min(255, Math.max(0, data[i] + grain));
    data[i + 1] = Math.min(255, Math.max(0, data[i + 1] + grain));
    data[i + 2] = Math.min(255, Math.max(0, data[i + 2] + grain));
  }
  ctx.putImageData(imageData, 0, 0);
}

function _hexToRgb(hex) {
  const m = hex.replace("#", "");
  return {
    r: parseInt(m.substring(0, 2), 16),
    g: parseInt(m.substring(2, 4), 16),
    b: parseInt(m.substring(4, 6), 16),
  };
}

// Grandes taches douces (dégradés radiaux, faible opacité) façon traces
// de chiffon/éponge — contrairement au grain fin (bruit haute fréquence,
// pixel à pixel), ce sont de larges zones lisses : beaucoup moins
// coûteuses à compresser en H.264 qu'un bruit fin équivalent en surface,
// et c'est ce qui donne l'impression "tableau réellement essuyé" plutôt
// qu'un aplat de couleur uniforme + neige TV.
function _addSoftClouds(ctx, width, height, baseColor) {
  const rgb = _hexToRgb(baseColor);
  const cloudCount = 10 + Math.floor(Math.random() * 8);
  ctx.save();
  for (let i = 0; i < cloudCount; i++) {
    const cx = Math.random() * width;
    const cy = Math.random() * height;
    const r = (0.12 + Math.random() * 0.22) * Math.max(width, height);
    const squash = 0.5 + Math.random() * 0.5;
    const alpha = 0.03 + Math.random() * 0.05;
    // Le dégradé et la forme remplie sont définis dans le MÊME espace
    // transformé (translate + rotate + scale) plutôt qu'un dégradé
    // circulaire non déformé rempli dans une ellipse aplatie/pivotée :
    // sans ça, le rayon du dégradé (calibré pour un cercle) dépasse le
    // petit axe de l'ellipse avant de s'estomper à alpha=0, ce qui laisse
    // un bord dur visible (constaté à l'écran) au lieu d'un fondu propre.
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Math.random() * Math.PI);
    ctx.scale(1, squash);
    const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
    grad.addColorStop(0, `rgba(${rgb.r + 70}, ${rgb.g + 70}, ${rgb.b + 70}, ${alpha})`);
    grad.addColorStop(1, `rgba(${rgb.r + 70}, ${rgb.g + 70}, ${rgb.b + 70}, 0)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
  ctx.restore();
}

window.buildBoardNoise = function buildBoardNoise(width, height, baseColor) {
  const off = document.createElement("canvas");
  off.width = width;
  off.height = height;
  const octx = off.getContext("2d");
  octx.fillStyle = baseColor;
  octx.fillRect(0, 0, width, height);
  _addSoftClouds(octx, width, height, baseColor);
  _fineGrain(octx, width, height, 4);
  return off;
};

// Largeur du cadre en bois, en fraction de la plus petite dimension du
// canvas (identique en portrait/paysage puisque les deux formats
// partagent la même dimension la plus petite, 1080px — voir
// app/scenes/schema.py::CANVAS_WIDTH_PORTRAIT/HEIGHT_PORTRAIT). DOIT
// rester synchronisé avec BOARD_FRAME_RATIO dans app/scenes/schema.py,
// qui l'utilise pour garder les éléments placés par le LLM à l'intérieur
// de la zone craie (jamais sous le cadre).
window.BOARD_FRAME_RATIO = 0.035;

// Région d'un seul montant du cadre, coupée en onglet à 45° à chaque coin
// (comme un vrai cadre assemblé) plutôt qu'un simple rectangle — sans ça,
// les 4 montants se chevauchent aux coins et aucune ligne de joint n'est
// possible, ce qui est une bonne partie de ce qui fait "autocollant plat"
// plutôt que "cadre construit".
function _miteredSidePath(ctx, width, height, frameWidth, side) {
  ctx.beginPath();
  if (side === "top") {
    ctx.moveTo(0, 0); ctx.lineTo(width, 0);
    ctx.lineTo(width - frameWidth, frameWidth); ctx.lineTo(frameWidth, frameWidth);
  } else if (side === "bottom") {
    ctx.moveTo(0, height); ctx.lineTo(width, height);
    ctx.lineTo(width - frameWidth, height - frameWidth); ctx.lineTo(frameWidth, height - frameWidth);
  } else if (side === "left") {
    ctx.moveTo(0, 0); ctx.lineTo(frameWidth, frameWidth);
    ctx.lineTo(frameWidth, height - frameWidth); ctx.lineTo(0, height);
  } else {
    ctx.moveTo(width, 0); ctx.lineTo(width, height);
    ctx.lineTo(width - frameWidth, height - frameWidth); ctx.lineTo(width - frameWidth, frameWidth);
  }
  ctx.closePath();
}

// Traits de veine longs et LÉGÈREMENT ONDULÉS (courbe quadratique, pas des
// droites) courant le long de l'axe du montant — c'est cette ondulation,
// absente de l'ancienne version (droites 1-2px dans n'importe quel sens),
// qui distingue une vraie texture de bois d'un simple hachurage aléatoire.
// `horizontal` = le sens du fil (true pour les traverses haut/bas, false
// pour les montants gauche/droite) ; les couleurs alternent clair/foncé et
// varient en opacité/épaisseur pour éviter tout effet de motif répété.
function _woodGrainStreaks(ctx, x, y, w, h, horizontal, light, dark) {
  const length = horizontal ? w : h;
  const thickness = horizontal ? h : w;
  const count = Math.max(6, Math.round(length / (thickness * 1.8)));
  for (let i = 0; i < count; i++) {
    const t = (i + 0.5) / count + (Math.random() - 0.5) * (1 / count) * 0.7;
    ctx.strokeStyle = Math.random() > 0.4 ? dark : light;
    ctx.globalAlpha = 0.10 + Math.random() * 0.18;
    ctx.lineWidth = Math.max(0.6, thickness * (0.03 + Math.random() * 0.06));
    ctx.beginPath();
    if (horizontal) {
      const yPos = y + t * h;
      const wobble = h * 0.35;
      ctx.moveTo(x, yPos + (Math.random() - 0.5) * wobble);
      ctx.quadraticCurveTo(
        x + w * 0.5, yPos + (Math.random() - 0.5) * wobble,
        x + w, yPos + (Math.random() - 0.5) * wobble
      );
    } else {
      const xPos = x + t * w;
      const wobble = w * 0.35;
      ctx.moveTo(xPos + (Math.random() - 0.5) * wobble, y);
      ctx.quadraticCurveTo(
        xPos + (Math.random() - 0.5) * wobble, y + h * 0.5,
        xPos + (Math.random() - 0.5) * wobble, y + h
      );
    }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function _drawWoodFrame(ctx, width, height, frameWidth) {
  // Palette calibrée sur la photo de référence (moyennes de pixels réels,
  // pas choisies à l'oeil) : un bois beaucoup plus roux/saturé qu'un brun
  // neutre — c'est en grande partie ce qui faisait "plastique" avant.
  const base = "#6e3a0f";
  const light = "#a8734b";
  const dark = "#462302";
  const groove = "#140a03";
  // Fin liseré clair juste avant la rainure sombre — repéré sur la photo
  // de référence (un pixel-scan de la zone de jonction cadre/tableau y
  // montre un pic de luminosité net juste avant la ligne sombre, signe
  // d'une feuillure biseautée qui accroche la lumière plutôt qu'une
  // simple marche d'escalier) : sans ce liseré, la transition cadre ->
  // tableau reste plate même avec un dégradé sur le montant.
  const bevelHighlight = "#c99a72";

  ctx.save();

  // Fond de sécurité : les 4 montants en onglet ci-dessous se rejoignent
  // exactement aux coins, mais un aplat dessous évite tout liseré blanc
  // d'arrondi de sous-pixel entre deux régions adjacentes.
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, width, height);

  // Chaque montant : dégradé PERPENDICULAIRE au fil (à travers son
  // épaisseur, pas le long) — plus clair vers l'extérieur du cadre, plus
  // sombre vers l'intérieur (là où le tableau s'encastre). C'est ce
  // dégradé qui donne un profil légèrement bombé/biseauté au lieu d'un
  // aplat de couleur uniforme ; `outer` fixe le point de départ (bord
  // extérieur, clair) et le point d'arrivée (bord intérieur, sombre) du
  // dégradé pour chaque montant.
  const sides = [
    { name: "top", x: 0, y: 0, w: width, h: frameWidth, horizontal: true,
      outer: [0, 0, 0, frameWidth] },
    { name: "bottom", x: 0, y: height - frameWidth, w: width, h: frameWidth, horizontal: true,
      outer: [0, height, 0, height - frameWidth] },
    { name: "left", x: 0, y: 0, w: frameWidth, h: height, horizontal: false,
      outer: [0, 0, frameWidth, 0] },
    { name: "right", x: width - frameWidth, y: 0, w: frameWidth, h: height, horizontal: false,
      outer: [width, 0, width - frameWidth, 0] },
  ];

  for (const side of sides) {
    ctx.save();
    _miteredSidePath(ctx, width, height, frameWidth, side.name);
    ctx.clip();

    const grad = ctx.createLinearGradient(...side.outer);
    grad.addColorStop(0, light);
    grad.addColorStop(0.55, base);
    grad.addColorStop(1, dark);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);

    _woodGrainStreaks(ctx, side.x, side.y, side.w, side.h, side.horizontal, light, dark);

    ctx.restore();
  }

  // Joints d'onglet aux 4 coins (45°) — discrets mais présents sur un
  // vrai cadre assemblé, contrairement à une bordure de couleur unie sans
  // aucune séparation entre montants.
  ctx.strokeStyle = "rgba(25, 12, 4, 0.35)";
  ctx.lineWidth = Math.max(1, frameWidth * 0.015);
  ctx.beginPath();
  ctx.moveTo(0, 0); ctx.lineTo(frameWidth, frameWidth);
  ctx.moveTo(width, 0); ctx.lineTo(width - frameWidth, frameWidth);
  ctx.moveTo(0, height); ctx.lineTo(frameWidth, height - frameWidth);
  ctx.moveTo(width, height); ctx.lineTo(width - frameWidth, height - frameWidth);
  ctx.stroke();

  // Liseré clair juste avant la rainure (voir bevelHighlight ci-dessus) :
  // légèrement plus large et positionné juste à l'extérieur du trait
  // sombre, pour lire comme une arête biseautée qui accroche la lumière
  // plutôt qu'une deuxième ligne parallèle sans rapport avec la première.
  const grooveWidth = Math.max(3, frameWidth * 0.16);
  const highlightWidth = Math.max(2, frameWidth * 0.1);
  const highlightInset = frameWidth - grooveWidth - highlightWidth / 2;
  ctx.strokeStyle = bevelHighlight;
  ctx.globalAlpha = 0.55;
  ctx.lineWidth = highlightWidth;
  ctx.strokeRect(
    highlightInset, highlightInset,
    width - 2 * highlightInset, height - 2 * highlightInset
  );
  ctx.globalAlpha = 1;

  // Feuillure intérieure : le tableau est ENCASTRÉ dans le cadre, pas
  // simplement peint dessus — un trait large et sombre (pas un simple
  // filet 2px) pour suggérer une vraie rainure plutôt qu'une ligne de
  // séparation plate.
  ctx.strokeStyle = groove;
  ctx.globalAlpha = 0.85;
  ctx.lineWidth = grooveWidth;
  ctx.strokeRect(
    frameWidth - grooveWidth / 2, frameWidth - grooveWidth / 2,
    width - 2 * frameWidth + grooveWidth, height - 2 * frameWidth + grooveWidth
  );
  ctx.globalAlpha = 1;

  ctx.restore();
}

function _roundRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// Deux bâtons de craie statiques dans le coin bas-droit, comme sur la
// photo de référence — coin OPPOSÉ à l'ancre de la mascotte (bas-gauche,
// voir MASCOT_ANCHOR_FRACTION dans mascot.js) pour ne jamais se
// chevaucher avec elle. Fait partie du fond statique (comme le cadre),
// donc automatiquement respecté par le mécanisme d'effacement local des
// animations (qui redessine depuis ce même cache).
function _drawChalkSticks(ctx, width, height, frameWidth) {
  const stickLen = Math.min(width, height) * 0.06;
  const stickW = stickLen * 0.22;
  const baseX = width - frameWidth - stickLen * 1.3;
  const baseY = height - frameWidth - stickLen * 0.9;

  ctx.save();
  ctx.shadowColor = "rgba(0, 0, 0, 0.25)";
  ctx.shadowBlur = stickW * 0.6;
  ctx.shadowOffsetY = stickW * 0.15;
  ctx.fillStyle = "#f0ede3";
  ctx.strokeStyle = "#bdb69f";
  ctx.lineWidth = Math.max(1, stickW * 0.08);
  // Décalés en x ET en y (pas juste superposés verticalement) pour se lire
  // comme deux bâtons distincts plutôt qu'une seule forme mêlée.
  [
    { dx: -stickLen * 0.18, dy: 0, angle: -0.3 },
    { dx: stickLen * 0.2, dy: stickW * 1.7, angle: 0.32 },
  ].forEach(({ dx, dy, angle }) => {
    ctx.save();
    ctx.translate(baseX + dx, baseY + dy);
    ctx.rotate(angle);
    _roundRectPath(ctx, -stickLen / 2, -stickW / 2, stickLen, stickW, stickW * 0.42);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  });
  ctx.restore();
}

// Variante "encadrée" de buildBoardNoise — cadre en bois + zone craie
// (grain existant) insérée à l'intérieur, plutôt que le grain plat
// occupant tout le canvas bord à bord. La zone craie garde exactement les
// mêmes dimensions relatives que prévu côté Python (voir
// BOARD_FRAME_RATIO ci-dessus) : les éléments placés par le LLM restent
// dans cette zone, jamais sous le cadre.
window.buildFramedBoardNoise = function buildFramedBoardNoise(width, height, baseColor) {
  const off = document.createElement("canvas");
  off.width = width;
  off.height = height;
  const octx = off.getContext("2d");

  const frameWidth = Math.min(width, height) * window.BOARD_FRAME_RATIO;
  _drawWoodFrame(octx, width, height, frameWidth);

  const innerW = Math.round(width - 2 * frameWidth);
  const innerH = Math.round(height - 2 * frameWidth);
  const boardTex = window.buildBoardNoise(innerW, innerH, baseColor);
  octx.drawImage(boardTex, frameWidth, frameWidth);

  _drawChalkSticks(octx, width, height, frameWidth);

  return off;
};
