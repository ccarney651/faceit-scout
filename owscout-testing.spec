# -*- mode: python ; coding: utf-8 -*-
# The TESTERS' build: same code as owscout.spec, but bakes in a GUIDED marker so
# the app starts in tabbed + gated mode (Calibrate under Settings; the Scout tab
# stays greyed until each setup step is done). This is the exe to hand to
# teammates. The curator build (owscout.spec -> owscout.exe) is the flat layout.
import os

datas = [
    ('faceit_sync/hero_icons.json', 'faceit_sync'),
    ('matches.txt', '.'),
    ('GUIDED', '.'),          # <-- makes gui.main() start in guided mode
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
    name='owscout-testing',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # packers trip antivirus; keep it unpacked (see owscout.spec)
    upx_exclude=[],
    version='owscout_version.txt' if os.path.exists('owscout_version.txt') else None,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
