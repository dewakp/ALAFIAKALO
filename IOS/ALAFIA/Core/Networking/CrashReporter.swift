import Foundation
import UIKit

/// Lightweight crash and error reporter.
/// Captures uncaught exceptions and signal-based crashes and persists them to
/// disk, where they can be read off the device for support.
///
/// ⚠️ **There is no upload.** This used to POST every report to
/// `/diagnostics/crash-report`, which has never existed — `diagnostics` is the
/// CLINICAL router (ICD-10, assessments, screening) and has no crash endpoint.
/// Every upload 404'd, the failure was swallowed by a `print`, and because a
/// failed report is deliberately kept for "retry next launch", reports
/// accumulated in Caches indefinitely and were never sent. A crash reporter
/// that cannot deliver also cannot report that it cannot deliver.
///
/// Adding a server-side ingest endpoint is a deliberate decision, not a
/// bug-fix: a stack trace can carry user data, and this app's egress rules
/// (CLAUDE.md §3al) apply to anything leaving the device. Until that endpoint
/// exists on purpose, reports stay local and bounded.
final class CrashReporter {
    static let shared = CrashReporter()

    /// How many crash files to keep on disk. Nothing uploads them, so this
    /// is the only thing stopping them growing without bound.
    private static let maxStoredReports = 20

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

        // Reports from previous sessions stay on disk; keep them bounded.
        prunePendingReports()
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

    /// Keeps the most recent reports and discards the rest.
    ///
    /// Nothing is uploaded (see the type comment). Retention is bounded because
    /// the previous "retry next launch, never delete on failure" behaviour had
    /// no ceiling: with the upload permanently 404ing, every crash a device ever
    /// had was still sitting in Caches.
    private func prunePendingReports() {
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: crashDir,
            includingPropertiesForKeys: [.contentModificationDateKey]
        ).filter({ $0.pathExtension == "json" }) else { return }

        guard files.count > Self.maxStoredReports else { return }
        let byNewest = files.sorted {
            let a = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            let b = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            return a > b
        }
        for stale in byNewest.dropFirst(Self.maxStoredReports) {
            try? FileManager.default.removeItem(at: stale)
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

