# -*- mode: python ; coding: utf-8 -*-
import os

# Baked-in resources. hero_icons.json: the Publish preview's portraits.
# matches.txt: the seed list that lets a FRESH machine bootstrap its match
# database (run_all iterates stored championships - none, on a new install).
# owscout_refs.zip: the curator's learned library, making the exe PRE-TRAINED -
# export it right before building (`owscout refs export --out owscout_refs.zip`);
# building without it just yields an un-trained exe.
datas = [
    ('faceit_sync/hero_icons.json', 'faceit_sync'),
    ('matches.txt', '.'),
]
if os.path.exists('owscout_refs.zip'):
    datas.append(('owscout_refs.zip', '.'))
else:
    print('WARNING: owscout_refs.zip not found - the exe will NOT be pre-trained')

a = Analysis(
    ['owscout_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='owscout',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX OFF on purpose: packed binaries are a top AV false-positive trigger,
    # and this is a binary handed to non-technical friends. A larger, unpacked
    # exe that antivirus leaves alone beats a smaller one it quarantines.
    upx=False,
    upx_exclude=[],
    # Real Windows file properties so it shows as "OW Scout", not a blank binary.
    version='owscout_version.txt' if os.path.exists('owscout_version.txt') else None,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
