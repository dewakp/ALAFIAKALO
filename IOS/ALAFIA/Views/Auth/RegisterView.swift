import SwiftUI

struct RegisterView: View {
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) var dismiss
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var phone = ""
    /// Two-step signup: details are taken, the verification email goes out, and
    /// the account is created only once the address is confirmed. Payment is
    /// NOT taken here — Apple requires in-app purchase, and an IAP receipt has
    /// to attach to an account that does not exist yet, so the paywall is the
    /// screen after this one.
    @State private var awaitingVerification = false
    @State private var checking = false
    @State private var notice: String?
    @State private var email = ""
    @State private var password = ""
    // Defaults to 30 years ago rather than today, so the wheel does not open on
    // a date that can never be valid.
    @State private var dateOfBirth = Calendar.current.date(
        byAdding: .year, value: -30, to: Date()) ?? Date()
    @State private var isLoading = false

    /// The API parses `YYYY-MM-DD`; a locale-formatted date would not parse.
    /// "We emailed you a link."
    ///
    /// The app does not read the mailbox, so it ASKS the server whether the
    /// address has been confirmed yet rather than guessing. Until it has, the
    /// account does not exist — which is the gate `/auth/register` never had,
    /// and why a real person ended up holding an account they could not use
    /// with no email to explain it.
    private var verificationStep: some View {
        VStack(spacing: 16) {
            Image(systemName: "envelope.badge")
                .font(.system(size: 44))
                .foregroundStyle(.green)

            Text("Confirm your email")
                .font(.title3).bold()

            Text("We sent a link to \(email). Open it, then come back and tap Continue.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if let notice {
                Text(notice)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            LKButton(title: "I've confirmed — continue", isLoading: checking) {
                checking = true
                Task {
                    do {
                        let status = try await authManager.signupStatus(email: email)
                        if status.emailVerified {
                            // Creates the account and signs in. It is created
                            // UNPAID, so the paywall is the next screen.
                            try await authManager.signupCompleteMobile(
                                email: email, password: password)
                        } else {
                            notice = "Not confirmed yet. Check your inbox, and your spam folder."
                        }
                    } catch {
                        authManager.error = error.localizedDescription
                    }
                    checking = false
                }
            }

            Button("Send the email again") {
                Task {
                    do {
                        try await authManager.signupResend(email: email)
                        notice = "Sent. It can take a minute to arrive."
                    } catch {
                        authManager.error = error.localizedDescription
                    }
                }
            }
            .font(.subheadline)

            Button("Change my details") { awaitingVerification = false }
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 12)
    }

    private static let isoDate: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
    
    var body: some View {
        ScrollView {
            VStack(spacing: 32) {
                VStack(spacing: 8) {
                    Image(systemName: "person.crop.circle.badge.plus")
                        .font(.system(size: 56))
                        .foregroundStyle(.green)
                    
                    Text("Create Account")
                        .font(.title)
                        .fontWeight(.bold)
                    
                    Text("Join ALAFIA today")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 40)
                
                if let error = authManager.error {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(12)
                        .frame(maxWidth: .infinity)
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                }
                
                if awaitingVerification {
                    verificationStep
                } else {
                VStack(spacing: 16) {
                    LKTextField(title: "First Name", text: $firstName)
                        .textContentType(.givenName)

                    LKTextField(title: "Last Name", text: $lastName)
                        .textContentType(.familyName)
                    
                    LKTextField(title: "Email", text: $email, keyboardType: .emailAddress)
                        .textContentType(.emailAddress)

                    VStack(alignment: .leading, spacing: 4) {
                        DatePicker("Date of Birth", selection: $dateOfBirth,
                                   in: ...Date(), displayedComponents: .date)
                        Text("An account holder must be an adult. A child is tracked as a dependent profile under a parent or guardian's account.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                        .autocapitalization(.none)
                    
                    LKTextField(title: "Phone Number (optional — enables phone login)",
                                text: $phone, keyboardType: .phonePad)
                        .textContentType(.telephoneNumber)

                    LKTextField(title: "Password", text: $password, isSecure: true)
                        .textContentType(.newPassword)
                    
                    LKButton(title: "Continue", isLoading: isLoading) {
                        // Checked here so the message names WHICH box is wrong.
                        // The API enforces the same rule regardless — a client
                        // check is a kindness, never the enforcement.
                        let first = firstName.trimmingCharacters(in: .whitespacesAndNewlines)
                        let last = lastName.trimmingCharacters(in: .whitespacesAndNewlines)
                        if first.count < 3 {
                            authManager.error = "First name must be at least 3 characters."
                            return
                        }
                        if last.count < 3 {
                            authManager.error = "Last name must be at least 3 characters."
                            return
                        }
                        isLoading = true
                        Task {
                            do {
                                try await authManager.signupStart(
                                    email: email, password: password,
                                    firstName: first, lastName: last,
                                    dateOfBirth: Self.isoDate.string(from: dateOfBirth),
                                    phone: phone)
                                awaitingVerification = true
                                notice = nil
                            } catch {
                                authManager.error = error.localizedDescription
                            }
                            isLoading = false
                        }
                    }
                }
                
                }

                Button {
                    dismiss()
                } label: {
                    HStack(spacing: 4) {
                        Text("Already have an account?")
                            .foregroundStyle(.secondary)
                        Text("Sign In")
                            .foregroundStyle(.green)
                            .fontWeight(.semibold)
                    }
                    .font(.subheadline)
                }
            }
            .padding(.horizontal, 32)
        }
        .background(Color(.systemGroupedBackground))
        .navigationBarTitleDisplayMode(.inline)
    }
}
