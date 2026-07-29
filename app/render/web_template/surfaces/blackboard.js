window.SURFACES = window.SURFACES || {};

window.SURFACES.blackboard = function drawSurface(ctx, width, height) {
  ctx.fillStyle = "#161616";
  ctx.fillRect(0, 0, width, height);
  // TODO: bruit/grain procédural + légères traces d'effaçage pour le réalisme
};
