import Foundation

// MARK: - Physician

struct Physician: Codable, Identifiable {
    let id: Int
    let userId: Int?
    let fullName: String
    let specialty: String
    let specialtyCategory: String?
    let credentials: String?
    let npiNumber: String?
    let facilityName: String?
    let addressLine1: String?
    let addressLine2: String?
    let city: String?
    let stateProvince: String?
    let postalCode: String?
    let country: String?
    let latitude: Double?
    let longitude: Double?
    let phone: String?
    let fax: String?
    let email: String?
    let website: String?
    let operatingHours: String?
    let languagesSpoken: String?
    let acceptingNewPatients: Bool
    let telehealthAvailable: Bool
    let insuranceAccepted: String?
    let averageRating: Double?
    let reviewCount: Int
    let isVerified: Bool
    let source: String?
    let status: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, specialty, credentials, phone, fax, email, website, latitude, longitude, source, status
        case userId = "user_id"
        case fullName = "full_name"
        case specialtyCategory = "specialty_category"
        case npiNumber = "npi_number"
        case facilityName = "facility_name"
        case addressLine1 = "address_line1"
        case addressLine2 = "address_line2"
        case city, country
        case stateProvince = "state_province"
        case postalCode = "postal_code"
        case operatingHours = "operating_hours"
        case languagesSpoken = "languages_spoken"
        case acceptingNewPatients = "accepting_new_patients"
        case telehealthAvailable = "telehealth_available"
        case insuranceAccepted = "insurance_accepted"
        case averageRating = "average_rating"
        case reviewCount = "review_count"
        case isVerified = "is_verified"
        case createdAt = "created_at"
    }

    var locationDisplay: String {
        [city, stateProvince, country].compactMap { $0 }.joined(separator: ", ")
    }
}

struct PhysicianCreate: Encodable {
    var fullName: String
    var specialty: String
    var credentials: String?
    var npiNumber: String?
    var facilityName: String?
    var addressLine1: String?
    var city: String?
    var stateProvince: String?
    var postalCode: String?
    var country: String?
    var phone: String?
    var email: String?
    var website: String?
    var acceptingNewPatients: Bool = true
    var telehealthAvailable: Bool = false
    var languagesSpoken: String?

    enum CodingKeys: String, CodingKey {
        case specialty, credentials, phone, email, website, city, country
        case fullName = "full_name"
        case npiNumber = "npi_number"
        case facilityName = "facility_name"
        case addressLine1 = "address_line1"
        case stateProvince = "state_province"
        case postalCode = "postal_code"
        case acceptingNewPatients = "accepting_new_patients"
        case telehealthAvailable = "telehealth_available"
        case languagesSpoken = "languages_spoken"
    }
}

// MARK: - Saved Physician

struct SavedPhysician: Codable, Identifiable {
    let id: Int
    let userId: Int
    let physicianId: Int
    let nickname: String?
    let notes: String?
    let isPrimaryCare: Bool
    let relationshipType: String?
    let physician: Physician?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, nickname, notes, physician
        case userId = "user_id"
        case physicianId = "physician_id"
        case isPrimaryCare = "is_primary_care"
        case relationshipType = "relationship_type"
        case createdAt = "created_at"
    }
}

struct SavePhysicianRequest: Encodable {
    let physicianId: Int
    var nickname: String?
    var notes: String?
    var isPrimaryCare: Bool = false
    var relationshipType: String?

    enum CodingKeys: String, CodingKey {
        case nickname, notes
        case physicianId = "physician_id"
        case isPrimaryCare = "is_primary_care"
        case relationshipType = "relationship_type"
    }
}

// MARK: - Review

struct PhysicianReview: Codable, Identifiable {
    let id: Int
    let physicianId: Int
    let userId: Int
    let rating: Int
    let title: String?
    let reviewText: String?
    let isAnonymous: Bool
    let reviewerName: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, rating, title
        case physicianId = "physician_id"
        case userId = "user_id"
        case reviewText = "review_text"
        case isAnonymous = "is_anonymous"
        case reviewerName = "reviewer_name"
        case createdAt = "created_at"
    }
}

struct ReviewCreate: Encodable {
    var rating: Int
    var title: String?
    var reviewText: String?
    var isAnonymous: Bool = false

    enum CodingKeys: String, CodingKey {
        case rating, title
        case reviewText = "review_text"
        case isAnonymous = "is_anonymous"
    }
}

// MARK: - Specialty Categories

struct SpecialtyCategoriesResponse: Codable {
    let categories: [String: [String]]
}

// MARK: - Geo types

struct GeoSearchResult: Codable, Identifiable {
    var id: String { "\(physician.id)" }
    let physician: Physician
    let distanceKm: Double

    enum CodingKeys: String, CodingKey {
        case physician
        case distanceKm = "distance_km"
    }
}

struct NearbySearchResponse: Codable {
    let results: [GeoSearchResult]
    let total: Int
    let searchLat: Double
    let searchLon: Double
    let radiusKm: Double

    enum CodingKeys: String, CodingKey {
        case results, total
        case searchLat = "search_lat"
        case searchLon = "search_lon"
        case radiusKm = "radius_km"
    }
}
