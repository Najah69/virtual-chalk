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

function _drawWoodFrame(ctx, width, height, frameWidth) {
  const base = "#8a5a34";
  const dark = "#6b4423";
  const light = "#a9744a";
  const bevel = "#4a2d15";

  ctx.save();
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, width, height);

  // Bandes de grain (variation de teinte) horizontales/verticales au
  // hasard — suggère une texture de bois sans reproduire un vrai motif de
  // veines (inutile à l'échelle/lisibilité d'une vidéo). Dessinées sur
  // tout le canvas puis recouvertes au centre par la zone craie : plus
  // simple qu'un clip, coût négligeable (texture construite une seule
  // fois par vidéo, pas par frame).
  ctx.globalAlpha = 0.35;
  for (let i = 0; i < 14; i++) {
    ctx.fillStyle = Math.random() > 0.5 ? dark : light;
    if (Math.random() > 0.5) {
      ctx.fillRect(0, Math.random() * height, width, 1 + Math.random() * 2);
    } else {
      ctx.fillRect(Math.random() * width, 0, 1 + Math.random() * 2, height);
    }
  }
  ctx.globalAlpha = 1;

  // Biseau intérieur : séparation visible entre le cadre et le tableau,
  // comme sur un vrai cadre en bois.
  const lineWidth = Math.max(2, frameWidth * 0.06);
  ctx.strokeStyle = bevel;
  ctx.lineWidth = lineWidth;
  ctx.strokeRect(
    frameWidth - lineWidth / 2, frameWidth - lineWidth / 2,
    width - 2 * frameWidth + lineWidth, height - 2 * frameWidth + lineWidth
  );
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
