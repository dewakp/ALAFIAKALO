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

    private let privacyPolicy = URL(string: "https://alafia.app/privacy")!

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    Label("Your health data stays on ALAFIA's own servers",
                          systemImage: "lock.shield.fill")
                        .font(.subheadline.weight(.semibold))
                    Text("When you ask the assistant a question, log a meal or have a photo "
                         + "analysed, that request is answered by inference servers ALAFIA "
                         + "operates. It is not sent to a third-party AI provider.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }

            Section("If a third-party service is ever used") {
                bullet("It is used only for requests that carry no health information.")
                bullet("You are identified by a token issued by ALAFIA — never your name, "
                       + "email address, phone number or date of birth.")
                bullet("Direct identifiers are removed from the text before it is sent.")
                bullet("Your data is never used to train a third party's models.")
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
