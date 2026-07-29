window.TOOLS = window.TOOLS || {};

// Effet feutre Veleda : trait lisse et opaque, sans grain, léger effet
// d'encre qui "pool" en début/fin de trait.
window.TOOLS.marker_veleda = function drawStroke(ctx, path, color, width, progress) {
  const visiblePoints = Math.max(2, Math.floor(path.length * progress));
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.globalAlpha = 0.95;

  ctx.beginPath();
  ctx.moveTo(path[0].x, path[0].y);
  for (let i = 1; i < visiblePoints; i++) {
    ctx.lineTo(path[i].x, path[i].y);
  }
  ctx.stroke();

  // Léger "pool" d'encre au point de départ
  ctx.beginPath();
  ctx.arc(path[0].x, path[0].y, width * 0.6, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.restore();
};
