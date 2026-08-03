import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var engine: NovaEngine
    @State private var input = ""

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            conversation
            Divider()
            composer
        }
        .frame(minWidth: 520, idealWidth: 620, minHeight: 480, idealHeight: 640)
        .background(Color(nsColor: .windowBackgroundColor))
        .background(WindowCapture())
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundStyle(.purple)
            VStack(alignment: .leading, spacing: 1) {
                Text("Nova").font(.headline)
                Text(engine.state.label)
                    .font(.caption)
                    .foregroundStyle(statusColor)
            }
            Spacer()
        }
        .padding(16)
    }

    private var conversation: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 12) {
                    if engine.messages.isEmpty {
                        VStack(spacing: 10) {
                            Image(systemName: "message.fill")
                                .font(.system(size: 34))
                                .foregroundStyle(.secondary)
                            Text("Ask Nova anything")
                                .font(.title3.weight(.semibold))
                            Text("Your existing memory, voice, live information, and actions are connected.")
                                .multilineTextAlignment(.center)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: 360)
                        }
                        .padding(.top, 100)
                    }
                    ForEach(engine.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }
                    if engine.state == .thinking {
                        HStack {
                            ProgressView().controlSize(.small)
                            Text("Nova is thinking…").foregroundStyle(.secondary)
                            Spacer()
                        }
                        .padding(.horizontal, 18)
                    }
                }
                .padding(.vertical, 16)
            }
            .onChange(of: engine.messages.count) {
                guard let last = engine.messages.last else { return }
                withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
            }
        }
    }

    private var composer: some View {
        HStack(spacing: 10) {
            TextField("Message Nova", text: $input, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...4)
                .onSubmit(send)
            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill").font(.title2)
            }
            .buttonStyle(.plain)
            .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !engine.state.isReady)
        }
        .padding(14)
    }

    private var statusColor: Color {
        switch engine.state {
        case .ready: return .green
        case .thinking, .starting: return .orange
        case .unavailable: return .red
        }
    }

    private func send() {
        let message = input
        input = ""
        engine.sendMessage(message)
    }
}

private struct WindowCapture: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            if let window = view.window {
                WindowCoordinator.shared.attach(window)
            }
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async {
            if let window = nsView.window {
                WindowCoordinator.shared.attach(window)
            }
        }
    }
}

private struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 80) }
            Text(message.text)
                .textSelection(.enabled)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .background(background)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            if message.role != .user { Spacer(minLength: 80) }
        }
        .padding(.horizontal, 16)
    }

    private var background: Color {
        message.role == .user ? .purple.opacity(0.22) : Color(nsColor: .controlBackgroundColor)
    }
}
