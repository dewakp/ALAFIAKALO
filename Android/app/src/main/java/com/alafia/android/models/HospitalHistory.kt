// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android.models

import com.google.gson.annotations.SerializedName

// Hospital stays and surgical procedures.
//
// Nullability matches the SCHEMA, not the rows that happened to be on hand.
// §3aj: Android's `Medication` model declared `dosage`, `frequency`, `reason`
// and `start_date` non-null while the API allows null for every one — and Gson
// writes null into a Kotlin non-null field regardless, so the declaration
// bought nothing and hid the risk until a row created by `promote-logged`
// arrived carrying only a name.
//
// Every field here that the API may omit is nullable with a default, so a row
// from a FHIR import (no outcome, no surgeon) and one typed by hand (no code)
// both decode without surprising a composable.

/** One procedure, as the canonical reader returns it. */
data class ProcedureView(
    val name: String,
    val performed: String? = null,
    val code: String? = null,
    // The code is unusable without the vocabulary that issued it: ICD-10-PCS,
    // CPT, SNOMED and ICHI are different systems and are never converted
    // between (§3ad).
    @SerializedName("code_system") val codeSystem: String? = null,
    @SerializedName("body_site") val bodySite: String? = null,
    val outcome: String? = null,
    /**
     * What this operation STILL does to the patient. Present only when the
     * record states it — never derived from the procedure's name.
     */
    @SerializedName("ongoing_effects") val ongoingEffects: String? = null,
    val facility: String? = null,
    val surgeon: String? = null,
    /**
     * The stay this belonged to, or null. Null is an ordinary answer: day-case
     * surgery and anything recorded years later has no admission.
     */
    val admission: String? = null,
    val source: String? = null
)

/** One hospital stay, with the procedures performed during it. */
data class HospitalizationView(
    val admitted: String,
    val discharged: String? = null,
    val facility: String? = null,
    val reason: String? = null,
    val diagnosis: String? = null,
    @SerializedName("admission_type") val admissionType: String? = null,
    val status: String? = null,
    /**
     * Null while the patient is still an inpatient — never a length measured
     * against today.
     */
    val nights: Int? = null,
    val procedures: List<ProcedureView> = emptyList(),
    val source: String? = null
)

/**
 * `GET /hospital/history`.
 *
 * `procedures` is the COMPLETE list and is deliberately not derivable from
 * `stays`: walking stays and their nested procedures loses every operation
 * with no admission attached, which is the case this feature exists for.
 */
data class HospitalHistoryResponse(
    val stays: List<HospitalizationView> = emptyList(),
    val procedures: List<ProcedureView> = emptyList(),
    @SerializedName("lasting_effects") val lastingEffects: List<String> = emptyList()
)

/**
 * A raw stay row. Carries the id, so it is what an edit or a delete works
 * from. `procedures` is populated by the create response
 * (`HospitalizationDetail`) and absent from the list endpoint, hence nullable.
 */
data class HospitalizationRow(
    val id: Int,
    @SerializedName("admitted_at") val admittedAt: String,
    @SerializedName("discharged_at") val dischargedAt: String? = null,
    @SerializedName("facility_name") val facilityName: String? = null,
    val reason: String? = null,
    @SerializedName("primary_diagnosis") val primaryDiagnosis: String? = null,
    @SerializedName("admission_type") val admissionType: String? = null,
    val status: String? = null,
    val source: String? = null,
    val procedures: List<SurgicalProcedureRow>? = null
)

data class SurgicalProcedureRow(
    val id: Int,
    val name: String,
    @SerializedName("performed_at") val performedAt: String? = null,
    val code: String? = null,
    @SerializedName("code_system") val codeSystem: String? = null,
    @SerializedName("body_site") val bodySite: String? = null,
    val outcome: String? = null,
    @SerializedName("ongoing_effects") val ongoingEffects: String? = null,
    val surgeon: String? = null,
    @SerializedName("hospitalization_id") val hospitalizationId: Int? = null,
    val source: String? = null
)

/**
 * The enum VALUES the API accepts — not display text.
 *
 * Labels shown to a patient are resolved from `strings.xml` separately, so a
 * translated label can never be sent as a value. §3aw: display text follows
 * the patient's language, but a field a guard or a lookup reads stays English.
 */
object HospitalVocabulary {
    val admissionTypes = listOf(
        "emergency", "elective", "urgent", "observation",
        "day_case", "maternity", "rehabilitation", "other"
    )
    val statuses = listOf("planned", "in_progress", "discharged", "transferred", "cancelled")
    val outcomes = listOf(
        "successful", "partially_successful", "unsuccessful",
        "complicated", "abandoned", "unknown"
    )
}
