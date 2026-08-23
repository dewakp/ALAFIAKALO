import SwiftUI

/// The paywall as a WALL. A signed-in user without an active membership does not
/// reach the app at all — the backend already answers 402 to every gated path, so
/// letting them into the tabs only produces a screen of failed requests.
///
/// The states are deliberately four, not two: `.unavailable` (we could not ask)
/// must never render as "you haven't paid". Telling a paying member to subscribe
/// because their train went into a tunnel is the worse of the two mistakes.
struct SubscriptionGateView: View {
    @EnvironmentObject var authManager: AuthManager
    @EnvironmentObject var entitlement: EntitlementManager

    var body: some View {
        Group {
            switch entitlement.state {
            case .entitled:
                MainTabView()
            case .locked:
                SubscriptionView(blocking: true)
            case .unavailable(let message):
                unavailableView(message)
            case .unknown, .checking:
                LoadingView()
            }
        }
        .animation(.easeInOut, value: entitlement.state)
        .task {
            if entitlement.state == .unknown { await entitlement.refresh() }
        }
    }

    private func unavailableView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
            Text("Couldn’t check your membership")
                .font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Try again") {
                Task { await entitlement.refresh() }
            }
            .buttonStyle(.borderedProminent)
            Button("Sign out") {
                entitlement.reset()
                authManager.logout()
            }
            .font(.footnote)
        }
        .padding(32)
    }
}
