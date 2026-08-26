import SwiftUI

/// What the AI does with your data — stated in the app, not only in the policy.
///
/// App Review asked three questions of submission 0ace0f33: whether a
/// third-party AI service is used, what personal data reaches it, and whether
/// the user consents before anything is sent. This screen is the in-app answer,
/// and it is written to stay true: the guarantee it describes is enforced in the
/// dispatcher (a prompt carrying health data is answered by ALAFIA-operated
/// inference or it fails — there is no third-party fallback), not by convention.
struct AIAndDataView: View {
    @EnvironmentObject private var consent: AIConsentManager

    private let privacyPolicy = URL(string: "https://alafia.app/privacy")!

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    Label("You are never identified to an AI provider",
                          systemImage: "lock.shield.fill")
                        .font(.subheadline.weight(.semibold))
                    Text("ALAFIA's AI features are answered by model providers we work "
                         + "with. Your request is de-identified before it leaves ALAFIA: "
                         + "the provider sees the health details needed to answer, "
                         + "attached to a token we issue rather than to you.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }

            Section("What reaches the provider") {
                bullet("The health details needed to answer — for example a lab value, "
                       + "a medication name and its dose.")
                bullet("A token ALAFIA issues, such as “alafia-ba9e8bb2f9077c6e”, which "
                       + "means nothing outside ALAFIA.")
            }

            Section("What never reaches the provider") {
                bullet("Your name, email address or phone number.")
                bullet("Your date of birth, or any record or policy number.")
                bullet("The names of clinicians you mention.")
                bullet("Your data is never used to train a provider's models.")
            }

            Section {
                if consent.accepted {
                    Button(role: .destructive) {
                        consent.withdraw()
                    } label: {
                        Label("Turn off AI features", systemImage: "xmark.circle")
                    }
                } else {
                    Label("AI features are turned off", systemImage: "xmark.circle")
                        .foregroundStyle(.secondary)
                }
            } footer: {
                Text("Turning these off stops ALAFIA sending anything to a model "
                     + "provider. You can turn them back on at any time.")
            }

            Section("What ALAFIA stores") {
                bullet("What you log — meals, medications, symptoms, readings and notes.")
                bullet("Photos and documents you add, such as lab reports.")
                bullet("Your health profile, including conditions and allergies.")
                Link(destination: privacyPolicy) {
                    Label("Read the full Privacy Policy", systemImage: "arrow.up.right.square")
                }
            }

            Section {
                NavigationLink {
                    MedicalSourcesView()
                } label: {
                    Label("Where health information comes from", systemImage: "book.closed")
                }
            } footer: {
                Text("ALAFIA is not a medical device. It does not diagnose, treat or "
                     + "prescribe, and it is not a substitute for your care team.")
            }
        }
        .navigationTitle("AI & Your Data")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func bullet(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•").foregroundStyle(.secondary)
            Text(text).font(.footnote)
        }
        .padding(.vertical, 1)
    }
}

#Preview {
    NavigationStack { AIAndDataView() }
}
