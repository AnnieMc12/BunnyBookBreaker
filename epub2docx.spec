# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Bunny Book Breaker."""

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('pics', 'pics'),  # Bundle bunny images
    ],
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
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
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
    name='BunnyBookBreaker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BunnyBookBreaker',
)
