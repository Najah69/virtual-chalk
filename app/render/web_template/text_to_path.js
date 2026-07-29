// Convertit un texte (police manuscrite) en tracés vectoriels (contours de
// glyphes), pour que le texte soit dessiné avec le même moteur d'outil
// (craie/feutre) que les formes libres.
//
// TODO: intégrer une lib d'extraction de contours de police (ex. opentype.js)
// pour remplacer ce placeholder qui simule un tracé rectiligne par lettre.
window.textToPaths = function textToPaths(text, x, y, fontSize) {
  const paths = [];
  let cursorX = x;
  for (const ch of text) {
    if (ch !== " ") {
      paths.push([
        { x: cursorX, y: y },
        { x: cursorX + fontSize * 0.5, y: y },
      ]);
    }
    cursorX += fontSize * 0.6;
  }
  return paths;
};
