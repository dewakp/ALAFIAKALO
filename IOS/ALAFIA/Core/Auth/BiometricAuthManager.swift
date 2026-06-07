import Foundation
import LocalAuthentication

/// Wraps LAContext to provide biometric (Face ID / Touch ID) authentication.
/// Stores the user's preference in UserDefaults so it's available before the
/// backend settings are loaded.
actor BiometricAuthManager {

    static let shared = BiometricAuthManager()
    private init() {}

    // MARK: - UserDefaults key

    private static let preferenceKey = "alafia_require_biometric_auth"

    // MARK: - Preference persistence

    static func setPreference(_ enabled: Bool) {
        UserDefaults.standard.set(enabled, forKey: preferenceKey)
    }

    static func preferenceEnabled() -> Bool {
        UserDefaults.standard.bool(forKey: preferenceKey)
    }

    // MARK: - Availability

    /// Returns true when the device has a biometric sensor that is enrolled.
    static func isAvailable() -> Bool {
        let ctx = LAContext()
        var error: NSError?
        return ctx.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error)
    }

    // MARK: - Prompt

    /// Presents the system biometric prompt.
    /// - Returns: `true` on success; `false` if the user cancels or fails.
    func authenticate(reason: String = "Confirm it's you to open ALAFIA") async -> Bool {
        guard BiometricAuthManager.isAvailable() else { return true } // no sensor → pass through
        let ctx = LAContext()
        ctx.localizedCancelTitle = "Use Passcode"
        do {
            return try await ctx.evaluatePolicy(
                .deviceOwnerAuthenticationWithBiometrics,
                localizedReason: reason
            )
        } catch {
            return false
        }
    }
}
