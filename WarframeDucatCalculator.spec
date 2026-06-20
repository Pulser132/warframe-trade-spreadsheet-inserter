# -*- mode: python ; coding: utf-8 -*-
# Single source of build truth for the PyInstaller one-folder build. Run via
# build.ps1, or directly: pyinstaller WarframeDucatCalculator.spec
#
# Writable data (configs/, data/) is intentionally NOT bundled here — it lives
# beside the built exe and is created/seeded at runtime (see paths.py and
# ocr_scanner._ensure_lookup_seeded). scripts/ (the Node resolver) is also not
# bundled and isn't needed at runtime at all — ocr_scanner.py's OCR resolution
# runs entirely through resolver.py (a pure-Python port), which PyInstaller
# picks up automatically as a regular import, against the seeded ducat cache.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("PIL")
hiddenimports += collect_submodules("googleapiclient")
hiddenimports += collect_submodules("google.auth")
hiddenimports += collect_submodules("google_auth_httplib2")

datas = [
    ("assets", "assets"),
    ("api_config.example.json", "."),
]
datas += collect_data_files("googleapiclient")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WarframeDucatCalculator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app.ico",
    version="version_info.txt",
    # Flat layout (no "_internal" subfolder) so api_config.example.json and
    # configs/data/ all land directly beside the exe, matching paths.py's
    # user_data_path() model (writable data lives in os.path.dirname(sys.executable)).
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WarframeDucatCalculator",
)
