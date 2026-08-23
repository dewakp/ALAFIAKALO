import SwiftUI

struct ContentView: View {
    @EnvironmentObject var authManager: AuthManager
    
    var body: some View {
        Group {
            if authManager.isLoading {
                LoadingView()
            } else if authManager.awaitingBiometric {
                BiometricLockView()
            } else if authManager.isAuthenticated {
                // Signed in is not the same as allowed in: the membership gate
                // decides whether the app opens. See SubscriptionGateView.
                SubscriptionGateView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut, value: authManager.isAuthenticated)
    }
}

struct LoadingView: View {
    var body: some View {
        ZStack {
            Color(.systemBackground).ignoresSafeArea()
            VStack(spacing: 16) {
                ProgressView()
                    .scaleEffect(1.5)
                Text("ALAFIA")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(.green)
            }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthManager.preview)
        .previewDevice("iPhone 15 Pro")
}
