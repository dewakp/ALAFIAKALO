import Foundation

struct User: Codable, Identifiable {
    let id: Int
    let email: String
    let fullName: String

    // Demographics
    let dateOfBirth: String?
    let gender: String?
    let genderAtBirth: String?
    let profilePictureUrl: String?
    let bloodType: String?

    // Insurance
    let insuranceId: String?
    let insuranceProvider: String?
    let insuranceCountry: String?

    // Physical
    let heightCm: Double?
    let currentWeightKg: Double?
    let targetWeightKg: Double?

    // Location & Culture
    let locale: String?
    let timezone: String?
    let country: String?
    let preferredUnits: String?
    let preferredLanguage: String?

    // Health Profile
    let allergies: String?
    let foodIntolerances: String?
    let dietaryRestrictions: String?
    let dietaryPreferences: String?
    let familyHistory: String?

    // Fitness
    let activityLevel: String?
    let fitnessGoals: String?
    let preferredActivities: String?
    let exerciseFrequencyPerWeek: Int?

    // Lifestyle
    let smokingStatus: String?
    let alcoholConsumption: String?
    let sleepSchedule: String?
    let occupation: String?
    let stressLevel: String?

    // AI Preferences
    let aiCoachingEnabled: Bool?
    let aiPersonalityPreference: String?
    let aiLanguageComplexity: String?

    // Privacy
    let dataSharingConsent: Bool?
    let aiTrainingConsent: Bool?

    // System
    let isActive: Bool
    let createdAt: Date
    let systemId: String?

    // Persona
    let primaryRole: String?
    let activeRoles: [String]?
    let isHealthcareProfessional: Bool?

    enum CodingKeys: String, CodingKey {
        case id, email, gender, locale, timezone, country, allergies, occupation
        case fullName = "full_name"
        case dateOfBirth = "date_of_birth"
        case genderAtBirth = "gender_at_birth"
        case profilePictureUrl = "profile_picture_url"
        case bloodType = "blood_type"
        case insuranceId = "insurance_id"
        case insuranceProvider = "insurance_provider"
        case insuranceCountry = "insurance_country"
        case heightCm = "height_cm"
        case currentWeightKg = "current_weight_kg"
        case targetWeightKg = "target_weight_kg"
        case preferredUnits = "preferred_units"
        case preferredLanguage = "preferred_language"
        case foodIntolerances = "food_intolerances"
        case dietaryRestrictions = "dietary_restrictions"
        case dietaryPreferences = "dietary_preferences"
        case familyHistory = "family_history"
        case activityLevel = "activity_level"
        case fitnessGoals = "fitness_goals"
        case preferredActivities = "preferred_activities"
        case exerciseFrequencyPerWeek = "exercise_frequency_per_week"
        case smokingStatus = "smoking_status"
        case alcoholConsumption = "alcohol_consumption"
        case sleepSchedule = "sleep_schedule"
        case stressLevel = "stress_level"
        case aiCoachingEnabled = "ai_coaching_enabled"
        case aiPersonalityPreference = "ai_personality_preference"
        case aiLanguageComplexity = "ai_language_complexity"
        case dataSharingConsent = "data_sharing_consent"
        case aiTrainingConsent = "ai_training_consent"
        case isActive = "is_active"
        case createdAt = "created_at"
        case systemId = "system_id"
        case primaryRole = "primary_role"
        case activeRoles = "active_roles"
        case isHealthcareProfessional = "is_healthcare_professional"
    }

    var firstName: String {
        fullName.components(separatedBy: " ").first ?? fullName
    }
}

/// Partial update payload — only non-nil fields are included in JSON.
struct UserUpdate: Encodable {
    var fullName: String?
    var dateOfBirth: String?
    var gender: String?
    var genderAtBirth: String?
    var profilePictureUrl: String?
    var bloodType: String?
    var insuranceId: String?
    var insuranceProvider: String?
    var insuranceCountry: String?
    var heightCm: Double?
    var currentWeightKg: Double?
    var targetWeightKg: Double?
    var locale: String?
    var timezone: String?
    var country: String?
    var preferredUnits: String?
    var preferredLanguage: String?
    var allergies: String?
    var foodIntolerances: String?
    var dietaryRestrictions: String?
    var dietaryPreferences: String?
    var familyHistory: String?
    var activityLevel: String?
    var fitnessGoals: String?
    var preferredActivities: String?
    var exerciseFrequencyPerWeek: Int?
    var smokingStatus: String?
    var alcoholConsumption: String?
    var sleepSchedule: String?
    var occupation: String?
    var stressLevel: String?
    var aiCoachingEnabled: Bool?
    var aiPersonalityPreference: String?
    var aiLanguageComplexity: String?
    var dataSharingConsent: Bool?
    var aiTrainingConsent: Bool?

    enum CodingKeys: String, CodingKey {
        case gender, locale, timezone, country, allergies, occupation
        case fullName = "full_name"
        case dateOfBirth = "date_of_birth"
        case genderAtBirth = "gender_at_birth"
        case profilePictureUrl = "profile_picture_url"
        case bloodType = "blood_type"
        case insuranceId = "insurance_id"
        case insuranceProvider = "insurance_provider"
        case insuranceCountry = "insurance_country"
        case heightCm = "height_cm"
        case currentWeightKg = "current_weight_kg"
        case targetWeightKg = "target_weight_kg"
        case preferredUnits = "preferred_units"
        case preferredLanguage = "preferred_language"
        case foodIntolerances = "food_intolerances"
        case dietaryRestrictions = "dietary_restrictions"
        case dietaryPreferences = "dietary_preferences"
        case familyHistory = "family_history"
        case activityLevel = "activity_level"
        case fitnessGoals = "fitness_goals"
        case preferredActivities = "preferred_activities"
        case exerciseFrequencyPerWeek = "exercise_frequency_per_week"
        case smokingStatus = "smoking_status"
        case alcoholConsumption = "alcohol_consumption"
        case sleepSchedule = "sleep_schedule"
        case stressLevel = "stress_level"
        case aiCoachingEnabled = "ai_coaching_enabled"
        case aiPersonalityPreference = "ai_personality_preference"
        case aiLanguageComplexity = "ai_language_complexity"
        case dataSharingConsent = "data_sharing_consent"
        case aiTrainingConsent = "ai_training_consent"
    }
}
