#!/bin/sh
# Build `Spaced Positions.app` and `dist/Spaced-Positions-<version>-macOS.dmg` (spec 09 §11). Needs the dev extras
# (`pip install -e ".[dev]"`, which has PyInstaller). The app isn't signed: the first open is right click → Open.
set -e
cd "$(dirname "$0")/.."
python manage.py design build
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/spos.spec
version=$(python -c "import spaced_positions; print(spaced_positions.__version__)")
stage=$(mktemp -d)  # a fresh folder each time: the image holds exactly the app and the Applications link
trap 'rm -rf "$stage"' EXIT
cp -R "dist/Spaced Positions.app" "$stage/"
ln -s /Applications "$stage/Applications"
rm -f "dist/Spaced-Positions-$version-macOS.dmg"
hdiutil create -volname "Spaced Positions" -srcfolder "$stage" -format UDZO -ov "dist/Spaced-Positions-$version-macOS.dmg"
echo "dist/Spaced-Positions-$version-macOS.dmg"
