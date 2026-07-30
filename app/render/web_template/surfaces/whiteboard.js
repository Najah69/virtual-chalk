window.SURFACES = window.SURFACES || {};

window.SURFACES.whiteboard = function drawSurface(ctx, width, height) {
  // Mis en cache comme les autres surfaces (même sans grain visible) pour
  // que le système d'animation puisse "effacer" une zone localement en
  // redessinant depuis ce cache — voir animations.js.
  const tex = window.getCachedBoardTexture("whiteboard", width, height, "#fafafa");
  ctx.drawImage(tex, 0, 0);
  // TODO: léger reflet/brillance pour simuler la surface laquée
};
