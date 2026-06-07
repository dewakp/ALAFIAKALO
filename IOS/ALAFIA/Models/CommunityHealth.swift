import Foundation

// MARK: - Community Health Alert

struct CommunityHealthAlert: Codable, Identifiable {
    let id: Int
    let title: String
    let summary: String?
    let description: String?
    let category: String
    let severity: String
    let source: String
    let sourceUrl: String?
    let sourceReferenceId: String?
    let affectedCountries: [String]?
    let affectedRegions: [String]?
    let isGlobal: Bool
    let issuedDate: String?
    let effectiveDate: String?
    let expiryDate: String?
    // Recall fields
    let productName: String?
    let productType: String?
    let manufacturer: String?
    let lotNumbers: [String]?
    let reasonForRecall: String?
    let recallClass: String?
    // Outbreak fields
    let diseaseName: String?
    let pathogen: String?
    let confirmedCases: Int?
    let deaths: Int?
    // Advisory fields
    let recommendedActions: [String]?
    let targetPopulation: [String]?
    // Status
    let isActive: Bool
    let isResolved: Bool
    let resolutionDate: String?
    let resolutionNotes: String?
    let tags: [String]?
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, summary, description, category, severity, source, tags
        case sourceUrl = "source_url"
        case sourceReferenceId = "source_reference_id"
        case affectedCountries = "affected_countries"
        case affectedRegions = "affected_regions"
        case isGlobal = "is_global"
        case issuedDate = "issued_date"
        case effectiveDate = "effective_date"
        case expiryDate = "expiry_date"
        case productName = "product_name"
        case productType = "product_type"
        case manufacturer
        case lotNumbers = "lot_numbers"
        case reasonForRecall = "reason_for_recall"
        case recallClass = "recall_class"
        case diseaseName = "disease_name"
        case pathogen
        case confirmedCases = "confirmed_cases"
        case deaths
        case recommendedActions = "recommended_actions"
        case targetPopulation = "target_population"
        case isActive = "is_active"
        case isResolved = "is_resolved"
        case resolutionDate = "resolution_date"
        case resolutionNotes = "resolution_notes"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var categoryIcon: String {
        switch category {
        case "pandemic": return "🦠"
        case "epidemic": return "🏥"
        case "outbreak": return "⚠️"
        case "recall_drug": return "💊"
        case "recall_food": return "🍽️"
        case "recall_device": return "🩺"
        case "advisory": return "📢"
        case "poison": return "☠️"
        case "environmental": return "🌍"
        case "natural_disaster": return "🌪️"
        case "vaccination": return "💉"
        case "guideline_update": return "📋"
        case "travel_health": return "✈️"
        case "water_safety": return "💧"
        case "air_quality": return "🌫️"
        default: return "📌"
        }
    }

    var severityColor: String {
        switch severity {
        case "critical": return "red"
        case "high": return "orange"
        case "moderate": return "yellow"
        case "low": return "green"
        case "info": return "blue"
        default: return "gray"
        }
    }
}

struct AlertCreate: Encodable {
    let title: String
    let summary: String
    let category: String
    let severity: String
    let source: String

    enum CodingKeys: String, CodingKey {
        case title, summary, category, severity, source
    }
}

// MARK: - Community Health Report

struct CommunityHealthReport: Codable, Identifiable {
    let id: Int
    let userId: Int
    let reportType: String
    let title: String
    let description: String?
    let latitude: Double?
    let longitude: Double?
    let locationName: String?
    let country: String?
    let region: String?
    let symptomsReported: [String]?
    let numberAffected: Int?
    let onsetDate: String?
    let productInvolved: String?
    let severity: String?
    let isVerified: Bool
    let isActive: Bool
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, description, latitude, longitude, country, region, severity
        case userId = "user_id"
        case reportType = "report_type"
        case locationName = "location_name"
        case symptomsReported = "symptoms_reported"
        case numberAffected = "number_affected"
        case onsetDate = "onset_date"
        case productInvolved = "product_involved"
        case isVerified = "is_verified"
        case isActive = "is_active"
        case createdAt = "created_at"
    }
}

