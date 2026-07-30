// Convertit un élément texte en tracé (points) dessinable par le moteur
// craie/feutre. Placeholder volontairement simple : un segment horizontal
// dont la longueur approxime la largeur du texte.
//
// TODO: remplacer par un vrai contour de police (ex. opentype.js) pour un
// rendu manuscrit fidèle — actuellement le texte apparaît comme une barre
// texturée plutôt que des lettres, mais c'est déjà visible et positionné.
window.textToPaths = function textToPaths(text, x, y, fontSize) {
  const estimatedWidth = text.length * fontSize * 0.55;
  return [
    { x: x, y: y },
    { x: x + estimatedWidth, y: y },
  ];
};
