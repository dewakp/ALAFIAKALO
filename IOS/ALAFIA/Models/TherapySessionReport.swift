import Foundation

/// The physician's read of one dialysis session.
///
/// Served by `/clinician-dashboard/patient/{id}/therapy-sessions/{sid}` — the
/// clinician-scoped route. The patient-side `/chronic/therapy-sessions/*`
/// endpoints filter by the CALLER's user id, so a physician opening a patient's
/// session got a 404 from them, including from `/review`.
struct TherapySessionDetail: Codable, Hashable {
    let id: Int
    let date: String
    let therapy: String?
    let name: String?
    let status: String?
    let facilityName: String?
    let attendingPhysician: String?
    let attendingNurse: String?
    let dialysisAccessType: String?
    let durationMinutes: Int?
    let preDialysisWeightKg: Double?
    let postDialysisWeightKg: Double?
    let dryWeightKg: Double?
    let fluidRemovedMl: Double?
    let bloodFlowRate: Double?
    let dialysateFlowRate: Double?
    let preSystolicBp: Int?
    let preDiastolicBp: Int?
    let postSystolicBp: Int?
    let postDiastolicBp: Int?
    let preHeartRate: Int?
    let postHeartRate: Int?
    let preTemperature: Double?
    let postTemperature: Double?
    let complications: String?
    let adverseReactions: String?
    let patientTolerance: String?
    let patientNotes: String?

    enum CodingKeys: String, CodingKey {
        case id, date, therapy, name, status, complications
        case facilityName = "facility_name"
        case attendingPhysician = "attending_physician"
        case attendingNurse = "attending_nurse"
        case dialysisAccessType = "dialysis_access_type"
        case durationMinutes = "duration_minutes"
        case preDialysisWeightKg = "pre_dialysis_weight_kg"
        case postDialysisWeightKg = "post_dialysis_weight_kg"
        case dryWeightKg = "dry_weight_kg"
        case fluidRemovedMl = "fluid_removed_ml"
        case bloodFlowRate = "blood_flow_rate"
        case dialysateFlowRate = "dialysate_flow_rate"
        case preSystolicBp = "pre_systolic_bp"
        case preDiastolicBp = "pre_diastolic_bp"
        case postSystolicBp = "post_systolic_bp"
        case postDiastolicBp = "post_diastolic_bp"
        case preHeartRate = "pre_heart_rate"
        case postHeartRate = "post_heart_rate"
        case preTemperature = "pre_temperature"
        case postTemperature = "post_temperature"
        case adverseReactions = "adverse_reactions"
        case patientTolerance = "patient_tolerance"
        case patientNotes = "patient_notes"
    }
}

// `IntradialyticReading` already exists in NewFeatureModels.swift with the full
// column set — it is reused here rather than redeclared. The clinician endpoint
// therefore returns every column that model expects; a trimmed payload compiled
// fine and failed to decode only on the device.

/// A clinical note on a therapy session. Named for its domain because
/// `SessionNote` is already taken by the telehealth models, which are a
/// different row entirely (content/diagnosis codes, not note_text).
struct TherapySessionNote: Codable, Hashable, Identifiable {
    let id: Int
    let authorRole: String?
    let noteType: String?
    let noteText: String
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case authorRole = "author_role"
        case noteType = "note_type"
        case noteText = "note_text"
        case createdAt = "created_at"
    }
}

/// Who has attested to this record. Reported even when empty, so the physician
/// can see they are signing on top of an unsigned flowsheet rather than
/// countersigning a signed one.
struct SessionSignoff: Codable, Hashable {
    let flowsheetStatus: String?
    let signedAt: String?
    let signedBy: Int?
    let countersignedAt: String?
    let countersignedBy: Int?
    let reviewedAt: String?
    let reviewedBy: Int?
    let payloadHash: String?

    var isReviewed: Bool { flowsheetStatus == "reviewed" || reviewedAt != nil }

    enum CodingKeys: String, CodingKey {
        case flowsheetStatus = "flowsheet_status"
        case signedAt = "signed_at"
        case signedBy = "signed_by"
        case countersignedAt = "countersigned_at"
        case countersignedBy = "countersigned_by"
        case reviewedAt = "reviewed_at"
        case reviewedBy = "reviewed_by"
        case payloadHash = "payload_hash"
    }
}

struct TherapySessionReport: Codable {
    let patient: BoardPatient
    let session: TherapySessionDetail
    let readings: [IntradialyticReading]
    let notes: [TherapySessionNote]
    let signoff: SessionSignoff
}

struct SessionReviewResponse: Codable {
    let id: Int
    let signoff: SessionSignoff
    let message: String?
}

/// One ledger block behind a session, as the integrity check reports it.
struct IntegrityBlock: Codable, Hashable {
    let blockUid: String
    let index: Int
    let action: String
    let event: String?
    let actorId: Int?
    let recordedAt: String?
    let hash: String?
    let previousHash: String?
    let anchored: Bool
    let txHash: String?
    let blockNumber: Int?

