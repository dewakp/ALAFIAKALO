import Foundation

// MARK: - Prescription

struct Prescription: Codable, Identifiable {
    let id: Int
    let patientId: Int
    let prescriberId: Int
    let medicationName: String
    let rxnormCode: String?
    let dosage: String?
    let dosageUnit: String?
    let strength: String?
    let form: String?
    let route: String?
    let frequency: String?
    let durationDays: Int?
    let quantity: Int?
    let refillsAuthorized: Int
    let refillsRemaining: Int
    let diagnosis: String?
    let instructions: String?
    let pharmacyNotes: String?
    let substitutionAllowed: Bool
    let dawCode: String?
    let prescribedDate: String?
    let expiryDate: String?
    let startDate: String?
    let endDate: String?
    let status: String
    let isControlledSubstance: Bool
    let deaSchedule: String?
    let medicationId: Int?
    let createdAt: Date
    let updatedAt: Date
    let patientName: String?
    let prescriberName: String?
    let dispenseCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, dosage, strength, form, route, frequency, quantity, diagnosis, instructions, status
        case patientId = "patient_id"
        case prescriberId = "prescriber_id"
        case medicationName = "medication_name"
        case rxnormCode = "rxnorm_code"
        case dosageUnit = "dosage_unit"
        case durationDays = "duration_days"
        case refillsAuthorized = "refills_authorized"
        case refillsRemaining = "refills_remaining"
        case pharmacyNotes = "pharmacy_notes"
        case substitutionAllowed = "substitution_allowed"
        case dawCode = "daw_code"
        case prescribedDate = "prescribed_date"
        case expiryDate = "expiry_date"
        case startDate = "start_date"
        case endDate = "end_date"
        case isControlledSubstance = "is_controlled_substance"
        case deaSchedule = "dea_schedule"
        case medicationId = "medication_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case patientName = "patient_name"
        case prescriberName = "prescriber_name"
        case dispenseCount = "dispense_count"
    }

    var dosageDisplay: String {
        [dosage, dosageUnit].compactMap { $0 }.joined(separator: " ")
    }
}

struct PrescriptionCreate: Encodable {
    let patientId: Int
    let medicationName: String
    var dosage: String?
    var dosageUnit: String?
    var strength: String?
    var form: String?
    var route: String?
    var frequency: String?
    var durationDays: Int?
    var quantity: Int?
    var refillsAuthorized: Int = 0
    var diagnosis: String?
    var instructions: String?
    var substitutionAllowed: Bool = true

    enum CodingKeys: String, CodingKey {
        case dosage, strength, form, route, frequency, quantity, diagnosis, instructions
        case patientId = "patient_id"
        case medicationName = "medication_name"
        case dosageUnit = "dosage_unit"
        case durationDays = "duration_days"
        case refillsAuthorized = "refills_authorized"
        case substitutionAllowed = "substitution_allowed"
    }
}

// MARK: - Dispense

struct DispenseRecord: Codable, Identifiable {
    let id: Int
    let prescriptionId: Int
    let pharmacistId: Int
    let quantityDispensed: Int?
    let daysSupply: Int?
    let ndcCode: String?
    let lotNumber: String?
    let manufacturer: String?
    let isGeneric: Bool
    let interactionsChecked: Bool
    let allergyChecked: Bool
    let counselingProvided: Bool
    let clinicalNotes: String?
    let status: String
    let dispensedAt: Date?
    let createdAt: Date
    let pharmacistName: String?
    let medicationName: String?

    enum CodingKeys: String, CodingKey {
        case id, manufacturer, status
        case prescriptionId = "prescription_id"
        case pharmacistId = "pharmacist_id"
        case quantityDispensed = "quantity_dispensed"
        case daysSupply = "days_supply"
        case ndcCode = "ndc_code"
        case lotNumber = "lot_number"
        case isGeneric = "is_generic"
        case interactionsChecked = "interactions_checked"
        case allergyChecked = "allergy_checked"
        case counselingProvided = "counseling_provided"
        case clinicalNotes = "clinical_notes"
        case dispensedAt = "dispensed_at"
        case createdAt = "created_at"
        case pharmacistName = "pharmacist_name"
        case medicationName = "medication_name"
    }
}

