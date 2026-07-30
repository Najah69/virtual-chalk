Les fichiers chalk_tap_*.wav de ce dossier sont générés automatiquement au
premier lancement par app/render/chalk_audio.py::ensure_sound_pack() — un
bruit filtré synthétisé procéduralement (pas d'enregistrement réel de
craie disponible localement). Ils ne sont pas versionnés dans git.

Pour utiliser de vrais enregistrements : placer ici des fichiers nommés
chalk_tap_00.wav, chalk_tap_01.wav, etc. (mono, 22050 Hz recommandé) —
ensure_sound_pack() ne (re)génère que les fichiers manquants, donc les
vôtres ne seront jamais écrasés.
