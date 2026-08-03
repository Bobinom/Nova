import AppKit
import SwiftUI

@main
struct NovaMenuBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var engine = NovaEngine()

    var body: some Scene {
        WindowGroup("Nova", id: "chat") {
            ContentView().environmentObject(engine)
        }
        .defaultSize(width: 620, height: 640)

        MenuBarExtra("Nova", systemImage: "sparkles") {
            NovaMenu(engine: engine)
        }
    }
}

private struct NovaMenu: View {
    @Environment(\.openWindow) private var openWindow
    @ObservedObject var engine: NovaEngine

    var body: some View {
        Button("Open Nova") {
            NSApp.activate(ignoringOtherApps: true)
            openWindow(id: "chat")
        }
        Divider()
        Label(engine.state.label, systemImage: engine.state.isReady ? "checkmark.circle" : "circle.dotted")
        Divider()
        Button("Quit Nova") {
            engine.stop()
            NSApp.terminate(nil)
        }
        .keyboardShortcut("q")
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}
