import SwiftUI

private let novaPurple = Color(red: 0.60, green: 0.32, blue: 1.0)
private let novaCyan = Color(red: 0.15, green: 0.78, blue: 1.0)
private let panelBackground = Color.white.opacity(0.035)
private let panelBorder = Color(red: 0.55, green: 0.36, blue: 0.92).opacity(0.55)

struct ContentView: View {
    enum InterfaceMode: String, CaseIterable {
        case voice = "Voice"
        case chat = "Chat"
    }

    @EnvironmentObject private var engine: NovaEngine
    @StateObject private var calendarModel = CalendarModel()
    @StateObject private var loginItem = LoginItemManager()
    @AppStorage("nova.onboarding.completed.v1") private var onboardingCompleted = false
    @State private var showingOnboarding = false
    @State private var elevenLabsAPIKey = ""
    @State private var elevenLabsVoiceID = "GmM3ucvssIf0NWKHkiyc"
    @State private var mode: InterfaceMode = .voice
    @State private var input = ""
    @State private var showingSettings = false

    var body: some View {
        ZStack {
            atmosphericBackground

            HStack(spacing: 0) {
                glassNavigation

                VStack(spacing: 16) {
                    glassHeader

                    if showingSettings {
                        settingsView
                            .transition(.opacity.combined(with: .scale(scale: 0.985)))
                    } else {
                        HStack(spacing: 18) {
                            Group {
                                if mode == .voice {
                                    voiceCenter
                                } else {
                                    chatCenter
                                }
                            }
                            .id(mode)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .transition(.opacity.combined(with: .scale(scale: 0.985)))

                            glassCards
                                .frame(width: 270)
                        }
                    }

                    if !showingSettings, let action = engine.pendingAction {
                        ActionConfirmationCard(action: action)
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    if !showingSettings, mode == .voice {
                        floatingComposer
                    }
                }
                .padding(.leading, 22)
                .padding(.trailing, 24)
                .padding(.top, 34)
                .padding(.bottom, 22)
            }
        }
        .frame(minWidth: 840, idealWidth: 960, minHeight: 580, idealHeight: 660)
        .background(WindowCapture())
        .preferredColorScheme(.dark)
        .animation(.easeInOut(duration: 0.24), value: mode)
        .animation(.easeInOut(duration: 0.22), value: engine.pendingAction != nil)
        .sheet(
            isPresented: Binding(
                get: { !onboardingCompleted || showingOnboarding },
                set: { presented in
                    if !presented { showingOnboarding = false }
                }
            )
        ) {
            OnboardingView(
                engine: engine,
                calendarModel: calendarModel,
                loginItem: loginItem,
                onFinish: {
                    onboardingCompleted = true
                    showingOnboarding = false
                }
            )
            .interactiveDismissDisabled(!onboardingCompleted)
        }
    }

    private var atmosphericBackground: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.035, green: 0.05, blue: 0.16),
                    Color(red: 0.07, green: 0.055, blue: 0.20),
                    Color(red: 0.012, green: 0.018, blue: 0.055),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Circle()
                .fill(novaPurple.opacity(0.16))
                .frame(width: 520, height: 520)
                .blur(radius: 115)
                .offset(x: 300, y: -260)
            Circle()
                .fill(novaCyan.opacity(0.08))
                .frame(width: 420, height: 420)
                .blur(radius: 130)
                .offset(x: -360, y: 290)
        }
        .ignoresSafeArea()
    }

    private var glassNavigation: some View {
        VStack(spacing: 18) {
            MiniOrb()
                .scaleEffect(0.55)
                .frame(width: 32, height: 32)
                .padding(.top, 42)

            Spacer().frame(height: 20)

            glassNavButton(icon: "sparkles", selected: mode == .voice) {
                withAnimation {
                    showingSettings = false
                    mode = .voice
                }
            }
            glassNavButton(icon: "message", selected: mode == .chat) {
                withAnimation {
                    showingSettings = false
                    mode = .chat
                }
            }

            Divider()
                .overlay(Color.white.opacity(0.10))
                .padding(.horizontal, 17)

            glassNavButton(
                icon: "clock.arrow.circlepath",
                selected: !showingSettings && mode == .chat
            ) {
                withAnimation {
                    showingSettings = false
                    mode = .chat
                }
            }

            Spacer()

            glassNavButton(icon: "gearshape", selected: showingSettings) {
                withAnimation { showingSettings = true }
            }
                .padding(.bottom, 24)
        }
        .frame(width: 68)
        .background(.ultraThinMaterial)
        .overlay(alignment: .trailing) {
            Rectangle().fill(Color.white.opacity(0.08)).frame(width: 1)
        }
    }

    private func glassNavButton(
        icon: String,
        selected: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(selected ? Color.white : Color.secondary)
                .frame(width: 40, height: 40)
                .background(selected ? novaPurple.opacity(0.24) : .clear)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay {
                    if selected {
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(novaPurple.opacity(0.35), lineWidth: 1)
                    }
                }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(navigationLabel(for: icon))
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private func navigationLabel(for icon: String) -> String {
        switch icon {
        case "sparkles": return "Voice"
        case "message": return "Chat"
        case "clock.arrow.circlepath": return "Conversation history"
        case "gearshape": return "Settings"
        default: return "Navigation"
        }
    }

    private var glassHeader: some View {
        HStack {
            Text("Nova")
                .font(.system(size: 18, weight: .medium, design: .rounded))
            Spacer()
            Circle().fill(statusColor).frame(width: 7, height: 7)
            Text(engine.state.label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var glassCards: some View {
        VStack(spacing: 14) {
            GlassCard(icon: "calendar", title: "Today") {
                Text(calendarModel.nextEventTitle)
                    .font(.title3.weight(.medium))
                    .lineLimit(2)
                Text(
                    calendarModel.nextEventTime.isEmpty
                        ? "Connect Google Calendar"
                        : calendarModel.nextEventTime
                )
                .font(.caption)
                .foregroundStyle(.secondary)
                Spacer(minLength: 4)
                Button("Open calendar access", action: calendarModel.requestOrConnect)
                    .buttonStyle(.plain)
                    .font(.caption)
                    .foregroundStyle(novaCyan)
            }

            GlassCard(icon: "sparkles", title: "Suggested") {
                Text("Check your local weather")
                    .font(.title3.weight(.medium))
                Text(
                    engine.weather.summary.isEmpty
                        ? "Use your saved location for a live update."
                        : engine.weather.summary
                )
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(4)
                Spacer(minLength: 4)
                Button(action: engine.refreshWeather) {
                    Label(
                        engine.weather.isLoading ? "Loading…" : "Refresh weather",
                        systemImage: "arrow.right"
                    )
                }
                .buttonStyle(.plain)
                .font(.caption)
                .foregroundStyle(novaCyan)
                .disabled(!engine.dashboard.liveInformationEnabled || engine.weather.isLoading)
            }
        }
    }

    private var floatingComposer: some View {
        HStack(spacing: 12) {
            Image(systemName: "sparkles")
                .foregroundStyle(novaPurple)
            TextField("Message Nova…", text: $input)
                .textFieldStyle(.plain)
                .onSubmit(send)
            Button(action: send) {
                Image(systemName: "arrow.up")
                    .font(.system(size: 14, weight: .semibold))
                    .frame(width: 34, height: 34)
                    .background(
                        LinearGradient(
                            colors: [novaPurple, novaCyan],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Send message")
            .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !engine.state.isReady)
        }
        .padding(.horizontal, 17)
        .padding(.vertical, 10)
        .background(.ultraThinMaterial)
        .clipShape(Capsule())
        .overlay(Capsule().stroke(Color.white.opacity(0.16), lineWidth: 1))
        .frame(maxWidth: 600)
    }

    private var settingsView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Settings")
                        .font(.system(size: 30, weight: .semibold, design: .rounded))
                    Text("Your preferences stay on this Mac.")
                        .foregroundStyle(.secondary)
                }

                SettingsGroup(title: "Voice", icon: "waveform") {
                    SettingsToggle(
                        title: "Voice mode",
                        detail: "Allow microphone input and speech output.",
                        isOn: preferenceBinding("voice.enabled", value: engine.dashboard.voiceEnabled)
                    )
                    SettingsToggle(
                        title: "Speak responses",
                        detail: "Read Nova's answers aloud automatically.",
                        isOn: preferenceBinding("voice.auto_speak", value: engine.dashboard.autoSpeak)
                    )
                    SettingsToggle(
                        title: "Hands-free wake phrase",
                        detail: "Listen for \"\(engine.dashboard.wakePhrase)\" without saving audio.",
                        isOn: Binding(
                            get: { engine.dashboard.wakeEnabled },
                            set: { engine.setWakeEnabled($0) }
                        )
                    )
                    if !engine.wakeStatusMessage.isEmpty {
                        Label(
                            engine.wakeStatusMessage,
                            systemImage: engine.dashboard.wakeEnabled
                                ? "mic.fill"
                                : "mic.slash"
                        )
                        .font(.caption)
                        .foregroundStyle(
                            engine.dashboard.wakeEnabled ? novaCyan : .secondary
                        )
                    }
                    Picker(
                        "Voice output",
                        selection: Binding(
                            get: { engine.dashboard.outputProvider },
                            set: { engine.setVoiceProvider($0) }
                        )
                    ) {
                        Text("Built-in macOS").tag("macos")
                        Text("ElevenLabs custom voice").tag("elevenlabs")
                    }
                    .pickerStyle(.segmented)

                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("ElevenLabs custom voice")
                                Text(
                                    engine.dashboard.elevenLabsConfigured
                                        ? "API key stored securely in macOS Keychain."
                                        : "Connect your account without storing the key in Nova."
                                )
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Circle()
                                .fill(engine.dashboard.elevenLabsConfigured ? .green : .orange)
                                .frame(width: 8, height: 8)
                        }
                        TextField("Voice ID", text: $elevenLabsVoiceID)
                            .textFieldStyle(.roundedBorder)
                        SecureField(
                            engine.dashboard.elevenLabsConfigured
                                ? "New API key (leave blank to keep current key)"
                                : "ElevenLabs API key",
                            text: $elevenLabsAPIKey
                        )
                        .textFieldStyle(.roundedBorder)
                        HStack {
                            Button("Save custom voice") {
                                engine.configureElevenLabs(
                                    apiKey: elevenLabsAPIKey,
                                    voiceID: elevenLabsVoiceID
                                )
                                elevenLabsAPIKey = ""
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(novaPurple)
                            Button("Test voice") { engine.testVoice() }
                                .buttonStyle(.bordered)
                                .disabled(!engine.dashboard.elevenLabsConfigured)
                        }
                        if !engine.voiceOutputMessage.isEmpty {
                            Text(engine.voiceOutputMessage)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.top, 4)
                }

                SettingsGroup(title: "Privacy & memory", icon: "lock.shield") {
                    SettingsToggle(
                        title: "Save conversation episodes",
                        detail: "Keep useful past discussions for later recall.",
                        isOn: preferenceBinding("memory.episode_auto_save", value: engine.dashboard.episodeAutoSave)
                    )
                    SettingsToggle(
                        title: "Confirm new memories",
                        detail: "Ask before Nova stores a new personal fact.",
                        isOn: preferenceBinding("memory.confirm_semantic", value: engine.dashboard.confirmSemanticMemory)
                    )
                    SettingsToggle(
                        title: "Live information",
                        detail: "Allow Open-Meteo and approved factual sources.",
                        isOn: preferenceBinding("live.enabled", value: engine.dashboard.liveInformationEnabled)
                    )
                }

                SettingsGroup(title: "Actions", icon: "cursorarrow.click") {
                    SettingsToggle(
                        title: "Computer actions",
                        detail: "Actions still require confirmation before execution.",
                        isOn: preferenceBinding("actions.enabled", value: engine.dashboard.actionsEnabled)
                    )
                }

                SettingsGroup(title: "Local engine", icon: "cpu") {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Ollama model")
                            Text("Model switching remains managed by Nova Core.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(engine.dashboard.ollamaModel)
                            .font(.callout.monospaced())
                            .foregroundStyle(novaCyan)
                    }
                }

                SettingsGroup(title: "Setup", icon: "checklist") {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("First-launch guide")
                            Text("Review Nova Core, voice, calendar, and privacy.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button("Open setup") { showingOnboarding = true }
                            .buttonStyle(.bordered)
                    }
                }
            }
            .padding(.vertical, 10)
            .frame(maxWidth: 650, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func preferenceBinding(_ key: String, value: Bool) -> Binding<Bool> {
        Binding(
            get: { value },
            set: { engine.setPreference(key, enabled: $0) }
        )
    }

    private var voiceCenter: some View {
        VStack(spacing: 10) {
            Spacer(minLength: 0)
            NovaOrb(state: engine.state)
            HStack(spacing: 7) {
                Circle().fill(statusColor).frame(width: 9, height: 9)
                Text(engine.state.label).foregroundStyle(.secondary)
            }
            Button {
                if engine.dashboard.wakeEnabled {
                    engine.setWakeEnabled(false)
                } else {
                    engine.listen()
                }
            } label: {
                Image(systemName: engine.state == .listening ? "waveform" : "mic.fill")
                    .font(.system(size: 25))
                    .frame(width: 64, height: 64)
                    .background(.ultraThinMaterial)
                    .clipShape(Circle())
                    .overlay(Circle().stroke(LinearGradient(colors: [novaPurple, novaCyan], startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1.5))
                    .shadow(color: novaPurple.opacity(0.35), radius: 15)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(
                engine.dashboard.wakeEnabled
                    ? "Stop hands-free listening"
                    : engine.state == .listening ? "Listening" : "Start listening"
            )
            .disabled(!engine.state.isReady)
            Text(
                engine.state == .listening
                    ? engine.dashboard.wakeEnabled
                        ? "Say \"\(engine.dashboard.wakePhrase)\"…"
                        : "Listening…"
                    : engine.state == .speaking ? "Speaking…" : "Click to speak"
            )
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
        }
    }

    private var chatCenter: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 10) {
                        if engine.messages.isEmpty {
                            ContentUnavailableView(
                                "Ask Nova anything",
                                systemImage: "message.fill",
                                description: Text("Your local assistant is ready.")
                            )
                            .padding(.top, 90)
                        }
                        ForEach(engine.messages) { message in
                            MessageBubble(message: message).id(message.id)
                        }
                        if engine.state == .thinking {
                            HStack {
                                ProgressView().controlSize(.small)
                                Text("Nova is thinking…").foregroundStyle(.secondary)
                                Spacer()
                            }
                            .padding(.horizontal, 14)
                        }
                    }
                    .padding(.vertical, 12)
                }
                .onChange(of: engine.messages.count) {
                    guard let last = engine.messages.last else { return }
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            Divider().overlay(panelBorder)
            composer
        }
        .background(panelBackground)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(panelBorder, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var composer: some View {
        HStack(spacing: 10) {
            TextField("Message Nova", text: $input, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...3)
                .onSubmit(send)
            Button(action: engine.listen) {
                Image(systemName: "mic.fill")
            }
            .buttonStyle(.plain)
            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill").font(.title2)
            }
            .buttonStyle(.plain)
            .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !engine.state.isReady)
        }
        .padding(13)
    }

    private var statusColor: Color {
        switch engine.state {
        case .ready: return .green
        case .thinking, .listening, .speaking, .starting: return novaCyan
        case .unavailable: return .red
        }
    }


    private func send() {
        let message = input
        input = ""
        engine.sendMessage(message)
    }
}

private struct GlassCard<Content: View>: View {
    let icon: String
    let title: String
    @ViewBuilder let content: Content

    init(icon: String, title: String, @ViewBuilder content: () -> Content) {
        self.icon = icon
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: icon)
                .font(.caption.weight(.medium))
                .foregroundStyle(Color.white.opacity(0.72))
            Divider().overlay(Color.white.opacity(0.10))
            content
        }
        .padding(17)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(.ultraThinMaterial)
        .background(
            LinearGradient(
                colors: [Color.white.opacity(0.055), novaPurple.opacity(0.035)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(Color.white.opacity(0.16), lineWidth: 1)
        )
        .shadow(color: Color.black.opacity(0.22), radius: 22, y: 12)
    }
}

private struct SettingsGroup<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder let content: Content

    init(title: String, icon: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.icon = icon
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(title, systemImage: icon)
                .font(.headline)
                .foregroundStyle(novaPurple)
            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(Color.white.opacity(0.13), lineWidth: 1)
        )
    }
}

private struct SettingsToggle: View {
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
        .tint(novaPurple)
        .accessibilityHint(detail)
    }
}

