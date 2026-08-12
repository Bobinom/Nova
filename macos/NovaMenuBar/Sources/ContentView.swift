import SwiftUI

private let novaPurple = Color(red: 0.98, green: 0.03, blue: 0.06)
private let novaCyan = Color(red: 1.0, green: 0.30, blue: 0.30)
private let panelBackground = Color.white.opacity(0.035)
private let panelBorder = Color.white.opacity(0.18)
private let novaRed = Color(red: 1.0, green: 0.29, blue: 0.025)

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
    @State private var openAIAPIKey = ""
    @State private var mode: InterfaceMode = .voice
    @State private var input = ""
    @State private var newTaskTitle = ""
    @State private var showingSettings = false

    var body: some View {
        ZStack {
            atmosphericBackground
            if !showingSettings, mode == .voice {
                RedEnergyCore(state: engine.state)
                    .allowsHitTesting(false)
                    .ignoresSafeArea()
            }
            VStack(spacing: 12) {
                commandHeader
                Group {
                    if showingSettings {
                        settingsView
                    } else if mode == .chat {
                        chatCenter
                            .padding(.horizontal, 18)
                    } else {
                        commandDashboard
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                if !showingSettings, let action = engine.pendingAction {
                    ActionConfirmationCard(action: action)
                        .padding(.horizontal, 18)
                } else if !showingSettings, !engine.actionProgressMessage.isEmpty {
                    ActionProgressCard(message: engine.actionProgressMessage)
                        .padding(.horizontal, 18)
                }
                commandDock
            }
            .padding(18)
        }
        .frame(minWidth: 1040, idealWidth: 1280, minHeight: 680, idealHeight: 800)
        .background(WindowCapture())
        .preferredColorScheme(.dark)
        .animation(.easeInOut(duration: 0.24), value: mode)
        .animation(.easeInOut(duration: 0.22), value: engine.pendingAction != nil)
        .animation(.easeInOut(duration: 0.22), value: engine.actionProgressMessage)
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
            Color(red: 0.008, green: 0.012, blue: 0.013)
            GridBackground()
            RadialGradient(
                colors: [novaRed.opacity(0.08), .clear],
                center: .center,
                startRadius: 40,
                endRadius: 520
            )
        }
        .ignoresSafeArea()
    }

    private var commandHeader: some View {
        VStack(spacing: 8) {
            HStack {
                HStack(spacing: 9) {
                    Circle().fill(novaRed).frame(width: 7, height: 7)
                    Text("NOVA // COMMAND INTERFACE")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .tracking(2.4)
                }
                Spacer()
                Text(engine.dashboard.effectiveProvider.uppercased())
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                Circle().fill(statusColor).frame(width: 7, height: 7)
                Text(engine.state.label.uppercased())
                    .font(.caption2.monospaced())
            }
            .padding(.horizontal, 14)
            Rectangle()
                .fill(novaRed)
                .frame(height: 10)
                .shadow(color: novaRed.opacity(0.9), radius: 9)
                .overlay(Rectangle().stroke(Color.white.opacity(0.6), lineWidth: 1))
        }
        .padding(10)
        .background(Color.black.opacity(0.66))
        .modifier(TechFrame())
    }

    private var commandDashboard: some View {
        HStack(alignment: .top, spacing: 18) {
            taskCommandPanel.frame(width: 270)
            coreCommandCenter
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            calendarCommandPanel.frame(width: 270)
        }
        .padding(14)
        .background(Color.black.opacity(0.28))
        .modifier(TechFrame())
    }

    private var taskCommandPanel: some View {
        CommandPanel(title: "TASKS", count: engine.dashboard.tasks.count) {
            if engine.dashboard.tasks.isEmpty {
                Text("NO ACTIVE TASKS")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 18)
            } else {
                ForEach(engine.dashboard.tasks.prefix(5)) { task in
                    Button { engine.completeTask(task.id) } label: {
                        HStack(alignment: .top, spacing: 9) {
                            Circle().fill(novaRed).frame(width: 5, height: 5).padding(.top, 6)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(task.title).font(.callout).lineLimit(2)
                                Text(task.project.uppercased())
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                    }
                    .buttonStyle(.plain)
                    Divider().overlay(Color.white.opacity(0.10))
                }
            }
            HStack {
                TextField("Add task…", text: $newTaskTitle).textFieldStyle(.plain).onSubmit(addTask)
                Button(action: addTask) { Image(systemName: "plus") }
                    .buttonStyle(.plain).foregroundStyle(novaRed)
            }
            .padding(9)
            .background(Color.black.opacity(0.45))
            .overlay(Rectangle().stroke(Color.white.opacity(0.13)))
        }
    }

    private var calendarCommandPanel: some View {
        CommandPanel(title: "CALENDAR", count: calendarModel.nextEventTitle.isEmpty ? 0 : 1) {
            HStack(alignment: .top, spacing: 9) {
                Circle().fill(novaRed).frame(width: 5, height: 5).padding(.top, 6)
                VStack(alignment: .leading, spacing: 5) {
                    Text(calendarModel.nextEventTitle.isEmpty ? "Calendar offline" : calendarModel.nextEventTitle)
                        .font(.callout).lineLimit(3)
                    Text(calendarModel.nextEventTime.isEmpty ? "CONNECT GOOGLE CALENDAR" : calendarModel.nextEventTime.uppercased())
                        .font(.caption2.monospaced()).foregroundStyle(.secondary)
                }
                Spacer()
            }
            Divider().overlay(Color.white.opacity(0.10))
            Button("OPEN CALENDAR ACCESS", action: calendarModel.requestOrConnect)
                .buttonStyle(.plain)
                .font(.caption2.monospaced())
                .foregroundStyle(novaRed)
        }
    }

    private var coreCommandCenter: some View {
        VStack(spacing: 4) {
            Color.clear
                .frame(width: 420, height: 350)
                .contentShape(Circle())
                .onTapGesture { if engine.state.isReady { engine.listen() } }
            HStack(spacing: 8) {
                Circle().fill(statusColor).frame(width: 7, height: 7)
                Text("NOVA (engine.state.label.uppercased())")
                    .font(.caption.monospaced()).tracking(2)
            }
            .foregroundStyle(.secondary)
            floatingComposer
                .padding(.top, 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
    }

    private var commandDock: some View {
        HStack(spacing: 16) {
            DockButton(icon: "waveform", active: !showingSettings && mode == .voice) {
                showingSettings = false; mode = .voice
            }
            DockButton(icon: "message.fill", active: !showingSettings && mode == .chat) {
                showingSettings = false; mode = .chat
            }
            DockButton(icon: "mic.fill", active: engine.state == .listening) { engine.listen() }
            DockButton(icon: "calendar", active: false) { calendarModel.requestOrConnect() }
            DockButton(icon: "gearshape.fill", active: showingSettings) { showingSettings = true }
            Spacer()
            Text("MEM (engine.dashboard.memories)  //  V(engine.dashboard.version)")
                .font(.caption2.monospaced()).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
        .background(Color.black.opacity(0.72))
        .modifier(TechFrame())
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

            GlassCard(icon: "checklist", title: "Tasks") {
                if engine.dashboard.agentStatus != "idle" {
                    Text(engine.dashboard.agentObjective)
                        .font(.caption.weight(.semibold))
                        .lineLimit(1)
                    Text("\(engine.dashboard.agentStatus.capitalized) • \(engine.dashboard.agentProgress)")
                        .font(.caption2)
                        .foregroundStyle(novaCyan)
                }
                if engine.dashboard.tasks.isEmpty {
                    Text("Your workspace is clear")
                        .font(.title3.weight(.medium))
                    Text("Add a task for Nova to track locally.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(engine.dashboard.tasks.prefix(3)) { task in
                        Button {
                            engine.completeTask(task.id)
                        } label: {
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: task.status == "in_progress" ? "circle.dotted" : "circle")
                                    .foregroundStyle(novaCyan)
                                Text(task.title)
                                    .font(.caption)
                                    .lineLimit(2)
                                Spacer(minLength: 0)
                            }
                        }
                        .buttonStyle(.plain)
                        .help("Mark task complete")
                    }
                }
                Spacer(minLength: 4)
                HStack(spacing: 7) {
                    TextField("New task…", text: $newTaskTitle)
                        .textFieldStyle(.plain)
                        .onSubmit(addTask)
                    Button(action: addTask) {
                        Image(systemName: "plus.circle.fill")
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(novaPurple)
                    .disabled(newTaskTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                .padding(8)
                .background(Color.white.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 9))
            }
        }
    }

    private func addTask() {
        let title = newTaskTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return }
        engine.addTask(title)
        newTaskTitle = ""
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
                    SettingsToggle(
                        title: "Natural follow-up conversation",
                        detail: "Keep listening briefly after each answer, without repeating the wake phrase.",
                        isOn: preferenceBinding(
                            "voice.follow_up_enabled",
                            value: engine.dashboard.followUpEnabled
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

                SettingsGroup(title: "Personality", icon: "theatermasks") {
                    Picker(
                        "Nova's style",
                        selection: Binding(
                            get: { engine.dashboard.personality },
                            set: { engine.setPersonality($0) }
                        )
                    ) {
                        Text("Concise").tag("concise")
                        Text("Warm").tag("warm")
                        Text("Jarvis").tag("jarvis")
                    }
                    .pickerStyle(.segmented)
                    Text(
                        "Jarvis is composed, perceptive, capable, and subtly witty—without pretending Nova completed actions it could not verify."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                SettingsGroup(title: "Nova brain", icon: "brain.head.profile") {
                    Picker(
                        "Processing mode",
                        selection: Binding(
                            get: { engine.dashboard.brainMode },
                            set: { engine.setBrainMode($0) }
                        )
                    ) {
                        Text("Local").tag("local")
                        Text("Hybrid").tag("hybrid")
                        Text("Cloud").tag("cloud")
                    }
                    .pickerStyle(.segmented)
                    Text(
                        engine.dashboard.brainMode == "local"
                            ? "Private and offline through Ollama."
                            : "OpenAI handles conversation; Nova keeps actions, permissions, and memory storage on this Mac."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("OpenAI cloud brain")
                            Text(
                                engine.dashboard.cloudConfigured
                                    ? "API key stored securely in macOS Keychain."
                                    : "Connect an API key to enable Hybrid and Cloud modes."
                            )
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Circle()
                            .fill(engine.dashboard.cloudConfigured ? .green : .orange)
                            .frame(width: 8, height: 8)
                    }
                    SecureField(
                        engine.dashboard.cloudConfigured
                            ? "New API key (leave blank to keep current key)"
                            : "OpenAI API key",
                        text: $openAIAPIKey
                    )
                    .textFieldStyle(.roundedBorder)
                    Button("Connect OpenAI") {
                        engine.configureOpenAI(apiKey: openAIAPIKey)
                        openAIAPIKey = ""
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(novaPurple)
                    .disabled(openAIAPIKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Text("Active: \(engine.dashboard.effectiveProvider.capitalized) • \(engine.dashboard.cloudModel)")
                        .font(.caption.monospaced())
                        .foregroundStyle(novaCyan)
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

private struct GridBackground: View {
    var body: some View {
        Canvas { context, size in
            let spacing: CGFloat = 24
            var path = Path()
            stride(from: 0, through: size.width, by: spacing).forEach { x in
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
            }
            stride(from: 0, through: size.height, by: spacing).forEach { y in
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
            }
            context.stroke(path, with: .color(Color.white.opacity(0.025)), lineWidth: 0.5)
        }
        .allowsHitTesting(false)
    }
}

private struct TechFrame: ViewModifier {
    func body(content: Content) -> some View {
        content
            .overlay(Rectangle().stroke(Color.white.opacity(0.20), lineWidth: 1))
            .overlay(alignment: .topLeading) {
                HStack(spacing: 3) {
                    Rectangle().fill(novaRed).frame(width: 26, height: 2)
                    Rectangle().fill(Color.white.opacity(0.36)).frame(width: 12, height: 2)
                }
                .padding(5)
            }
            .shadow(color: Color.black.opacity(0.65), radius: 18, y: 8)
    }
}

private struct CommandPanel<Content: View>: View {
    let title: String
    let count: Int
    @ViewBuilder let content: Content

    init(title: String, count: Int, @ViewBuilder content: () -> Content) {
        self.title = title
        self.count = count
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack {
                Text(title).font(.system(size: 13, weight: .medium, design: .monospaced))
                Spacer()
                Text("\(count)").font(.caption.monospaced()).foregroundStyle(.secondary)
            }
            Rectangle().fill(novaRed.opacity(0.65)).frame(height: 1)
            content
            Spacer(minLength: 0)
        }
        .padding(15)
        .frame(maxWidth: .infinity, maxHeight: 330, alignment: .topLeading)
        .background(Color(red: 0.035, green: 0.045, blue: 0.047).opacity(0.92))
        .modifier(TechFrame())
    }
}

private struct DockButton: View {
    let icon: String
    let active: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(active ? novaRed : Color.white.opacity(0.82))
                .frame(width: 43, height: 43)
                .background(Color.black.opacity(0.7))
                .clipShape(Circle())
                .overlay(Circle().stroke(active ? novaRed : Color.white.opacity(0.55), lineWidth: active ? 2 : 1))
                .shadow(color: active ? novaRed.opacity(0.75) : .clear, radius: 9)
        }
        .buttonStyle(.plain)
    }
}

private struct RedEnergyCore: View {
    let state: NovaEngine.State

    var body: some View {
        GeometryReader { geometry in
            TimelineView(.animation(minimumInterval: 1.0 / 24.0)) { timeline in
                let phase = timeline.date.timeIntervalSinceReferenceDate
                let visuals = visuals(at: phase)
                ZStack {
                    if state == .listening {
                        listeningWaves(at: phase, size: geometry.size)
                    }
                    coreImage
                        .frame(width: geometry.size.width, height: geometry.size.height)
                        .scaleEffect(visuals.scale)
                        .rotationEffect(.degrees(visuals.rotation))
                        .rotation3DEffect(
                            .degrees(sin(phase * visuals.tiltSpeed) * visuals.tilt),
                            axis: (x: 0, y: 1, z: 0),
                            perspective: 0.35
                        )
                        .brightness(visuals.brightness)
                        .saturation(visuals.saturation)
                        .shadow(color: novaRed.opacity(visuals.glowOpacity), radius: visuals.glowRadius)
                }
            }
        }
    }

    private func visuals(at phase: TimeInterval) -> CoreVisuals {
        switch state {
        case .ready:
            return CoreVisuals(
                scale: 1 + sin(phase * 1.25) * 0.018,
                rotation: sin(phase * 0.18) * 1.2,
                tilt: 1.8, tiltSpeed: 0.3,
                brightness: 0, saturation: 0.96,
                glowOpacity: 0.32, glowRadius: 12
            )
        case .listening:
            return CoreVisuals(
                scale: 1.03 + sin(phase * 4.4) * 0.038,
                rotation: sin(phase * 0.5) * 2,
                tilt: 3.2, tiltSpeed: 0.7,
                brightness: 0.13, saturation: 1.18,
                glowOpacity: 0.9, glowRadius: 34
            )
        case .thinking:
            return CoreVisuals(
                scale: 1.01 + sin(phase * 5.8) * 0.022,
                rotation: phase * 7.5,
                tilt: 5.5, tiltSpeed: 1.25,
                brightness: 0.08, saturation: 1.08,
                glowOpacity: 0.72, glowRadius: 24
            )
        case .speaking:
            let voicePulse = (sin(phase * 9.0) + sin(phase * 14.0) * 0.45) / 1.45
            return CoreVisuals(
                scale: 1.035 + voicePulse * 0.055,
                rotation: sin(phase * 0.9) * 3,
                tilt: 4, tiltSpeed: 0.85,
                brightness: 0.12 + voicePulse * 0.035,
                saturation: 1.22,
                glowOpacity: 0.92, glowRadius: 38 + voicePulse * 7
            )
        case .starting, .unavailable:
            return CoreVisuals(
                scale: 0.98, rotation: 0,
                tilt: 0, tiltSpeed: 0,
                brightness: -0.16, saturation: 0.45,
                glowOpacity: 0.12, glowRadius: 6
            )
        }
    }

    private func listeningWaves(at phase: TimeInterval, size: CGSize) -> some View {
        let diameter = min(size.width, size.height) * 0.48
        return ZStack {
            ForEach(0..<3, id: \.self) { index in
                let progress = (phase * 0.55 + Double(index) / 3).truncatingRemainder(dividingBy: 1)
                Circle()
                    .stroke(novaRed.opacity(0.42 * (1 - progress)), lineWidth: 2)
                    .frame(width: diameter, height: diameter)
                    .scaleEffect(1 + progress * 1.45)
            }
        }
    }

    @ViewBuilder
    private var coreImage: some View {
        if let directory = Bundle.main.resourceURL?.appendingPathComponent(
            "nova-red-particle-frames",
            isDirectory: true
        ) {
            AnimatedFrameView(directory: directory, frameCount: 68, framesPerSecond: 50.0 / 3.0)
                .scaledToFit()
        } else {
            Circle().fill(novaRed).frame(width: 220, height: 220)
        }
    }
}

private struct CoreVisuals {
    let scale: CGFloat
    let rotation: Double
    let tilt: Double
    let tiltSpeed: Double
    let brightness: Double
    let saturation: Double
    let glowOpacity: Double
    let glowRadius: CGFloat
}

private struct AnimatedFrameView: View {
    @StateObject private var frameStore: AnimationFrameStore
    let frameCount: Int
    let framesPerSecond: Double

    init(directory: URL, frameCount: Int, framesPerSecond: Double) {
        _frameStore = StateObject(
            wrappedValue: AnimationFrameStore(directory: directory, frameCount: frameCount)
        )
        self.frameCount = frameCount
        self.framesPerSecond = framesPerSecond
    }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1.0 / framesPerSecond)) { context in
            let frameIndex = Int(
                context.date.timeIntervalSinceReferenceDate * framesPerSecond
            ) % max(frameStore.frames.count, 1)
            if frameStore.frames.indices.contains(frameIndex) {
                let image = frameStore.frames[frameIndex]
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
            }
        }
    }
}

@MainActor
private final class AnimationFrameStore: ObservableObject {
    let frames: [NSImage]

    init(directory: URL, frameCount: Int) {
        frames = (1...frameCount).compactMap { frame in
            let url = directory.appendingPathComponent(
                String(format: "core-%03d.png", frame)
            )
            return NSImage(contentsOf: url)
        }
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

private struct ActionProgressCard: View {
    let message: String

    var body: some View {
        HStack(spacing: 12) {
            ProgressView()
                .controlSize(.small)
                .tint(novaCyan)
            Text(message)
                .font(.callout)
                .lineLimit(1)
            Spacer()
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
