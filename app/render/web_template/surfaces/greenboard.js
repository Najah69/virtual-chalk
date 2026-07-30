window.SURFACES = window.SURFACES || {};

let _greenboardNoise = null;

window.SURFACES.greenboard = function drawSurface(ctx, width, height) {
  if (!_greenboardNoise || _greenboardNoise.width !== width || _greenboardNoise.height !== height) {
    _greenboardNoise = window.buildBoardNoise(width, height, "#1f4d3a");
  }
  ctx.drawImage(_greenboardNoise, 0, 0);
};
