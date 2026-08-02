// Mascotte animée : couche de dessin séparée du reste du moteur (texte/
// icônes/formes qui s'accumulent, jamais effacées — voir index.html) et
// des animations à stroke unique (window.ANIMATIONS, voir animations.js).
// La mascotte est pilotée par plusieurs PHASES successives
// (Scene.mascot_timeline, voir app/scenes/schema.py::MascotAction) plutôt
// que par un seul stroke, mais suit le même principe d'effacement local
// depuis le cache de texture du tableau à chaque frame active.
//
// Position d'ancrage FIXE (coin bas-gauche) : seule la pose interne
// bouge (bras, yeux, échelle d'apparition/disparition), ce qui borne une
// fois pour toutes la région à effacer/redessiner, y compris pour
// action_type "point" où le bras s'étend vers une cible qui peut être
// n'importe où sur le tableau (MASCOT_POINT_REACH plafonne cette portée).
window.MASCOT_ANCHOR_FRACTION = { x: 0.075, y: 0.86 };
window.MASCOT_SIZE = 130;
window.MASCOT_POINT_REACH = 260;

window.MASCOT_COLORS = {
  chalk_board: "#ffe66d",
  whiteboard_marker: "#1f5fd1",
};

// Retrouve la phase active à l'instant t (les phases d'un
// mascot_timeline se suivent sans recouvrement ni trou, voir
// default_mascot_timeline côté Python), ou null hors de toute phase
// (mascotte absente de la scène, ou timeline vide).
window.mascotActiveAction = function (mascotTimeline, t) {
  if (!mascotTimeline || !mascotTimeline.length) return null;
  for (const action of mascotTimeline) {
    if (t >= action.start_sec && t < action.end_sec) return action;
  }
  return null;
};

function mascotRegion(canvasWidth, canvasHeight) {
  const anchor = window.MASCOT_ANCHOR_FRACTION;
  const cx = canvasWidth * anchor.x;
  const cy = canvasHeight * anchor.y;
  const pad = window.MASCOT_SIZE + window.MASCOT_POINT_REACH + 20;
  return { cx, cy, x: cx - pad, y: cy - pad, w: pad * 2, h: pad * 2 };
}

function eraseMascotRegion(ctx, boardTexture, canvasWidth, canvasHeight) {
  if (!boardTexture) return;
  const r = mascotRegion(canvasWidth, canvasHeight);
  ctx.drawImage(boardTexture, r.x, r.y, r.w, r.h, r.x, r.y, r.w, r.h);
}

