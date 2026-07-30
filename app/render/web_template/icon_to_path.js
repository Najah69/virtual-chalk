// Convertit une icône (nom + position + taille) en tracé dessinable par le
// moteur craie/feutre, à partir de icon_paths.js (points précalculés côté
// build depuis des icônes Feather Icons — voir docs/architecture.md).
window.iconToPoints = function iconToPoints(iconName, x, y, size) {
  const nativePoints = window.ICON_PATHS && window.ICON_PATHS[iconName];
  if (!nativePoints || !nativePoints.length) return [{ x, y }, { x: x + size, y }];
  const scale = size / 24; // les icônes sources sont dans un viewBox 24x24
  return nativePoints.map((p) =>
    p.penUp
      ? { penUp: true, x: x + p.x * scale, y: y + p.y * scale }
      : { x: x + p.x * scale, y: y + p.y * scale }
  );
};
