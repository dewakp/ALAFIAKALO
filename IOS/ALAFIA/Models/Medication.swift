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

/// A recorded "taken" event for a medication dose (with pre-medication vitals).
struct MedicationDoseLog: Decodable, Identifiable {
    let id: Int
    let medicationId: Int?
    let medicationName: String
    let logDate: String
    let logTime: String?
    let doseAmount: Double
    let doseUnit: String
    let preSystolicBp: Int?
    let preDiastolicBp: Int?
    let preHeartRate: Int?
    let preTemperatureC: Double?
    let postSystolicBp: Int?
    let postDiastolicBp: Int?
    let postHeartRate: Int?
    let postTemperatureC: Double?
    let nutrientsResolved: Bool
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case id, notes
        case medicationId = "medication_id"
        case medicationName = "medication_name"
        case logDate = "log_date"
        case logTime = "log_time"
        case doseAmount = "dose_amount"
        case doseUnit = "dose_unit"
        case preSystolicBp = "pre_systolic_bp"
        case preDiastolicBp = "pre_diastolic_bp"
        case preHeartRate = "pre_heart_rate"
        case preTemperatureC = "pre_temperature_c"
        case postSystolicBp = "post_systolic_bp"
        case postDiastolicBp = "post_diastolic_bp"
        case postHeartRate = "post_heart_rate"
        case postTemperatureC = "post_temperature_c"
        case nutrientsResolved = "nutrients_resolved"
    }

    /// "HH:mm" for display, from a "HH:mm:ss" backend time.
    var timeDisplay: String? {
        guard let t = logTime, t.count >= 5 else { return nil }
        return String(t.prefix(5))
    }
    var hasVitals: Bool {
        preSystolicBp != nil || preDiastolicBp != nil || preHeartRate != nil || preTemperatureC != nil
    }
}

/// Payload for recording that a dose was taken (POST /medications/dose-logs).
struct MedicationDoseLogCreate: Encodable {
    let medicationName: String
    let logDate: String
    let doseAmount: Double
    let doseUnit: String
    var logTime: String? = nil
    var medicationId: Int? = nil
    var preSystolicBp: Int? = nil
    var preDiastolicBp: Int? = nil
    var preHeartRate: Int? = nil
    var preTemperatureC: Double? = nil
    var notes: String? = nil
    /// Records a dose the guard flagged, deliberately. The guard fails OPEN on an
    /// unreachable RxNorm, so this is for a dose the PATIENT confirms is right —
    /// never a default, and never set without showing them what was flagged.
    var acknowledgeUnusual: Bool = false

    enum CodingKeys: String, CodingKey {
        case notes
        case medicationName = "medication_name"
        case logDate = "log_date"
        case logTime = "log_time"
        case doseAmount = "dose_amount"
        case doseUnit = "dose_unit"
        case medicationId = "medication_id"
        case preSystolicBp = "pre_systolic_bp"
        case preDiastolicBp = "pre_diastolic_bp"
        case preHeartRate = "pre_heart_rate"
        case preTemperatureC = "pre_temperature_c"
        case acknowledgeUnusual = "acknowledge_unusual"
    }
}

/// One drug this patient actually takes, from their own dose logs
/// (`GET /medications/frequent`).
///
/// The intake picker used to offer PRESCRIPTIONS only. On the production record
/// that is 943 dose logs against zero prescriptions — so typing "Calcium"
/// offered nothing while the history held Calcium carbonate 489 times. Canon
/// §3aa: prescribed and taken are different facts, and reading one table and
/// calling it the answer hides the other.
struct FrequentMedication: Decodable, Identifiable {
    let name: String
    let timesLogged: Int
    let lastTaken: String?

    var id: String { name.lowercased() }

    enum CodingKeys: String, CodingKey {
        case name
        case timesLogged = "times_logged"
        case lastTaken = "last_taken"
    }
}

/// What the dose guard refused, and how to proceed anyway
/// (the `detail` object of a 422 from `POST /medications/dose-logs`).
///
/// This is the half that mobile threw away. iOS decoded `detail` as a String,
/// which fails on an object, so a refusal rendered as "Request failed (422)" —
/// no reason, no suggestion, no route forward, on a guard that had already
/// worked out that "Calcium Carbonated" should be "Calcium Carbonate". A guard
/// that cannot explain itself gets blamed for the thing it did not do.
struct DoseGuardRefusal: Decodable {
    struct Detail: Decodable {
        let message: String
        let findings: [MedicationDoseFinding]
        let overrideWith: String?

        enum CodingKeys: String, CodingKey {
            case message, findings
            case overrideWith = "override_with"
        }
    }
    let detail: Detail

    /// Decodes a refusal out of an `APIError`, or nil if this was some other failure.
    static func from(_ error: Error) -> DoseGuardRefusal? {
        guard case APIError.structured(_, let status, let body) = error, status == 422 else {
            return nil
        }
        guard let refusal = try? JSONDecoder().decode(DoseGuardRefusal.self, from: body),
              !refusal.detail.findings.isEmpty else { return nil }
        return refusal
    }
}

/// °F ↔ °C helpers (backend stores medication-dose temps in °C).
enum TempConvert {
    static func toCelsius(_ fahrenheit: Double) -> Double { (fahrenheit - 32) * 5 / 9 }
    static func toFahrenheit(_ celsius: Double) -> Double { celsius * 9 / 5 + 32 }
    static func fahrenheitString(fromCelsius c: Double) -> String { String(format: "%.1f°F", toFahrenheit(c)) }
}

/// A dose read out of free text ("I take Calcitriol") that the user confirms.
///
/// The backend supplies a missing dose from this user's own logging history and
/// says where it came from. It writes nothing — on this data most user/medication
/// pairs use more than one dose over time, so a proposal is honest and a silent
/// write is not. `findings` carries anything the dose guard could prove wrong.
struct MedicationIntakeProposal: Decodable {
    let medicationName: String
    let doseAmount: Double?
    let doseUnit: String?
    let doseSource: String        // stated | history | prescription | unknown
    let provenance: String?
    let confidence: Double
    let needsConfirmation: Bool
    let findings: [MedicationDoseFinding]

    var hasDose: Bool { doseAmount != nil }
    var blocking: [MedicationDoseFinding] { findings.filter { $0.level == "error" } }

    enum CodingKeys: String, CodingKey {
        case provenance, confidence, findings
        case medicationName = "medication_name"
        case doseAmount = "dose_amount"
        case doseUnit = "dose_unit"
        case doseSource = "dose_source"
        case needsConfirmation = "needs_confirmation"
    }
}

struct MedicationDoseFinding: Decodable, Identifiable {
    let level: String             // "error" | "warning"
    let code: String
    let message: String
    let suggestion: String?
    var id: String { code + message }
}

struct MedicationIntakeRequest: Encodable {
    let text: String
}
