import Carbon

private func novaHotKeyHandler(
    _ nextHandler: EventHandlerCallRef?,
    _ event: EventRef?,
    _ userData: UnsafeMutableRawPointer?
) -> OSStatus {
    Task { @MainActor in
        WindowCoordinator.shared.show()
    }
    return noErr
}

final class GlobalHotKey {
    private var hotKey: EventHotKeyRef?
    private var eventHandler: EventHandlerRef?

    func register() {
        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        InstallEventHandler(
            GetApplicationEventTarget(),
            novaHotKeyHandler,
            1,
            &eventType,
            nil,
            &eventHandler
        )

        let identifier = EventHotKeyID(signature: 0x4E4F5641, id: 1)
        RegisterEventHotKey(
            UInt32(kVK_Space),
            UInt32(optionKey),
            identifier,
            GetApplicationEventTarget(),
            0,
            &hotKey
        )
    }

    func unregister() {
        if let hotKey { UnregisterEventHotKey(hotKey) }
        if let eventHandler { RemoveEventHandler(eventHandler) }
        hotKey = nil
        eventHandler = nil
    }

    deinit {
        unregister()
    }
}