struct DispenseCreate: Encodable {
    let prescriptionId: Int
    var quantityDispensed: Int?
    var daysSupply: Int?
    var ndcCode: String?
    var lotNumber: String?
    var manufacturer: String?
    var isGeneric: Bool = false
    var interactionsChecked: Bool = false
    var allergyChecked: Bool = false
    var counselingProvided: Bool = false
    var clinicalNotes: String?

    enum CodingKeys: String, CodingKey {
        case manufacturer
        case prescriptionId = "prescription_id"
        case quantityDispensed = "quantity_dispensed"
        case daysSupply = "days_supply"
        case ndcCode = "ndc_code"
        case lotNumber = "lot_number"
        case isGeneric = "is_generic"
        case interactionsChecked = "interactions_checked"
        case allergyChecked = "allergy_checked"
        case counselingProvided = "counseling_provided"
        case clinicalNotes = "clinical_notes"
    }
}

// MARK: - Adherence

struct AdherenceLog: Codable, Identifiable {
    let id: Int
    let patientId: Int
    let prescriptionId: Int
    let scheduledTime: Date
    let actualTime: Date?
    let status: String
    let doseTaken: String?
    let notes: String?
    let sideEffectsReported: String?
    let moodBefore: Int?
    let moodAfter: Int?
    let painBefore: Int?
    let painAfter: Int?
    let symptomChange: String?
    let createdAt: Date
    let medicationName: String?

    enum CodingKeys: String, CodingKey {
        case id, status, notes
        case patientId = "patient_id"
        case prescriptionId = "prescription_id"
        case scheduledTime = "scheduled_time"
        case actualTime = "actual_time"
        case doseTaken = "dose_taken"
        case sideEffectsReported = "side_effects_reported"
        case moodBefore = "mood_before"
        case moodAfter = "mood_after"
        case painBefore = "pain_before"
        case painAfter = "pain_after"
        case symptomChange = "symptom_change"
        case createdAt = "created_at"
        case medicationName = "medication_name"
    }
}

struct AdherenceLogCreate: Encodable {
    let prescriptionId: Int
    let scheduledTime: String
    var actualTime: String?
    var status: String = "taken"
    var doseTaken: String?
    var notes: String?
    var sideEffectsReported: String?
    var moodBefore: Int?
    var moodAfter: Int?
    var painBefore: Int?
    var painAfter: Int?

    enum CodingKeys: String, CodingKey {
        case status, notes
        case prescriptionId = "prescription_id"
        case scheduledTime = "scheduled_time"
        case actualTime = "actual_time"
        case doseTaken = "dose_taken"
        case sideEffectsReported = "side_effects_reported"
        case moodBefore = "mood_before"
        case moodAfter = "mood_after"
        case painBefore = "pain_before"
        case painAfter = "pain_after"
    }
}

struct AdherenceReport: Codable {
    let prescriptionId: Int?
    let patientId: Int
    let medicationName: String?
    let totalScheduled: Int
    let totalTaken: Int
    let totalMissed: Int
    let totalSkipped: Int
    let totalLate: Int
    let adherenceRate: Double
    let avgDelayMinutes: Double?
    let streakCurrent: Int
    let streakLongest: Int
    let commonSideEffects: [String]

    enum CodingKeys: String, CodingKey {
        case prescriptionId = "prescription_id"
        case patientId = "patient_id"
        case medicationName = "medication_name"
        case totalScheduled = "total_scheduled"
        case totalTaken = "total_taken"
        case totalMissed = "total_missed"
        case totalSkipped = "total_skipped"
        case totalLate = "total_late"
        case adherenceRate = "adherence_rate"
        case avgDelayMinutes = "avg_delay_minutes"
        case streakCurrent = "streak_current"
        case streakLongest = "streak_longest"
        case commonSideEffects = "common_side_effects"
    }
}

