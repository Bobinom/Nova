import AppKit
import SwiftUI

@main
struct NovaMenuBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var engine = NovaEngine()
    @StateObject private var loginItem = LoginItemManager()

    var body: some Scene {
        WindowGroup("Nova", id: "chat") {
            ContentView().environmentObject(engine)
        }
        .defaultSize(width: 940, height: 640)

        MenuBarExtra("Nova", systemImage: "sparkles") {
            NovaMenu(engine: engine, loginItem: loginItem)
        }
    }
}

private struct NovaMenu: View {
    @ObservedObject var engine: NovaEngine
    @ObservedObject var loginItem: LoginItemManager

    var body: some View {
        Button("Open Nova") {
            WindowCoordinator.shared.show()
        }
        .keyboardShortcut(.space, modifiers: .option)
        Divider()
        Label(engine.state.label, systemImage: engine.state.isReady ? "checkmark.circle" : "circle.dotted")
        Toggle(
            "Launch at Login",
            isOn: Binding(
                get: { loginItem.enabled },
                set: { loginItem.setEnabled($0) }
            )
        )
        if let error = loginItem.errorMessage {
            Text(error)
        }
        Divider()
        Button("Quit Nova") {
            engine.stop()
            NSApp.terminate(nil)
        }
        .keyboardShortcut("q")
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let hotKey = GlobalHotKey()

    func applicationDidFinishLaunching(_ notification: Notification) {
        hotKey.register()
    }

    func applicationWillTerminate(_ notification: Notification) {
        hotKey.unregister()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}
