import Foundation

enum AppConfig {
    /// Production API. This is the default for EVERY build, simulator included.
    ///
    /// The simulator used to default to `http://localhost:8005/api/v1`, which
    /// meant a simulator run read from whatever local backend and local database
    /// happened to be up. When that local DB fell behind deployed — which it
    /// always eventually did — the app showed stale state while looking fine.
    /// Pointing at production removes that class of drift entirely: there is no
    /// second database to keep in sync.
    ///
    /// ⚠️ A simulator on this default writes to PRODUCTION. Logging a meal or
    /// deleting an entry changes real patient data.
    static let productionBaseURL = "https://api.alafia.app/api/v1"

    /// Base URL for the API — production unless deliberately overridden.
    ///
    /// To run against a local backend on purpose, set `ALAFIA_API_URL`:
    ///   • Xcode: scheme → Run → Arguments → Environment Variables
    ///   • simctl: `SIMCTL_CHILD_ALAFIA_API_URL=http://localhost:8005/api/v1`
    ///     (simctl requires the `SIMCTL_CHILD_` prefix; `--setenv` is ignored)
    static let baseURL: String = {
        if let envURL = ProcessInfo.processInfo.environment["ALAFIA_API_URL"],
           !envURL.isEmpty {
            return envURL
        }
        return productionBaseURL
    }()
    
    /// Public web pages — Help, Contact Us, Investors. These are the marketing
    /// site, not the API, so they are pinned to the app host rather than
    /// `baseURL`: an `ALAFIA_API_URL` override points a local backend at the
    /// simulator, and there is no local copy of the marketing site to open.
    static let webBaseURL = "https://alafia.app"

    static func webURL(_ path: String) -> URL? {
        URL(string: webBaseURL + path)
    }

    static let tokenKey = "alafia_jwt_token"
    static let userKey = "alafia_user"

    /// HealthKit background sync task identifier
    static let healthSyncTaskID = "com.alafia.healthkit-sync"

    /// Deep link URL scheme
    static let urlScheme = "alafia"
    /// Universal Links domain
    /// Universal Links domain. MUST be a domain we control and that serves
    /// /.well-known/apple-app-site-association — alafia.app does; alafia.com is
    /// NOT ours, so trusting it would let whoever owns it claim our links.
    static let universalLinkDomain = "alafia.app"
}
