# PyInstaller spec for the double-click app (spec 09 §11): macOS `Spaced Positions.app`, Windows `Spaced Positions`
# folder with `Spaced Positions.exe`. Build: `pyinstaller packaging/spos.spec` (packaging/build-macos.sh makes the
# .dmg; .github/workflows/release.yml builds both on a version tag).
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
name = "Spaced Positions"

hidden = collect_submodules("spaced_positions") + collect_submodules("django") + collect_submodules("waitress") + \
    collect_submodules("whitenoise") + ["chess", "chess.pgn", "chess.engine", "chess.svg", "platformdirs"]
datas = collect_data_files("spaced_positions", include_py_files=False) + collect_data_files("django")

a = Analysis(
    [os.path.join(SPECPATH, "app.py")],
    pathex=[os.path.join(SPECPATH, "..")],
    hiddenimports=hidden,
    datas=datas,
    excludes=["tkinter", "pytest", "playwright", "PIL", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=name, console=False, disable_windowed_traceback=False,
    icon=os.path.join(SPECPATH, "icon.icns" if sys.platform == "darwin" else "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name=name)
if sys.platform == "darwin":
    app = BUNDLE(
        coll, name=f"{name}.app", icon=os.path.join(SPECPATH, "icon.icns"), bundle_identifier="org.spacedpositions.app",
        info_plist={"CFBundleShortVersionString": __import__("spaced_positions").__version__, "LSUIElement": False,
                    "NSHighResolutionCapable": True},
    )
