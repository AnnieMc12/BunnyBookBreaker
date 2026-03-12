# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for EPUB to DOCX Converter."""

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'ebooklib',
        'ebooklib.epub',
        'ebooklib.utils',
        'lxml',
        'lxml.etree',
        'docx',
        'docx.shared',
        'docx.enum.text',
        'PIL',
        'PIL.Image',
        'PIL.ImageFilter',
        'pytesseract',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='epub2docx',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app, no console window
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='epub2docx',
)
