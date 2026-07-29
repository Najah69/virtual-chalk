# Virtual-Chalk

Application Windows autonome qui transforme un document ou un prompt en
vidéo explicative animée façon tableau (craie ou feutre), avec export
optionnel `.h5p` pour Moodle.

Voir [`docs/architecture.md`](docs/architecture.md) pour le détail des
décisions de conception.

## Développement

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

## Build (.exe)

```
pyinstaller build/pyinstaller.spec
```

Puis génération de l'installeur avec Inno Setup via `build/installer.iss`.