private struct NovaOrb: View {
    let state: NovaEngine.State

    var body: some View {
        TimelineView(
            .periodic(
                from: .now,
                by: state == .listening || state == .thinking || state == .speaking
                    ? 1.0 / 20.0
                    : 1.0 / 10.0
            )
        ) { context in
            ReferenceOrbArtwork(
                phase: context.date.timeIntervalSinceReferenceDate,
                state: state
            )
        }
        .frame(width: 390, height: 224)
    }
}

private struct ReferenceOrbArtwork: View {
    let phase: TimeInterval
    let state: NovaEngine.State

    var body: some View {
        let listening = state == .listening
        let speaking = state == .speaking
        let active = listening || speaking || state == .thinking
        let breathWave = sin(phase * (active ? 3.6 : 1.55))
        let breathing = active
            ? 1 + 0.036 * breathWave
            : 1 + 0.022 * breathWave
        let breathGlow = 0.5 + 0.5 * breathWave
        let breathLift = CGFloat(-2.5 * breathGlow)
        let driftX = sin(phase * 0.45) * (active ? 2.6 : 1.2)
        let driftY = cos(phase * 0.38) * (active ? 2.0 : 0.8)
        let sweep = 0.5 + 0.5 * sin(phase * 0.7)

        ZStack {
            Ellipse()
                .fill(
                    RadialGradient(
                        colors: [novaPurple.opacity(active ? 0.20 : 0.11), novaCyan.opacity(0.035), .clear],
                        center: .center,
                        startRadius: 0,
                        endRadius: 175
                    )
                )
                .frame(
                    width: 360 + CGFloat(breathGlow * 14),
                    height: 218 + CGFloat(breathGlow * 9)
                )
                .blur(radius: 12 + breathGlow * 5)
                .opacity(0.72 + breathGlow * 0.28)

            orbImage
                .scaleEffect(breathing)
                .rotation3DEffect(
                    .degrees(driftY),
                    axis: (x: 1, y: 0, z: 0),
                    perspective: 0.38
                )
                .offset(y: breathLift)
                .brightness(breathGlow * 0.035)

            CoreEnergyAnimation(
                phase: phase,
                active: active,
                speaking: speaking
            )
                .rotation3DEffect(
                    .degrees(driftX),
                    axis: (x: 0, y: 1, z: 0),
                    perspective: 0.38
                )

            LinearGradient(
                colors: [
                    .clear,
                    Color.white.opacity(active ? 0.14 : 0.07),
                    novaCyan.opacity(active ? 0.10 : 0.045),
                    .clear,
                ],
                startPoint: UnitPoint(x: sweep - 0.35, y: 0.1),
                endPoint: UnitPoint(x: sweep + 0.35, y: 0.9)
            )
            .blendMode(.screen)
            .mask(
                Circle()
                    .frame(width: 208, height: 208)
                    .offset(x: -16)
            )
            .scaleEffect(breathing)

            Circle()
                .trim(from: 0.06, to: 0.28)
                .stroke(
                    LinearGradient(
                        colors: [.clear, .white.opacity(active ? 0.75 : 0.38), novaPurple, .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    ),
                    style: StrokeStyle(lineWidth: active ? 2.2 : 1.2, lineCap: .round)
                )
                .frame(width: 191, height: 191)
                .rotationEffect(.degrees(phase * (active ? 18 : 7)))
                .offset(x: -16)
                .blur(radius: active ? 1.2 : 0.5)
                .blendMode(.screen)

            Circle()
                .stroke(novaPurple.opacity(active ? 0.22 : 0.08), lineWidth: active ? 3 : 1)
                .frame(width: 205, height: 205)
                .offset(x: -16)
                .blur(radius: active ? 8 : 5)
                .scaleEffect(breathing)
                .opacity(0.55 + breathGlow * 0.45)

            if listening {
                ListeningOrbAnimation(phase: phase)
                    .transition(.opacity)
            }

            if speaking {
                SpeakingOrbAnimation(phase: phase)
                    .transition(.opacity.combined(with: .scale(scale: 0.9)))
            }
        }
        .frame(width: 390, height: 224)
        .offset(x: 13)
        .animation(.easeInOut(duration: 0.25), value: active)
    }

    @ViewBuilder
    private var orbImage: some View {
        if let url = Bundle.main.url(
            forResource: "nova-orb-transparent",
            withExtension: "png"
        ), let image = NSImage(contentsOf: url) {
            Image(nsImage: image)
                .resizable()
                .interpolation(.high)
                .antialiased(true)
                .aspectRatio(786.0 / 452.0, contentMode: .fit)
        } else {
            MiniOrb()
                .scaleEffect(3.8)
                .frame(width: 390, height: 224)
            }
    }
}

private struct CoreEnergyAnimation: View {
    let phase: TimeInterval
    let active: Bool
    let speaking: Bool

