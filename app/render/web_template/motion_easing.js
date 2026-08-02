// Anime.js utilisé UNIQUEMENT comme bibliothèque d'easing pur (fonction
// mathématique progress -> progress, voir anime.easing(name) dans
// anime.min.js) — jamais son moteur d'animation temps réel
// (requestAnimationFrame, autoplay, instances/timelines). Le rendu final
// ne tourne JAMAIS en temps réel (voir renderAtTime, index.html) : chaque
// frame est calculée pour un instant t EXACT, indépendant de la vitesse de
// la machine — seule une fonction pure progress -> progress est
// compatible avec ce modèle. Décision actée dans docs/architecture.md
// (section Timeline éditable & Anime.js) : additif, portée limitée au
// fondu/easing sur des transitions existantes, pas un remplacement du
// moteur d'animation (falling_rain/orbit restent tels quels).
//
// Résultat toujours ramené à [0, 1] : certaines courbes nommées d'anime.js
// (easeOutElastic, easeOutBack...) dépassent momentanément cet intervalle
// (rebond) — anodin pour une échelle, mais casserait silencieusement
// ctx.globalAlpha (la spec Canvas ignore une valeur hors [0,1] et GARDE
// L'ANCIENNE, donc un fondu piloté par une courbe qui dépasse 1 se
// figerait au lieu de continuer). D'où le choix, pour ce premier usage,
// de courbes non dépassantes (easeOutCubic/easeInCubic) — un futur effet
// qui voudrait un vrai rebond visuel sur une valeur non-alpha devra
// appeler anime.easing(name) directement, pas ce wrapper.
window.easedProgress = function (linearProgress, easingName) {
  const clamped = Math.min(1, Math.max(0, linearProgress));
  const fn = window.anime && window.anime.easing ? window.anime.easing(easingName) : null;
  const eased = fn ? fn(clamped) : clamped;
  return Math.min(1, Math.max(0, eased));
};
