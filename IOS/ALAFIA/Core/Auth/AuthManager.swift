import Foundation
import SwiftUI

/// Manages authentication state across the app
@MainActor
class AuthManager: ObservableObject {
    @Published var currentUser: User?
    @Published var isAuthenticated = false
    @Published var isLoading = true
    @Published var error: String?
    /// True while waiting for biometric verification after a valid session is found.
    @Published var awaitingBiometric = false

    private static let refreshTokenKey = "alafia_refresh_token"
    
    init(skipSessionCheck: Bool = false) {
        if skipSessionCheck {
            isLoading = false
        } else {
            Task { await checkExistingSession() }
        }
    }
    
    static var preview: AuthManager {
        let manager = AuthManager(skipSessionCheck: true)
        manager.currentUser = .preview
        manager.isAuthenticated = true
        manager.isLoading = false
        return manager
    }
    
    // MARK: - Session
    
    private func checkExistingSession() async {
        #if DEBUG
        // Screenshot / UI-automation hook (DEBUG only — never in a release build):
        // seed a session from ALAFIA_TEST_TOKEN so the app launches straight into
        // the authenticated UI for automated App Store screenshot capture.
        if let t = ProcessInfo.processInfo.environment["ALAFIA_TEST_TOKEN"], !t.isEmpty {
            KeychainHelper.save(key: AppConfig.tokenKey, value: t)
            if let r = ProcessInfo.processInfo.environment["ALAFIA_TEST_REFRESH"], !r.isEmpty {
                KeychainHelper.save(key: Self.refreshTokenKey, value: r)
            }
            await APIClient.shared.setToken(t)
        }
        #endif
        guard KeychainHelper.get(key: AppConfig.tokenKey) != nil else {
            isLoading = false
            return
        }
        
        do {
            let user: User = try await APIClient.shared.get("/users/me")
            self.currentUser = user
            // Gate with biometric before granting access
            if BiometricAuthManager.preferenceEnabled() {
                awaitingBiometric = true
                isLoading = false
                return
            }
            self.isAuthenticated = true
        } catch {
            // Attempt token refresh before giving up
            if await refreshTokenIfPossible() {
                do {
                    let user: User = try await APIClient.shared.get("/users/me")
                    self.currentUser = user
                    if BiometricAuthManager.preferenceEnabled() {
                        awaitingBiometric = true
                        isLoading = false
                        return
                    }
                    self.isAuthenticated = true
                } catch {
                    clearTokens()
                }
            } else {
                clearTokens()
            }
        }
        
        isLoading = false
    }
    
    // MARK: - Biometric

    /// Call this when the user is on the biometric lock screen.
    func verifyBiometric() async {
        let passed = await BiometricAuthManager.shared.authenticate()
        if passed {
            awaitingBiometric = false
            isAuthenticated = true
        } else {
            // Biometric failed / cancelled — force re-login
            awaitingBiometric = false
            clearTokens()
            currentUser = nil
        }
    }

    // MARK: - Login
    
