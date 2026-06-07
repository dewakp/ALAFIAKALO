import SwiftUI

struct LoginView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var email = ""
    @State private var password = ""
    @State private var showRegister = false
    @State private var showForgotPassword = false
    @State private var isLoading = false
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 32) {
                    // Logo
                    VStack(spacing: 8) {
                        Image(systemName: "heart.circle.fill")
                            .font(.system(size: 72))
                            .foregroundStyle(.green)
                        
                        Text("ALAFIA")
                            .font(.largeTitle)
                            .fontWeight(.bold)
                            .foregroundStyle(.green)
                        
                        Text("Your Holistic Health Companion")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 60)
                    
                    // Error
                    if let error = authManager.error {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                            .padding(12)
                            .frame(maxWidth: .infinity)
                            .background(Color.red.opacity(0.1))
                            .cornerRadius(8)
                    }
                    
                    // Form
                    VStack(spacing: 16) {
                        LKTextField(title: "Email", text: $email, keyboardType: .emailAddress)
                            .textContentType(.emailAddress)
                            .autocapitalization(.none)
                        
                        LKTextField(title: "Password", text: $password, isSecure: true)
                            .textContentType(.password)
                        
                        LKButton(title: "Sign In", isLoading: isLoading) {
                            isLoading = true
                            Task {
                                await authManager.login(email: email, password: password)
                                isLoading = false
                            }
                        }
                    }
                    
                    // Forgot password
                    Button {
                        showForgotPassword = true
                    } label: {
                        Text("Forgot password?")
                            .font(.subheadline)
                            .foregroundStyle(.green)
                    }
                    
                    // Register link
                    Button {
                        showRegister = true
                    } label: {
                        HStack(spacing: 4) {
                            Text("Don't have an account?")
                                .foregroundStyle(.secondary)
                            Text("Sign Up")
                                .foregroundStyle(.green)
                                .fontWeight(.semibold)
                        }
                        .font(.subheadline)
                    }
                }
                .padding(.horizontal, 32)
            }
            .background(Color(.systemGroupedBackground))
            .navigationDestination(isPresented: $showRegister) {
                RegisterView()
            }
            .navigationDestination(isPresented: $showForgotPassword) {
                ForgotPasswordView()
            }
        }
    }
}