// MARK: - Schedule

struct MedicationSchedule: Codable, Identifiable {
    let id: Int
    let patientId: Int
    let prescriptionId: Int
    let timeOfDay: String
    let daysOfWeek: String?
    let doseLabel: String?
    let isActive: Bool
    let reminderMinutesBefore: Int
    let createdAt: Date
    let medicationName: String?

    enum CodingKeys: String, CodingKey {
        case id
        case patientId = "patient_id"
        case prescriptionId = "prescription_id"
        case timeOfDay = "time_of_day"
        case daysOfWeek = "days_of_week"
        case doseLabel = "dose_label"
        case isActive = "is_active"
        case reminderMinutesBefore = "reminder_minutes_before"
        case createdAt = "created_at"
        case medicationName = "medication_name"
    }
}

struct ScheduleCreate: Encodable {
    let prescriptionId: Int
    let timeOfDay: String
    var daysOfWeek: String?
    var doseLabel: String?
    var isActive: Bool = true
    var reminderMinutesBefore: Int = 15

    enum CodingKeys: String, CodingKey {
        case prescriptionId = "prescription_id"
        case timeOfDay = "time_of_day"
        case daysOfWeek = "days_of_week"
        case doseLabel = "dose_label"
        case isActive = "is_active"
        case reminderMinutesBefore = "reminder_minutes_before"
    }
}

// MARK: - Refill

struct RefillRequest: Codable, Identifiable {
    let id: Int
    let prescriptionId: Int
    let patientId: Int
    let requestedById: Int
    let approvedById: Int?
    let status: String
    let quantityRequested: Int?
    let notes: String?
    let denialReason: String?
    let requestedAt: Date
    let resolvedAt: Date?
    let medicationName: String?

    enum CodingKeys: String, CodingKey {
        case id, status, notes
        case prescriptionId = "prescription_id"
        case patientId = "patient_id"
        case requestedById = "requested_by_id"
        case approvedById = "approved_by_id"
        case quantityRequested = "quantity_requested"
        case denialReason = "denial_reason"
        case requestedAt = "requested_at"
        case resolvedAt = "resolved_at"
        case medicationName = "medication_name"
    }
}

struct RefillCreate: Encodable {
    let prescriptionId: Int
    var quantityRequested: Int?
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case notes
        case prescriptionId = "prescription_id"
        case quantityRequested = "quantity_requested"
    }
}

// MARK: - Impact

struct MedicationImpactReport: Codable {
    let prescriptionId: Int
    let medicationName: String
    let patientId: Int
    let analysisPeriodDays: Int
    let adherenceRate: Double
    let dosesTaken: Int
    let dosesMissed: Int
    let avgMoodBefore: Double?
    let avgMoodAfter: Double?
    let moodTrend: String?
    let reportedSideEffects: [String]
    let sideEffectFrequency: [String: Int]?
    let effectivenessScore: Double?
    let tolerabilityScore: Double?
    let aiSummary: String?

    enum CodingKeys: String, CodingKey {
        case prescriptionId = "prescription_id"
        case medicationName = "medication_name"
        case patientId = "patient_id"
        case analysisPeriodDays = "analysis_period_days"
        case adherenceRate = "adherence_rate"
        case dosesTaken = "doses_taken"
        case dosesMissed = "doses_missed"
        case avgMoodBefore = "avg_mood_before"
        case avgMoodAfter = "avg_mood_after"
        case moodTrend = "mood_trend"
        case reportedSideEffects = "reported_side_effects"
        case sideEffectFrequency = "side_effect_frequency"
        case effectivenessScore = "effectiveness_score"
        case tolerabilityScore = "tolerability_score"
        case aiSummary = "ai_summary"
    }
}
