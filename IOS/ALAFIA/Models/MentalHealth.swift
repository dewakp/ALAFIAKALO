import Foundation

// MARK: - Assessment

struct MentalHealthAssessment: Codable, Identifiable {
    let id: Int
    let userId: Int
    let assessmentDate: String
    let assessmentType: String // phq9, gad7, who5
    let totalScore: Int?
    let severity: String?
    let createdAt: String?

    // PHQ-9 fields
    let phqInterest: Int?
    let phqFeelingDown: Int?
    let phqSleep: Int?
    let phqEnergy: Int?
    let phqAppetite: Int?
    let phqSelfEsteem: Int?
    let phqConcentration: Int?
    let phqPsychomotor: Int?
    let phqSuicidalIdeation: Int?

    // GAD-7 fields
    let gadNervous: Int?
    let gadUncontrollableWorry: Int?
    let gadExcessiveWorry: Int?
    let gadTroubleRelaxing: Int?
    let gadRestless: Int?
    let gadIrritable: Int?
    let gadAfraid: Int?

    // WHO-5 fields
    let who5Cheerful: Int?
    let who5Calm: Int?
    let who5Active: Int?
    let who5Rested: Int?
    let who5Interesting: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case assessmentDate = "assessment_date"
        case assessmentType = "assessment_type"
        case totalScore = "total_score"
        case severity
        case createdAt = "created_at"
        case phqInterest = "phq_interest"
        case phqFeelingDown = "phq_feeling_down"
        case phqSleep = "phq_sleep"
        case phqEnergy = "phq_energy"
        case phqAppetite = "phq_appetite"
        case phqSelfEsteem = "phq_self_esteem"
        case phqConcentration = "phq_concentration"
        case phqPsychomotor = "phq_psychomotor"
        case phqSuicidalIdeation = "phq_suicidal_ideation"
        case gadNervous = "gad_nervous"
        case gadUncontrollableWorry = "gad_uncontrollable_worry"
        case gadExcessiveWorry = "gad_excessive_worry"
        case gadTroubleRelaxing = "gad_trouble_relaxing"
        case gadRestless = "gad_restless"
        case gadIrritable = "gad_irritable"
        case gadAfraid = "gad_afraid"
        case who5Cheerful = "who5_cheerful"
        case who5Calm = "who5_calm"
        case who5Active = "who5_active"
        case who5Rested = "who5_rested"
        case who5Interesting = "who5_interesting"
    }
}

struct AssessmentCreate: Encodable {
    let assessmentDate: String
    let assessmentType: String
    var phqInterest: Int?
    var phqFeelingDown: Int?
    var phqSleep: Int?
    var phqEnergy: Int?
    var phqAppetite: Int?
    var phqSelfEsteem: Int?
    var phqConcentration: Int?
    var phqPsychomotor: Int?
    var phqSuicidalIdeation: Int?
    var gadNervous: Int?
    var gadUncontrollableWorry: Int?
    var gadExcessiveWorry: Int?
    var gadTroubleRelaxing: Int?
    var gadRestless: Int?
    var gadIrritable: Int?
    var gadAfraid: Int?
    var who5Cheerful: Int?
    var who5Calm: Int?
    var who5Active: Int?
    var who5Rested: Int?
    var who5Interesting: Int?

    enum CodingKeys: String, CodingKey {
        case assessmentDate = "assessment_date"
        case assessmentType = "assessment_type"
        case phqInterest = "phq_interest"
        case phqFeelingDown = "phq_feeling_down"
        case phqSleep = "phq_sleep"
        case phqEnergy = "phq_energy"
        case phqAppetite = "phq_appetite"
        case phqSelfEsteem = "phq_self_esteem"
        case phqConcentration = "phq_concentration"
        case phqPsychomotor = "phq_psychomotor"
        case phqSuicidalIdeation = "phq_suicidal_ideation"
        case gadNervous = "gad_nervous"
        case gadUncontrollableWorry = "gad_uncontrollable_worry"
        case gadExcessiveWorry = "gad_excessive_worry"
        case gadTroubleRelaxing = "gad_trouble_relaxing"
        case gadRestless = "gad_restless"
        case gadIrritable = "gad_irritable"
        case gadAfraid = "gad_afraid"
        case who5Cheerful = "who5_cheerful"
        case who5Calm = "who5_calm"
        case who5Active = "who5_active"
        case who5Rested = "who5_rested"
        case who5Interesting = "who5_interesting"
    }
}

