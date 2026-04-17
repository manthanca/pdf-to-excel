# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for MRACA Smart Contract Note Converter.
Build with:  pyinstaller MRACA_Converter.spec
Output:      dist/MRACA_Converter/MRACA_Converter.exe
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

# Collect all Streamlit resources (HTML, CSS, JS, etc.)
streamlit_datas, streamlit_binaries, streamlit_hiddenimports = collect_all("streamlit")

# pdfplumber / pdfminer resources
pdfplumber_datas,  _, pdfplumber_hiddenimports  = collect_all("pdfplumber")
pdfminer_datas,    _, pdfminer_hiddenimports     = collect_all("pdfminer")

# App source files to bundle
app_datas = [
    ("app_final.py",                       "."),
    ("universal_angel_one_processor.py",   "."),
    ("obligation_parser.py",               "."),
    ("core",                               "core"),
]

all_datas    = streamlit_datas + pdfplumber_datas + pdfminer_datas + app_datas
all_binaries = streamlit_binaries
all_hidden   = (
    streamlit_hiddenimports +
    pdfplumber_hiddenimports +
    pdfminer_hiddenimports +
    [
        "streamlit.web.cli",
        "streamlit.runtime.scriptrunner",
        "pdfplumber", "pdfminer", "pdfminer.high_level",
        "openpyxl", "pandas", "PIL",
        "collections.abc",
    ]
)

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "matplotlib", "scipy", "notebook", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MRACA_Converter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,         # keep console so startup messages are visible
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MRACA_Converter",
)
