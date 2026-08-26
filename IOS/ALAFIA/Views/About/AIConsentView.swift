import SwiftUI

/// Whether this user has agreed to AI features being processed by third-party
/// model providers.
///
/// AI requests are de-identified before they leave ALAFIA — the user is
/// represented by a token we issue, and direct identifiers are stripped from the
/// text (see `privacy.py` on the backend). Consent is still asked for, because
/// "we removed your name" is our assurance, not the user's decision.
@MainActor
final class AIConsentManager: ObservableObject {
    private static let key = "alafia.aiConsentAccepted.v1"

    @Published private(set) var accepted: Bool

    init() {
        accepted = UserDefaults.standard.bool(forKey: Self.key)
    }

    func accept() {
        accepted = true
        UserDefaults.standard.set(true, forKey: Self.key)
    }

    /// Withdrawal is a real option, not a formality — it turns the features off.
    func withdraw() {
        accepted = false
        UserDefaults.standard.set(false, forKey: Self.key)
    }
}

/// Shown in place of an AI feature until the user accepts.
struct AIConsentView: View {
    @EnvironmentObject var consent: AIConsentManager

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Label("Before you use ALAFIA's AI", systemImage: "sparkles")
                    .font(.title3.weight(.semibold))

                Text("ALAFIA's AI features are answered by established model "
                     + "providers we work with. Here is exactly what that means "
                     + "for your information.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                group("What is sent", [
                    "The health details needed to answer — for example a lab value, "
                    + "a medication name and its dose.",
                ])

                group("What is never sent", [
                    "Your name, email address or phone number.",
                    "Your date of birth or any record number.",
                    "The names of clinicians you mention.",
                ])

                group("How you are identified", [
                    "By a token ALAFIA issues, such as “alafia-ba9e8bb2f9077c6e”. "
                    + "It means nothing outside ALAFIA and cannot be linked back "
                    + "to you by the provider.",
                ])

                group("Your choices", [
                    "You can withdraw at any time in Profile → AI & Your Data, "
                    + "which turns these features off.",
                    "Your data is never used to train a provider's models.",
                ])

                Text("ALAFIA is not a medical device. It does not diagnose, treat "
                     + "or prescribe, and it is not a substitute for your care team.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Button {
                    consent.accept()
                } label: {
                    Text("Accept & Enable AI Features")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                NavigationLink {
                    AIAndDataView()
                } label: {
                    Text("Read more about AI & your data")
                        .font(.footnote)
                        .frame(maxWidth: .infinity)
                }
                .padding(.top, -4)
            }
            .padding(24)
        }
    }

    private func group(_ title: String, _ items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.weight(.semibold))
            ForEach(items, id: \.self) { item in
                HStack(alignment: .top, spacing: 8) {
                    Text("•").foregroundStyle(.secondary)
                    Text(item).font(.footnote)
                }
            }
        }
    }
}

/// Wraps an AI feature so it cannot run before consent is given.
struct AIConsentGate<Content: View>: View {
    @EnvironmentObject var consent: AIConsentManager
    @ViewBuilder var content: () -> Content

    var body: some View {
        if consent.accepted {
            content()
        } else {
            NavigationStack { AIConsentView() }
        }
    }
}

#Preview {
    NavigationStack { AIConsentView() }
        .environmentObject(AIConsentManager())
}
