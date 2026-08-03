import Foundation

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: Role
    let text: String

    enum Role {
        case user
        case nova
        case system
    }
}

struct PendingAction {
    let description: String
    let target: String
}

struct DashboardStatus {
    var version = ""
    var memories = 0
    var voiceReady = false
    var actionsEnabled = false
    var liveInformationEnabled = false
    var databaseHealthy = false
    var voiceEnabled = false
    var autoSpeak = false
    var episodeAutoSave = true
    var confirmSemanticMemory = false
    var ollamaModel = "llama3.2"
}

struct WeatherStatus {
    var summary = ""
    var location = ""
    var isLoading = false
}

@MainActor
final class NovaEngine: ObservableObject {
    enum State: Equatable {
        case starting
        case ready
        case thinking
        case listening
        case speaking
        case unavailable(String)

        var label: String {
            switch self {
            case .starting: return "Starting"
            case .ready: return "Ready"
            case .thinking: return "Thinking"
            case .listening: return "Listening"
            case .speaking: return "Speaking"
            case .unavailable: return "Unavailable"
            }
        }

        var isReady: Bool { self == .ready }

        var isAvailable: Bool {
            if case .unavailable = self { return false }
            return true
        }
    }

    @Published private(set) var state: State = .starting
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var pendingAction: PendingAction?
    @Published private(set) var dashboard = DashboardStatus()
    @Published private(set) var weather = WeatherStatus()

    private var process: Process?
    private var input: FileHandle?
    private var outputBuffer = Data()
    private var pendingCommands: [String: String] = [:]

    init() {
        start()
    }

