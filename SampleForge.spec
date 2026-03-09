# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para SampleForge
# Generado por build_app.command — no editar manualmente

import sys
from pathlib import Path

APP_DIR = Path(SPECPATH)

block_cipher = None

# Datos extras que PyInstaller no detecta automáticamente
added_datas = [
    (str(APP_DIR / "ui" / "styles"), "ui/styles"),
    (str(APP_DIR / "config.py"), "."),
]

# Hidden imports necesarios para transformers, torch y chromadb
hidden_imports = [
    # transformers / CLAP
    "transformers",
    "transformers.models.clap",
    "transformers.models.clap.modeling_clap",
    "transformers.models.clap.processing_clap",
    "transformers.models.clap.feature_extraction_clap",
    "transformers.pipelines",
    "huggingface_hub",
    "huggingface_hub.file_download",
    "safetensors",
    "safetensors.torch",
    # torch
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torchaudio",
    # audio
    "librosa",
    "soundfile",
    "sounddevice",
    "mutagen",
    "mutagen.mp3",
    "mutagen.flac",
    "mutagen.mp4",
    "audioread",
    # vector db
    "chromadb",
    "chromadb.db.impl",
    "chromadb.segment",
    "chromadb.segment.impl",
    "hnswlib",
    # umap
    "umap",
    "umap.umap_",
    "sklearn",
    "sklearn.neighbors",
    "sklearn.utils",
    "pynndescent",
    # UI
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    # misc
    "numpy",
    "scipy",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
]

a = Analysis(
    [str(APP_DIR / "main.py")],
    pathex=[str(APP_DIR)],
    binaries=[],
    datas=added_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",   # no lo usamos directamente
        "tkinter",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SampleForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # sin ventana de terminal
    disable_windowed_traceback=False,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SampleForge",
)

# macOS: crear .app bundle
app = BUNDLE(
    coll,
    name="SampleForge.app",
    icon=None,
    bundle_identifier="com.sampleforge.app",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSAppleScriptEnabled": False,
        "CFBundleDisplayName": "SampleForge",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "SampleForge necesita acceso al audio.",
        "com.apple.security.device.audio-input": True,
    },
)
