// Utilitaire partagé par les surfaces "tableau" : génère une texture de
// grain, mise en cache dans window._boardTextureCache (accessible aussi
// par le système d'animation — voir animations.js — pour "effacer"
// localement une zone en la redessinant depuis ce cache, sans toucher au
// reste du tableau déjà tracé). La clé de cache DOIT rester le nom exact
// de la surface (ex: "greenboard", voir themes.js) : c'est cette même
// clé que index.html relit pour l'effacement local des animations.
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

