import SwiftUI

struct RegisterView: View {
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) var dismiss
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var phone = ""
    @State private var email = ""
    @State private var password = ""
    // Defaults to 30 years ago rather than today, so the wheel does not open on
    // a date that can never be valid.
    @State private var dateOfBirth = Calendar.current.date(
        byAdding: .year, value: -30, to: Date()) ?? Date()
    @State private var isLoading = false

    /// The API parses `YYYY-MM-DD`; a locale-formatted date would not parse.
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
                    
                    LKButton(title: "Create Account", isLoading: isLoading) {
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
                            await authManager.register(
                                email: email, password: password,
                                firstName: first, lastName: last,
                                dateOfBirth: Self.isoDate.string(from: dateOfBirth),
                                phone: phone)
                            isLoading = false
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
