window.TOOLS = window.TOOLS || {};

// Effet feutre Veleda : trait lisse et opaque, sans grain, léger effet
// d'encre qui "pool" en début de trait.
//
// Dessin INCRÉMENTAL comme pour la craie (voir tools/chalk.js) : ne
// redessine que le segment nouvellement révélé, pas tout le tracé depuis
// le début à chaque frame.
window.TOOLS.marker_veleda = function drawStroke(ctx, stroke, progress) {
  const path = stroke.points;
  // Le texte/icône utilise stroke.width comme taille, pas comme épaisseur
  // de trait (voir tools/chalk.js pour le même souci).
  const penWidth =
    stroke.kind === "text" ? Math.max(4, stroke.width * 0.16)
    : stroke.kind === "icon" ? Math.max(4, stroke.width * 0.07)
    : stroke.width;
  const visibleCount = Math.max(2, Math.floor(path.length * progress));
  const from = stroke._lastDrawnCount || 0;
  if (visibleCount <= from) return;

  ctx.save();
  ctx.strokeStyle = stroke.color;
  ctx.lineWidth = penWidth;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.globalAlpha = 0.95;

  ctx.beginPath();
  let penDown = false;
  const start = Math.max(0, from - 1); // se raccorde au trait déjà tracé
  for (let i = start; i < visibleCount; i++) {
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

  if (from === 0 && !path[0].penUp) {
    ctx.beginPath();
    ctx.arc(path[0].x, path[0].y, penWidth * 0.6, 0, Math.PI * 2);
    ctx.fillStyle = stroke.color;
    ctx.fill();
  }
  ctx.restore();
  stroke._lastDrawnCount = visibleCount;
};
