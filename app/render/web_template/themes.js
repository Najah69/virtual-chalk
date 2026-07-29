// Registre des thèmes disponibles = combinaison {surface, outil, palette}.
// Ajouter un thème = ajouter une entrée ici + les modules surfaces/tools
// correspondants, sans toucher au reste du moteur.
window.THEMES = {
  chalk_board: {
    label: "Tableau craie",
    surface: "greenboard",
    tool: "chalk",
    palette: ["#ffffff", "#ffe66d", "#ff6b6b", "#6bd4ff", "#8fe388", "#ff9ecb", "#ffa94d"],
  },
  whiteboard_marker: {
    label: "Tableau blanc + feutres",
    surface: "whiteboard",
    tool: "marker_veleda",
    palette: ["#1a1a1a", "#1f5fd1", "#e0313b", "#1f9e56", "#f2a900"],
  },
};

window.getTheme = function (themeId) {
  return window.THEMES[themeId] || window.THEMES.chalk_board;
};