    var body: some View {
        let speed = speaking ? 2.2 : active ? 1.55 : 0.72
        let pulse = 0.5 + 0.5 * sin(phase * (active ? 4.4 : 2.0))
        let lightX = 0.42 + 0.12 * sin(phase * 0.65 * speed)
        let lightY = 0.44 + 0.10 * cos(phase * 0.52 * speed)

        ZStack {
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            novaCyan.opacity(0.10 + pulse * 0.12),
                            novaPurple.opacity(0.10),
                            .clear,
                        ],
                        center: UnitPoint(x: lightX, y: lightY),
                        startRadius: 0,
                        endRadius: 62
                    )
                )

            ForEach(0..<4, id: \.self) { index in
                Ellipse()
                    .trim(
                        from: 0.04 + Double(index) * 0.12,
                        to: 0.40 + Double(index) * 0.11
                    )
                    .stroke(
                        AngularGradient(
                            colors: [
                                .clear,
                                index.isMultiple(of: 2)
                                    ? novaPurple.opacity(0.34)
                                    : novaCyan.opacity(0.30),
                                Color.white.opacity(0.12),
                                .clear,
                            ],
                            center: .center
                        ),
                        style: StrokeStyle(
                            lineWidth: CGFloat(5 + index * 2),
                            lineCap: .round
                        )
                    )
                    .frame(
                        width: CGFloat(96 + index * 7),
                        height: CGFloat(68 + index * 9)
                    )
                    .rotationEffect(
                        .degrees(
                            phase * speed * (index.isMultiple(of: 2) ? 18 : -14)
                                + Double(index * 31)
                        )
                    )
                    .blur(radius: CGFloat(1.5 + Double(index) * 0.55))
                    .blendMode(.screen)
            }

