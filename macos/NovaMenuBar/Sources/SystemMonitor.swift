import Darwin
import Foundation

@MainActor
final class SystemMonitor: ObservableObject {
    @Published private(set) var cpuUsage = 0
    @Published private(set) var memoryUsage = 0
    @Published private(set) var thermalState = "Nominal"

    private var timer: Timer?
    private var previousCPU: (used: UInt64, total: UInt64)?

    init() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) {
            [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    deinit {
        timer?.invalidate()
    }

    private func refresh() {
        cpuUsage = readCPUUsage()
        memoryUsage = readMemoryUsage()
        switch ProcessInfo.processInfo.thermalState {
        case .nominal: thermalState = "Nominal"
        case .fair: thermalState = "Warm"
        case .serious: thermalState = "High"
        case .critical: thermalState = "Critical"
        @unknown default: thermalState = "Unknown"
        }
    }

    private func readCPUUsage() -> Int {
        var info = host_cpu_load_info_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<host_cpu_load_info_data_t>.size
                / MemoryLayout<integer_t>.size
        )
        let result = withUnsafeMutablePointer(to: &info) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics(
                    mach_host_self(),
                    HOST_CPU_LOAD_INFO,
                    $0,
                    &count
                )
            }
        }
        guard result == KERN_SUCCESS else { return cpuUsage }
        let used = UInt64(info.cpu_ticks.0)
            + UInt64(info.cpu_ticks.1)
            + UInt64(info.cpu_ticks.3)
        let total = used + UInt64(info.cpu_ticks.2)
        defer { previousCPU = (used, total) }
        guard let previousCPU, total > previousCPU.total else { return cpuUsage }
        let usedDelta = used - previousCPU.used
        let totalDelta = total - previousCPU.total
        return Int((Double(usedDelta) / Double(totalDelta) * 100).rounded())
    }

    private func readMemoryUsage() -> Int {
        var stats = vm_statistics64_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<vm_statistics64_data_t>.size
                / MemoryLayout<integer_t>.size
        )
        let result = withUnsafeMutablePointer(to: &stats) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(
                    mach_host_self(),
                    HOST_VM_INFO64,
                    $0,
                    &count
                )
            }
        }
        guard result == KERN_SUCCESS else { return memoryUsage }
        let pageSize = UInt64(vm_kernel_page_size)
        let usedPages = UInt64(stats.active_count)
            + UInt64(stats.wire_count)
            + UInt64(stats.compressor_page_count)
        let used = usedPages * pageSize
        let total = ProcessInfo.processInfo.physicalMemory
        guard total > 0 else { return 0 }
        return min(100, Int((Double(used) / Double(total) * 100).rounded()))
    }
}
