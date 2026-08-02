// Bibliothèque personnelle d'éléments vectorisés (Tâche 6) : convertit un
// LibraryAsset (points normalisés, voir app/library/asset_library.py) en
// points PLACÉS en espace canvas réel — même formule que
// icon_to_path.js::iconToPoints, réutilisée à l'identique pour que le
// mécanisme de placement par clic (editor_canvas.js) et de vignette
// (drawLibraryAssetThumbnail) soit un simple appel de plus, pas une
// nouvelle logique.
//
// Aucune persistance ici : le stockage est GLOBAL et vit côté Python
// (Api.list_library_assets/save_library_asset/delete_library_asset) — ce
// fichier ne fait que la conversion géométrique.

(function () {
  "use strict";

  // Doit rester synchronisé avec LIBRARY_NATIVE_WIDTH dans
  // app/library/asset_library.py.
  const LIBRARY_NATIVE_WIDTH = 24.0;

  function assetToPoints(asset, x, y, size) {
    const scale = size / LIBRARY_NATIVE_WIDTH;
    return asset.points.map((p) =>
      p.pen_up
        ? { penUp: true, x: x + p.x * scale, y: y + p.y * scale }
        : { x: x + p.x * scale, y: y + p.y * scale }
    );
  }

  window.Library = { assetToPoints, LIBRARY_NATIVE_WIDTH };
})();
