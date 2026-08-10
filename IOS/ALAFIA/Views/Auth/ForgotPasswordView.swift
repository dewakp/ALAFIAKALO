import SwiftUI

struct ForgotPasswordView: View {
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss
    
    @State private var email = ""
    @State private var step: Step = .request
    @State private var isLoading = false
    @State private var error: String?
    @State private var message: String?
    
    /// No in-app confirm step: the reset link in the email opens the web reset
    /// page. The app previously asked the user to paste a reset "code", which
    /// only worked because the email printed a ~200-character JWT as text.
    enum Step { case request, sent }
    
    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                Image(systemName: "key.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(.green)
                    .padding(.top, 40)
                
                Text("Reset Password")
                    .font(.title2)
                    .fontWeight(.bold)
                
                if let error {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(12)
                        .frame(maxWidth: .infinity)
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                }
                
                if let message {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(.green)
                        .padding(12)
                        .frame(maxWidth: .infinity)
                        .background(Color.green.opacity(0.1))
                        .cornerRadius(8)
                }
                
                switch step {
                case .request:
                    requestView
                case .sent:
                    sentView
                }
            }
            .padding(.horizontal, 32)
        }
        .background(Color(.systemGroupedBackground))
        .navigationBarBackButtonHidden(false)
    }
    
    private var requestView: some View {
        VStack(spacing: 16) {
            Text("Enter your email address and we'll send you a reset link.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            
            LKTextField(title: "Email", text: $email, keyboardType: .emailAddress)
                .textContentType(.emailAddress)
                .autocapitalization(.none)
            
            LKButton(title: "Send Reset Link", isLoading: isLoading) {
                Task { await requestReset() }
            }
        }
    }
    
    private var sentView: some View {
        VStack(spacing: 16) {
            Image(systemName: "envelope.badge.fill")
                .font(.system(size: 40))
                .foregroundStyle(.green)

            Text("Open the link in that email to choose a new password.")
                .font(.subheadline)
                .multilineTextAlignment(.center)

            Text("Your current password keeps working until you do.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            LKButton(title: "Back to Login") {
                dismiss()
            }
        }
    }
    
    private func requestReset() async {
        error = nil; message = nil; isLoading = true
        defer { isLoading = false }
        do {
            let response = try await authManager.requestPasswordReset(email: email)
            message = response.message
            step = .sent
        } catch {
            self.error = error.localizedDescription
        }
    }
    
}
