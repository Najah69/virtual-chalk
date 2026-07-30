window.SURFACES = window.SURFACES || {};

window.SURFACES.greenboard = function drawSurface(ctx, width, height) {
  const tex = window.getCachedBoardTexture("greenboard", width, height, "#1f4d3a");
  ctx.drawImage(tex, 0, 0);
};
