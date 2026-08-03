import ServiceManagement

@MainActor
final class LoginItemManager: ObservableObject {
    @Published private(set) var enabled: Bool
    @Published private(set) var errorMessage: String?

    init() {
        enabled = SMAppService.mainApp.status == .enabled
    }

    func setEnabled(_ shouldEnable: Bool) {
        errorMessage = nil
        do {
            if shouldEnable {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
            enabled = SMAppService.mainApp.status == .enabled
        } catch {
            enabled = SMAppService.mainApp.status == .enabled
            errorMessage = "Login setting failed: \(error.localizedDescription)"
        }
    }
}
