window.SURFACES = window.SURFACES || {};

window.SURFACES.greenboard = function drawSurface(ctx, width, height) {
  // Cadre en bois + tableau vert inséré à l'intérieur (voir board_noise.js
  // ::buildFramedBoardNoise) — contrairement au grain plat des autres
  // surfaces, occupant tout le canvas bord à bord.
  const tex = window.getCachedBoardTexture(
    "greenboard", width, height, "#1f4d3a", window.buildFramedBoardNoise
  );
  ctx.drawImage(tex, 0, 0);
};
