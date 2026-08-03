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
    @StateObject private var systemMonitor = SystemMonitor()
    @StateObject private var calendarModel = CalendarModel()
    @State private var mode: InterfaceMode = .voice
    @State private var input = ""

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.018, green: 0.025, blue: 0.055),
                    Color(red: 0.025, green: 0.035, blue: 0.075),
                    Color.black,
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(spacing: 10) {
                topBar
                HStack(alignment: .top, spacing: 12) {
                    leftColumn
                    centerColumn
                    rightColumn
                }
                bottomStatus
            }
            .padding(12)
        }
        .frame(minWidth: 860, idealWidth: 940, minHeight: 580, idealHeight: 640)
        .background(WindowCapture())
        .preferredColorScheme(.dark)
    }

    private var topBar: some View {
        HStack {
            HStack(spacing: 12) {
                MiniOrb()
                VStack(alignment: .leading, spacing: 2) {
                    Text("NOVA")
                        .font(.system(size: 20, weight: .medium, design: .rounded))
                        .tracking(5)
                    Text("PERSONAL ASSISTANT")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .tracking(1.5)
                }
            }
            Spacer()
            TimelineView(.periodic(from: .now, by: 1)) { context in
                VStack(alignment: .trailing, spacing: 2) {
                    Text(context.date.formatted(date: .complete, time: .omitted).uppercased())
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(context.date.formatted(date: .omitted, time: .standard))
                        .font(.system(size: 19, weight: .light, design: .monospaced))
                        .foregroundStyle(novaCyan)
                }
            }
        }
        .padding(.horizontal, 15)
        .padding(.vertical, 8)
        .background(panelBackground)
        .overlay(alignment: .bottom) {
            LinearGradient(colors: [.clear, novaPurple, novaCyan, .clear], startPoint: .leading, endPoint: .trailing)
                .frame(height: 1)
        }
        .clipShape(CutCornerShape(cut: 16))
    }

    private var leftColumn: some View {
        VStack(spacing: 10) {
            DashboardPanel(title: "GOOGLE CALENDAR", icon: "calendar") {
                MonthGrid()
                Divider().overlay(panelBorder)
                Button(action: calendarModel.requestOrConnect) {
                    HStack(spacing: 10) {
                        Image(systemName: "calendar.badge.clock")
                            .foregroundStyle(novaPurple)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(calendarModel.nextEventTitle).lineLimit(1)
                            if !calendarModel.nextEventTime.isEmpty {
                                Text(calendarModel.nextEventTime)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                    }
                }
                .buttonStyle(.plain)
            }
            .layoutPriority(1.15)

            DashboardPanel(title: "SYSTEM", icon: "desktopcomputer") {
                StatusRow(label: "Nova Core", value: engine.state.isAvailable ? "Connected" : "Offline", good: engine.state.isAvailable)
                StatusRow(label: "Voice Input", value: engine.dashboard.voiceReady ? "Ready" : "Unavailable", good: engine.dashboard.voiceReady)
                StatusRow(label: "Actions", value: engine.dashboard.actionsEnabled ? "Enabled" : "Off", good: engine.dashboard.actionsEnabled)
                StatusRow(label: "Database", value: engine.dashboard.databaseHealthy ? "Healthy" : "Check", good: engine.dashboard.databaseHealthy)
            }
            .layoutPriority(0.85)
        }
        .frame(width: 235)
    }

    private var centerColumn: some View {
        VStack(spacing: 12) {
            Group {
                if mode == .voice {
                    voiceCenter
                } else {
                    chatCenter
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if let action = engine.pendingAction {
                ActionConfirmationCard(action: action)
            }

            ModeToggle(mode: $mode)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var voiceCenter: some View {
        VStack(spacing: 10) {
            Spacer(minLength: 0)
            NovaOrb(state: engine.state)
            Text("Nova")
                .font(.system(size: 38, weight: .light, design: .rounded))
            HStack(spacing: 7) {
                Circle().fill(statusColor).frame(width: 9, height: 9)
                Text(engine.state.label).foregroundStyle(.secondary)
            }
            Button(action: engine.listen) {
                Image(systemName: engine.state == .listening ? "waveform" : "mic.fill")
                    .font(.system(size: 25))
                    .frame(width: 64, height: 64)
                    .background(.ultraThinMaterial)
                    .clipShape(Circle())
                    .overlay(Circle().stroke(LinearGradient(colors: [novaPurple, novaCyan], startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1.5))
                    .shadow(color: novaPurple.opacity(0.35), radius: 15)
            }
            .buttonStyle(.plain)
            .disabled(!engine.state.isReady)
            Text(engine.state == .listening ? "Listening…" : "Click to speak")
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

    private var rightColumn: some View {
        VStack(spacing: 10) {
            DashboardPanel(title: "TODAY", icon: "sun.max") {
                VStack(alignment: .leading, spacing: 8) {
                    Text(Date.now.formatted(.dateTime.weekday(.wide).month(.wide).day()))
                        .font(.title3.weight(.medium))
                    Text(calendarModel.nextEventTitle)
                        .lineLimit(1)
                    Text(calendarModel.nextEventTime.isEmpty ? "Google Calendar not connected" : calendarModel.nextEventTime)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Divider().overlay(panelBorder)
                    StatusRow(
                        label: "Live information",
                        value: engine.dashboard.liveInformationEnabled ? "On" : "Off",
                        good: engine.dashboard.liveInformationEnabled
                    )
                }
            }
            .layoutPriority(0.85)

            DashboardPanel(title: "SYSTEM HEALTH", icon: "heart.text.square") {
                MetricRow(label: "CPU", value: systemMonitor.cpuUsage, suffix: "%")
                MetricRow(label: "MEMORY", value: systemMonitor.memoryUsage, suffix: "%")
                ThermalRow(state: systemMonitor.thermalState)
                Divider().overlay(panelBorder)
                HStack(spacing: 7) {
                    Circle().fill(thermalColor).frame(width: 8, height: 8)
                    Text(systemMonitor.thermalState == "Nominal" ? "Mac operating normally" : "Thermal state: \(systemMonitor.thermalState)")
                        .font(.caption)
                        .foregroundStyle(thermalColor)
                }
            }
            .layoutPriority(1.15)
        }
        .frame(width: 235)
    }

    private var bottomStatus: some View {
        HStack(spacing: 16) {
            Label("NOVA STATUS", systemImage: "waveform.path.ecg")
                .foregroundStyle(novaPurple)
            Text(engine.state.isAvailable ? "OPERATIONAL" : "OFFLINE")
                .font(.caption.weight(.semibold))
            Spacer()
            WaveformStrip(active: engine.state == .listening || engine.state == .thinking)
            Text(engine.state == .listening ? "NOVA IS LISTENING" : "NOVA IS READY")
                .font(.caption2)
                .tracking(3)
                .foregroundStyle(novaCyan)
            Spacer()
            Label("Local engine", systemImage: "cpu")
            Circle().fill(.green).frame(width: 7, height: 7)
            Label("\(engine.dashboard.memories) memories", systemImage: "bookmark")
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 16)
        .padding(.vertical, 9)
        .background(panelBackground)
        .overlay(CutCornerShape(cut: 13).stroke(panelBorder, lineWidth: 1))
        .clipShape(CutCornerShape(cut: 13))
    }

    private var statusColor: Color {
        switch engine.state {
        case .ready: return .green
        case .thinking, .listening, .starting: return novaCyan
        case .unavailable: return .red
        }
    }

    private var thermalColor: Color {
        systemMonitor.thermalState == "Nominal" ? .green : .orange
    }

    private func send() {
        let message = input
        input = ""
        engine.sendMessage(message)
    }
}

private struct DashboardPanel<Content: View>: View {
    let title: String
    let icon: String
    @ViewBuilder let content: Content

    init(title: String, icon: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.icon = icon
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: icon)
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .tracking(1.4)
                .foregroundStyle(novaPurple)
                .fixedSize(horizontal: false, vertical: true)
                .layoutPriority(10)
            Divider().overlay(panelBorder)
            content
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(
            LinearGradient(
                colors: [Color.white.opacity(0.055), Color.white.opacity(0.018)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .overlay(CutCornerShape(cut: 12).stroke(panelBorder, lineWidth: 1))
        .shadow(color: novaPurple.opacity(0.08), radius: 14, y: 6)
        .clipShape(CutCornerShape(cut: 12))
    }
}

private struct StatusRow: View {
    let label: String
    let value: String
    let good: Bool

    var body: some View {
        HStack {
            Text(label).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.caption)
            Circle().fill(good ? .green : .gray).frame(width: 7, height: 7)
        }
        .font(.caption)
        .padding(.vertical, 3)
    }
}

private struct MetricRow: View {
    let label: String
    let value: Int
    let suffix: String

    var body: some View {
        VStack(spacing: 5) {
            HStack {
                Text(label).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text("\(value)\(suffix)").font(.caption.monospacedDigit())
            }
            ProgressView(value: Double(value), total: 100)
                .tint(LinearGradient(colors: [novaPurple, novaCyan], startPoint: .leading, endPoint: .trailing))
        }
    }
}

private struct ThermalRow: View {
    let state: String

    var body: some View {
        VStack(spacing: 5) {
            HStack {
                Text("THERMAL").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text(state).font(.caption)
            }
            ProgressView(value: state == "Nominal" ? 0.2 : state == "Warm" ? 0.5 : 0.85)
                .tint(state == "Nominal" ? .green : .orange)
        }
    }
}

private struct MonthGrid: View {
    private let calendar = Calendar.current
    private let now = Date()

    var body: some View {
        let cells = monthCells()
        VStack(spacing: 4) {
            Text(now.formatted(.dateTime.month(.wide).year()).uppercased())
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 3) {
                ForEach(calendar.shortWeekdaySymbols, id: \.self) { symbol in
                    Text(symbol.prefix(1)).font(.caption2).foregroundStyle(.secondary)
                }
                ForEach(Array(cells.enumerated()), id: \.offset) { _, day in
                    if let day {
                        Text("\(day)")
                            .font(.caption2.monospacedDigit())
                            .frame(width: 19, height: 19)
                            .background(day == calendar.component(.day, from: now) ? novaPurple.opacity(0.45) : .clear)
                            .clipShape(Circle())
                    } else {
                        Color.clear.frame(width: 19, height: 19)
                    }
                }
            }
        }
    }

    private func monthCells() -> [Int?] {
        guard let interval = calendar.dateInterval(of: .month, for: now),
              let range = calendar.range(of: .day, in: .month, for: now) else {
            return []
        }
        let weekday = calendar.component(.weekday, from: interval.start)
        let leading = (weekday - calendar.firstWeekday + 7) % 7
        return Array(repeating: nil, count: leading) + range.map(Optional.some)
    }
}

private struct ModeToggle: View {
    @Binding var mode: ContentView.InterfaceMode

    var body: some View {
        HStack(spacing: 4) {
            modeButton(.voice, icon: "waveform")
            modeButton(.chat, icon: "message")
        }
        .padding(4)
        .frame(width: 260)
        .background(Color.white.opacity(0.045))
        .overlay(Capsule().stroke(panelBorder, lineWidth: 1))
        .clipShape(Capsule())
    }

    private func modeButton(
        _ candidate: ContentView.InterfaceMode,
        icon: String
    ) -> some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { mode = candidate }
        } label: {
            Label(candidate.rawValue, systemImage: icon)
                .font(.callout.weight(.medium))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 7)
                .background(
                    mode == candidate
                        ? LinearGradient(
                            colors: [novaPurple.opacity(0.85), novaCyan.opacity(0.55)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                        : LinearGradient(colors: [.clear], startPoint: .leading, endPoint: .trailing)
                )
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

private struct NovaOrb: View {
    let state: NovaEngine.State

    var body: some View {
        TimelineView(
            .periodic(
                from: .now,
                by: state == .listening || state == .thinking ? 1.0 / 20.0 : 1.0 / 8.0
            )
        ) { context in
            let phase = context.date.timeIntervalSinceReferenceDate
            ZStack {
                Circle()
                    .fill(novaPurple.opacity(0.12))
                    .blur(radius: 34)
                    .padding(30)

                ForEach(0..<6, id: \.self) { index in
                    Circle()
                        .trim(
                            from: 0.03 + Double(index) * 0.045,
                            to: 0.40 + Double(index) * 0.075
                        )
                        .stroke(
                            index.isMultiple(of: 2)
                                ? novaPurple.opacity(0.42)
                                : novaCyan.opacity(0.35),
                            style: StrokeStyle(
                                lineWidth: index < 2 ? 1.5 : 0.8,
                                lineCap: .round,
                                dash: index < 3 ? [2, 5] : [1, 8]
                            )
                        )
                        .rotationEffect(
                            .degrees(
                                phase * (index.isMultiple(of: 2) ? 8 : -6)
                                    + Double(index * 41)
                            )
                        )
                        .padding(CGFloat(index * 8))
                }

                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                Color(red: 0.02, green: 0.01, blue: 0.07),
                                Color(red: 0.10, green: 0.035, blue: 0.24),
                                Color(red: 0.025, green: 0.02, blue: 0.09),
                            ],
                            center: UnitPoint(x: 0.43, y: 0.38),
                            startRadius: 0,
                            endRadius: 105
                        )
                    )
                    .padding(38)
                    .overlay {
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [.white.opacity(0.18), .clear, novaCyan.opacity(0.09)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .blur(radius: 12)
                            .padding(51)
                    }

                Circle()
                    .trim(from: 0.03, to: 0.97)
                    .stroke(
                        AngularGradient(
                            colors: [novaPurple, .white, novaPurple, novaCyan, .white, novaPurple],
                            center: .center
                        ),
                        style: StrokeStyle(
                            lineWidth: state == .listening ? 13 : 9,
                            lineCap: .round
                        )
                    )
                    .padding(35)
                    .rotationEffect(.degrees(phase * 6))
                    .blur(radius: 7)
                    .opacity(0.7)

                Circle()
                    .trim(from: 0.02, to: 0.98)
                    .stroke(
                        AngularGradient(
                            colors: [novaPurple, .white, novaPurple, novaCyan, .white, novaPurple],
                            center: .center
                        ),
                        style: StrokeStyle(lineWidth: state == .listening ? 12 : 8, lineCap: .round)
                    )
                    .padding(35)
                    .rotationEffect(.degrees(phase * 6))
                    .shadow(color: novaPurple.opacity(0.95), radius: state == .listening ? 24 : 14)
                    .animation(.easeInOut(duration: 0.25), value: state)

                Circle()
                    .stroke(Color.white.opacity(0.22), lineWidth: 0.7)
                    .padding(50)
            }
            .drawingGroup(opaque: false, colorMode: .extendedLinear)
        }
        .frame(width: 255, height: 255)
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

private struct WaveformStrip: View {
    let active: Bool

    var body: some View {
        if active {
            TimelineView(.periodic(from: .now, by: 1.0 / 12.0)) { context in
                bars(phase: context.date.timeIntervalSinceReferenceDate)
            }
        } else {
            bars(phase: 0)
        }
    }

    private func bars(phase: TimeInterval) -> some View {
            HStack(spacing: 3) {
                ForEach(0..<18, id: \.self) { index in
                    let wave = sin(phase * 5 + Double(index) * 0.65)
                    Capsule()
                        .fill(index.isMultiple(of: 2) ? novaPurple : novaCyan)
                        .frame(width: 2, height: active ? 5 + abs(wave) * 14 : 4)
                }
            }
            .frame(width: 90, height: 22)
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

private struct CutCornerShape: Shape {
    let cut: CGFloat

    func path(in rect: CGRect) -> Path {
        Path { path in
            path.move(to: CGPoint(x: rect.minX + cut, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX - cut, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + cut))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX + cut, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY - cut))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.minY + cut))
            path.closeSubpath()
        }
    }
}
