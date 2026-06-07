import Foundation

struct FitnessLog: Codable, Identifiable {
    let id: Int
    let userId: Int
    let logDate: String
    let activityType: String
    let durationMinutes: Int?
    let distanceKm: Double?
    let caloriesBurned: Double?
    let heartRateAvg: Int?
    let heartRateMax: Int?
    let steps: Int?
    let sets: Int?
    let reps: Int?
    let weightKg: Double?
    let intensity: String?
    let notes: String?
    let createdAt: Date
    
    enum CodingKeys: String, CodingKey {
        case id, steps, sets, reps, intensity, notes
        case userId = "user_id"
        case logDate = "log_date"
        case activityType = "activity_type"
        case durationMinutes = "duration_minutes"
        case distanceKm = "distance_km"
        case caloriesBurned = "calories_burned"
        case heartRateAvg = "heart_rate_avg"
        case heartRateMax = "heart_rate_max"
        case weightKg = "weight_kg"
        case createdAt = "created_at"
    }
}

struct FitnessLogCreate: Encodable {
    let logDate: String
    let activityType: String
    var durationMinutes: Int?
    var caloriesBurned: Double?
    var steps: Int?
    var intensity: String?
    var notes: String?
    
    enum CodingKeys: String, CodingKey {
        case logDate = "log_date"
        case activityType = "activity_type"
        case durationMinutes = "duration_minutes"
        case caloriesBurned = "calories_burned"
        case steps, intensity, notes
    }
}
