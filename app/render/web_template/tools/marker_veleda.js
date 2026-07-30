window.TOOLS = window.TOOLS || {};

// Effet feutre Veleda : trait lisse et opaque, sans grain, léger effet
// d'encre qui "pool" en début de trait.
window.TOOLS.marker_veleda = function drawStroke(ctx, stroke, progress) {
  const path = stroke.points;
  const visiblePoints = Math.max(2, Math.floor(path.length * progress));
  ctx.save();
  ctx.strokeStyle = stroke.color;
  ctx.lineWidth = stroke.width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.globalAlpha = 0.95;

  ctx.beginPath();
  ctx.moveTo(path[0].x, path[0].y);
  for (let i = 1; i < visiblePoints; i++) {
    ctx.lineTo(path[i].x, path[i].y);
  }
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(path[0].x, path[0].y, stroke.width * 0.6, 0, Math.PI * 2);
  ctx.fillStyle = stroke.color;
  ctx.fill();
  ctx.restore();
};
