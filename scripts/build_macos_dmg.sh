#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$REPO_DIR/dist/Nova.app"
DMG_PATH="$REPO_DIR/dist/Nova-7.5.0.dmg"
STAGING_DIR="$REPO_DIR/build/dmg"

if [[ ! -x "$APP_DIR/Contents/MacOS/Nova" ]]; then
    "$REPO_DIR/scripts/build_macos_app.sh"
fi

if [[ "$STAGING_DIR" != "$REPO_DIR/build/dmg" ]]; then
    echo "Refusing to clean an unexpected staging path: $STAGING_DIR"
    exit 1
fi
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$APP_DIR" "$STAGING_DIR/Nova.app"
ln -s /Applications "$STAGING_DIR/Applications"
rm -f "$DMG_PATH"
hdiutil create \
    -volname "Nova 7.5" \
    -srcfolder "$STAGING_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

echo "Built $DMG_PATH"
