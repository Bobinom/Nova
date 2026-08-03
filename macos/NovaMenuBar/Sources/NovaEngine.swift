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

@MainActor
final class NovaEngine: ObservableObject {
    enum State: Equatable {
        case starting
        case ready
        case thinking
        case unavailable(String)

        var label: String {
            switch self {
            case .starting: return "Starting"
            case .ready: return "Ready"
            case .thinking: return "Thinking"
            case .unavailable: return "Unavailable"
            }
        }

        var isReady: Bool { self == .ready }
    }

    @Published private(set) var state: State = .starting
    @Published private(set) var messages: [ChatMessage] = []

    private var process: Process?
    private var input: FileHandle?
    private var outputBuffer = Data()

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
                self?.state = .unavailable(message.trimmingCharacters(in: .whitespacesAndNewlines))
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
            send(command: "status")
        } catch {
            state = .unavailable(error.localizedDescription)
        }
    }

    func sendMessage(_ text: String) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, state.isReady else { return }
        messages.append(ChatMessage(role: .user, text: cleaned))
        state = .thinking
        send(command: "message", text: cleaned)
    }

    func stop() {
        guard process != nil else { return }
        send(command: "shutdown")
        input?.closeFile()
    }

    private func repositoryPath() -> String? {
        guard let url = Bundle.main.url(forResource: "repo-path", withExtension: "txt"),
              let value = try? String(contentsOf: url, encoding: .utf8) else {
            return nil
        }
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func send(command: String, text: String? = nil) {
        guard let input else { return }
        var payload: [String: Any] = [
            "id": UUID().uuidString,
            "command": command,
        ]
        if let text { payload["text"] = text }
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
        guard response["ok"] as? Bool == true else {
            let error = response["error"] as? String ?? "Unknown bridge error"
            state = .unavailable(error)
            return
        }
        if response["shutdown"] as? Bool == true { return }
        guard let result = response["result"] as? [String: Any] else {
            state = .ready
            return
        }
        if let reply = result["response"] as? String {
            messages.append(ChatMessage(role: .nova, text: reply))
        }
        state = .ready
    }
}
