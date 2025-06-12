# -*- mode: python ; coding: utf-8 -*-

import sys

kwargs = {}
if sys.platform == 'win32':
    kwargs['win_no_prefer_redirects'] = False
    kwargs['win_private_assemblies'] = False

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('settings.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPrintSupport',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtXml',
        'PySide6.QtSvg',
        'PySide6.QtNetwork',
        'tkinter',
        'doctest',
        'unittest',
        'pydoc',
        'pdb'
    ],
    cipher=None,
    noarchive=False,
    **kwargs
)
pyz = PYZ(a.pure, a.zipped_data, cipher=cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Scribe2SRT',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True if sys.platform != 'darwin' else False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)