// Éléments réellement animés (pas juste progressivement révélés puis
// figés comme le texte/les icônes) : redessinés à CHAQUE frame tant
// qu'actifs. Contrairement au reste du moteur (qui n'efface jamais le
// canvas, ne fait qu'accumuler de la craie), une animation doit "effacer"
// sa propre zone à chaque frame puisque ses éléments bougent — elle le
// fait en redessinant depuis le cache de texture du tableau
// (window._boardTextureCache, voir surfaces/board_noise.js), jamais en
// vidant tout le canvas, pour ne jamais toucher au reste du dessin déjà
// posé ailleurs sur le tableau.
//
// Une fois sa fenêtre de temps passée, l'animation cesse d'être appelée
// (voir index.html) : sa dernière image reste alors figée en permanence,
// comme tout le reste — cohérent avec le principe "la craie posée ne
// bouge plus" du moteur.
window.ANIMATIONS = window.ANIMATIONS || {};

window.ANIMATIONS.falling_rain = function (ctx, stroke, t, boardTexture, toolName) {
  const x = stroke.points[0].x;
  const y = stroke.points[0].y;
  const size = stroke.width;
  const regionX = x - 14;
  const regionY = y - 14;
  const regionW = size + 28;
  const regionH = size * 1.7 + 28;

  if (boardTexture) {
    ctx.drawImage(boardTexture, regionX, regionY, regionW, regionH, regionX, regionY, regionW, regionH);
  }

  // Nuage statique : texture craie précalculée une seule fois (sur le
  // stroke), pas recalculée à chaque frame — seules les gouttes bougent.
  if (!stroke._cloudSprite) {
    stroke._cloudSprite = window.renderIconSprite("cloud", size, stroke.color, toolName);
  }
  ctx.drawImage(stroke._cloudSprite, x, y);

  const dropCount = 5;
  const speed = 0.6; // boucles par seconde
  ctx.save();
  ctx.fillStyle = stroke.color;
  for (let i = 0; i < dropCount; i++) {
    const phase = (t * speed + i / dropCount) % 1;
    const dropX = x + size * (0.18 + 0.64 * (i / dropCount));
    const dropY = y + size * 0.62 + phase * size * 0.85;
    ctx.globalAlpha = Math.max(0, 0.85 - phase * 0.55);
    ctx.beginPath();
    ctx.ellipse(dropX, dropY, size * 0.018, size * 0.045, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
};