    enum CodingKeys: String, CodingKey {
        case index, action, event, hash, anchored
        case blockUid = "block_uid"
        case actorId = "actor_id"
        case recordedAt = "recorded_at"
        case previousHash = "previous_hash"
        case txHash = "tx_hash"
        case blockNumber = "block_number"
    }
}

/// Recomputed tamper-evidence for one session. `payloadMatches` is nil when the
/// record was never signed — which is a different fact from "does not match".
struct SessionIntegrity: Codable {
    let sessionId: Int
    let payloadHash: String?
    let payloadHashRecomputed: String?
    let payloadMatches: Bool?
    let chainIntact: Bool?
    let anchoredCount: Int
    let trail: [IntegrityBlock]

    enum CodingKeys: String, CodingKey {
        case trail
        case sessionId = "session_id"
        case payloadHash = "payload_hash"
        case payloadHashRecomputed = "payload_hash_recomputed"
        case payloadMatches = "payload_matches"
        case chainIntact = "chain_intact"
        case anchoredCount = "anchored_count"
    }
}


/// Server-computed session tiles — counted in SQL, not averaged over whatever
/// rows the page happened to return. A tile derived from the page is a function
/// of the page size, which is how "200 sessions" was once reported for a patient
/// with 730.
struct TherapySummary: Codable {
    let periodDays: Int
    let totalSessions: Int
    let totalSessionsAllTime: Int
    let avgPreWeightKg: Double?
    let avgPostWeightKg: Double?
    let avgFluidRemovedMl: Double?
    let avgDurationMin: Double?
    let earliestSession: String?
    let latestSession: String?

    enum CodingKeys: String, CodingKey {
        case periodDays = "period_days"
        case totalSessions = "total_sessions"
        case totalSessionsAllTime = "total_sessions_all_time"
        case avgPreWeightKg = "avg_pre_weight_kg"
        case avgPostWeightKg = "avg_post_weight_kg"
        case avgFluidRemovedMl = "avg_fluid_removed_ml"
        case avgDurationMin = "avg_duration_min"
        case earliestSession = "earliest_session"
        case latestSession = "latest_session"
    }
}

// MARK: - New-treatment defaults (/chronic/therapy-sessions/defaults)

/// Settings carried from the last completed treatment. Every value is a
/// *default* the patient can change — nothing here is submitted on their behalf.
struct FlowsheetCarriedForward: Codable {
    let attendingPhysician: String?
    let attendingNurse: String?
    let dialysisAccessType: String?
    let dialysateVolumeLiters: Double?
    let dialysateLactateMeq: Double?
    let dialysatePotassiumMeq: Double?
    let bloodFlowRate: Double?
    let dialysateFlowRate: Double?
    let flowFraction: Double?
    let cartridgeLot: String?
    let sakLot: String?
    let sakNumber: Int?
    let cyclerNumber: String?
    let warmerSerial: String?
    let controlPanelSerial: String?
    /// Last treatment's POST weight — this treatment's PREVIOUS weight, and how
    /// the unit computes today's fluid target. The patient was re-typing a
    /// number the record already held.
    let previousPostWeightKg: Double?

    enum CodingKeys: String, CodingKey {
        case attendingPhysician = "attending_physician"
        case attendingNurse = "attending_nurse"
        case dialysisAccessType = "dialysis_access_type"
        case dialysateVolumeLiters = "dialysate_volume_liters"
        case dialysateLactateMeq = "dialysate_lactate_meq"
        case dialysatePotassiumMeq = "dialysate_potassium_meq"
        case bloodFlowRate = "blood_flow_rate"
        case dialysateFlowRate = "dialysate_flow_rate"
        case flowFraction = "flow_fraction"
        case cartridgeLot = "cartridge_lot"
        case sakLot = "sak_lot"
        case sakNumber = "sak_number"
        case cyclerNumber = "cycler_number"
        case warmerSerial = "warmer_serial"
        case controlPanelSerial = "control_panel_serial"
        case previousPostWeightKg = "previous_post_weight_kg"
    }
}

struct FlowsheetDefaults: Codable {
    /// Mean of recent post-treatment weights; nil until some are on file.
    let targetWeightKg: Double?
    let targetWeightBasis: String?
    let targetWeightSampleSize: Int?

    let accessType: String?
    /// "catheter" | "needled" | "unknown"
    let accessKind: String?
    /// Fields the client should DISABLE (not hide) for this access.
    let disabledFields: [String]?

    let carriedForward: FlowsheetCarriedForward?
    let carriedFromDate: String?
    let notes: [String]?

    enum CodingKeys: String, CodingKey {
        case notes
        case targetWeightKg = "target_weight_kg"
        case targetWeightBasis = "target_weight_basis"
        case targetWeightSampleSize = "target_weight_sample_size"
        case accessType = "access_type"
        case accessKind = "access_kind"
        case disabledFields = "disabled_fields"
        case carriedForward = "carried_forward"
        case carriedFromDate = "carried_from_date"
    }
}
