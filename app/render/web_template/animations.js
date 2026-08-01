// Éléments réellement animés (pas juste progressivement révélés puis
// figés comme le texte/les icônes) : redessinés à CHAQUE frame tant
// qu'actifs. Contrairement au reste du moteur (qui n'efface jamais le
// canvas, ne fait qu'accumuler de la craie), une animation doit "effacer"
// sa propre zone à chaque frame puisque ses éléments bougent — elle le
// fait en redessinant depuis le cache de texture du tableau
// (window._boardTextureCache, voir surfaces/board_noise.js), jamais en
// vidant tout le canvas, pour ne jamais toucher au reste du dessin déjà
// posé ailleurs sur le tableau.
//
// Une fois sa fenêtre de temps passée, l'animation cesse d'être appelée
// (voir index.html) : sa dernière image reste alors figée en permanence,
// comme tout le reste — cohérent avec le principe "la craie posée ne
// bouge plus" du moteur.
window.ANIMATIONS = window.ANIMATIONS || {};

window.ANIMATIONS.falling_rain = function (ctx, stroke, t, boardTexture, toolName) {
  const x = stroke.points[0].x;
  const y = stroke.points[0].y;
  const size = stroke.width;
  const regionX = x - 14;
  const regionY = y - 14;
  const regionW = size + 28;
  const regionH = size * 1.7 + 28;

  if (boardTexture) {
    ctx.drawImage(boardTexture, regionX, regionY, regionW, regionH, regionX, regionY, regionW, regionH);
  }

  // Nuage statique : texture craie précalculée une seule fois (sur le
  // stroke), pas recalculée à chaque frame — seules les gouttes bougent.
  if (!stroke._cloudSprite) {
    stroke._cloudSprite = window.renderIconSprite("cloud", size, stroke.color, toolName);
  }
  ctx.drawImage(stroke._cloudSprite, x, y);

  const dropCount = 5;
  const speed = 0.6; // boucles par seconde
  ctx.save();
  ctx.fillStyle = stroke.color;
  for (let i = 0; i < dropCount; i++) {
    const phase = (t * speed + i / dropCount) % 1;
    const dropX = x + size * (0.18 + 0.64 * (i / dropCount));
    const dropY = y + size * 0.62 + phase * size * 0.85;
    ctx.globalAlpha = Math.max(0, 0.85 - phase * 0.55);
    ctx.beginPath();
    ctx.ellipse(dropX, dropY, size * 0.018, size * 0.045, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
};

// Premier "verbe" de la grammaire de mouvement (voir docs/architecture.md) :
// N corps qui tournent en cercle autour d'un centre — système solaire,
// électron/noyau, satellite, lune... — plutôt qu'une animation par sujet,
// un seul verbe générique paramétré par le LLM (stroke.params, voir
// strokes_from_visual_elements côté Python, qui a déjà converti les
// rayons/tailles de pourcentage en pixels). Dessine elle-même le corps
// central (params.center_icon, optionnel) plutôt que de compter sur le
// LLM pour placer une icône statique séparée au même point : le système
// de résolution de chevauchements ne saurait pas que les deux doivent
// rester co-localisés, et écarterait l'icône du vrai centre de rotation
// dès qu'elle chevauche l'emprise de l'orbite (bug constaté à l'écran :
// le "soleil" se retrouvait décalé des anneaux qu'il est censé occuper).
window.ANIMATIONS.orbit = function (ctx, stroke, t, boardTexture, toolName) {
  const cx = stroke.points[0].x;
  const cy = stroke.points[0].y;
  const params = stroke.params || {};
  const bodies = params.bodies || [];
  if (!bodies.length) return;

  // Région à effacer = le plus grand cercle atteint par un corps (ou le
  // centre, s'il est plus large que la première orbite), quelle que soit
  // la position actuelle des corps sur leur orbite — sinon une frange de
  // traînée resterait visible d'une frame à l'autre.
  let maxReach = (params.center_size || 0) / 2;
  for (const b of bodies) {
    maxReach = Math.max(maxReach, b.radius + b.size / 2);
  }
  const pad = 14;
  const regionX = cx - maxReach - pad;
  const regionY = cy - maxReach - pad;
  const regionSize = maxReach * 2 + pad * 2;

  if (boardTexture) {
    ctx.drawImage(
      boardTexture, regionX, regionY, regionSize, regionSize,
      regionX, regionY, regionSize, regionSize
    );
  }

  // Anneaux-guides : tracés simples et bon marché à chaque frame (pas
  // besoin de les mettre en cache comme le nuage statique de
  // falling_rain, dont la forme est bien plus coûteuse à calculer).
  if (params.draw_orbit_rings) {
    ctx.save();
    ctx.strokeStyle = stroke.color;
    ctx.globalAlpha = 0.35;
    ctx.lineWidth = 1.5;
    for (const b of bodies) {
      ctx.beginPath();
      ctx.arc(cx, cy, b.radius, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
  }

  // Sprites calculés une seule fois (leur forme ne change jamais, seule
  // la position des corps orbitants bouge) — même principe que le nuage
  // statique de falling_rain.
  if (!stroke._orbitSprites) {
    stroke._orbitSprites = bodies.map((b) =>
      window.renderIconSprite(b.icon, b.size, stroke.color, toolName)
    );
    if (params.center_icon) {
      stroke._orbitCenterSprite = window.renderIconSprite(
        params.center_icon, params.center_size, stroke.color, toolName
      );
    }
  }

  if (stroke._orbitCenterSprite) {
    const s = params.center_size;
    ctx.drawImage(stroke._orbitCenterSprite, cx - s / 2, cy - s / 2);
  }

  bodies.forEach((b, i) => {
    const angleRad = (b.phase_deg * Math.PI) / 180 + (2 * Math.PI * t) / b.period_s;
    const bx = cx + Math.cos(angleRad) * b.radius;
    const by = cy + Math.sin(angleRad) * b.radius;
    ctx.drawImage(stroke._orbitSprites[i], bx - b.size / 2, by - b.size / 2);
  });
};
