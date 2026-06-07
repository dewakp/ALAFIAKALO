import Foundation
import Combine

struct PrivacySettings: Codable {
    var userId: Int
    var allowAnonymizedAnalytics: Bool
    var allowCollectiveInsights: Bool
    var allowResearchParticipation: Bool
    var allowMarketingEmails: Bool
    var allowProductUpdates: Bool
    var allowHealthReminders: Bool
    var aiCoachingEnabled: Bool
    var aiMemoryEnabled: Bool
    var aiExplainabilityLevel: String
    var requireBiometricAuth: Bool
    var sessionTimeoutMinutes: Int
    var gdprApplies: Bool
    var hipaaApplies: Bool
    
    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case allowAnonymizedAnalytics = "allow_anonymized_analytics"
        case allowCollectiveInsights = "allow_collective_insights"
        case allowResearchParticipation = "allow_research_participation"
        case allowMarketingEmails = "allow_marketing_emails"
        case allowProductUpdates = "allow_product_updates"
        case allowHealthReminders = "allow_health_reminders"
        case aiCoachingEnabled = "ai_coaching_enabled"
        case aiMemoryEnabled = "ai_memory_enabled"
        case aiExplainabilityLevel = "ai_explainability_level"
        case requireBiometricAuth = "require_biometric_auth"
        case sessionTimeoutMinutes = "session_timeout_minutes"
        case gdprApplies = "gdpr_applies"
        case hipaaApplies = "hipaa_applies"
    }
    
    static var `default`: PrivacySettings {
        PrivacySettings(
            userId: 0,
            allowAnonymizedAnalytics: true,
            allowCollectiveInsights: false,
            allowResearchParticipation: false,
            allowMarketingEmails: false,
            allowProductUpdates: true,
            allowHealthReminders: true,
            aiCoachingEnabled: true,
            aiMemoryEnabled: true,
            aiExplainabilityLevel: "standard",
            requireBiometricAuth: false,
            sessionTimeoutMinutes: 60,
            gdprApplies: false,
            hipaaApplies: false
        )
    }
}

struct DataExportStatus: Codable {
    let id: Int
    let status: String
    let exportFormat: String
    let requestedAt: String
    let processedAt: String?
    let downloadUrl: String?
    let expiresAt: String?
    let fileSizeBytes: Int?
    
    enum CodingKeys: String, CodingKey {
        case id, status
        case exportFormat = "export_format"
        case requestedAt = "requested_at"
        case processedAt = "processed_at"
        case downloadUrl = "download_url"
        case expiresAt = "expires_at"
        case fileSizeBytes = "file_size_bytes"
    }
}

@MainActor
class PrivacySettingsViewModel: ObservableObject {
    @Published var settings = PrivacySettings.default
    @Published var message = ""
    @Published var exportStatus: DataExportStatus?
    
    func loadSettings() {
        Task {
            do {
                settings = try await APIClient.shared.get("/privacy/settings")
            } catch {
                message = "Failed to load privacy settings: \(error.localizedDescription)"
            }
        }
    }
    
    func updateSetting<T: Encodable>(key: String, value: T) {
        Task {
            do {
                let updateData = [key: value]
                settings = try await APIClient.shared.put("/privacy/settings", body: updateData)
                message = "Settings updated successfully"
                
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                message = ""
            } catch {
                message = "Failed to update settings: \(error.localizedDescription)"
            }
        }
    }
    
    func requestDataExport(format: String = "json") {
        Task {
            do {
                exportStatus = try await APIClient.shared.post("/privacy/export?export_format=\(format)", body: EmptyBody())
                message = "Data export requested. Check back in a few minutes."
                
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                message = ""
            } catch {
                message = "Failed to request export: \(error.localizedDescription)"
            }
        }
    }
    
    func downloadExport(url downloadPath: String) {
        message = "Export download initiated for \(downloadPath)"
    }
    
    func requestAccountDeletion() {
        Task {
            do {
                let body = ["reason": "User requested deletion"]
                let _: [String: String] = try await APIClient.shared.post("/privacy/delete-account", body: body)
                message = "Account deletion requested. You will be contacted for confirmation."
            } catch {
                message = "Failed to request deletion: \(error.localizedDescription)"
            }
        }
    }
}
