# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path.cwd()
BACKEND = ROOT / "apps" / "backend"
WEB_DIST = ROOT / "apps" / "web" / "dist"
LOGO = ROOT / "apps" / "web" / "src" / "components" / "brand" / "weir-logo-premium.webp"
TRAY_ICON_PNG = ROOT / "packaging" / "windows" / "assets" / "weir-tray-icon.png"
TRAY_ICON_ICO = ROOT / "packaging" / "windows" / "assets" / "weir-tray-icon.ico"
FFMPEG_VENDOR = ROOT / "packaging" / "windows" / "vendor" / "ffmpeg"
THIRD_PARTY_NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"

hiddenimports = collect_submodules("weir") + collect_submodules("uvicorn")
datas = [
    (str(BACKEND / "alembic"), "alembic"),
    (str(BACKEND / "alembic.ini"), "."),
    (str(WEB_DIST), "web-dist"),
    (str(LOGO), "assets"),
    (str(TRAY_ICON_PNG), "assets"),
    (str(TRAY_ICON_ICO), "assets"),
    (str(THIRD_PARTY_NOTICES), "."),
    # The Direct Play device list is data read at runtime (#467); without it the badge cannot load.
    (
        str(BACKEND / "src" / "weir" / "refiner" / "direct_play" / "devices.json"),
        "weir/refiner/direct_play",
    ),
]
datas += copy_metadata("weir-backend")
if FFMPEG_VENDOR.is_dir():
    datas.append((str(FFMPEG_VENDOR), "bin/ffmpeg"))

a = Analysis(
    [str(BACKEND / "src" / "weir" / "windows" / "server_entry.py")],
    pathex=[str(BACKEND / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

server_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WeirServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(TRAY_ICON_ICO),
)

coll = COLLECT(
    server_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["*.pyd", "python*.dll", "vcruntime*.dll"],
    name="WeirServer",
)
