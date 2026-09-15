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

/// The languages ALAFIA offers — the same eleven codes on web, iOS, Android and
/// the backend (`WEB/backend/app/services/prompt_language.py`).
enum AppLanguage {
    static let codes = ["en", "es", "fr", "de", "pt", "ar", "zh", "yo", "ig", "ha", "sw"]

    static let nativeNames: [String: String] = [
        "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch",
        "pt": "Português", "ar": "العربية", "zh": "中文", "yo": "Yorùbá",
        "ig": "Igbo", "ha": "Hausa", "sw": "Kiswahili",
    ]

    /// The patient's choice, as last synced from their profile or set here.
    static let storageKey = "alafia_app_language"

    /// The language this app is in: the patient's choice, else the device's
    /// language when ALAFIA offers it, else English.
    ///
    /// Sent on every request as `X-Client-Language`, and the backend puts it
    /// FIRST. So the saved profile preference must become the choice here when
    /// the profile loads — sending the device language instead would answer a
    /// patient who chose Yoruba in English on an English-language phone.
    static var current: String {
        resolve(UserDefaults.standard.string(forKey: storageKey))
    }

    /// `current`, for a stored choice the caller already holds — the app root
    /// observes the choice itself, so a change re-renders every screen at once.
    static func resolve(_ chosen: String?) -> String {
        if let chosen, codes.contains(chosen) {
            return chosen
        }
        for preferred in Locale.preferredLanguages {
            let code = normalise(preferred)
            if !code.isEmpty { return code }
        }
        return "en"
    }

    /// The locale the interface is drawn in: the chosen language, on the device's
    /// own region, so a French-speaking patient in the US keeps US date order.
    ///
    /// Applied as SwiftUI's `\.locale` environment, deliberately NOT by writing
    /// `AppleLanguages`. That key changes `Locale.current`, which every
    /// `DateFormatter` here that sets no locale of its own reads — and several
    /// of those format dates for API payloads, the same reason Android wraps its
    /// Context instead of calling `Locale.setDefault`.
    static func locale(_ chosen: String?) -> Locale {
        Locale(components: .init(languageCode: .init(resolve(chosen)), languageRegion: Locale.current.region))
    }

    static func isRightToLeft(_ chosen: String?) -> Bool {
        Locale.Language(identifier: resolve(chosen)).characterDirection == .rightToLeft
    }

    /// Remember the patient's choice. An empty or unknown value is ignored,
    /// never guessed at: a blank profile field does not erase a choice.
    static func choose(_ value: String?) {
        let code = normalise(value)
        guard !code.isEmpty else { return }
        UserDefaults.standard.set(code, forKey: storageKey)
    }

    /// A product code for any stored form — "fr", "fr-FR", "French", "Français"
    /// — or "" when it is none of them. Profiles hold both codes and names.
    static func normalise(_ value: String?) -> String {
        guard let raw = value?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return "" }
        let prefix = String(raw.prefix(while: { $0 != "-" && $0 != "_" })).lowercased()
        if codes.contains(prefix) { return prefix }
        let english = Locale(identifier: "en")
        for code in codes {
            let englishName = english.localizedString(forLanguageCode: code) ?? ""
            if raw.caseInsensitiveCompare(englishName) == .orderedSame
                || raw.caseInsensitiveCompare(nativeNames[code] ?? "") == .orderedSame {
                return code
            }
        }
        return ""
    }

    static func displayName(_ code: String) -> String {
        code.isEmpty ? "—" : (nativeNames[code] ?? code.uppercased())
    }
}
