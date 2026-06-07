import Foundation

/// Lightweight file-based JSON cache for offline support.
/// Stores API responses keyed by path and replays them when the network is unavailable.
///
/// Usage:
/// ```
/// // Write
/// OfflineCache.shared.store(value, for: "/labs")
///
/// // Read
/// let labs: [LabResult]? = OfflineCache.shared.load(for: "/labs")
/// ```
final class OfflineCache {
    static let shared = OfflineCache()

    private let cacheDir: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    /// Maximum age before a cached response is considered stale (24 hours)
    private let maxAge: TimeInterval = 86400

    private init() {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        cacheDir = base.appendingPathComponent("LKOfflineCache", isDirectory: true)
        try? FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
    }

    // MARK: - Public API

    /// Store an Encodable response for the given API path.
    func store<T: Encodable>(_ value: T, for path: String) {
        let file = fileURL(for: path)
        do {
            let wrapper = CacheEntry(timestamp: Date(), data: try encoder.encode(value))
            let data = try encoder.encode(wrapper)
            try data.write(to: file, options: .atomic)
        } catch {
            print("[OfflineCache] write error for \(path): \(error.localizedDescription)")
        }
    }

    /// Load a previously cached response, if it exists and is not stale.
    func load<T: Decodable>(for path: String) -> T? {
        let file = fileURL(for: path)
        guard let raw = try? Data(contentsOf: file),
              let entry = try? decoder.decode(CacheEntry.self, from: raw),
              Date().timeIntervalSince(entry.timestamp) < maxAge else {
            return nil
        }
        return try? decoder.decode(T.self, from: entry.data)
    }

    /// Remove a specific key.
    func remove(for path: String) {
        try? FileManager.default.removeItem(at: fileURL(for: path))
    }

    /// Purge all cached data.
    func clear() {
        try? FileManager.default.removeItem(at: cacheDir)
        try? FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
    }

    // MARK: - Internals

    private func fileURL(for path: String) -> URL {
        // Sanitize the path to a safe filename
        let safe = path
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "?", with: "_")
            .prefix(120)
        return cacheDir.appendingPathComponent("\(safe).json")
    }
}

// MARK: - Cache wrapper

private struct CacheEntry: Codable {
    let timestamp: Date
    let data: Data
}
