# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path.cwd()
BACKEND = ROOT / "apps" / "backend"
WEB_DIST = ROOT / "apps" / "web" / "dist"
LOGO = ROOT / "apps" / "web" / "src" / "components" / "brand" / "mediamop-logo-premium.png"
TRAY_ICON_PNG = ROOT / "packaging" / "windows" / "assets" / "mediamop-tray-icon.png"
TRAY_ICON_ICO = ROOT / "packaging" / "windows" / "assets" / "mediamop-tray-icon.ico"

hiddenimports = collect_submodules("mediamop")
datas = [
    (str(BACKEND / "alembic"), "alembic"),
    (str(BACKEND / "alembic.ini"), "."),
    (str(WEB_DIST), "web-dist"),
    (str(LOGO), "assets"),
    (str(TRAY_ICON_PNG), "assets"),
    (str(TRAY_ICON_ICO), "assets"),
]

a = Analysis(
    [str(BACKEND / "src" / "mediamop" / "windows" / "tray_app.py")],
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

tray_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediaMop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(TRAY_ICON_ICO),
)

server_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediaMopServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(TRAY_ICON_ICO),
)

coll = COLLECT(
    tray_exe,
    server_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MediaMop",
)
