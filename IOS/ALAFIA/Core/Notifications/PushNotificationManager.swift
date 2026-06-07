import Foundation
import UserNotifications
import UIKit

/// Handles APNs registration and push notification delivery
class PushNotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = PushNotificationManager()
    
    @Published var deviceToken: String?
    
    private override init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }
    
    // MARK: - Registration
    
    func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
            if granted {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
    }
    
    func handleDeviceToken(_ deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        DispatchQueue.main.async {
            self.deviceToken = token
            self.registerTokenWithBackend()
        }
    }

    func handleRegistrationError(_ error: Error) {
        print("APNs registration failed: \(error.localizedDescription)")
    }

    /// Sends the most recent APNs device token to the backend.
    ///
    /// Best-effort and idempotent: the backend upserts by token, so it is safe
    /// to call repeatedly. Because the token can arrive before the user logs in
    /// (fresh install), `AuthManager` also calls this after a successful login /
    /// session restore so the registration completes once authenticated.
    func registerTokenWithBackend() {
        guard let token = deviceToken else { return }
        Task {
            do {
                let _: DeviceTokenResponse = try await APIClient.shared.post(
                    "/notifications/apns-token",
                    body: DeviceTokenRequest(token: token, platform: "ios")
                )
            } catch {
                // Will be retried after the next login / app launch.
                print("APNs token registration failed: \(error.localizedDescription)")
            }
        }
    }
    
    // MARK: - UNUserNotificationCenterDelegate
    
    /// Handle notifications received while app is in foreground
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .badge, .sound])
    }
    
    /// Handle notification tap
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        // TODO: Navigate to relevant screen based on userInfo["category"]
        _ = userInfo
        completionHandler()
    }
}

// MARK: - Device Token DTOs

private struct DeviceTokenRequest: Encodable {
    let token: String
    let platform: String
}

private struct DeviceTokenResponse: Decodable {
    let id: Int
    let platform: String
}