struct ReportCreate: Encodable {
    var reportType: String = "symptom_cluster"
    var title: String = ""
    var description: String = ""
    var locationName: String?
    var country: String?
    var severity: String = "moderate"
    var numberAffected: Int = 1
    var symptomsReported: [String]?

    enum CodingKeys: String, CodingKey {
        case title, description, country, severity
        case reportType = "report_type"
        case locationName = "location_name"
        case numberAffected = "number_affected"
        case symptomsReported = "symptoms_reported"
    }
}

// MARK: - Health Guideline

struct HealthGuideline: Codable, Identifiable {
    let id: Int
    let title: String
    let summary: String?
    let fullText: String?
    let category: String
    let source: String
    let sourceUrl: String?
    let version: String?
    let effectiveDate: String?
    let supersededDate: String?
    let isCurrent: Bool
    let targetPopulation: [String]?
    let applicableCountries: [String]?
    let applicableConditions: [String]?
    let recommendations: [String]?
    let tags: [String]?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, summary, category, source, version, tags, recommendations
        case fullText = "full_text"
        case sourceUrl = "source_url"
        case effectiveDate = "effective_date"
        case supersededDate = "superseded_date"
        case isCurrent = "is_current"
        case targetPopulation = "target_population"
        case applicableCountries = "applicable_countries"
        case applicableConditions = "applicable_conditions"
        case createdAt = "created_at"
    }
}

// MARK: - Dashboard Stats

struct CommunityDashboardStats: Codable {
    let totalActiveAlerts: Int
    let criticalAlerts: Int
    let activeRecalls: Int
    let activeOutbreaks: Int
    let activeAdvisories: Int
    let activePoisonAlerts: Int
    let totalGuidelines: Int
    let userReports30d: Int
    let unreadAlerts: Int
    let bookmarkedAlerts: Int
    let latestOutbreaks: [CommunityHealthAlert]
    let latestRecalls: [CommunityHealthAlert]
    let latestAdvisories: [CommunityHealthAlert]

    enum CodingKeys: String, CodingKey {
        case totalActiveAlerts = "total_active_alerts"
        case criticalAlerts = "critical_alerts"
        case activeRecalls = "active_recalls"
        case activeOutbreaks = "active_outbreaks"
        case activeAdvisories = "active_advisories"
        case activePoisonAlerts = "active_poison_alerts"
        case totalGuidelines = "total_guidelines"
        case userReports30d = "user_reports_30d"
        case unreadAlerts = "unread_alerts"
        case bookmarkedAlerts = "bookmarked_alerts"
        case latestOutbreaks = "latest_outbreaks"
        case latestRecalls = "latest_recalls"
        case latestAdvisories = "latest_advisories"
    }
}

// MARK: - Reference Data

struct AlertCategoryInfo: Codable, Identifiable {
    let id: String
    let name: String
    let description: String
    let icon: String
}

struct AlertSourceInfo: Codable, Identifiable {
    let id: String
    let name: String
    let fullName: String
    let url: String?
    let country: String?

    enum CodingKeys: String, CodingKey {
        case id, name, url, country
        case fullName = "full_name"
    }
}

// MARK: - Subscription

struct AlertSubscription: Codable {
    let id: Int?
    let userId: Int?
    let categories: [String]?
    let sources: [String]?
    let countries: [String]?
    let severities: [String]?
    let pushEnabled: Bool
    let emailEnabled: Bool
    let smsEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case id, categories, sources, countries, severities
        case userId = "user_id"
        case pushEnabled = "push_enabled"
        case emailEnabled = "email_enabled"
        case smsEnabled = "sms_enabled"
    }
}

struct SubscriptionCreate: Encodable {
    var categories: [String] = []
    var sources: [String] = []
    var countries: [String] = []
    var severities: [String] = ["critical", "high"]
    var pushEnabled: Bool = true
    var emailEnabled: Bool = false
    var smsEnabled: Bool = false

    enum CodingKeys: String, CodingKey {
        case categories, sources, countries, severities
        case pushEnabled = "push_enabled"
        case emailEnabled = "email_enabled"
        case smsEnabled = "sms_enabled"
    }
}