            Circle()
                .fill(Color.white.opacity(0.06 + pulse * 0.08))
                .frame(width: 28 + pulse * 10, height: 28 + pulse * 10)
                .blur(radius: 12)
                .offset(
                    x: CGFloat(sin(phase * speed) * 13),
                    y: CGFloat(cos(phase * speed * 0.8) * 9)
                )
        }
        .frame(width: 126, height: 126)
        .clipShape(Circle())
        .offset(x: -16, y: 3)
        .opacity(active ? 0.88 : 0.62)
        .allowsHitTesting(false)
    }
}

private struct ListeningOrbAnimation: View {
    let phase: TimeInterval

    var body: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { index in
                let progress = (phase * 0.72 + Double(index) / 3.0)
                    .truncatingRemainder(dividingBy: 1)
                Circle()
                    .stroke(
                        LinearGradient(
                            colors: [novaCyan, novaPurple.opacity(0.45), .clear],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 2.2 - progress
                    )
                    .frame(width: 202, height: 202)
                    .scaleEffect(1 + progress * 0.34)
                    .opacity(0.72 * (1 - progress))
            }

            Circle()
                .trim(from: 0.08, to: 0.32)
                .stroke(novaCyan, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .frame(width: 211, height: 211)
                .rotationEffect(.degrees(phase * 48))
                .shadow(color: novaCyan, radius: 8)
        }
        .offset(x: -16)
    }
}