// MARK: - Breathing

struct BreathingExerciseInfo: Codable, Identifiable {
    let id: String
    let name: String
    let description: String
    let inhaleSeconds: Int
    let holdSeconds: Int
    let exhaleSeconds: Int
    let holdAfterExhaleSeconds: Int
    let recommendedCycles: Int
    let benefits: [String]

    enum CodingKeys: String, CodingKey {
        case id, name, description, benefits
        case inhaleSeconds = "inhale_seconds"
        case holdSeconds = "hold_seconds"
        case exhaleSeconds = "exhale_seconds"
        case holdAfterExhaleSeconds = "hold_after_exhale_seconds"
        case recommendedCycles = "recommended_cycles"
    }
}

struct BreathingSession: Codable, Identifiable {
    let id: Int
    let userId: Int
    let sessionDate: String
    let exerciseType: String
    let durationSeconds: Int
    let moodBefore: Int?
    let moodAfter: Int?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case sessionDate = "session_date"
        case exerciseType = "exercise_type"
        case durationSeconds = "duration_seconds"
        case moodBefore = "mood_before"
        case moodAfter = "mood_after"
        case createdAt = "created_at"
    }
}

struct BreathingSessionCreate: Encodable {
    let sessionDate: String
    let exerciseType: String
    let durationSeconds: Int
    let moodBefore: Int?
    let moodAfter: Int?

    enum CodingKeys: String, CodingKey {
        case sessionDate = "session_date"
        case exerciseType = "exercise_type"
        case durationSeconds = "duration_seconds"
        case moodBefore = "mood_before"
        case moodAfter = "mood_after"
    }
}

// MARK: - Gratitude

struct GratitudeEntry: Codable, Identifiable {
    let id: Int
    let userId: Int
    let entryDate: String
    let item1: String
    let item2: String?
    let item3: String?
    let reflection: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case entryDate = "entry_date"
        case item1 = "item_1"
        case item2 = "item_2"
        case item3 = "item_3"
        case reflection
        case createdAt = "created_at"
    }
}

struct GratitudeCreate: Encodable {
    let entryDate: String
    let item1: String
    let item2: String?
    let item3: String?
    let reflection: String?

    enum CodingKeys: String, CodingKey {
        case entryDate = "entry_date"
        case item1 = "item_1"
        case item2 = "item_2"
        case item3 = "item_3"
        case reflection
    }
}

// MARK: - Stats

struct MentalHealthStats: Codable {
    let avgMood7d: Double?
    let avgMood30d: Double?
    let avgStress7d: Double?
    let avgAnxiety7d: Double?
    let avgSleepQuality7d: Double?
    let avgSleepHours7d: Double?
    let moodTrend: String?
    let totalEntries30d: Int
    let streakDays: Int
    let totalBreathingMinutes30d: Int
    let latestPhq9Score: Int?
    let latestPhq9Severity: String?
    let latestGad7Score: Int?
    let latestGad7Severity: String?
    let latestWho5Score: Int?
    let wellnessScore: Int?

    enum CodingKeys: String, CodingKey {
        case avgMood7d = "avg_mood_7d"
        case avgMood30d = "avg_mood_30d"
        case avgStress7d = "avg_stress_7d"
        case avgAnxiety7d = "avg_anxiety_7d"
        case avgSleepQuality7d = "avg_sleep_quality_7d"
        case avgSleepHours7d = "avg_sleep_hours_7d"
        case moodTrend = "mood_trend"
        case totalEntries30d = "total_entries_30d"
        case streakDays = "streak_days"
        case totalBreathingMinutes30d = "total_breathing_minutes_30d"
        case latestPhq9Score = "latest_phq9_score"
        case latestPhq9Severity = "latest_phq9_severity"
        case latestGad7Score = "latest_gad7_score"
        case latestGad7Severity = "latest_gad7_severity"
        case latestWho5Score = "latest_who5_score"
        case wellnessScore = "wellness_score"
    }
}
