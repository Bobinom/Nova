import SwiftUI

private let setupPurple = Color(red: 0.60, green: 0.32, blue: 1.0)
private let setupCyan = Color(red: 0.15, green: 0.78, blue: 1.0)

struct OnboardingView: View {
    @ObservedObject var engine: NovaEngine
    @ObservedObject var calendarModel: CalendarModel
    @ObservedObject var loginItem: LoginItemManager
    let onFinish: () -> Void

    @State private var step = 0

    private let stepCount = 5

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.025, green: 0.035, blue: 0.11),
                    Color(red: 0.075, green: 0.045, blue: 0.18),
                    Color(red: 0.012, green: 0.018, blue: 0.05),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            Circle()
                .fill(setupPurple.opacity(0.18))
                .frame(width: 430, height: 430)
                .blur(radius: 105)
                .offset(x: 260, y: -220)

            VStack(spacing: 0) {
                header
                Group {
                    switch step {
                    case 0: welcome
                    case 1: coreSetup
                    case 2: voiceSetup
                    case 3: calendarSetup
                    default: privacySetup
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                footer
            }
            .padding(34)
        }
        .frame(width: 720, height: 560)
        .preferredColorScheme(.dark)
    }

    private var header: some View {
        HStack {
            Label("NOVA SETUP", systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .tracking(2.5)
                .foregroundStyle(setupCyan)
            Spacer()
            Text("\(step + 1) of \(stepCount)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private var footer: some View {
        HStack {
            Button("Back") {
                withAnimation { step -= 1 }
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .opacity(step == 0 ? 0 : 1)
            .disabled(step == 0)

            Spacer()

            HStack(spacing: 7) {
                ForEach(0..<stepCount, id: \.self) { index in
                    Capsule()
                        .fill(index == step ? setupCyan : Color.white.opacity(0.16))
                        .frame(width: index == step ? 24 : 7, height: 7)
                }
            }

            Spacer()

            Button(step == stepCount - 1 ? "Finish" : "Continue") {
                if step == stepCount - 1 {
                    onFinish()
                } else {
                    withAnimation { step += 1 }
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(setupPurple)
            .keyboardShortcut(.defaultAction)
        }
        .padding(.top, 18)
    }

    private var welcome: some View {
        SetupPage(
            icon: "sparkles",
            title: "Welcome to Nova",
            subtitle: "Let’s make your private, local assistant ready for everyday use. This takes about a minute."
        ) {
            HStack(spacing: 14) {
                FeatureChip(icon: "lock.shield", text: "Private by design")
                FeatureChip(icon: "waveform", text: "Voice ready")
                FeatureChip(icon: "desktopcomputer", text: "Built for your Mac")
            }
        }
    }

    private var coreSetup: some View {
        SetupPage(
            icon: "cpu",
            title: "Nova Core",
            subtitle: "Nova runs its intelligence and memory locally on this Mac."
        ) {
            VStack(spacing: 12) {
                CheckRow(
                    title: "Local engine",
                    detail: engine.state.isAvailable ? "Connected" : "Needs attention",
                    ready: engine.state.isAvailable
                )
                CheckRow(
                    title: "Memory database",
                    detail: engine.dashboard.databaseHealthy ? "Healthy" : "Checking…",
                    ready: engine.dashboard.databaseHealthy
                )
                CheckRow(
                    title: "Ollama model",
                    detail: engine.dashboard.ollamaModel,
                    ready: engine.state.isAvailable
                )
                if case let .unavailable(message) = engine.state {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(.orange)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

    private var voiceSetup: some View {
        SetupPage(
            icon: "waveform",
            title: "Talk with Nova",
            subtitle: "Microphone access is used only when you click to speak or enable a listening mode."
        ) {
            VStack(spacing: 14) {
                SetupToggle(
                    title: "Enable voice input",
                    detail: "Turn speech recognition on for Nova.",
                    isOn: Binding(
                        get: { engine.dashboard.voiceEnabled },
                        set: { engine.setPreference("voice.enabled", enabled: $0) }
                    )
                )
                Button {
                    if !engine.dashboard.voiceEnabled {
                        engine.setPreference("voice.enabled", enabled: true)
                    }
                    engine.setupVoice()
                } label: {
                    Label("Check microphone access", systemImage: "mic.badge.plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(setupPurple)

                if !engine.voiceSetupMessage.isEmpty {
                    Text(engine.voiceSetupMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text("Language: \(engine.dashboard.voiceLocale)  •  Listening: \(engine.dashboard.listenSeconds)s  •  \(engine.dashboard.recognitionMode)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var calendarSetup: some View {
        SetupPage(
            icon: "calendar",
            title: "Connect Google Calendar",
            subtitle: "Nova reads Google calendars already connected to macOS. Calendar access is optional."
        ) {
            VStack(spacing: 14) {
                CheckRow(
                    title: "Calendar access",
                    detail: calendarModel.googleConnected
                        ? "Google Calendar connected"
                        : calendarModel.accessGranted
                            ? "Add Google in Internet Accounts"
                            : "Not connected",
                    ready: calendarModel.googleConnected
                )
                Button {
                    calendarModel.requestOrConnect()
                } label: {
                    Label("Allow calendar access", systemImage: "calendar.badge.plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(setupPurple)
                Text("You can skip this and connect later from Nova’s Today card.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var privacySetup: some View {
        SetupPage(
            icon: "checkmark.shield",
            title: "Choose how Nova works",
            subtitle: "These choices can be changed anytime in Settings. Sensitive actions still require confirmation."
        ) {
            VStack(spacing: 12) {
                SetupToggle(
                    title: "Remember useful conversations",
                    detail: "Save selected discussions for future context.",
                    isOn: preferenceBinding(
                        "memory.episode_auto_save",
                        engine.dashboard.episodeAutoSave
                    )
                )
                SetupToggle(
                    title: "Ask before saving personal facts",
                    detail: "You approve new semantic memories.",
                    isOn: preferenceBinding(
                        "memory.confirm_semantic",
                        engine.dashboard.confirmSemanticMemory
                    )
                )
                SetupToggle(
                    title: "Live information",
                    detail: "Allow weather and approved factual sources.",
                    isOn: preferenceBinding(
                        "live.enabled",
                        engine.dashboard.liveInformationEnabled
                    )
                )
                SetupToggle(
                    title: "Computer actions",
                    detail: "Enable confirmed actions such as opening apps.",
                    isOn: preferenceBinding(
                        "actions.enabled",
                        engine.dashboard.actionsEnabled
                    )
                )
                SetupToggle(
                    title: "Launch Nova when you sign in",
                    detail: "Keep Nova available from the menu bar.",
                    isOn: Binding(
                        get: { loginItem.enabled },
                        set: { loginItem.setEnabled($0) }
                    )
                )
            }
        }
    }

    private func preferenceBinding(_ key: String, _ value: Bool) -> Binding<Bool> {
        Binding(
            get: { value },
            set: { engine.setPreference(key, enabled: $0) }
        )
    }
}

private struct SetupPage<Content: View>: View {
    let icon: String
    let title: String
    let subtitle: String
    @ViewBuilder let content: Content

    init(
        icon: String,
        title: String,
        subtitle: String,
        @ViewBuilder content: () -> Content
    ) {
        self.icon = icon
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 22) {
            Image(systemName: icon)
                .font(.system(size: 34, weight: .light))
                .foregroundStyle(
                    LinearGradient(
                        colors: [setupPurple, setupCyan],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 76, height: 76)
                .background(.ultraThinMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            VStack(spacing: 9) {
                Text(title)
                    .font(.system(size: 30, weight: .semibold, design: .rounded))
                Text(subtitle)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 510)
            }
            content
                .frame(maxWidth: 520)
        }
        .padding(.top, 22)
    }
}

private struct CheckRow: View {
    let title: String
    let detail: String
    let ready: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: ready ? "checkmark.circle.fill" : "clock.fill")
                .foregroundStyle(ready ? .green : .orange)
            Text(title)
            Spacer()
            Text(detail)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(Color.white.opacity(0.055))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct SetupToggle: View {
    let title: String
    let detail: String
    @Binding var isOn: Bool

    var body: some View {
        Toggle(isOn: $isOn) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .toggleStyle(.switch)
        .tint(setupPurple)
        .padding(12)
        .background(Color.white.opacity(0.045))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct FeatureChip: View {
    let icon: String
    let text: String

    var body: some View {
        Label(text, systemImage: icon)
            .font(.caption)
            .padding(.horizontal, 13)
            .padding(.vertical, 9)
            .background(Color.white.opacity(0.06))
            .clipShape(Capsule())
    }
}