    func start() {
        guard process == nil else { return }
        state = .starting

        guard let repositoryPath = repositoryPath() else {
            state = .unavailable("Nova repository location is missing.")
            return
        }

        let python = URL(fileURLWithPath: repositoryPath)
            .appendingPathComponent(".venv/bin/python").path
        guard FileManager.default.isExecutableFile(atPath: python) else {
            state = .unavailable("Nova's Python environment was not found.")
            return
        }

        let inputPipe = Pipe()
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        let task = Process()
        task.executableURL = URL(fileURLWithPath: python)
        task.arguments = ["-m", "nova.gui_bridge"]
        task.currentDirectoryURL = URL(fileURLWithPath: repositoryPath)
        task.standardInput = inputPipe
        task.standardOutput = outputPipe
        task.standardError = errorPipe
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        task.environment = environment

        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            Task { @MainActor in self?.consume(data) }
        }
        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let message = String(data: data, encoding: .utf8) else {
                return
            }
            Task { @MainActor in
                self?.state = .unavailable(
                    message.trimmingCharacters(in: .whitespacesAndNewlines)
                )
            }
        }
        task.terminationHandler = { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                self.process = nil
                self.input = nil
                if case .unavailable = self.state { return }
                self.state = .unavailable("Nova's local engine stopped.")
            }
        }

        do {
            try task.run()
            process = task
            input = inputPipe.fileHandleForWriting
            send(command: "dashboard")
        } catch {
            state = .unavailable(error.localizedDescription)
        }
    }

    func sendMessage(_ text: String) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, state.isReady else { return }
        messages.append(ChatMessage(role: .user, text: cleaned))
        state = .thinking
        send(command: "message", values: ["text": cleaned])
    }

    func listen() {
        guard state.isReady else { return }
        state = .listening
        send(command: "listen_gui")
    }

    func refreshWeather() {
        guard state.isAvailable, !weather.isLoading else { return }
        weather.isLoading = true
        send(command: "weather")
    }

    func setPreference(_ key: String, enabled: Bool) {
        switch key {
        case "voice.enabled": dashboard.voiceEnabled = enabled
        case "voice.auto_speak": dashboard.autoSpeak = enabled
        case "actions.enabled": dashboard.actionsEnabled = enabled
        case "live.enabled": dashboard.liveInformationEnabled = enabled
        case "memory.episode_auto_save": dashboard.episodeAutoSave = enabled
        case "memory.confirm_semantic": dashboard.confirmSemanticMemory = enabled
        default: return
        }
        send(
            command: "set_preference",
            values: ["key": key, "value": enabled]
        )
    }

    func confirmAction() {
        respondToAction("yes")
    }

    func cancelAction() {
        respondToAction("no")
    }

    func stop() {
        guard process != nil else { return }
        send(command: "shutdown")
        input?.closeFile()
    }

    private func respondToAction(_ response: String) {
        guard pendingAction != nil, state.isReady else { return }
        state = .thinking
        send(command: "message", values: ["text": response])
    }

    private func repositoryPath() -> String? {
        guard let url = Bundle.main.url(forResource: "repo-path", withExtension: "txt"),
              let value = try? String(contentsOf: url, encoding: .utf8) else {
            return nil
        }
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func send(command: String, values: [String: Any] = [:]) {
        guard let input else { return }
        let id = UUID().uuidString
        var payload = values
        payload["id"] = id
        payload["command"] = command
        pendingCommands[id] = command
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              var line = String(data: data, encoding: .utf8) else { return }
        line.append("\n")
        input.write(Data(line.utf8))
    }

    private func consume(_ data: Data) {
        outputBuffer.append(data)
        while let newline = outputBuffer.firstRange(of: Data([0x0A])) {
            let line = outputBuffer.subdata(in: outputBuffer.startIndex..<newline.lowerBound)
            outputBuffer.removeSubrange(outputBuffer.startIndex...newline.lowerBound)
            guard !line.isEmpty,
                  let object = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                continue
            }
            handle(object)
        }
    }

    private func handle(_ response: [String: Any]) {
        let id = response["id"] as? String ?? ""
        let command = pendingCommands.removeValue(forKey: id) ?? ""
        guard response["ok"] as? Bool == true else {
            let error = response["error"] as? String ?? "Unknown bridge error"
            if command == "dashboard" {
                state = .unavailable(error)
            } else if command == "weather" {
                weather.isLoading = false
                weather.summary = error
            } else {
                messages.append(ChatMessage(role: .system, text: error))
                state = .ready
            }
            return
        }
        if response["shutdown"] as? Bool == true { return }

        switch command {
        case "dashboard", "set_preference":
            if let result = response["result"] as? [String: Any] {
                updateDashboard(result)
            }
            if command == "dashboard" {
                send(command: "history", values: ["limit": 30])
            }
        case "history":
            if let turns = response["result"] as? [[String: Any]] {
                messages = turns.compactMap { turn in
                    guard let text = turn["text"] as? String,
                          let role = turn["role"] as? String else { return nil }
                    return ChatMessage(
                        role: role == "user" ? .user : .nova,
                        text: text
                    )
                }
            }
            state = .ready
        case "listen", "listen_gui":
            if let result = response["result"] as? [String: Any] {
                if let transcript = result["transcript"] as? String {
                    messages.append(ChatMessage(role: .user, text: transcript))
                }
                applyConversationResult(result)
                if command == "listen_gui",
                   result["should_speak"] as? Bool == true,
                   let speech = result["speech_text"] as? String,
                   !speech.isEmpty {
                    state = .speaking
                    send(command: "speak", values: ["text": speech])
                    return
                }
            }
            state = .ready
        case "speak":
            state = .ready
        case "message":
            if let result = response["result"] as? [String: Any] {
                applyConversationResult(result)
            }
            state = .ready
        case "weather":
            if let result = response["result"] as? [String: Any] {
                weather = WeatherStatus(
                    summary: result["spoken_response"] as? String
                        ?? result["response"] as? String
                        ?? "Weather is unavailable.",
                    location: result["location"] as? String ?? "",
                    isLoading: false
                )
            } else {
                weather.isLoading = false
            }
        default:
            state = .ready
        }
    }

    private func applyConversationResult(_ result: [String: Any]) {
        if let reply = result["response"] as? String {
            messages.append(ChatMessage(role: .nova, text: reply))
        }
        if result["action_status"] as? String == "pending_confirmation",
           let action = result["action"] as? [String: Any] {
            pendingAction = PendingAction(
                description: action["description"] as? String ?? "Confirm action",
                target: action["target"] as? String ?? "Nova action"
            )
        } else if result["action_status"] != nil {
            pendingAction = nil
        }
    }

    private func updateDashboard(_ result: [String: Any]) {
        let status = result["status"] as? [String: Any] ?? [:]
        let voice = result["voice"] as? [String: Any] ?? [:]
        let actions = result["actions"] as? [String: Any] ?? [:]
        let live = result["live_information"] as? [String: Any] ?? [:]
        let privacy = result["privacy"] as? [String: Any] ?? [:]
        dashboard = DashboardStatus(
            version: status["version"] as? String ?? "",
            memories: status["memories"] as? Int ?? 0,
            voiceReady: voice["input_available"] as? Bool ?? false,
            actionsEnabled: actions["enabled"] as? Bool ?? false,
            liveInformationEnabled: (
                live["enabled"] as? Bool
                ?? live["allow_web_access"] as? Bool
                ?? false
            ),
            databaseHealthy: status["database_status"] as? String == "healthy",
            voiceEnabled: voice["enabled"] as? Bool ?? false,
            autoSpeak: voice["auto_speak"] as? Bool ?? false,
            episodeAutoSave: privacy["episode_auto_save"] as? Bool ?? true,
            confirmSemanticMemory: (
                privacy["confirm_semantic_memory"] as? Bool ?? false
            ),
            ollamaModel: result["ollama_model"] as? String ?? "llama3.2"
        )
    }
}
