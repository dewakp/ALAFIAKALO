import Foundation

struct LifestyleEntry: Codable, Identifiable {
    let id: Int
    let userId: Int
    let entryDate: String
    let weightKg: Double?
    let heightCm: Double?
    let bmi: Double?
    let bloodPressureSystolic: Int?
    let bloodPressureDiastolic: Int?
    let restingHeartRate: Int?
    let bodyTemperatureC: Double?
    let bloodOxygenPct: Double?
    let smokingStatus: String?
    let alcoholDrinks: Int?
    let caffeineMg: Double?
    let screenTimeMinutes: Int?
    let outdoorTimeMinutes: Int?
    let socialInteractions: Int?
    let notes: String?
    let createdAt: Date
    
    enum CodingKeys: String, CodingKey {
        case id, bmi, notes
        case userId = "user_id"
        case entryDate = "entry_date"
        case weightKg = "weight_kg"
        case heightCm = "height_cm"
        case bloodPressureSystolic = "blood_pressure_systolic"
        case bloodPressureDiastolic = "blood_pressure_diastolic"
        case restingHeartRate = "resting_heart_rate"
        case bodyTemperatureC = "body_temperature_c"
        case bloodOxygenPct = "blood_oxygen_pct"
        case smokingStatus = "smoking_status"
        case alcoholDrinks = "alcohol_drinks"
        case caffeineMg = "caffeine_mg"
        case screenTimeMinutes = "screen_time_minutes"
        case outdoorTimeMinutes = "outdoor_time_minutes"
        case socialInteractions = "social_interactions"
        case createdAt = "created_at"
    }
    
    var bloodPressure: String? {
        guard let sys = bloodPressureSystolic, let dia = bloodPressureDiastolic else { return nil }
        return "\(sys)/\(dia)"
    }
}

struct LifestyleEntryCreate: Encodable {
    let entryDate: String
    var weightKg: Double?
    var bloodPressureSystolic: Int?
    var bloodPressureDiastolic: Int?
    var restingHeartRate: Int?
    var bodyTemperatureC: Double?
    var bloodOxygenPct: Double?
    var screenTimeMinutes: Int?
    var outdoorTimeMinutes: Int?
    var notes: String?
    
    enum CodingKeys: String, CodingKey {
        case entryDate = "entry_date"
        case weightKg = "weight_kg"
        case bloodPressureSystolic = "blood_pressure_systolic"
        case bloodPressureDiastolic = "blood_pressure_diastolic"
        case restingHeartRate = "resting_heart_rate"
        case bodyTemperatureC = "body_temperature_c"
        case bloodOxygenPct = "blood_oxygen_pct"
        case screenTimeMinutes = "screen_time_minutes"
        case outdoorTimeMinutes = "outdoor_time_minutes"
        case notes
    }
}
