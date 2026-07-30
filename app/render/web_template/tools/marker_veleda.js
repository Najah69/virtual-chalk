window.TOOLS = window.TOOLS || {};

// Effet feutre Veleda : trait lisse et opaque, sans grain, léger effet
// d'encre qui "pool" en début de trait.
window.TOOLS.marker_veleda = function drawStroke(ctx, stroke, progress) {
  const path = stroke.points;
  // Le texte utilise stroke.width comme taille de police, pas comme
  // épaisseur de trait (voir tools/chalk.js pour le même souci).
  const penWidth = stroke.kind === "text" ? Math.max(3, stroke.width * 0.1) : stroke.width;
  const visiblePoints = Math.max(2, Math.floor(path.length * progress));
  ctx.save();
  ctx.strokeStyle = stroke.color;
  ctx.lineWidth = penWidth;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.globalAlpha = 0.95;

  ctx.beginPath();
  let penDown = false;
  for (let i = 0; i < visiblePoints; i++) {
    const p = path[i];
    if (p.penUp) {
      penDown = false;
      continue;
    }
    if (!penDown) {
      ctx.moveTo(p.x, p.y);
      penDown = true;
    } else {
      ctx.lineTo(p.x, p.y);
    }
  }
  ctx.stroke();

  if (!path[0].penUp) {
    ctx.beginPath();
    ctx.arc(path[0].x, path[0].y, penWidth * 0.6, 0, Math.PI * 2);
    ctx.fillStyle = stroke.color;
    ctx.fill();
  }
  ctx.restore();
};
