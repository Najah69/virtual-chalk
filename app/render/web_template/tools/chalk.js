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
//
// Le trait reste opaque (alpha élevé, pour survivre à la compression
// H.264 — voir commit precedent) mais le grain est fin et dense : des
// points nombreux et petits, resserrés autour du tracé, plutôt que peu de
// gros points épars. Un grain trop gros par rapport à l'épaisseur du
// trait donne un aspect "zoomé"/grossier, en particulier sur du texte
// (retour utilisateur : lettres floues/grossières, comme "méga-zoomées").
function chalkPrecompute(stroke) {
  const rng = mulberry32(hashSeed(stroke));
  const path = stroke.points;
  // Pour du texte/icône, stroke.width est une taille (police ou icône),
  // pas l'épaisseur du trait de craie — trait plus fin qu'avant (0.16/0.07
  // au lieu de 0.22/0.09) pour un rendu plus délicat, proche d'un vrai
  // trait de craie plutôt qu'un feutre épais.
  const penWidth =
    stroke.kind === "text" ? Math.max(6, stroke.width * 0.16)
    : stroke.kind === "icon" ? Math.max(5, stroke.width * 0.07)
    : stroke.width;
  // Le nuage de points est tamponné avec un rayon de dispersion aléatoire
  // autour du tracé réel — trop large, il éloigne les dabs du contour de
  // lettre exact et floute la forme (retour utilisateur : texte encore
  // "pas totalement lisible" malgré le trait affiné). Resserré pour le
  // texte spécifiquement (0.22 au lieu de 0.4) : les dabs restent proches
  // du contour de police réel, la craie reste texturée sans brouiller la
  // forme des lettres. Les icônes/formes gardent une dispersion plus
  // large (0.4), qui ne pose pas ce problème de lisibilité fine.
  const jitterFactor = stroke.kind === "text" ? 0.22 : 0.4;
  const spacing = Math.max(0.8, penWidth * 0.28);
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
      const dotCount = 9 + Math.floor(rng() * 5);
      const dots = [];
      for (let d = 0; d < dotCount; d++) {
        const angle = rng() * Math.PI * 2;
        const r = rng() * penWidth * jitterFactor;
        dots.push({
          dx: Math.cos(angle) * r,
          dy: Math.sin(angle) * r,
          size: 0.25 + rng() * 0.55,
          alpha: 0.55 + rng() * 0.35,
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
//
// Dessin INCRÉMENTAL : ne redessine que les tampons nouvellement révélés
// depuis le dernier appel (stroke._lastDrawnCount), jamais tout depuis le
// début — redessiner l'intégralité à chaque frame coûtait O(frames ×
// tampons visibles), ce qui explosait avec de vrais contours de lettres.
window.TOOLS.chalk = function drawStroke(ctx, stroke, progress) {
  if (!stroke._chalkDabs) {
    stroke._chalkDabs = chalkPrecompute(stroke);
  }
  const dabs = stroke._chalkDabs;
  const visibleCount = Math.floor(dabs.length * progress);
  const from = stroke._lastDrawnCount || 0;
  if (visibleCount <= from) return;

  ctx.save();
  ctx.fillStyle = stroke.color;
  for (let i = from; i < visibleCount; i++) {
    const dab = dabs[i];
    for (const dot of dab.dots) {
      ctx.globalAlpha = dot.alpha;
      ctx.beginPath();
      ctx.arc(dab.x + dot.dx, dab.y + dot.dy, dot.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
  stroke._lastDrawnCount = visibleCount;
};
