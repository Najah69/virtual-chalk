window.SURFACES = window.SURFACES || {};

let _blackboardNoise = null;

window.SURFACES.blackboard = function drawSurface(ctx, width, height) {
  if (!_blackboardNoise || _blackboardNoise.width !== width || _blackboardNoise.height !== height) {
    _blackboardNoise = window.buildBoardNoise(width, height, "#161616");
  }
  ctx.drawImage(_blackboardNoise, 0, 0);
};
