// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import Foundation

// Hospital stays and surgical procedures.
//
// `APIClient`'s decoder is a plain `JSONDecoder()` with NO
// `.convertFromSnakeCase` strategy, so every snake_case field needs an explicit
// `CodingKeys` entry. Omitting one does not fail loudly — it decodes to nil and
// the screen renders a blank, which is how a tool once returned four empty
// objects and the model reported "no medications taken" on a patient with four
// dose-logged drugs (§3am).
//
// Nullability matches the SCHEMA, not the rows that happened to be on hand
// (§3aj): a procedure imported from FHIR carries no outcome, one entered by
// hand carries no code, and anything historical carries no admission.

/// One procedure, as the canonical reader returns it.
struct ProcedureView: Codable, Identifiable {
    let name: String
    let performed: String?
    let code: String?
    let codeSystem: String?
    let bodySite: String?
    let outcome: String?
    /// What this operation STILL does to the patient. Present only when the
    /// record states it — never derived from the procedure's name.
    let ongoingEffects: String?
    let facility: String?
    let surgeon: String?
    /// The stay this belonged to, or nil. Nil is an ordinary answer: day-case
    /// surgery and anything recorded years later has no admission.
    let admission: String?
    let source: String?

    /// Composite, because the API returns a read VIEW with no row id. Two
    /// identical operations on the same date would collide; that is accepted
    /// here rather than inventing an id the server never sent.
    var id: String { "\(name)|\(performed ?? "")|\(code ?? "")|\(admission ?? "")" }

    enum CodingKeys: String, CodingKey {
        case name, performed, code, outcome, facility, surgeon, admission, source
        case codeSystem = "code_system"
        case bodySite = "body_site"
        case ongoingEffects = "ongoing_effects"
    }
}

/// One hospital stay, with the procedures performed during it.
struct HospitalizationView: Codable, Identifiable {
    let admitted: String
    let discharged: String?
    let facility: String?
    let reason: String?
    let diagnosis: String?
    let admissionType: String?
    let status: String?
    /// Absent while the patient is still an inpatient — never a length
    /// measured against today.
    let nights: Int?
    let procedures: [ProcedureView]
    let source: String?

    var id: String { "\(admitted)|\(facility ?? "")" }

    enum CodingKeys: String, CodingKey {
        case admitted, discharged, facility, reason, diagnosis, status, nights
        case procedures, source
        case admissionType = "admission_type"
    }
}

/// `GET /hospital/history`.
///
/// `procedures` is the COMPLETE list and is deliberately not derivable from
/// `stays`: walking stays and their nested procedures loses every operation
/// with no admission attached, which is the case this feature exists for.
struct HospitalHistoryResponse: Codable {
    let stays: [HospitalizationView]
    let procedures: [ProcedureView]
    let lastingEffects: [String]

    enum CodingKeys: String, CodingKey {
        case stays, procedures
        case lastingEffects = "lasting_effects"
    }
}

/// A raw stay row from `GET /hospital/stays` — carries the id, so it is what
/// an edit or delete works from.
struct HospitalizationRow: Codable, Identifiable {
    let id: Int
    let admittedAt: String
    let dischargedAt: String?
    let facilityName: String?
    let reason: String?
    let status: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case id, reason, status, source
        case admittedAt = "admitted_at"
        case dischargedAt = "discharged_at"
        case facilityName = "facility_name"
    }
}

struct SurgicalProcedureRow: Codable, Identifiable {
    let id: Int
    let name: String
    let performedAt: String?
    let ongoingEffects: String?
    let hospitalizationId: Int?

    enum CodingKeys: String, CodingKey {
        case id, name
        case performedAt = "performed_at"
        case ongoingEffects = "ongoing_effects"
        case hospitalizationId = "hospitalization_id"
    }
}

// MARK: - Writes

/// A procedure to create. `hospitalizationId` is optional on purpose.
struct SurgicalProcedureCreate: Encodable {
    var name: String
    var performedAt: String?
    var code: String?
    var codeSystem: String?
    var bodySite: String?
    var outcome: String?
    var ongoingEffects: String?
    var surgeon: String?
    var hospitalizationId: Int?

    enum CodingKeys: String, CodingKey {
        case name, code, outcome, surgeon
        case performedAt = "performed_at"
        case codeSystem = "code_system"
        case bodySite = "body_site"
        case ongoingEffects = "ongoing_effects"
        case hospitalizationId = "hospitalization_id"
    }
}

/// A stay to create, optionally carrying the procedures performed during it —
/// one request, because that is how a discharge summary arrives.
struct HospitalizationCreate: Encodable {
    var admittedAt: String
    var dischargedAt: String?
    var facilityName: String?
    var admissionType: String?
    var status: String?
    var reason: String?
    var primaryDiagnosis: String?
    var attendingPhysician: String?
    var procedures: [SurgicalProcedureCreate] = []

    enum CodingKeys: String, CodingKey {
        case status, reason, procedures
        case admittedAt = "admitted_at"
        case dischargedAt = "discharged_at"
        case facilityName = "facility_name"
        case admissionType = "admission_type"
        case primaryDiagnosis = "primary_diagnosis"
        case attendingPhysician = "attending_physician"
    }
}

// MARK: - Vocabulary
//
// Values, not display text. These are the enum VALUES the API accepts; the
// labels shown to a patient are localized separately, so a translated label
// can never be sent as a value (§3aw: a field a guard reads stays English).

enum HospitalVocabulary {
    static let admissionTypes = ["emergency", "elective", "urgent", "observation",
                                 "day_case", "maternity", "rehabilitation", "other"]
    static let statuses = ["planned", "in_progress", "discharged", "transferred", "cancelled"]
    static let outcomes = ["successful", "partially_successful", "unsuccessful",
                           "complicated", "abandoned", "unknown"]
}
