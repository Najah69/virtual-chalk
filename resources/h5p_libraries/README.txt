Librairies H5P.InteractiveVideo (vue seule, sans types d'interaction
embarqués comme QCM/vrai-faux — hors périmètre v1) assemblées depuis les
dépôts officiels https://github.com/h5p :

  H5P.InteractiveVideo-1.28  H5P.Video-1.6        H5P.DragNBar-1.5
  H5P.DragNDrop-1.1          H5P.DragNResize-1.2  H5P.FontIcons-1.0
  H5P.Components-1.0         jQuery.ui-1.10       FontAwesome-4.5

H5P.InteractiveVideo et H5P.Components livrent leur JS/CSS via un build
webpack non commité dans leurs dépôts (dossier dist/) — reconstruit ici
avec `npm install && npm run build` avant intégration.

Chaîne de dépendances vérifiée cohérente (chaque preloadedDependencies de
chaque library.json pointe vers un dossier réellement présent) et testée
avec un vrai .h5p généré par app/h5p/packager.py.

app/h5p/packager.py lit la version de H5P.InteractiveVideo directement
depuis ces dossiers (pas de version figée en dur) — mettre à jour ces
librairies ne demande donc aucun changement de code.

Pour ajouter les types d'interaction optionnels (QCM, vrai/faux, texte à
trous, etc.) plus tard : `h5p clone h5p-interactive-video view` avec
l'outil officiel h5p-cli (npm install -g h5p-cli) depuis un dossier de
travail séparé, puis copier les dossiers voulus ici.
