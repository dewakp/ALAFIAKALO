import SwiftUI

struct ForgotPasswordView: View {
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss
    
    @State private var email = ""
    @State private var resetToken = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var step: Step = .request
    @State private var isLoading = false
    @State private var error: String?
    @State private var message: String?
    
    enum Step { case request, confirm, done }
    
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
                case .confirm:
                    confirmView
                case .done:
                    doneView
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
    
    private var confirmView: some View {
        VStack(spacing: 16) {
            LKTextField(title: "Reset Token", text: $resetToken)
            
            LKTextField(title: "New Password", text: $newPassword, isSecure: true)
                .textContentType(.newPassword)
            
            LKTextField(title: "Confirm Password", text: $confirmPassword, isSecure: true)
                .textContentType(.newPassword)
            
            LKButton(title: "Reset Password", isLoading: isLoading) {
                Task { await confirmReset() }
            }
        }
    }
    
    private var doneView: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 48))
                .foregroundStyle(.green)
            
            Text("Password reset successfully!")
                .font(.headline)
                .foregroundStyle(.green)
            
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
            if let token = response.resetToken {
                resetToken = token
            }
            step = .confirm
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    private func confirmReset() async {
        error = nil; message = nil
        guard newPassword == confirmPassword else {
            error = "Passwords do not match"
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            _ = try await authManager.confirmPasswordReset(token: resetToken, newPassword: newPassword)
            step = .done
        } catch {
            self.error = error.localizedDescription
        }
    }
}
