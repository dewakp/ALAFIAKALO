import SwiftUI
import BackgroundTasks

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        CrashReporter.shared.install()
        PushNotificationManager.shared.requestPermission()
        registerBackgroundTasks()
        return true
    }
    
    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        PushNotificationManager.shared.handleDeviceToken(deviceToken)
    }
    
    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        PushNotificationManager.shared.handleRegistrationError(error)
    }

    // MARK: - Background Tasks

    private func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: AppConfig.healthSyncTaskID,
            using: nil
        ) { task in
            self.handleHealthKitSync(task: task as! BGProcessingTask)
        }
    }

    func scheduleHealthKitSync() {
        let request = BGProcessingTaskRequest(identifier: AppConfig.healthSyncTaskID)
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false
        request.earliestBeginDate = Date(timeIntervalSinceNow: 4 * 3600) // 4 hours
        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            print("[BGTask] Failed to schedule HealthKit sync: \(error.localizedDescription)")
        }
    }

    private func handleHealthKitSync(task: BGProcessingTask) {
        // Schedule the next sync before starting
        scheduleHealthKitSync()

        let syncTask = Task {
            let manager = HealthKitSyncManager.shared
            let enabledTypes = HealthKitSyncManager.allDataTypes.map(\.key)
            await manager.performSync(dataTypes: enabledTypes)
        }

        task.expirationHandler = {
            syncTask.cancel()
        }

        Task {
            _ = await syncTask.result
            task.setTaskCompleted(success: HealthKitSyncManager.shared.syncError == nil)
        }
    }
}

@main
struct ALAFIAApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var authManager = AuthManager()
    @StateObject private var deepLinkRouter = DeepLinkRouter()
    @StateObject private var clinicianMode = ClinicianMode()
    @Environment(\.scenePhase) private var scenePhase
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .environmentObject(deepLinkRouter)
                .environmentObject(clinicianMode)
                .onOpenURL { url in
                    deepLinkRouter.handle(url: url)
                }
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .background {
                appDelegate.scheduleHealthKitSync()
            }
        }
    }
}
