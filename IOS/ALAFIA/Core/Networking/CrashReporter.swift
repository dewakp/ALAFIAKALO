import Foundation
import UIKit

/// Lightweight crash and error reporter.
/// Captures uncaught exceptions and signal-based crashes, persists them to disk,
/// and uploads to the backend on next launch.
///
/// For production, replace the upload target with Sentry/Crashlytics if desired.
/// This gives immediate crash visibility without a third-party SDK.
final class CrashReporter {
    static let shared = CrashReporter()

    private let crashDir: URL
    private let encoder = JSONEncoder()

    private init() {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        crashDir = base.appendingPathComponent("LKCrashReports", isDirectory: true)
        try? FileManager.default.createDirectory(at: crashDir, withIntermediateDirectories: true)
    }

    // MARK: - Setup (call once from AppDelegate)

    func install() {
        NSSetUncaughtExceptionHandler { exception in
            CrashReporter.shared.saveCrash(
                name: exception.name.rawValue,
                reason: exception.reason ?? "unknown",
                stackTrace: exception.callStackSymbols
            )
        }

        // Capture POSIX signals (SIGSEGV, SIGBUS, SIGABRT, etc.)
        for sig: Int32 in [SIGABRT, SIGBUS, SIGSEGV, SIGFPE, SIGILL, SIGTRAP] {
            signal(sig) { signalNumber in
                CrashReporter.shared.saveCrash(
                    name: "Signal \(signalNumber)",
                    reason: "Caught fatal signal",
                    stackTrace: Thread.callStackSymbols
                )
                // Re-raise so the default handler can terminate
                signal(signalNumber, SIG_DFL)
                raise(signalNumber)
            }
        }

        // Upload any crash reports from previous sessions
        Task { await uploadPendingReports() }
    }

    // MARK: - Record non-fatal errors

    /// Log a non-fatal error for server-side analysis.
    func recordError(_ error: Error, context: String? = nil) {
        let report = CrashReport(
            id: UUID().uuidString,
            timestamp: Date(),
            name: String(describing: type(of: error)),
            reason: error.localizedDescription,
            stackTrace: Thread.callStackSymbols,
            context: context,
            appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
            osVersion: "\(UIDevice.current.systemName) \(UIDevice.current.systemVersion)",
            device: UIDevice.current.model,
            isFatal: false
        )
        save(report)
    }

    // MARK: - Internals

    private func saveCrash(name: String, reason: String, stackTrace: [String]) {
        let report = CrashReport(
            id: UUID().uuidString,
            timestamp: Date(),
            name: name,
            reason: reason,
            stackTrace: stackTrace,
            context: nil,
            appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
            osVersion: "\(UIDevice.current.systemName) \(UIDevice.current.systemVersion)",
            device: UIDevice.current.model,
            isFatal: true
        )
        save(report)
    }

    private func save(_ report: CrashReport) {
        let file = crashDir.appendingPathComponent("\(report.id).json")
        if let data = try? encoder.encode(report) {
            try? data.write(to: file, options: .atomic)
        }
    }

    private func uploadPendingReports() async {
        guard let files = try? FileManager.default
            .contentsOfDirectory(at: crashDir, includingPropertiesForKeys: nil)
            .filter({ $0.pathExtension == "json" }) else { return }

        for file in files {
            do {
                let data = try Data(contentsOf: file)
                let report = try JSONDecoder().decode(CrashReport.self, from: data)
                // Upload to backend (fire-and-forget)
                let _: EmptyResponse = try await APIClient.shared.post("/diagnostics/crash-report", body: report)
                try? FileManager.default.removeItem(at: file)
            } catch {
                // Will retry next launch — don't delete the file
                print("[CrashReporter] upload failed: \(error.localizedDescription)")
            }
        }
    }
}

// MARK: - DTOs

private struct CrashReport: Codable {
    let id: String
    let timestamp: Date
    let name: String
    let reason: String
    let stackTrace: [String]
    let context: String?
    let appVersion: String
    let osVersion: String
    let device: String
    let isFatal: Bool
}

private struct EmptyResponse: Decodable {}
