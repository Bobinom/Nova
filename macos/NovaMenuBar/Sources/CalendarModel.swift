import AppKit
import EventKit
import Foundation

@MainActor
final class CalendarModel: ObservableObject {
    @Published private(set) var accessGranted = false
    @Published private(set) var googleConnected = false
    @Published private(set) var nextEventTitle = "Google Calendar access off"
    @Published private(set) var nextEventTime = ""

    let store = EKEventStore()

    init() {
        refreshAuthorization()
    }

    func requestOrConnect() {
        if accessGranted {
            openInternetAccounts()
            return
        }
        if #available(macOS 14.0, *) {
            store.requestFullAccessToEvents { [weak self] granted, _ in
                Task { @MainActor in self?.applyAccess(granted) }
            }
        } else {
            store.requestAccess(to: .event) { [weak self] granted, _ in
                Task { @MainActor in self?.applyAccess(granted) }
            }
        }
    }

    private func refreshAuthorization() {
        let status = EKEventStore.authorizationStatus(for: .event)
        let granted: Bool
        if #available(macOS 14.0, *) {
            granted = status == .fullAccess
        } else {
            granted = status == .authorized
        }
        applyAccess(granted)
    }

    private func applyAccess(_ granted: Bool) {
        accessGranted = granted
        guard granted else {
            googleConnected = false
            nextEventTitle = "Allow Google Calendar"
            nextEventTime = ""
            return
        }
        let calendars = googleCalendars()
        googleConnected = !calendars.isEmpty
        guard googleConnected else {
            nextEventTitle = "Connect Google Calendar"
            nextEventTime = "Open Internet Accounts"
            return
        }
        let now = Date()
        let end = Calendar.current.date(byAdding: .day, value: 30, to: now) ?? now
        let events = store.events(
            matching: store.predicateForEvents(
                withStart: now,
                end: end,
                calendars: calendars
            )
        )
        if let event = events.first {
            nextEventTitle = event.title ?? "Calendar event"
            nextEventTime = event.startDate.formatted(
                date: .abbreviated,
                time: .shortened
            )
        } else {
            nextEventTitle = "No upcoming events"
            nextEventTime = "Next 30 days"
        }
    }

    private func googleCalendars() -> [EKCalendar] {
        store.calendars(for: .event).filter { calendar in
            guard let source = calendar.source else { return false }
            let name = source.title.lowercased()
            if name.contains("google") || name.contains("gmail") {
                return true
            }
            return source.sourceType == .calDAV
                && name != "icloud"
                && name != "caldav"
        }
    }

    private func openInternetAccounts() {
        guard let url = URL(
            string: "x-apple.systempreferences:com.apple.Internet-Accounts-Settings.extension"
        ) else { return }
        NSWorkspace.shared.open(url)
    }
}
