import Foundation

struct Insurance: Codable, Identifiable {
    let id: Int
    let userId: Int
    let region: String
    let countryCode: String
    let countryName: String
    let providerCode: String
    let providerName: String
    let policyNumber: String?
    let groupNumber: String?
    let memberId: String?
    let planName: String?
    let planType: String?
    let coverageStart: String?
    let coverageEnd: String?
    let isPrimary: Bool
    let isActive: Bool
    let subscriberName: String?
    let subscriberRelationship: String?
    let insurancePhone: String?
    let notes: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, region, notes
        case userId = "user_id"
        case countryCode = "country_code"
        case countryName = "country_name"
        case providerCode = "provider_code"
        case providerName = "provider_name"
        case policyNumber = "policy_number"
        case groupNumber = "group_number"
        case memberId = "member_id"
        case planName = "plan_name"
        case planType = "plan_type"
        case coverageStart = "coverage_start"
        case coverageEnd = "coverage_end"
        case isPrimary = "is_primary"
        case isActive = "is_active"
        case subscriberName = "subscriber_name"
        case subscriberRelationship = "subscriber_relationship"
        case insurancePhone = "insurance_phone"
        case createdAt = "created_at"
    }
}

struct InsuranceCreate: Encodable {
    let region: String
    let countryCode: String
    let countryName: String
    let providerCode: String
    let providerName: String
    var policyNumber: String?
    var groupNumber: String?
    var memberId: String?
    var planName: String?
    var planType: String?
    var coverageStart: String?
    var coverageEnd: String?
    var isPrimary: Bool = false
    var isActive: Bool = true
    var subscriberName: String?
    var subscriberRelationship: String?
    var insurancePhone: String?
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case region, notes
        case countryCode = "country_code"
        case countryName = "country_name"
        case providerCode = "provider_code"
        case providerName = "provider_name"
        case policyNumber = "policy_number"
        case groupNumber = "group_number"
        case memberId = "member_id"
        case planName = "plan_name"
        case planType = "plan_type"
        case coverageStart = "coverage_start"
        case coverageEnd = "coverage_end"
        case isPrimary = "is_primary"
        case isActive = "is_active"
        case subscriberName = "subscriber_name"
        case subscriberRelationship = "subscriber_relationship"
        case insurancePhone = "insurance_phone"
    }
}

struct InsuranceCountry: Codable, Identifiable {
    let code: String
    let name: String
    var id: String { code }
}

struct InsuranceProvider: Codable, Identifiable {
    let code: String
    let name: String
    var id: String { code }
}
