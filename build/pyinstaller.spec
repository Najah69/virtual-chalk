# -*- mode: python ; coding: utf-8 -*-
# Build : pyinstaller build/pyinstaller.spec (depuis la racine du projet)

block_cipher = None

a = Analysis(
    ["../app/main.py"],
    pathex=["../"],
    binaries=[],
    datas=[
        ("../ui", "ui"),
        ("../app/render/web_template", "app/render/web_template"),
        ("../app/render/assets", "app/render/assets"),
        ("../resources", "resources"),
    ],
    hiddenimports=["webview.platforms.winforms"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="virtual-chalk",
    console=False,
    # Icone de l'exe (barre des taches, raccourcis, association .vchalk —
    # voir build/installer.iss) — derivee de icone-Virtual-Chalk-3.png,
    # voir resources/branding/app_icon.ico (multi-resolution 16..256px).
    icon="../resources/branding/app_icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="virtual-chalk",
)
