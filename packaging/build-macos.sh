#!/bin/sh
# Build `Spaced Positions.app` and `dist/<name>.dmg` (default Spaced-Positions-<version>-macOS) (spec 09 §11). Needs the dev extras
# (`pip install -e ".[dev]"`, which has PyInstaller). The app isn't signed: the first open needs System Settings →
# Privacy & Security → Open Anyway (macOS 15 and newer) or right click → Open (older macOS).
set -e
cd "$(dirname "$0")/.."
python manage.py design build
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/spos.spec
version=$(python -c "import spaced_positions; print(spaced_positions.__version__)")
name="${1:-Spaced-Positions-$version-macOS}"  # the release workflow names it, e.g. Spaced-Positions-0.2.0-macOS-Intel
stage=$(mktemp -d)  # a fresh folder each time: the image holds exactly the app and the Applications link
trap 'rm -rf "$stage"' EXIT
cp -R "dist/Spaced Positions.app" "$stage/"
ln -s /Applications "$stage/Applications"
rm -f "dist/$name.dmg"
hdiutil create -volname "Spaced Positions" -srcfolder "$stage" -format UDZO -ov "dist/$name.dmg"
echo "dist/$name.dmg"
