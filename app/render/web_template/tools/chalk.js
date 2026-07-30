window.TOOLS = window.TOOLS || {};

function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashSeed(stroke) {
  const str = JSON.stringify(stroke.points) + stroke.color + stroke.width + (stroke.text || "");
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// Précalcule des tampons de grain stables le long du tracé, une seule fois
// par stroke (mis en cache dessus). Régénérer le grain avec Math.random() à
// chaque frame ferait scintiller la portion déjà tracée d'une image à
// l'autre — la craie ne doit pas changer d'aspect une fois posée.
function chalkPrecompute(stroke) {
  const rng = mulberry32(hashSeed(stroke));
  const path = stroke.points;
  // Pour du texte, stroke.width est la taille de police (utilisée pour
  // positionner/dimensionner les lettres), pas l'épaisseur du trait de
  // craie — un trait de lettre doit rester fin, sans quoi les contours de
  // lettres deviennent illisibles (blob épais au lieu d'un tracé net).
  const penWidth = stroke.kind === "text" ? Math.max(4, stroke.width * 0.12) : stroke.width;
  const spacing = Math.max(1.2, penWidth * 0.6);
  const dabs = [];

  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1];
    const b = path[i];
    if (a.penUp || b.penUp) continue; // ne relie pas deux sous-tracés (lettres/boucles distinctes)
    const segLen = Math.hypot(b.x - a.x, b.y - a.y);
    const steps = Math.max(1, Math.round(segLen / spacing));
    for (let s = 0; s < steps; s++) {
      const frac = s / steps;
      const cx = a.x + (b.x - a.x) * frac;
      const cy = a.y + (b.y - a.y) * frac;
      const dotCount = 5 + Math.floor(rng() * 5);
      const dots = [];
      for (let d = 0; d < dotCount; d++) {
        const angle = rng() * Math.PI * 2;
        const r = rng() * penWidth * 0.5;
        dots.push({
          dx: Math.cos(angle) * r,
          dy: Math.sin(angle) * r,
          size: 0.4 + rng() * 1.1,
          alpha: 0.15 + rng() * 0.35,
        });
      }
      dabs.push({ x: cx, y: cy, dots });
    }
  }
  return dabs;
}

// Effet craie : tamponne un grain "stipple" (nuage de points minuscules,
// taille/opacité irrégulières) le long du tracé plutôt qu'un trait plein —
// c'est ce qui distingue une craie crédible d'un simple trait vectoriel.
window.TOOLS.chalk = function drawStroke(ctx, stroke, progress) {
  if (!stroke._chalkDabs) {
    stroke._chalkDabs = chalkPrecompute(stroke);
  }
  const dabs = stroke._chalkDabs;
  const visibleCount = Math.floor(dabs.length * progress);

  ctx.save();
  ctx.fillStyle = stroke.color;
  for (let i = 0; i < visibleCount; i++) {
    const dab = dabs[i];
    for (const dot of dab.dots) {
      ctx.globalAlpha = dot.alpha;
      ctx.beginPath();
      ctx.arc(dab.x + dot.dx, dab.y + dot.dy, dot.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
};
