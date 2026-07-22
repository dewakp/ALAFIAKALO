import Foundation

enum AppConfig {
    /// Base URL for the API.
    /// Override at runtime via the `ALAFIA_API_URL` environment variable
    /// (set in Xcode scheme → Run → Arguments → Environment Variables),
    /// or fall back to compile-time defaults.
    static let baseURL: String = {
        if let envURL = ProcessInfo.processInfo.environment["ALAFIA_API_URL"],
           !envURL.isEmpty {
            return envURL
        }
        #if targetEnvironment(simulator)
        return "http://localhost:8005/api/v1"
        #else
        return "https://api.alafia.app/api/v1"  // Production — HTTPS enforced
        #endif
    }()
    
    static let tokenKey = "alafia_jwt_token"
    static let userKey = "alafia_user"

    /// HealthKit background sync task identifier
    static let healthSyncTaskID = "com.alafia.healthkit-sync"

    /// Deep link URL scheme
    static let urlScheme = "alafia"
    /// Universal Links domain
    static let universalLinkDomain = "alafia.com"
}
