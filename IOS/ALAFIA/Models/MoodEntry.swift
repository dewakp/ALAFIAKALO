import Foundation

struct MoodEntry: Codable, Identifiable {
    let id: Int
    let userId: Int
    let entryDate: String
    let moodScore: Int
    let energyLevel: Int?
    let stressLevel: Int?
    let anxietyLevel: Int?
    let sleepQuality: Int?
    let sleepHours: Double?
    let emotions: String?
    let triggers: String?
    let copingStrategies: String?
    let gratitude: String?
    let journalEntry: String?
    let notes: String?
    let createdAt: Date
    
    enum CodingKeys: String, CodingKey {
        case id, emotions, triggers, gratitude, notes
        case userId = "user_id"
        case entryDate = "entry_date"
        case moodScore = "mood_score"
        case energyLevel = "energy_level"
        case stressLevel = "stress_level"
        case anxietyLevel = "anxiety_level"
        case sleepQuality = "sleep_quality"
        case sleepHours = "sleep_hours"
        case copingStrategies = "coping_strategies"
        case journalEntry = "journal_entry"
        case createdAt = "created_at"
    }
    
    var moodEmoji: String {
        switch moodScore {
        case 8...10: return "😄"
        case 6...7: return "🙂"
        case 4...5: return "😐"
        case 2...3: return "😔"
        default: return "😢"
        }
    }
}

struct MoodEntryCreate: Encodable {
    let entryDate: String
    var moodScore: Int = 5
    var energyLevel: Int? = 5
    var stressLevel: Int? = 5
    var anxietyLevel: Int? = 5
    var sleepQuality: Int? = 5
    var sleepHours: Double?
    var emotions: String?
    var triggers: String?
    var copingStrategies: String?
    var gratitude: String?
    var journalEntry: String?
    
    enum CodingKeys: String, CodingKey {
        case entryDate = "entry_date"
        case moodScore = "mood_score"
        case energyLevel = "energy_level"
        case stressLevel = "stress_level"
        case anxietyLevel = "anxiety_level"
        case sleepQuality = "sleep_quality"
        case sleepHours = "sleep_hours"
        case emotions, triggers, gratitude
        case copingStrategies = "coping_strategies"
        case journalEntry = "journal_entry"
    }
}

// MARK: - AI-proposed mood score

struct MoodScoreRequest: Encodable {
    let notes: String
}

/// A PROPOSED mood score, read from what the patient wrote.
///
/// The web form used to pre-fill 7/10 — "Good" — and save that for anyone who
/// typed an entry without moving the slider, so "exhausted and fatigued" was
/// filed as Good. This proposes a number WITH its reason; the user still saves.
///
/// `available == false` means the model was unreachable or unusable. That is
/// not a score: the client falls back to asking, never to a made-up value.
struct MoodScoreSuggestion: Decodable {
    let moodScore: Int?
    let energyLevel: Int?
    let rationale: String
    let available: Bool

    enum CodingKeys: String, CodingKey {
        case moodScore = "mood_score"
        case energyLevel = "energy_level"
        case rationale, available
    }
}
