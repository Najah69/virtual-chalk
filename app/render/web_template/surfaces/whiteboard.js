window.SURFACES = window.SURFACES || {};

window.SURFACES.whiteboard = function drawSurface(ctx, width, height) {
  ctx.fillStyle = "#fafafa";
  ctx.fillRect(0, 0, width, height);
  // TODO: léger reflet/brillance pour simuler la surface laquée
};
