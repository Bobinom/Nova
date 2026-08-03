#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$REPO_DIR/dist/Nova.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
SOURCE_DIR="$REPO_DIR/macos/NovaMenuBar/Sources"

if ! xcodebuild -version >/dev/null 2>&1; then
    echo "The Nova macOS app requires full Xcode to build the SwiftUI interface."
    echo "Install Xcode from the App Store, open it once, then run this script again."
    exit 1
fi

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$REPO_DIR/macos/NovaMenuBar/Info.plist" "$CONTENTS_DIR/Info.plist"
printf '%s\n' "$REPO_DIR" > "$RESOURCES_DIR/repo-path.txt"

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
    "$SOURCE_DIR/ContentView.swift" \
    "$SOURCE_DIR/NovaMenuBarApp.swift"

codesign --force --deep --sign - "$APP_DIR"
echo "Built $APP_DIR"
