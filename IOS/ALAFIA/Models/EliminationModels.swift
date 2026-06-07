import Foundation

// MARK: - Bowel Movement

struct BowelMovement: Codable, Identifiable {
    let id: Int
    let userId: Int
    let logDate: String
    let logTime: String?
    let bristolScale: Int?
    let color: String?
    let consistency: String?
    let size: String?
    let bloodPresent: Bool?
    let mucusPresent: Bool?
    let undigestedFood: Bool?
    let painLevel: Int?
    let straining: Bool?
    let urgency: Bool?
    let durationMinutes: Int?
    let location: String?
    let associatedSymptoms: String?
    let notes: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, color, consistency, size, location, notes
        case userId = "user_id"
        case logDate = "log_date"
        case logTime = "log_time"
        case bristolScale = "bristol_scale"
        case bloodPresent = "blood_present"
        case mucusPresent = "mucus_present"
        case undigestedFood = "undigested_food"
        case painLevel = "pain_level"
        case straining, urgency
        case durationMinutes = "duration_minutes"
        case associatedSymptoms = "associated_symptoms"
        case createdAt = "created_at"
    }

    var bristolDescription: String {
        switch bristolScale {
        case 1: return "Type 1 – Hard lumps"
        case 2: return "Type 2 – Lumpy sausage"
        case 3: return "Type 3 – Crack surface"
        case 4: return "Type 4 – Smooth sausage"
        case 5: return "Type 5 – Soft blobs"
        case 6: return "Type 6 – Fluffy pieces"
        case 7: return "Type 7 – Liquid"
        default: return "Not recorded"
        }
    }
}

struct BowelMovementCreate: Encodable {
    var logDate: String
    var logTime: String?
    var bristolScale: Int?
    var color: String?
    var consistency: String?
    var bloodPresent: Bool?
    var mucusPresent: Bool?
    var painLevel: Int?
    var straining: Bool?
    var urgency: Bool?
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case logDate = "log_date"
        case logTime = "log_time"
        case bristolScale = "bristol_scale"
        case color, consistency, notes, straining, urgency
        case bloodPresent = "blood_present"
        case mucusPresent = "mucus_present"
        case painLevel = "pain_level"
    }
}

// MARK: - Urination Log

struct UrinationLog: Codable, Identifiable {
    let id: Int
    let userId: Int
    let logDate: String
    let logTime: String?
    let color: String?
    let clarity: String?
    let odor: String?
    let volumeMl: Int?
    let streamStrength: String?
    let painLevel: Int?
    let burningSensation: Bool?
    let urgency: Bool?
    let frequencyIncreased: Bool?
    let bloodPresent: Bool?
    let location: String?
    let nighttime: Bool?
    let notes: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, color, clarity, odor, location, notes, urgency, nighttime
        case userId = "user_id"
        case logDate = "log_date"
        case logTime = "log_time"
        case volumeMl = "volume_ml"
        case streamStrength = "stream_strength"
        case painLevel = "pain_level"
        case burningSensation = "burning_sensation"
        case frequencyIncreased = "frequency_increased"
        case bloodPresent = "blood_present"
        case createdAt = "created_at"
    }
}

struct UrinationLogCreate: Encodable {
    var logDate: String
    var logTime: String?
    var color: String?
    var clarity: String?
    var volumeMl: Int?
    var painLevel: Int?
    var burningSensation: Bool?
    var urgency: Bool?
    var bloodPresent: Bool?
    var nighttime: Bool?
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case logDate = "log_date"
        case logTime = "log_time"
        case color, clarity, notes, urgency, nighttime
        case volumeMl = "volume_ml"
        case painLevel = "pain_level"
        case burningSensation = "burning_sensation"
        case bloodPresent = "blood_present"
    }
}

// MARK: - Vomiting Log

struct VomitingLog: Codable, Identifiable {
    let id: Int
    let userId: Int
    let logDate: String
    let logTime: String?
    let volume: String?
    let color: String?
    let consistency: String?
    let containsFood: Bool?
    let containsBile: Bool?
    let containsBlood: Bool?
    let nauseaBefore: Bool?
    let nauseaAfter: Bool?
    let projectile: Bool?
    let trigger: String?
    let timeSinceLastMealHours: Double?
    let reliefAfter: Bool?
    let fever: Bool?
    let diarrhea: Bool?
    let headache: Bool?
    let dizziness: Bool?
    let notes: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, volume, color, consistency, trigger, fever, diarrhea, headache, dizziness, notes
        case userId = "user_id"
        case logDate = "log_date"
        case logTime = "log_time"
        case containsFood = "contains_food"
        case containsBile = "contains_bile"
        case containsBlood = "contains_blood"
        case nauseaBefore = "nausea_before"
        case nauseaAfter = "nausea_after"
        case projectile
        case timeSinceLastMealHours = "time_since_last_meal_hours"
        case reliefAfter = "relief_after"
        case createdAt = "created_at"
    }
}

struct VomitingLogCreate: Encodable {
    var logDate: String
    var logTime: String?
    var volume: String?
    var containsFood: Bool?
    var containsBile: Bool?
    var containsBlood: Bool?
    var nauseaBefore: Bool?
    var nauseaAfter: Bool?
    var projectile: Bool?
    var trigger: String?
    var reliefAfter: Bool?
    var fever: Bool?
    var dizziness: Bool?
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case logDate = "log_date"
        case logTime = "log_time"
        case volume, trigger, fever, dizziness, notes, projectile
        case containsFood = "contains_food"
        case containsBile = "contains_bile"
        case containsBlood = "contains_blood"
        case nauseaBefore = "nausea_before"
        case nauseaAfter = "nausea_after"
        case reliefAfter = "relief_after"
    }
}
