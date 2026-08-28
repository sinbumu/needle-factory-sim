# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows onedir build.

The Needle engine DLL and model are NOT bundled: cactus-needle downloads them
to ~/.cache/cactus-needle on first run (internet needed once), which keeps the
distribution small and avoids redistributing model binaries.

The jax/flax training stack is only used by needle's finetune/export tooling
(needle.model.*), never by the inference path this app uses, so it is excluded.
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent

EXCLUDES = [
    # needle training/export stack (unused by the inference path)
    "jax",
    "jaxlib",
    "flax",
    "scipy",
    "orbax",
    "tensorstore",
    "sentencepiece",
    "ml_dtypes",
    "opt_einsum",
    "numpy",
    "needle.model",
    "needle.cli",
    "needle.playground",
    # general fat we never import
    "matplotlib",
    "pandas",
    "tkinter",
    "IPython",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=["huggingface_hub"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="NeedleFactorySim",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NeedleFactorySim",
)
