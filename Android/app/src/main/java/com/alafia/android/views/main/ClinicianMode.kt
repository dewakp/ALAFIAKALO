package com.alafia.android.views.main

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * Roles that can practise in clinician mode.
 *
 * This list lives here rather than inside a screen because three places need
 * it — the tab shell, the More grid and the Role screen — and a copy in each is
 * how they drift apart.
 */
val CLINICIAN_ROLES = setOf(
    "physician", "surgeon", "nurse_practitioner",
    "physician_assistant", "resident", "fellow", "attending_physician",
    "cardiologist", "dermatologist", "endocrinologist", "gastroenterologist",
    "neurologist", "oncologist", "pediatrician", "radiologist",
    "general_surgeon", "orthopedic_surgeon", "neurosurgeon",
    "cardiothoracic_surgeon", "plastic_surgeon", "vascular_surgeon",
    "oral_surgeon", "clinical_nurse_specialist", "nurse_anesthetist",
    "nurse_midwife", "charge_nurse", "nurse_administrator",
    "medical_director", "chief_medical_officer",
)

/**
 * Which persona the app is presenting: the user's own record, or their clinical
 * practice. Switching swaps the whole tab bar rather than adding a screen, so a
 * physician reviewing patients is not navigating past their own meal diary.
 *
 * Process-scoped rather than persisted: the mode lasts for the session and
 * resets on a cold start, which also means a signed-out clinician cannot leave
 * the next account in a mode its roles do not allow.
 */
object ClinicianModeState {
    var isActive by mutableStateOf(false)
        private set

    /** Enter clinician mode. Refuses for a user without a clinical role. */
    fun enter(roles: List<String>) {
        if (roles.any { it in CLINICIAN_ROLES }) isActive = true
    }

    fun exit() {
        isActive = false
    }

    /** Drop out when the signed-in user can no longer hold the mode. */
    fun reconcile(roles: List<String>) {
        if (isActive && roles.none { it in CLINICIAN_ROLES }) isActive = false
    }
}

/**
 * Sentinel route for the More grid's "Clinician View" tile. It switches persona
 * instead of navigating, so it is intercepted rather than handed to the
 * NavController — the clinician shell is a different tab bar, not a destination
 * inside the patient one.
 */
const val CLINICIAN_MODE_ROUTE = "__clinician_mode__"