function drawMascotBody(ctx, cx, cy, size, color, bob) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = size * 0.05;
  ctx.beginPath();
  ctx.arc(cx, cy + bob, size * 0.5, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function drawMascotEyes(ctx, cx, cy, size, color, bob, blink) {
  const eyeY = cy + bob - size * 0.08;
  const eyeSpacing = size * 0.18;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = size * 0.025;
  for (const dx of [-eyeSpacing, eyeSpacing]) {
    ctx.beginPath();
    if (blink) {
      ctx.moveTo(cx + dx - size * 0.05, eyeY);
      ctx.lineTo(cx + dx + size * 0.05, eyeY);
      ctx.stroke();
    } else {
      ctx.arc(cx + dx, eyeY, size * 0.045, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}

window.MASCOT_POSES = {
  // easeOutCubic/easeInCubic (window.easedProgress, voir motion_easing.js)
  // plutôt qu'une interpolation linéaire — la mascotte arrive/repart avec
  // une accélération naturelle au lieu d'un mouvement mécanique à vitesse
  // constante. Premier usage d'Anime.js dans le moteur (additif, voir
  // docs/architecture.md) : uniquement comme bibliothèque d'easing pur,
  // jamais son moteur temps réel — appelé ici avec la même valeur t
  // EXACTE que le reste du rendu déterministe (renderAtTime, index.html).
  appear: function (ctx, cx, cy, size, color, progress) {
    const eased = window.easedProgress(progress, "easeOutCubic");
    const scale = Math.max(0.05, eased);
    ctx.save();
    ctx.globalAlpha = eased;
    drawMascotBody(ctx, cx, cy, size * scale, color, 0);
    drawMascotEyes(ctx, cx, cy, size * scale, color, 0, false);
    ctx.restore();
  },
  disappear: function (ctx, cx, cy, size, color, progress) {
    const eased = window.easedProgress(progress, "easeInCubic");
    const scale = Math.max(0.05, 1 - eased);
    ctx.save();
    ctx.globalAlpha = 1 - eased;
    drawMascotBody(ctx, cx, cy, size * scale, color, 0);
    drawMascotEyes(ctx, cx, cy, size * scale, color, 0, false);
    ctx.restore();
  },
  idle: function (ctx, cx, cy, size, color, progress, t) {
    const bob = Math.sin(t * 2.2) * size * 0.05;
    const blink = (t % 3) < 0.12;
    drawMascotBody(ctx, cx, cy, size, color, bob);
    drawMascotEyes(ctx, cx, cy, size, color, bob, blink);
  },
  wave: function (ctx, cx, cy, size, color, progress, t) {
    const bob = Math.sin(t * 2.2) * size * 0.05;
    drawMascotBody(ctx, cx, cy, size, color, bob);
    drawMascotEyes(ctx, cx, cy, size, color, bob, false);
    const waveAngle = -Math.PI / 3 + Math.sin(t * 8) * 0.35;
    ctx.save();
    ctx.translate(cx + size * 0.42, cy + bob - size * 0.1);
    ctx.rotate(waveAngle);
    ctx.strokeStyle = color;
    ctx.lineWidth = size * 0.06;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(size * 0.4, 0);
    ctx.stroke();
    ctx.restore();
  },
  point: function (ctx, cx, cy, size, color, progress, t, action) {
    const bob = Math.sin(t * 1.5) * size * 0.03;
    drawMascotBody(ctx, cx, cy, size, color, bob);
    drawMascotEyes(ctx, cx, cy, size, color, bob, false);

    const originX = cx;
    const originY = cy + bob;
    const dx = action.target_x - originX;
    const dy = action.target_y - originY;
    const dist = Math.max(1, Math.hypot(dx, dy));
    const reach = Math.min(window.MASCOT_POINT_REACH, dist);
    const ux = dx / dist;
    const uy = dy / dist;
    const tipX = originX + ux * reach;
    const tipY = originY + uy * reach;

    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = size * 0.06;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(originX + ux * size * 0.4, originY + uy * size * 0.4);
    ctx.lineTo(tipX, tipY);
    ctx.stroke();

    const arrowSize = size * 0.12;
    const angle = Math.atan2(uy, ux);
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - arrowSize * Math.cos(angle - 0.5), tipY - arrowSize * Math.sin(angle - 0.5));
    ctx.lineTo(tipX - arrowSize * Math.cos(angle + 0.5), tipY - arrowSize * Math.sin(angle + 0.5));
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  },
};

// Dessine la mascotte pour l'instant t si Scene.mascot_timeline a une
// phase active — appelé par renderAtTime (index.html) pour chaque scène
// qui a une mascotte (mascot_timeline non vide), jamais sinon (évite un
// effacement/redessin inutile à chaque frame des scènes sans mascotte).
window.drawMascot = function (ctx, scene, t, boardTexture, canvasWidth, canvasHeight, themeId) {
  eraseMascotRegion(ctx, boardTexture, canvasWidth, canvasHeight);
  const action = window.mascotActiveAction(scene.mascot_timeline, t);
  if (!action) return;
  const pose = window.MASCOT_POSES[action.action_type];
  if (!pose) return;
  const color = window.MASCOT_COLORS[themeId] || window.MASCOT_COLORS.chalk_board;
  const region = mascotRegion(canvasWidth, canvasHeight);
  const span = Math.max(action.end_sec - action.start_sec, 0.0001);
  const progress = Math.min(1, Math.max(0, (t - action.start_sec) / span));
  pose(ctx, region.cx, region.cy, window.MASCOT_SIZE, color, progress, t, action);
};
