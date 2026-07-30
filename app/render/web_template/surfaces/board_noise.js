// Utilitaire partagé par les surfaces "tableau" : génère une texture de
// grain, mise en cache dans window._boardTextureCache (accessible aussi
// par le système d'animation — voir animations.js — pour "effacer"
// localement une zone en la redessinant depuis ce cache, sans toucher au
// reste du tableau déjà tracé).
window._boardTextureCache = {};

window.getCachedBoardTexture = function getCachedBoardTexture(key, width, height, baseColor) {
  const cached = window._boardTextureCache[key];
  if (cached && cached.width === width && cached.height === height) return cached;
  const canvas = window.buildBoardNoise(width, height, baseColor);
  window._boardTextureCache[key] = canvas;
  return canvas;
};

window.buildBoardNoise = function buildBoardNoise(width, height, baseColor) {
  const off = document.createElement("canvas");
  off.width = width;
  off.height = height;
  const octx = off.getContext("2d");
  octx.fillStyle = baseColor;
  octx.fillRect(0, 0, width, height);

  // Amplitude volontairement faible : un grain trop marqué consomme du
  // débit vidéo (bruit haute fréquence coûteux à compresser en H.264) au
  // détriment de la lisibilité du texte à la craie, qui doit rester la
  // priorité visuelle.
  const imageData = octx.getImageData(0, 0, width, height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const grain = (Math.random() - 0.5) * 5;
    data[i] = Math.min(255, Math.max(0, data[i] + grain));
    data[i + 1] = Math.min(255, Math.max(0, data[i + 1] + grain));
    data[i + 2] = Math.min(255, Math.max(0, data[i + 2] + grain));
  }
  octx.putImageData(imageData, 0, 0);
  return off;
};
