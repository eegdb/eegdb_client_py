# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

PROJECT_ROOT = os.path.abspath(SPECPATH)

datas = []
datas.append((os.path.join(PROJECT_ROOT, 'LICENSE'), '.'))
datas.append((os.path.join(PROJECT_ROOT, 'THIRD_PARTY_LICENSES', 'WAVPACK-LICENSE'), 'THIRD_PARTY_LICENSES'))
binaries = []
hiddenimports = [
    'eegdb_client',
    'eegdb_client.cli',
    'eegdb_client.ui.main_window',
    'eegdb_client.ui.attrs_form',
    'eegdb_client.ui.study_dialog',
    'eegdb_client.ui.workers',
    'eegdb_client.ui.pages',
    'eegdb_client.ui.pages.connect_page',
    'eegdb_client.ui.pages.upload_page',
    'eegdb_client.ui.pages.browse_page',
    'eegdb_client.ui.pages.review_page',
    'eegdb_client.analysis.data',
    'eegdb_client.readers.bids',
    'eegdb_client.readers.brainvision_reader',
    'eegdb_client.readers.eeglab_reader',
    'eegdb_client.readers.lsl_reader',
    'eegdb_client.readers.xdf_reader',
    'pyxdf',
    'pylsl',
    'qfluentwidgets',
]
# qfluentwidgets loads theme and icon resources dynamically. The other major
# dependencies have PyInstaller hooks and are discovered through normal imports;
# collecting all of MNE or PyQt6 would pull in unused CLI, 3D, QML, and SQL code.
for package in ('qfluentwidgets',):
    tmp_ret = collect_all(package)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# MNE's lazy-loader reads package .pyi stubs at runtime. They are data rather
# than importable modules, so dependency analysis alone does not include them.
datas += collect_data_files('mne')
hiddenimports += collect_submodules('mne')

# Local compressed decoding is optional at runtime. Include the native codec
# and its shared library when its separately-built wheel is installed.
if find_spec('eegdb_codec') is not None:
    tmp_ret = collect_all('eegdb_codec')
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]


a = Analysis(
    ['app.py'],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='EEGDBClient',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EEGDBClient',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='EEGDBClient.app',
        icon=None,
        bundle_identifier='org.eegdb.client',
        info_plist={
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '0.1.0',
            'NSHighResolutionCapable': True,
        },
    )
