// Pré-rend une icône entièrement tracée (progress=1) sur un petit canvas
// offscreen, réutilisant le moteur craie/feutre existant — sert de partie
// statique aux animations (ex: le nuage de falling_rain), calculée une
// seule fois plutôt qu'à chaque frame.
window.renderIconSprite = function renderIconSprite(iconName, size, color, toolName) {
  const off = document.createElement("canvas");
  off.width = size;
  off.height = size;
  const octx = off.getContext("2d");
  const points = window.iconToPoints(iconName, 0, 0, size);
  const fakeStroke = { points, color, width: size, kind: "icon" };
  const drawStroke = window.TOOLS[toolName] || window.TOOLS.chalk;
  drawStroke(octx, fakeStroke, 1.0);
  return off;
};
