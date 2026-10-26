# PyInstaller spec for the double-click app (spec 09 §11): macOS `Spaced Positions.app`, Windows `Spaced Positions`
# folder with `Spaced Positions.exe`. Build: `pyinstaller packaging/spos.spec` (packaging/build-macos.sh makes the
# .dmg; .github/workflows/release.yml builds both on a version tag).
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

block_cipher = None
name = "Spaced Positions"

hidden = collect_submodules("spaced_positions") + collect_submodules("django") + collect_submodules("waitress") + \
    collect_submodules("whitenoise") + ["chess", "chess.pgn", "chess.engine", "chess.svg", "platformdirs"]
# Django's data: its translations and formats; not the contrib apps the app doesn't use (their templates, static files)
UNUSED = ["admin", "admindocs", "auth", "flatpages", "gis", "humanize", "messages", "postgres", "redirects", "sessions", "sitemaps",
          "sites", "syndication"]
datas = collect_data_files("spaced_positions", include_py_files=False) + collect_data_files(
    "django", excludes=[f"contrib/{app}/**" for app in UNUSED])
# The packages' metadata and licence files (Settings → Licences, /licences/notices.txt) and Python's own licence
for package in ("django", "asgiref", "sqlparse", "waitress", "whitenoise", "platformdirs", "chess"):
    datas += copy_metadata(package)
python_licence = os.path.join(sys.base_prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "LICENSE.txt")
if not os.path.exists(python_licence):
    python_licence = os.path.join(sys.base_prefix, "LICENSE.txt")
if os.path.exists(python_licence):
    datas.append((python_licence, "spaced_positions/static/licences"))

a = Analysis(
    [os.path.join(SPECPATH, "app.py")],
    pathex=[os.path.join(SPECPATH, "..")],
    hiddenimports=hidden,
    datas=datas,
    excludes=["tkinter", "pytest", "playwright", "PIL", "IPython"],
    noarchive=False,
)
# Windows: the .exe says what it is, who made it and which version (Properties → Details). A program without this
# looks anonymous, which is one of the things virus scanners' heuristics react to.
version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)

    version = __import__("spaced_positions").__version__
    numbers = tuple(int(n) for n in "".join(c if c.isdigit() or c == "." else " " for c in version).split()[0].split(".")[:3])
    numbers = (numbers + (0, 0, 0, 0))[:4]
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Spaced Positions (open source, github.com/Piscary/SpacedPositions)"),
                StringStruct("FileDescription", "Spaced Positions: chess puzzle training"),
                StringStruct("FileVersion", version),
                StringStruct("InternalName", name),
                StringStruct("LegalCopyright", "Free software under the GNU GPL-3.0-or-later"),
                StringStruct("OriginalFilename", f"{name}.exe"),
                StringStruct("ProductName", name),
                StringStruct("ProductVersion", version),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=name, console=False, disable_windowed_traceback=False,
    icon=os.path.join(SPECPATH, "icon.icns" if sys.platform == "darwin" else "icon.ico"),
    version=version_info,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name=name)
if sys.platform == "darwin":
    app = BUNDLE(
        coll, name=f"{name}.app", icon=os.path.join(SPECPATH, "icon.icns"), bundle_identifier="org.spacedpositions.app",
        info_plist={"CFBundleShortVersionString": __import__("spaced_positions").__version__, "LSUIElement": False,
                    "NSHighResolutionCapable": True, "CFBundleDisplayName": name,
                    "NSHumanReadableCopyright": "Free software under the GNU GPL-3.0-or-later"},
    )
