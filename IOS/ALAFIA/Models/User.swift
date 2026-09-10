import Foundation

struct User: Codable, Identifiable {
    let id: Int
    let email: String
    let fullName: String
    // The parts. `fullName` stays for display and for the accounts that
    // predate the split; these are what a form edits.
    let givenName: String?
    let familyName: String?
    let middleName: String?
    let namePrefix: String?
    let nameSuffix: String?

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
        case givenName = "first_name"
        case familyName = "last_name"
        case middleName = "middle_name"
        case namePrefix = "name_prefix"
        case nameSuffix = "name_suffix"
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

    /// What to call this person on a greeting.
    ///
    /// Prefers the field the server actually holds. The split is the fallback
    /// for accounts that predate the two-field signup — it is a guess, and a
    /// wrong one for anyone whose first name is two words, which is exactly
    /// why the parts are now stored rather than derived.
    var firstName: String {
        if let given = givenName, !given.isEmpty { return given }
        return fullName.components(separatedBy: " ").first ?? fullName
    }

    static let preview = User(
        id: 1,
        email: "preview@alafia.health",
        fullName: "Amina Kone",
        givenName: "Amina",
        familyName: "Kone",
        middleName: nil,
        namePrefix: nil,
        nameSuffix: nil,
        dateOfBirth: "1990-05-14",
        gender: "Female",
        genderAtBirth: "Female",
        profilePictureUrl: nil,
        bloodType: "O+",
        insuranceId: "PREVIEW123",
        insuranceProvider: "HealthSafe",
        insuranceCountry: "US",
        heightCm: 168,
        currentWeightKg: 68,
        targetWeightKg: 64,
        locale: "en_US",
        timezone: "America/New_York",
        country: "US",
        preferredUnits: "metric",
        preferredLanguage: "English",
        allergies: "None",
        foodIntolerances: "None",
        dietaryRestrictions: "Vegetarian",
        dietaryPreferences: "Whole foods",
        familyHistory: "Hypertension",
        activityLevel: "moderately_active",
        fitnessGoals: "Strength",
        preferredActivities: "Walking, Yoga",
        exerciseFrequencyPerWeek: 3,
        smokingStatus: "never",
        alcoholConsumption: "occasional",
        sleepSchedule: "night_owl",
        occupation: "Product Designer",
        stressLevel: "moderate",
        aiCoachingEnabled: true,
        aiPersonalityPreference: "supportive",
        aiLanguageComplexity: "moderate",
        dataSharingConsent: true,
        aiTrainingConsent: false,
        isActive: true,
        createdAt: Date(),
        systemId: "preview-system",
        primaryRole: "user",
        activeRoles: ["user"],
        isHealthcareProfessional: false
    )
}

/// Partial update payload — only non-nil fields are included in JSON.
struct UserUpdate: Encodable {
    var fullName: String?
    var firstName: String?
    var lastName: String?
    var middleName: String?
    var namePrefix: String?
    var nameSuffix: String?
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
    /// The unit the values above are in ("cm"/"in", "kg"/"lb"). The backend
    /// converts to what it stores. Omitting these means "already metric",
    /// which is how an imperial patient's height of 70 was stored as 70 cm.
    var heightUnit: String?
    var weightUnit: String?
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
        case firstName = "first_name"
        case lastName = "last_name"
        case middleName = "middle_name"
        case namePrefix = "name_prefix"
        case nameSuffix = "name_suffix"
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
        case heightUnit = "height_unit"
        case weightUnit = "weight_unit"
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
