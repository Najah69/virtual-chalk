// Convertit un élément texte en tracé dessinable par le moteur craie/feutre,
// à partir des vrais contours de la police manuscrite (via opentype.js),
// plutôt qu'un simple segment placeholder.

let _handwritingFont = null;

// pywebview sert cette page via un mini serveur HTTP local (pas file://),
// et un navigateur interdit de fixer `responseType` sur une requête XHR
// synchrone. On récupère donc le binaire via overrideMimeType (texte brut
// octet-par-octet), seule méthode encore autorisée en synchrone — c'est
// la technique historique pour lire un fichier binaire par XHR sync.
function loadBinarySync(url) {
  const xhr = new XMLHttpRequest();
  xhr.open("GET", url, false);
  xhr.overrideMimeType("text/plain; charset=x-user-defined");
  xhr.send(null);
  if (xhr.status !== 200 && xhr.status !== 0) {
    throw new Error("HTTP " + xhr.status);
  }
  const text = xhr.responseText;
  const bytes = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i++) {
    bytes[i] = text.charCodeAt(i) & 0xff;
  }
  return bytes.buffer;
}

(function loadHandwritingFont() {
  // Chargement synchrone volontaire : ce script tourne dans une page de
  // rendu offscreen dédiée (pas une UI interactive), donc bloquer le
  // thread ici le temps de charger un fichier local (quelques ms) est
  // plus simple et plus fiable qu'un chargement async à coordonner avec
  // Python avant le premier appel à loadScene.
  try {
    _handwritingFont = opentype.parse(loadBinarySync("fonts/Caveat.ttf"));
  } catch (e) {
    console.error("Echec du chargement de la police manuscrite:", e);
  }
})();

function cubicPoint(p0, p1, p2, p3, t) {
  const mt = 1 - t;
  return {
    x: mt * mt * mt * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t * t * t * p3.x,
    y: mt * mt * mt * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t * t * t * p3.y,
  };
}

function quadPoint(p0, p1, p2, t) {
  const mt = 1 - t;
  return {
    x: mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x,
    y: mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y,
  };
}

// Aplati le tracé vectoriel (courbes de Bézier) en une liste de points, en
// insérant un marqueur "levé de crayon" entre chaque sous-tracé (lettres
// séparées, boucles fermées d'un "o"/"e"...) pour que le moteur de tampon
// craie ne relie pas ces sous-tracés par un trait parasite.
function flattenOpentypePath(path) {
  const STEPS = 6;
  const subpaths = [];
  let current = [];
  let cursor = { x: 0, y: 0 };
  let start = { x: 0, y: 0 };

  function pushCurrent() {
    if (current.length > 1) subpaths.push(current);
    current = [];
  }

  for (const cmd of path.commands) {
    if (cmd.type === "M") {
      pushCurrent();
      cursor = { x: cmd.x, y: cmd.y };
      start = cursor;
      current = [cursor];
    } else if (cmd.type === "L") {
      cursor = { x: cmd.x, y: cmd.y };
      current.push(cursor);
    } else if (cmd.type === "C") {
      const p0 = cursor, p1 = { x: cmd.x1, y: cmd.y1 }, p2 = { x: cmd.x2, y: cmd.y2 }, p3 = { x: cmd.x, y: cmd.y };
      for (let i = 1; i <= STEPS; i++) current.push(cubicPoint(p0, p1, p2, p3, i / STEPS));
      cursor = p3;
    } else if (cmd.type === "Q") {
      const p0 = cursor, p1 = { x: cmd.x1, y: cmd.y1 }, p2 = { x: cmd.x, y: cmd.y };
      for (let i = 1; i <= STEPS; i++) current.push(quadPoint(p0, p1, p2, i / STEPS));
      cursor = p2;
    } else if (cmd.type === "Z") {
      current.push(start);
      cursor = start;
    }
  }
  pushCurrent();

  const flat = [];
  subpaths.forEach((sp, i) => {
    if (i > 0) flat.push({ penUp: true, x: sp[0].x, y: sp[0].y });
    flat.push(...sp);
  });
  return flat;
}

window.textToPaths = function textToPaths(text, x, y, fontSize) {
  if (!_handwritingFont) {
    // Repli si la police n'a pas pu charger : ancien comportement (barre).
    const estimatedWidth = text.length * fontSize * 0.55;
    return [{ x, y }, { x: x + estimatedWidth, y }];
  }
  const path = _handwritingFont.getPath(text, x, y, fontSize);
  return flattenOpentypePath(path);
};