private struct SpeakingOrbAnimation: View {
    let phase: TimeInterval

    var body: some View {
        ZStack {
            Circle()
                .trim(from: 0.03, to: 0.46)
                .stroke(
                    AngularGradient(colors: [novaPurple, .white, novaCyan, .clear], center: .center),
                    style: StrokeStyle(lineWidth: 3.2, lineCap: .round)
                )
                .frame(width: 211, height: 211)
                .rotationEffect(.degrees(phase * 65))
                .shadow(color: novaPurple, radius: 9)

            HStack(spacing: 3) {
                ForEach(0..<17, id: \.self) { index in
                    let wave = abs(sin(phase * 7.5 + Double(index) * 0.72))
                    Capsule()
                        .fill(index.isMultiple(of: 2) ? novaPurple : novaCyan)
                        .frame(width: 3, height: 5 + wave * 25)
                        .shadow(
                            color: index.isMultiple(of: 2) ? novaPurple : novaCyan,
                            radius: 4
                        )
                }
            }
            .frame(width: 122, height: 34)
            .padding(.horizontal, 11)
            .padding(.vertical, 5)
            .background(Color.black.opacity(0.16))
            .clipShape(Capsule())
            .offset(y: 54)
        }
        .offset(x: -16)
    }
}

private struct MiniOrb: View {
    var body: some View {
        Circle()
            .stroke(AngularGradient(colors: [novaPurple, novaCyan, novaPurple], center: .center), lineWidth: 4)
            .frame(width: 43, height: 43)
            .shadow(color: novaPurple.opacity(0.7), radius: 8)
    }
}

private struct ActionConfirmationCard: View {
    @EnvironmentObject private var engine: NovaEngine
    let action: PendingAction

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "sparkles").foregroundStyle(novaPurple)
            VStack(alignment: .leading, spacing: 3) {
                Text("Confirm action").font(.caption).foregroundStyle(.secondary)
                Text(action.description).lineLimit(1)
            }
            Spacer()
            Button("Confirm", action: engine.confirmAction)
                .buttonStyle(.borderedProminent)
                .tint(novaPurple)
            Button("Cancel", action: engine.cancelAction)
                .buttonStyle(.bordered)
        }
        .padding(13)
        .background(panelBackground)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(panelBorder, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

private struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 60) }
            Text(message.text)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(message.role == .user ? novaPurple.opacity(0.24) : Color.white.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            if message.role != .user { Spacer(minLength: 60) }
        }
        .padding(.horizontal, 12)
    }
}

private struct WindowCapture: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            if let window = view.window { WindowCoordinator.shared.attach(window) }
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async {
            if let window = nsView.window { WindowCoordinator.shared.attach(window) }
        }
    }
}
