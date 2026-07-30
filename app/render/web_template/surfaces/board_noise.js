// Utilitaire partagé par les surfaces "tableau" (craie) : génère une
// texture de grain une seule fois par taille de canvas (mise en cache par
// l'appelant), pour ne pas recalculer du bruit à chaque frame.
window.buildBoardNoise = function buildBoardNoise(width, height, baseColor) {
  const off = document.createElement("canvas");
  off.width = width;
  off.height = height;
  const octx = off.getContext("2d");
  octx.fillStyle = baseColor;
  octx.fillRect(0, 0, width, height);

  const imageData = octx.getImageData(0, 0, width, height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    const grain = (Math.random() - 0.5) * 14;
    data[i] = Math.min(255, Math.max(0, data[i] + grain));
    data[i + 1] = Math.min(255, Math.max(0, data[i + 1] + grain));
    data[i + 2] = Math.min(255, Math.max(0, data[i + 2] + grain));
  }
  octx.putImageData(imageData, 0, 0);
  return off;
};
