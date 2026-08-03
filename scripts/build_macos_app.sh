#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$REPO_DIR/dist/Nova.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
SOURCE_DIR="$REPO_DIR/macos/NovaMenuBar/Sources"
BUILD_DIR="$REPO_DIR/build/standalone"
CORE_DIR="$BUILD_DIR/dist/NovaCore"
ICONSET_DIR="$BUILD_DIR/Nova.iconset"

if ! xcodebuild -version >/dev/null 2>&1; then
    echo "The Nova macOS app requires full Xcode to build the SwiftUI interface."
    echo "Install Xcode from the App Store, open it once, then run this script again."
    exit 1
fi

if ! "$REPO_DIR/.venv/bin/python" -m PyInstaller --version >/dev/null 2>&1; then
    echo "Standalone packaging requires the development dependencies."
    echo "Run: .venv/bin/python -m pip install --requirement requirements-dev.txt"
    exit 1
fi

if [[ "$APP_DIR" != "$REPO_DIR/dist/Nova.app" ]]; then
    echo "Refusing to clean an unexpected app path: $APP_DIR"
    exit 1
fi
rm -rf "$APP_DIR" "$BUILD_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$BUILD_DIR/spec"
cp "$REPO_DIR/macos/NovaMenuBar/Info.plist" "$CONTENTS_DIR/Info.plist"
cp "$REPO_DIR/macos/NovaMenuBar/Resources/nova-orb-reference.png" \
    "$RESOURCES_DIR/nova-orb-reference.png"
cp "$REPO_DIR/macos/NovaMenuBar/Resources/nova-orb-transparent.png" \
    "$RESOURCES_DIR/nova-orb-transparent.png"

"$REPO_DIR/.venv/bin/python" -m PyInstaller \
    --noconfirm \
    --clean \
    --onedir \
    --name NovaCore \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work" \
    --specpath "$BUILD_DIR/spec" \
    --paths "$REPO_DIR" \
    --add-data \
    "$REPO_DIR/nova/voice/macos/NovaSpeechInput.m:nova/voice/macos" \
    "$REPO_DIR/nova/gui_bridge.py"
cp -R "$CORE_DIR" "$RESOURCES_DIR/NovaCore"

mkdir -p "$ICONSET_DIR"
sips --cropToHeightWidth 951 951 \
    "$REPO_DIR/macos/NovaMenuBar/Resources/nova-orb-transparent.png" \
    --out "$BUILD_DIR/icon-square.png" >/dev/null
for size in 16 32 128 256 512; do
    sips --resampleHeightWidth "$size" "$size" "$BUILD_DIR/icon-square.png" \
        --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
done
for size in 16 32 128 256 512; do
    double_size=$((size * 2))
    sips --resampleHeightWidth "$double_size" "$double_size" \
        "$BUILD_DIR/icon-square.png" \
        --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil --convert icns "$ICONSET_DIR" --output "$RESOURCES_DIR/Nova.icns"

xcrun swiftc \
    -swift-version 5 \
    -parse-as-library \
    -framework AppKit \
    -framework Carbon \
    -framework EventKit \
    -framework ServiceManagement \
    -framework SwiftUI \
    -o "$MACOS_DIR/Nova" \
    "$SOURCE_DIR/NovaEngine.swift" \
    "$SOURCE_DIR/WindowCoordinator.swift" \
    "$SOURCE_DIR/GlobalHotKey.swift" \
    "$SOURCE_DIR/LoginItemManager.swift" \
    "$SOURCE_DIR/SystemMonitor.swift" \
    "$SOURCE_DIR/CalendarModel.swift" \
    "$SOURCE_DIR/OnboardingView.swift" \
    "$SOURCE_DIR/ContentView.swift" \
    "$SOURCE_DIR/NovaMenuBarApp.swift"

codesign --force --deep --sign - "$APP_DIR"
echo "Built standalone $APP_DIR"
