#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'DMG builds require macOS and hdiutil.' >&2
  exit 1
fi
python3 packaging/collect-licenses.py
python3 -m PyInstaller --noconfirm --clean --windowed --name PDF-Tool \
  --osx-bundle-identifier de.pdf-tool.local \
  --add-data 'README.md:.' --add-data 'packaging/NOTICE.txt:.' --add-data 'packaging/generated-licenses:licenses' \
  --add-data 'index.html:.' --add-data 'workflows.js:.' --add-data 'tessdata:tessdata' \
  --collect-all pymupdf --collect-all PIL app.py
codesign --verify --deep --strict dist/PDF-Tool.app
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
ditto dist/PDF-Tool.app "$stage/PDF-Tool.app"
ln -s /Applications "$stage/Programme"
hdiutil create -volname 'PDF-Tool' -srcfolder "$stage" -ov -format UDZO "dist/PDF-Tool-macOS-$(uname -m).dmg"
hdiutil verify "dist/PDF-Tool-macOS-$(uname -m).dmg"
