import Foundation

// MARK: - Role Catalog

struct RoleCatalogEntry: Codable, Identifiable {
    let id: String
    let name: String
    let category: String
    let description: String?
}

struct RoleCategoryInfo: Codable, Identifiable {
    let id: String
    let name: String
    let roles: [RoleCatalogEntry]
}

struct RoleCategorySummary: Codable, Identifiable {
    let id: String
    let name: String
    let count: Int
}

// MARK: - Professional Profile

struct ProfessionalProfile: Codable, Identifiable {
    let id: Int
    let roleAssignmentId: Int
    // Credentials
    let licenseNumber: String?
    let licenseState: String?
    let licenseCountry: String?
    let licenseExpiry: String?
    let npiNumber: String?
    let deaNumber: String?
    let boardCertifications: [String]?
    // Education
    let medicalSchool: String?
    let degree: String?
    let graduationYear: Int?
    let residencyProgram: String?
    let fellowshipProgram: String?
    // Practice
    let specialty: String?
    let subSpecialty: String?
    let yearsOfExperience: Int?
    let practiceName: String?
    let practiceType: String?
    let practiceAddress: String?
    let practicePhone: String?
    let practiceEmail: String?
    let practiceWebsite: String?
    let acceptingPatients: Bool?
    // Hospital
    let hospitalAffiliations: [String]?
    let department: String?
    let title: String?
    // Languages
    let clinicalLanguages: [String]?
    // Telemedicine
    let telemedicineAvailable: Bool?
    let telemedicinePlatforms: [String]?
    // Verification
    let verificationStatus: String?
    let verificationDate: String?
    // Bio
    let professionalBio: String?
    let publications: [String]?
    let researchInterests: [String]?
    
    let createdAt: String?
    let updatedAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case roleAssignmentId = "role_assignment_id"
        case licenseNumber = "license_number"
        case licenseState = "license_state"
        case licenseCountry = "license_country"
        case licenseExpiry = "license_expiry"
        case npiNumber = "npi_number"
        case deaNumber = "dea_number"
        case boardCertifications = "board_certifications"
        case medicalSchool = "medical_school"
        case degree
        case graduationYear = "graduation_year"
        case residencyProgram = "residency_program"
        case fellowshipProgram = "fellowship_program"
        case specialty
        case subSpecialty = "sub_specialty"
        case yearsOfExperience = "years_of_experience"
        case practiceName = "practice_name"
        case practiceType = "practice_type"
        case practiceAddress = "practice_address"
        case practicePhone = "practice_phone"
        case practiceEmail = "practice_email"
        case practiceWebsite = "practice_website"
        case acceptingPatients = "accepting_patients"
        case hospitalAffiliations = "hospital_affiliations"
        case department, title
        case clinicalLanguages = "clinical_languages"
        case telemedicineAvailable = "telemedicine_available"
        case telemedicinePlatforms = "telemedicine_platforms"
        case verificationStatus = "verification_status"
        case verificationDate = "verification_date"
        case professionalBio = "professional_bio"
        case publications
        case researchInterests = "research_interests"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

// MARK: - Role Assignment

struct RoleAssignment: Codable, Identifiable {
    let id: Int
    let userId: Int
    let role: String
    let isPrimary: Bool
    let isActive: Bool
    let grantedAt: String?
    let professionalProfile: ProfessionalProfile?
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case role
        case isPrimary = "is_primary"
        case isActive = "is_active"
        case grantedAt = "granted_at"
        case professionalProfile = "professional_profile"
    }
    
    var displayName: String {
        role.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

// MARK: - User Persona Summary

struct UserPersonaSummary: Codable {
    let userId: Int
    let fullName: String
    let email: String
    let primaryRole: String
    let activeRoles: [String]
    let roleDetails: [RoleAssignment]
    let isHealthcareProfessional: Bool
    let roleCategories: [String]
    let permissions: [String]
    
    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case fullName = "full_name"
        case email
        case primaryRole = "primary_role"
        case activeRoles = "active_roles"
        case roleDetails = "role_details"
        case isHealthcareProfessional = "is_healthcare_professional"
        case roleCategories = "role_categories"
        case permissions
    }
}

// MARK: - Request Models

struct RoleAssignmentCreate: Encodable {
    let role: String
    let isPrimary: Bool
    
    enum CodingKeys: String, CodingKey {
        case role
        case isPrimary = "is_primary"
    }
}

struct ProfessionalProfileCreate: Encodable {
    var licenseNumber: String?
    var licenseState: String?
    var licenseCountry: String?
    var licenseExpiry: String?
    var npiNumber: String?
    var deaNumber: String?
    var boardCertifications: [String]?
    var medicalSchool: String?
    var degree: String?
    var graduationYear: Int?
    var residencyProgram: String?
    var fellowshipProgram: String?
    var specialty: String?
    var subSpecialty: String?
    var yearsOfExperience: Int?
    var practiceName: String?
    var practiceType: String?
    var practiceAddress: String?
    var practicePhone: String?
    var practiceEmail: String?
    var practiceWebsite: String?
    var acceptingPatients: Bool?
    var hospitalAffiliations: [String]?
    var department: String?
    var title: String?
    var clinicalLanguages: [String]?
    var telemedicineAvailable: Bool?
    var telemedicinePlatforms: [String]?
    var professionalBio: String?
    var publications: [String]?
    var researchInterests: [String]?
    
    enum CodingKeys: String, CodingKey {
        case licenseNumber = "license_number"
        case licenseState = "license_state"
        case licenseCountry = "license_country"
        case licenseExpiry = "license_expiry"
        case npiNumber = "npi_number"
        case deaNumber = "dea_number"
        case boardCertifications = "board_certifications"
        case medicalSchool = "medical_school"
        case degree
        case graduationYear = "graduation_year"
        case residencyProgram = "residency_program"
        case fellowshipProgram = "fellowship_program"
        case specialty
        case subSpecialty = "sub_specialty"
        case yearsOfExperience = "years_of_experience"
        case practiceName = "practice_name"
        case practiceType = "practice_type"
        case practiceAddress = "practice_address"
        case practicePhone = "practice_phone"
        case practiceEmail = "practice_email"
        case practiceWebsite = "practice_website"
        case acceptingPatients = "accepting_patients"
        case hospitalAffiliations = "hospital_affiliations"
        case department, title
        case clinicalLanguages = "clinical_languages"
        case telemedicineAvailable = "telemedicine_available"
        case telemedicinePlatforms = "telemedicine_platforms"
        case professionalBio = "professional_bio"
        case publications
        case researchInterests = "research_interests"
    }
}

// MARK: - Category Icons

let roleCategoryIcons: [String: String] = [
    "physician": "stethoscope",
    "surgeon": "scissors",
    "nursing": "cross.case.fill",
    "therapy": "figure.mind.and.body",
    "mental_health": "brain.head.profile",
    "social_work": "person.2.fill",
    "dental": "mouth.fill",
    "pharmacy": "pills.fill",
    "diagnostics": "microscope",
    "emergency": "cross.circle.fill",
    "allied_health": "heart.text.clipboard",
    "public_health": "globe.americas.fill",
    "administration": "building.2.fill",
    "research": "magnifyingglass",
    "traditional_complementary": "leaf.fill",
    "midwifery": "figure.and.child.holdinghands",
    "other": "person.fill.questionmark",
]

let verificationStatusColors: [String: String] = [
    "unverified": "gray",
    "pending": "orange",
    "verified": "green",
    "rejected": "red",
    "expired": "secondary",
]