    func login(email: String, password: String) async {
        error = nil
        do {
            let response: TokenResponse = try await APIClient.shared.postFormWithCSRF(
                "/auth/login",
                formData: ["username": email, "password": password]
            )
            KeychainHelper.save(key: AppConfig.tokenKey, value: response.accessToken)
            if let refresh = response.refreshToken {
                KeychainHelper.save(key: Self.refreshTokenKey, value: refresh)
            }
            await APIClient.shared.setToken(response.accessToken)
            
            let user: User = try await APIClient.shared.get("/users/me")
            self.currentUser = user
            self.isAuthenticated = true
            // Push the APNs token now that we're authenticated (it may have been
            // captured before login on a fresh install).
            PushNotificationManager.shared.registerTokenWithBackend()
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Firebase token exchange (phone / Google / Apple sign-in)

    /// Exchange a Firebase Auth ID token (minted by a native phone-OTP,
    /// Google or Apple sign-in flow) for ALAFIA JWTs via POST /auth/firebase.
    /// The provider SDK flows themselves are wired separately; this is the
    /// backend-parity plumbing they all funnel through.
    func loginWithFirebaseToken(_ idToken: String) async {
        error = nil
        do {
            struct FirebaseTokenBody: Encodable { let id_token: String }
            let response: TokenResponse = try await APIClient.shared.post(
                "/auth/firebase", body: FirebaseTokenBody(id_token: idToken)
            )
            KeychainHelper.save(key: AppConfig.tokenKey, value: response.accessToken)
            if let refresh = response.refreshToken {
                KeychainHelper.save(key: Self.refreshTokenKey, value: refresh)
            }
            await APIClient.shared.setToken(response.accessToken)

            let user: User = try await APIClient.shared.get("/users/me")
            self.currentUser = user
            self.isAuthenticated = true
            PushNotificationManager.shared.registerTokenWithBackend()
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Register

    func register(email: String, password: String, fullName: String,
                  dateOfBirth: String,
                  country: String? = Locale.current.region?.identifier) async {
        error = nil
        do {
            let body = RegisterRequest(email: email, password: password, fullName: fullName,
                                       dateOfBirth: dateOfBirth, country: country)
            let _: User = try await APIClient.shared.post("/auth/register", body: body)
            await login(email: email, password: password)
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    // MARK: - Token Refresh
    
    func refreshTokenIfPossible() async -> Bool {
        guard let refresh = KeychainHelper.get(key: Self.refreshTokenKey) else { return false }
        do {
            let body = RefreshTokenRequestBody(refreshToken: refresh)
            let response: TokenResponse = try await APIClient.shared.post("/auth/refresh", body: body)
            KeychainHelper.save(key: AppConfig.tokenKey, value: response.accessToken)
            if let newRefresh = response.refreshToken {
                KeychainHelper.save(key: Self.refreshTokenKey, value: newRefresh)
            }
            await APIClient.shared.setToken(response.accessToken)
            return true
        } catch {
            return false
        }
    }
    
    // MARK: - Password Reset
    
    func requestPasswordReset(email: String) async throws -> PasswordResetResponse {
        let body = PasswordResetRequestBody(email: email)
        return try await APIClient.shared.post("/auth/password-reset/request", body: body)
    }
    
    func confirmPasswordReset(token: String, newPassword: String) async throws -> PasswordResetResponse {
        let body = PasswordResetConfirmBody(token: token, newPassword: newPassword)
        return try await APIClient.shared.post("/auth/password-reset/confirm", body: body)
    }
    
    // MARK: - Logout
    
    func logout() {
        clearTokens()
        currentUser = nil
        isAuthenticated = false
    }
    
    private func clearTokens() {
        KeychainHelper.delete(key: AppConfig.tokenKey)
        KeychainHelper.delete(key: Self.refreshTokenKey)
        Task { await APIClient.shared.setToken(nil) }
    }
}

// MARK: - Auth DTOs

struct TokenResponse: Decodable {
    let accessToken: String
    let tokenType: String
    let refreshToken: String?
    
    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case refreshToken = "refresh_token"
    }
}

struct RegisterRequest: Encodable {
    let email: String
    let password: String
    let fullName: String
    /// REQUIRED by the API: an account holder must be an adult by their own
    /// jurisdiction's standard (app/core/age_policy.py). Omitting it 422s.
    let dateOfBirth: String
    /// Selects the age threshold; absent, the strictest (16) applies.
    let country: String?

    enum CodingKeys: String, CodingKey {
        case email, password, country
        case fullName = "full_name"
        case dateOfBirth = "date_of_birth"
    }
}

struct RefreshTokenRequestBody: Encodable {
    let refreshToken: String
    
    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

struct PasswordResetRequestBody: Encodable {
    let email: String
}

struct PasswordResetConfirmBody: Encodable {
    let token: String
    let newPassword: String
    
    enum CodingKeys: String, CodingKey {
        case token
        case newPassword = "new_password"
    }
}

struct PasswordResetResponse: Decodable {
    let message: String
    // Deliberately no `reset_token`. The API no longer returns one under any
    // setting — it is delivered only by email — and decoding a field that must
    // never exist invites re-adding the server side to "make the client work".
}
