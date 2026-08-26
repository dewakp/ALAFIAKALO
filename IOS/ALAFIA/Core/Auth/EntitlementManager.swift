import Foundation
import SwiftUI

extension Notification.Name {
    /// Raised by `APIClient` on any 402. The backend's app-wide paywall answers
    /// 402 to every gated path once `SUBSCRIPTION_REQUIRED` is on, so a session
    /// whose membership lapses mid-use is detected wherever it happens rather
    /// than only at launch.
    static let alafiaPaymentRequired = Notification.Name("alafia.paymentRequired")

    /// Raised by `APIClient` on a 401 that has already survived one transparent
    /// token refresh — i.e. the session is genuinely dead, not merely stale.
    ///
    /// Without this the app could hang on a spinner forever. `EntitlementManager`
    /// maps `.unauthorized` to `.unknown` on the stated grounds that "AuthManager
    /// owns the signed-out case" — but nothing ever told AuthManager, and
    /// `.unknown` renders a `ProgressView` whose `.task` does not re-run. The
    /// result was an INDEFINITE LOAD with no retry and no way out, which is what
    /// App Review saw (guideline 2.1(a), submission 0ace0f33).
    static let alafiaUnauthorized = Notification.Name("alafia.unauthorized")
}

/// Whether this signed-in user may use the app.
///
/// The backend owns entitlement — this only mirrors `GET /subscription/status`.
/// The one rule that shapes the whole type: **an error is not a lock.** A failed
/// status call means we do not know, and telling a paying member "subscribe" on
/// a dropped connection is a worse failure than showing a retry. `.unavailable`
/// is therefore its own state, never folded into `.locked`.
@MainActor
final class EntitlementManager: ObservableObject {

    enum State: Equatable {
        case unknown                 // not asked yet
        case checking                // asking now
        case entitled                // paid — the app opens
        case locked                  // definitively not paid — the paywall blocks
        case unavailable(String)     // we could not find out — retry, never assume
    }

    @Published private(set) var state: State = .unknown

    var isEntitled: Bool { state == .entitled }

    private var observer: NSObjectProtocol?

    init() {
        observer = NotificationCenter.default.addObserver(
            forName: .alafiaPaymentRequired, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                // A 402 is the server's own verdict, so it is authoritative —
                // but confirm rather than guess at the reason for the lock.
                await self?.refresh()
            }
        }
    }

    deinit {
        if let observer { NotificationCenter.default.removeObserver(observer) }
    }

    /// Ask the backend whether this user may use the app.
    func refresh() async {
        if state == .unknown { state = .checking }
        do {
            let status: SubscriptionStatus = try await APIClient.shared.get("/subscription/status")
            state = status.entitled ? .entitled : .locked
        } catch APIError.unauthorized {
            // Not an entitlement question — AuthManager owns the signed-out case.
            state = .unknown
        } catch {
            state = .unavailable(error.localizedDescription)
        }
    }

    /// Called after a verified purchase so the app opens without a round-trip.
    func markEntitled() { state = .entitled }

    /// Called on sign-out: the next user must be re-checked from scratch.
    func reset() { state = .unknown }
}
