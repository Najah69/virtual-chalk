window.SURFACES = window.SURFACES || {};

window.SURFACES.blackboard = function drawSurface(ctx, width, height) {
  const tex = window.getCachedBoardTexture("blackboard", width, height, "#161616");
  ctx.drawImage(tex, 0, 0);
};
