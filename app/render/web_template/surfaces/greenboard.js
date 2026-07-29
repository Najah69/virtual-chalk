window.SURFACES = window.SURFACES || {};

window.SURFACES.greenboard = function drawSurface(ctx, width, height) {
  ctx.fillStyle = "#1f4d3a";
  ctx.fillRect(0, 0, width, height);
  // TODO: bruit/grain procédural + légères traces d'effaçage pour le réalisme
};
