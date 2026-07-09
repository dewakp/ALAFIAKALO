import Foundation

struct Medication: Codable, Identifiable {
    let id: Int
    let userId: Int
    let name: String
    let rxnormCode: String?
    let dosage: String?
    let dosageUnit: String?
    let frequency: String?
    let route: String?
    let startDate: String?
    let endDate: String?
    let prescribingDoctor: String?
    let reason: String?
    let sideEffects: String?
    let isActive: Bool
    let notes: String?
    let source: String?     // nil = entered manually; else importing portal/org
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, dosage, frequency, route, reason, notes, source
        case userId = "user_id"
        case rxnormCode = "rxnorm_code"
        case dosageUnit = "dosage_unit"
        case startDate = "start_date"
        case endDate = "end_date"
        case prescribingDoctor = "prescribing_doctor"
        case sideEffects = "side_effects"
        case isActive = "is_active"
        case createdAt = "created_at"
    }
    
    var dosageDisplay: String {
        [dosage, dosageUnit].compactMap { $0 }.joined(separator: " ")
    }
}

struct MedicationCreate: Encodable {
    let name: String
    var dosage: String?
    var dosageUnit: String?
    var frequency: String?
    var route: String?
    var startDate: String?
    var prescribingDoctor: String?
    var reason: String?
    var isActive: Bool = true

    enum CodingKeys: String, CodingKey {
        case name, dosage, frequency, route, reason
        case dosageUnit = "dosage_unit"
        case startDate = "start_date"
        case prescribingDoctor = "prescribing_doctor"
        case isActive = "is_active"
    }
}

// MARK: - Dose Logging

/// A recorded "taken" event for a medication dose.
struct MedicationDoseLog: Decodable, Identifiable {
    let id: Int
    let medicationId: Int?
    let medicationName: String
    let logDate: String
    let doseAmount: Double
    let doseUnit: String
    let nutrientsResolved: Bool
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case id, notes
        case medicationId = "medication_id"
        case medicationName = "medication_name"
        case logDate = "log_date"
        case doseAmount = "dose_amount"
        case doseUnit = "dose_unit"
        case nutrientsResolved = "nutrients_resolved"
    }
}

/// Payload for recording that a dose was taken (POST /medications/dose-logs).
struct MedicationDoseLogCreate: Encodable {
    let medicationName: String
    let logDate: String
    let doseAmount: Double
    let doseUnit: String
    var medicationId: Int?
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case notes
        case medicationName = "medication_name"
        case logDate = "log_date"
        case doseAmount = "dose_amount"
        case doseUnit = "dose_unit"
        case medicationId = "medication_id"
    }
}
