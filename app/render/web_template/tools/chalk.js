window.TOOLS = window.TOOLS || {};

// Effet craie : tamponne une texture de grain le long du tracé, avec une
// légère variation aléatoire d'opacité/rotation/taille à chaque tampon.
// `progress` (0..1) = portion du tracé déjà dessinée à l'instant courant.
window.TOOLS.chalk = function drawStroke(ctx, path, color, width, progress) {
  const visiblePoints = Math.max(2, Math.floor(path.length * progress));
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.globalAlpha = 0.85;

  for (let i = 1; i < visiblePoints; i++) {
    const a = path[i - 1];
    const b = path[i];
    const jitter = () => (Math.random() - 0.5) * width * 0.15;
    ctx.beginPath();
    ctx.moveTo(a.x + jitter(), a.y + jitter());
    ctx.lineTo(b.x + jitter(), b.y + jitter());
    ctx.globalAlpha = 0.7 + Math.random() * 0.25; // grain: opacité irrégulière
    ctx.stroke();
  }
  ctx.restore();
  // TODO: remplacer le trait ligne par un tampon de texture (chalk_textures/)
  // pour un rendu grainé véritablement photoréaliste.
};
