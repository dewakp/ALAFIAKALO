import SwiftUI

/// Shown when the app resumes and biometric verification is required.
struct BiometricLockView: View {
    @EnvironmentObject var authManager: AuthManager

    var body: some View {
        ZStack {
            Color(.systemBackground).ignoresSafeArea()
            VStack(spacing: 28) {
                Image(systemName: "faceid")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 72, height: 72)
                    .foregroundStyle(.green)

                Text("ALAFIA")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(.green)

                Text("Biometric authentication required")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                Button {
                    Task { await authManager.verifyBiometric() }
                } label: {
                    Label("Unlock", systemImage: "lock.open.fill")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.green)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                }
                .padding(.horizontal, 40)

                Button("Sign in with Password") {
                    Task {
                        authManager.awaitingBiometric = false
                        authManager.currentUser = nil
                    }
                }
                .font(.footnote)
                .foregroundColor(.secondary)
            }
            .padding()
        }
        .onAppear {
            // Auto-prompt on appear
            Task { await authManager.verifyBiometric() }
        }
    }
}
