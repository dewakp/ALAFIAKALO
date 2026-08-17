package com.alafia.android.models

import com.google.gson.annotations.SerializedName
import java.time.LocalDateTime

// User Model
data class User(
    val id: Int,
    val email: String,
    val full_name: String,
    val date_of_birth: String?,
    val gender: String?,
    val profile_picture_url: String?,
    val is_active: Boolean,
    val is_superuser: Boolean,
    val created_at: String,
    val updated_at: String,
    val primary_role: String? = null,
    val active_roles: List<String>? = null,
    val is_healthcare_professional: Boolean? = null,
    val system_id: String? = null
)

// Fitness Log
data class FitnessLog(
    val id: Int,
    val user_id: Int,
    val log_date: String,
    val activity_type: String,
    val duration_minutes: Int?,
    val distance_km: Float?,
    val calories_burned: Float?,
    val heart_rate_avg: Int?,
    val heart_rate_max: Int?,
    val steps: Int?,
    val sets: Int?,
    val reps: Int?,
    val weight_kg: Float?,
    val intensity: String?,
    val notes: String?,
    val created_at: String
)

// Mood Entry
data class MoodEntry(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("entry_date") val entryDate: String,
    @SerializedName("mood_score") val moodScore: Int,
    @SerializedName("energy_level") val energyLevel: Int?,
    @SerializedName("stress_level") val stressLevel: Int?,
    @SerializedName("anxiety_level") val anxietyLevel: Int?,
    @SerializedName("sleep_quality") val sleepQuality: Int?,
    @SerializedName("sleep_hours") val sleepHours: Double?,
    val emotions: String?,
    val triggers: String?,
    @SerializedName("coping_strategies") val copingStrategies: String?,
    val gratitude: String?,
    @SerializedName("journal_entry") val journalEntry: String?,
    val notes: String?,
    @SerializedName("created_at") val createdAt: String
)

// Nutrition Log
data class NutritionLog(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("log_date") val logDate: String,
    @SerializedName("meal_type") val mealType: String,
    @SerializedName("food_name") val foodName: String,
    @SerializedName("serving_size") val servingSize: String?,
    @SerializedName("fdc_id") val fdcId: Int?,
    // pending | done | failed | skipped. Nutrients are filled in AFTER the meal
    // is saved, so a fresh entry arrives with no values and status "pending" —
    // show that rather than a blank, which reads as "zero calories".
    @SerializedName("nutrient_status") val nutrientStatus: String? = null,
    val calories: Float?,
    @SerializedName("protein_g") val proteinG: Float?,
    @SerializedName("carbs_g") val carbsG: Float?,
    @SerializedName("fat_g") val fatG: Float?,
    @SerializedName("fiber_g") val fiberG: Float?,
    @SerializedName("sugar_g") val sugarG: Float?,
    @SerializedName("saturated_fat_g") val saturatedFatG: Float?,
    @SerializedName("cholesterol_mg") val cholesterolMg: Float?,
    @SerializedName("sodium_mg") val sodiumMg: Float?,
    @SerializedName("potassium_mg") val potassiumMg: Float?,
    @SerializedName("calcium_mg") val calciumMg: Float?,
    @SerializedName("iron_mg") val ironMg: Float?,
    @SerializedName("vitamin_a_iu") val vitaminAIu: Float?,
    @SerializedName("vitamin_c_mg") val vitaminCMg: Float?,
    @SerializedName("vitamin_d_iu") val vitaminDIu: Float?,
    @SerializedName("vitamin_b6_mg") val vitaminB6Mg: Float?,
    @SerializedName("vitamin_b12_mcg") val vitaminB12Mcg: Float?,
    @SerializedName("extended_nutrients") val extendedNutrients: Map<String, Float>?,
    val notes: String?,
    @SerializedName("start_time") val startTime: String?,
    @SerializedName("end_time") val endTime: String?,
    @SerializedName("pre_meal_weight_kg") val preMealWeightKg: Float?,
    @SerializedName("post_meal_weight_kg") val postMealWeightKg: Float?,
    @SerializedName("food_image_uris") val foodImageUris: String?,
    @SerializedName("recipe_url") val recipeUrl: String?,
    @SerializedName("created_at") val createdAt: String
)

// USDA Food Search Result
data class USDAFoodResult(
    @SerializedName("fdc_id") val fdcId: Int,
    val description: String,
    @SerializedName("brand_owner") val brandOwner: String?,
    @SerializedName("data_type") val dataType: String?,
    @SerializedName("serving_size") val servingSize: Float?,
    @SerializedName("serving_size_unit") val servingSizeUnit: String?,
    val nutrients: Map<String, Float>
)

// USDA Food Nutrient (for breakdown)
data class USDAFoodNutrient(
    val key: String,
    val name: String,
    val unit: String,
    val value: Float,
    val rda: Float?,
    @SerializedName("percent_dv") val percentDv: Float?,
    val category: String
)

// USDA Food Detail
data class USDAFoodDetail(
    @SerializedName("fdc_id") val fdcId: Int,
    val description: String,
    @SerializedName("brand_owner") val brandOwner: String?,
    @SerializedName("data_type") val dataType: String?,
    @SerializedName("food_category") val foodCategory: String?,
    val nutrients: Map<String, Float>,
    val portions: List<Map<String, Any>>?,
    @SerializedName("nutrient_breakdown") val nutrientBreakdown: List<USDAFoodNutrient>
)

// Daily Summary
data class DailySummary(
    val date: String,
    @SerializedName("total_calories") val totalCalories: Float,
    @SerializedName("total_protein_g") val totalProteinG: Float,
    @SerializedName("total_carbs_g") val totalCarbsG: Float,
    @SerializedName("total_fat_g") val totalFatG: Float,
    @SerializedName("meal_count") val mealCount: Int,
    val nutrients: List<USDAFoodNutrient>
)

// Personalized daily nutrient goals (/nutrition/goal-progress)
data class NutrientGoalProgress(
    val key: String,
    val name: String,
    val unit: String,
    val current: Float,
    val goal: Float,
    val kind: String,      // "target" (reach) | "limit" (stay under)
    val pct: Float,
    val status: String,    // low | ok | warning | over
    val priority: Int,
    val rationale: String
)

data class GoalProgressResponse(
    val date: String,
    @SerializedName("profile_complete") val profileComplete: Boolean,
    @SerializedName("energy_kcal") val energyKcal: Float,
    val conditions: List<String>,
    val goals: List<NutrientGoalProgress>
)

// Lab Result
data class LabResult(
    val id: Int,
    val user_id: Int,
    val test_date: String = "",
    val test_name: String = "",
    val loinc_code: String? = null,
    val category: String? = null,
    val value: Float? = null,
    val value_string: String? = null,
    val unit: String? = null,
    val reference_range_low: Float? = null,
    val reference_range_high: Float? = null,
    val is_abnormal: Boolean? = null,
    val status: String = "final",
    val ordering_provider: String? = null,
    val performing_lab: String? = null,
    val notes: String? = null,
    val created_at: String = ""
)

// Medication
data class Medication(
    val id: Int,
    val user_id: Int,
    val name: String,
    val dosage: String,
    val frequency: String,
    val reason: String,
    val start_date: String,
    val end_date: String?,
    val notes: String?,
    val source: String? = null,   // null = entered manually; else importing portal/org
    val created_at: String
)

// Medication dose log — a recorded "taken" event (GET/POST /medications/dose-logs)
data class MedicationDoseLog(
    val id: Int,
    val user_id: Int,
    val medication_id: Int?,
    val med_profile_id: Int?,
    val medication_name: String,
    val log_date: String,
    val log_time: String? = null,
    val dose_amount: Double,
    val dose_unit: String,
    val pre_systolic_bp: Int? = null,
    val pre_diastolic_bp: Int? = null,
    val pre_heart_rate: Int? = null,
    val pre_temperature_c: Double? = null,
    val post_systolic_bp: Int? = null,
    val post_diastolic_bp: Int? = null,
    val post_heart_rate: Int? = null,
    val post_temperature_c: Double? = null,
    val nutrients_contributed: Map<String, Double>?,
    val nutrients_resolved: Boolean,
    val notes: String?,
    val created_at: String
)

// Lifestyle Entry
data class LifestyleEntry(
    val id: Int,
    val user_id: Int,
    val log_date: String,
    val category: String,
    val value: String,
    val notes: String?,
    val created_at: String
)

// Privacy Settings
data class PrivacySettings(
    @SerializedName("user_id") val userId: Int,
    @SerializedName("allow_anonymized_analytics") val allowAnonymizedAnalytics: Boolean,
    @SerializedName("allow_collective_insights") val allowCollectiveInsights: Boolean,
    @SerializedName("allow_research_participation") val allowResearchParticipation: Boolean,
    @SerializedName("allow_marketing_emails") val allowMarketingEmails: Boolean,
    @SerializedName("allow_product_updates") val allowProductUpdates: Boolean,
    @SerializedName("allow_health_reminders") val allowHealthReminders: Boolean,
    @SerializedName("ai_coaching_enabled") val aiCoachingEnabled: Boolean,
    @SerializedName("ai_memory_enabled") val aiMemoryEnabled: Boolean,
    @SerializedName("ai_explainability_level") val aiExplainabilityLevel: String,
    @SerializedName("require_biometric_auth") val requireBiometricAuth: Boolean,
    @SerializedName("session_timeout_minutes") val sessionTimeoutMinutes: Int,
    @SerializedName("gdpr_applies") val gdprApplies: Boolean,
    @SerializedName("hipaa_applies") val hipaaApplies: Boolean
)

// Chronic Condition
data class ChronicCondition(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("condition_name") val conditionName: String,
    val category: String,
    @SerializedName("icd10_code") val icd10Code: String?,
    val severity: String,
    @SerializedName("diagnosis_date") val diagnosisDate: String?,
    @SerializedName("diagnosed_by") val diagnosedBy: String?,
    @SerializedName("diagnosing_facility") val diagnosingFacility: String?,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("remission_date") val remissionDate: String?,
    val stage: String?,
    val grade: String?,
    @SerializedName("current_treatment_plan") val currentTreatmentPlan: String?,
    @SerializedName("primary_physician") val primaryPhysician: String?,
    @SerializedName("specialist_physician") val specialistPhysician: String?,
    @SerializedName("monitoring_frequency") val monitoringFrequency: String?,
    @SerializedName("next_appointment") val nextAppointment: String?,
    val notes: String?,
    val symptoms: String?,
    val complications: String?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
)

// Intradialytic Reading
data class IntradialyticReading(
    val id: Int,
    @SerializedName("session_id") val sessionId: Int,
    // Nullable: a source flowsheet often leaves the time blank. A non-null type
    // here is the same instinct that made the importer write 00:00:00 — pick a
    // value so the type is satisfied, and lose the fact that nothing was recorded.
    @SerializedName("reading_time") val readingTime: String?,
    @SerializedName("reading_number") val readingNumber: Int?,
    @SerializedName("systolic_bp") val systolicBp: Int?,
    @SerializedName("diastolic_bp") val diastolicBp: Int?,
    val pulse: Int?,
    @SerializedName("mean_arterial_pressure") val meanArterialPressure: Float?,
    @SerializedName("dialysate_rate") val dialysateRate: Float?,
    @SerializedName("dialysate_volume_remaining") val dialysateVolumeRemaining: Float?,
    @SerializedName("uf_rate") val ufRate: Float?,
    @SerializedName("uf_volume_removed") val ufVolumeRemoved: Float?,
    @SerializedName("blood_flow_rate") val bloodFlowRate: Float?,
    @SerializedName("arterial_pressure") val arterialPressure: Float?,
    @SerializedName("venous_pressure") val venousPressure: Float?,
    @SerializedName("effluent_pressure") val effluentPressure: Float?,
    @SerializedName("access_state") val accessState: String?,
    @SerializedName("saline_amount") val salineAmount: String?,
    val remarks: String?,
    @SerializedName("created_at") val createdAt: String?
)

// HD Summary Stats
data class HDSummary(
    @SerializedName("total_sessions") val totalSessions: Int,
    @SerializedName("avg_pre_weight_kg") val avgPreWeightKg: Float?,
    @SerializedName("avg_post_weight_kg") val avgPostWeightKg: Float?,
    @SerializedName("avg_fluid_removed_ml") val avgFluidRemovedMl: Float?,
    @SerializedName("avg_duration_min") val avgDurationMin: Float?,
    @SerializedName("sessions_with_readings") val sessionsWithReadings: Int?,
    @SerializedName("date_range") val dateRange: String?
)

// Therapy Session
data class TherapySession(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("condition_id") val conditionId: Int?,
    @SerializedName("therapy_type") val therapyType: String,
    @SerializedName("therapy_name") val therapyName: String?,
    @SerializedName("session_number") val sessionNumber: Int?,
    @SerializedName("total_sessions_planned") val totalSessionsPlanned: Int?,
    @SerializedName("scheduled_date") val scheduledDate: String,
    @SerializedName("actual_start_time") val actualStartTime: String?,
    @SerializedName("actual_end_time") val actualEndTime: String?,
    @SerializedName("duration_minutes") val durationMinutes: Int?,
    val status: String,
    @SerializedName("facility_name") val facilityName: String?,
    @SerializedName("facility_address") val facilityAddress: String?,
    @SerializedName("attending_physician") val attendingPhysician: String?,
    @SerializedName("attending_nurse") val attendingNurse: String?,
    @SerializedName("dialysis_access_type") val dialysisAccessType: String?,
    @SerializedName("pre_dialysis_weight_kg") val preDialysisWeightKg: Float?,
    @SerializedName("post_dialysis_weight_kg") val postDialysisWeightKg: Float?,
    @SerializedName("fluid_removed_ml") val fluidRemovedMl: Float?,
    @SerializedName("blood_flow_rate") val bloodFlowRate: Float?,
    @SerializedName("dialysate_flow_rate") val dialysateFlowRate: Float?,
    @SerializedName("drugs_administered") val drugsAdministered: String?,
    val dosage: String?,
    @SerializedName("route_of_administration") val routeOfAdministration: String?,
    @SerializedName("radiation_dose_gy") val radiationDoseGy: Float?,
    @SerializedName("treatment_area") val treatmentArea: String?,
    @SerializedName("pre_systolic_bp") val preSystolicBp: Int?,
    @SerializedName("pre_diastolic_bp") val preDiastolicBp: Int?,
    @SerializedName("post_systolic_bp") val postSystolicBp: Int?,
    @SerializedName("post_diastolic_bp") val postDiastolicBp: Int?,
    @SerializedName("pre_heart_rate") val preHeartRate: Int?,
    @SerializedName("post_heart_rate") val postHeartRate: Int?,
    @SerializedName("pre_temperature") val preTemperature: Float?,
    @SerializedName("post_temperature") val postTemperature: Float?,
    @SerializedName("oxygen_saturation") val oxygenSaturation: Int?,
    @SerializedName("side_effects") val sideEffects: String?,
    @SerializedName("adverse_reactions") val adverseReactions: String?,
    val complications: String?,
    @SerializedName("patient_tolerance") val patientTolerance: String?,
    @SerializedName("clinical_notes") val clinicalNotes: String?,
    @SerializedName("patient_notes") val patientNotes: String?,
    @SerializedName("next_session_scheduled") val nextSessionScheduled: String?,
    // HD-specific fields
    @SerializedName("dry_weight_kg") val dryWeightKg: Float? = null,
    @SerializedName("previous_post_weight_kg") val previousPostWeightKg: Float? = null,
    @SerializedName("fluid_to_remove_kg") val fluidToRemoveKg: Float? = null,
    @SerializedName("day_of_week") val dayOfWeek: String? = null,
    @SerializedName("rn_reviewer") val rnReviewer: String? = null,
    @SerializedName("dialysate_volume_liters") val dialysateVolumeLiters: Float? = null,
    @SerializedName("dialysate_lactate_meq") val dialysateLactateMeq: Float? = null,
    @SerializedName("dialysate_potassium_meq") val dialysatePotassiumMeq: Float? = null,
    @SerializedName("sak_number") val sakNumber: Int? = null,
    @SerializedName("needle_gauge") val needleGauge: String? = null,
    @SerializedName("needle_length") val needleLength: Float? = null,
    @SerializedName("buttonhole_technique") val buttonholeTechnique: Boolean? = null,
    // Standing vitals
    @SerializedName("pre_standing_systolic_bp") val preStandingSystolicBp: Int? = null,
    @SerializedName("pre_standing_diastolic_bp") val preStandingDiastolicBp: Int? = null,
    @SerializedName("pre_standing_heart_rate") val preStandingHeartRate: Int? = null,
    @SerializedName("post_standing_systolic_bp") val postStandingSystolicBp: Int? = null,
    @SerializedName("post_standing_diastolic_bp") val postStandingDiastolicBp: Int? = null,
    @SerializedName("post_standing_heart_rate") val postStandingHeartRate: Int? = null,
    // Pre-treatment assessment
    @SerializedName("pre_shortness_of_breath") val preShortnessOfBreath: Boolean? = null,
    @SerializedName("pre_swelling") val preSwelling: Boolean? = null,
    @SerializedName("pre_change_in_mobility") val preChangeInMobility: Boolean? = null,
    @SerializedName("pre_digestion_problems") val preDigestionProblems: Boolean? = null,
    @SerializedName("pre_hosp_er_since_last") val preHospErSinceLast: Boolean? = null,
    @SerializedName("access_thrill_bruit") val accessThrillBruit: Boolean? = null,
    @SerializedName("access_redness_drainage") val accessRednessDrainage: Boolean? = null,
    // Equipment
    @SerializedName("cartridge_lot") val cartridgeLot: String? = null,
    @SerializedName("sak_lot") val sakLot: String? = null,
    @SerializedName("cycler_number") val cyclerNumber: String? = null,
    @SerializedName("warmer_serial") val warmerSerial: String? = null,
    // Post-treatment totals
    @SerializedName("total_dialysate_liters") val totalDialysateLiters: Float? = null,
    @SerializedName("total_uf_liters") val totalUfLiters: Float? = null,
    @SerializedName("total_blood_volume_processed") val totalBloodVolumeProcessed: Float? = null,
    @SerializedName("dialyzer_appearance") val dialyzerAppearance: String? = null,
    @SerializedName("post_bleeding_stop_time") val postBleedingStopTime: String? = null,
    @SerializedName("post_bruising") val postBruising: Boolean? = null,
    @SerializedName("post_infiltration") val postInfiltration: Boolean? = null,
    @SerializedName("post_shortness_of_breath") val postShortnessOfBreath: Boolean? = null,
    @SerializedName("post_swelling") val postSwelling: Boolean? = null,
    @SerializedName("post_digestion_problems") val postDigestionProblems: Boolean? = null,
    @SerializedName("post_access_thrill_bruit") val postAccessThrillBruit: Boolean? = null,
    // Machine maintenance
    @SerializedName("purification_pak_change") val purificationPakChange: Boolean? = null,
    @SerializedName("air_filter_cleaned") val airFilterCleaned: Boolean? = null,
    @SerializedName("waste_line_bleach_disinfection") val wasteLineBleachDisinfection: Boolean? = null,
    @SerializedName("alarm_test_completed") val alarmTestCompleted: Boolean? = null,
    @SerializedName("sak_use_number") val sakUseNumber: Int? = null,
    @SerializedName("total_chloramine_level") val totalChloramineLevel: Float? = null,
    @SerializedName("lab_tubes_drawn") val labTubesDrawn: String? = null,
    // Intradialytic readings
    @SerializedName("intradialytic_readings") val intradialyticReadings: List<IntradialyticReading>? = null,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
    // Flowsheet lifecycle fields
    @SerializedName("flowsheet_status") val flowsheetStatus: String? = null,
    @SerializedName("signature_image") val signatureImage: String? = null,
    @SerializedName("signed_at") val signedAt: String? = null,
    @SerializedName("signed_by") val signedBy: Int? = null,
    @SerializedName("countersigned_at") val countersignedAt: String? = null,
    @SerializedName("countersigned_by") val countersignedBy: Int? = null,
    @SerializedName("reviewed_at") val reviewedAt: String? = null,
    @SerializedName("reviewed_by") val reviewedBy: Int? = null,
    @SerializedName("payload_hash") val payloadHash: String? = null,
    @SerializedName("clinical_notes_list") val clinicalNotesList: List<ClinicalNote>? = null
)

// Mental Health Assessment
data class MentalHealthAssessment(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("assessment_date") val assessmentDate: String,
    @SerializedName("assessment_type") val assessmentType: String,
    @SerializedName("total_score") val totalScore: Int?,
    val severity: String?,
    @SerializedName("phq_interest") val phqInterest: Int?,
    @SerializedName("phq_feeling_down") val phqFeelingDown: Int?,
    @SerializedName("phq_sleep") val phqSleep: Int?,
    @SerializedName("phq_energy") val phqEnergy: Int?,
    @SerializedName("phq_appetite") val phqAppetite: Int?,
    @SerializedName("phq_self_esteem") val phqSelfEsteem: Int?,
    @SerializedName("phq_concentration") val phqConcentration: Int?,
    @SerializedName("phq_psychomotor") val phqPsychomotor: Int?,
    @SerializedName("phq_suicidal_ideation") val phqSuicidalIdeation: Int?,
    @SerializedName("gad_nervous") val gadNervous: Int?,
    @SerializedName("gad_uncontrollable_worry") val gadUncontrollableWorry: Int?,
    @SerializedName("gad_excessive_worry") val gadExcessiveWorry: Int?,
    @SerializedName("gad_trouble_relaxing") val gadTroubleRelaxing: Int?,
    @SerializedName("gad_restless") val gadRestless: Int?,
    @SerializedName("gad_irritable") val gadIrritable: Int?,
    @SerializedName("gad_afraid") val gadAfraid: Int?,
    @SerializedName("who5_cheerful") val who5Cheerful: Int?,
    @SerializedName("who5_calm") val who5Calm: Int?,
    @SerializedName("who5_active") val who5Active: Int?,
    @SerializedName("who5_rested") val who5Rested: Int?,
    @SerializedName("who5_interesting") val who5Interesting: Int?,
    @SerializedName("created_at") val createdAt: String?
)

// Breathing Exercise Info (from API library)
data class BreathingExerciseInfo(
    val id: String,
    val name: String,
    val description: String,
    @SerializedName("inhale_seconds") val inhaleSeconds: Int,
    @SerializedName("hold_seconds") val holdSeconds: Int,
    @SerializedName("exhale_seconds") val exhaleSeconds: Int,
    @SerializedName("hold_after_exhale_seconds") val holdAfterExhaleSeconds: Int,
    @SerializedName("recommended_cycles") val recommendedCycles: Int,
    val benefits: List<String>
)

// Breathing Session
data class BreathingSessionResponse(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("session_date") val sessionDate: String,
    @SerializedName("exercise_type") val exerciseType: String,
    @SerializedName("duration_seconds") val durationSeconds: Int,
    @SerializedName("mood_before") val moodBefore: Int?,
    @SerializedName("mood_after") val moodAfter: Int?,
    @SerializedName("created_at") val createdAt: String?
)

// Gratitude Entry
data class GratitudeEntryResponse(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("entry_date") val entryDate: String,
    @SerializedName("item_1") val item1: String,
    @SerializedName("item_2") val item2: String?,
    @SerializedName("item_3") val item3: String?,
    val reflection: String?,
    @SerializedName("created_at") val createdAt: String?
)

// Mental Health Stats (dashboard)
data class MentalHealthStats(
    @SerializedName("avg_mood_7d") val avgMood7d: Float?,
    @SerializedName("avg_mood_30d") val avgMood30d: Float?,
    @SerializedName("avg_stress_7d") val avgStress7d: Float?,
    @SerializedName("avg_anxiety_7d") val avgAnxiety7d: Float?,
    @SerializedName("avg_sleep_quality_7d") val avgSleepQuality7d: Float?,
    @SerializedName("avg_sleep_hours_7d") val avgSleepHours7d: Float?,
    @SerializedName("mood_trend") val moodTrend: String?,
    @SerializedName("total_entries_30d") val totalEntries30d: Int,
    @SerializedName("streak_days") val streakDays: Int,
    @SerializedName("total_breathing_minutes_30d") val totalBreathingMinutes30d: Int,
    @SerializedName("latest_phq9_score") val latestPhq9Score: Int?,
    @SerializedName("latest_phq9_severity") val latestPhq9Severity: String?,
    @SerializedName("latest_gad7_score") val latestGad7Score: Int?,
    @SerializedName("latest_gad7_severity") val latestGad7Severity: String?,
    @SerializedName("latest_who5_score") val latestWho5Score: Int?,
    @SerializedName("wellness_score") val wellnessScore: Int?
)

// ─── Community Health Models ─────────────────────────────────────────

data class CommunityHealthAlert(
    val id: Int,
    val title: String,
    val summary: String,
    val description: String?,
    val category: String,
    val severity: String,
    val source: String,
    @SerializedName("source_url") val sourceUrl: String?,
    @SerializedName("source_reference_id") val sourceReferenceId: String?,
    @SerializedName("affected_countries") val affectedCountries: List<String>?,
    @SerializedName("affected_regions") val affectedRegions: List<String>?,
    @SerializedName("is_global") val isGlobal: Boolean,
    @SerializedName("issued_date") val issuedDate: String,
    @SerializedName("effective_date") val effectiveDate: String?,
    @SerializedName("expiry_date") val expiryDate: String?,
    @SerializedName("product_name") val productName: String?,
    @SerializedName("product_type") val productType: String?,
    val manufacturer: String?,
    @SerializedName("lot_numbers") val lotNumbers: List<String>?,
    @SerializedName("reason_for_recall") val reasonForRecall: String?,
    @SerializedName("recall_class") val recallClass: String?,
    @SerializedName("disease_name") val diseaseName: String?,
    val pathogen: String?,
    @SerializedName("confirmed_cases") val confirmedCases: Int?,
    val deaths: Int?,
    @SerializedName("recommended_actions") val recommendedActions: List<String>?,
    @SerializedName("target_population") val targetPopulation: List<String>?,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("is_resolved") val isResolved: Boolean,
    @SerializedName("resolution_date") val resolutionDate: String?,
    @SerializedName("resolution_notes") val resolutionNotes: String?,
    val tags: List<String>?,
    @SerializedName("created_at") val createdAt: String?,
    @SerializedName("updated_at") val updatedAt: String?
)

data class CommunityHealthReport(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("report_type") val reportType: String,
    val title: String,
    val description: String,
    val latitude: Double?,
    val longitude: Double?,
    @SerializedName("location_name") val locationName: String?,
    val country: String?,
    val region: String?,
    @SerializedName("symptoms_reported") val symptomsReported: List<String>?,
    @SerializedName("number_affected") val numberAffected: Int?,
    @SerializedName("onset_date") val onsetDate: String?,
    @SerializedName("product_involved") val productInvolved: String?,
    val severity: String,
    @SerializedName("is_verified") val isVerified: Boolean,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("created_at") val createdAt: String?
)

data class HealthGuideline(
    val id: Int,
    val title: String,
    val summary: String,
    @SerializedName("full_text") val fullText: String?,
    val category: String,
    val source: String,
    @SerializedName("source_url") val sourceUrl: String?,
    val version: String?,
    @SerializedName("effective_date") val effectiveDate: String?,
    @SerializedName("superseded_date") val supersededDate: String?,
    @SerializedName("is_current") val isCurrent: Boolean,
    @SerializedName("target_population") val targetPopulation: List<String>?,
    @SerializedName("applicable_countries") val applicableCountries: List<String>?,
    @SerializedName("applicable_conditions") val applicableConditions: List<String>?,
    val recommendations: List<String>?,
    val tags: List<String>?,
    @SerializedName("created_at") val createdAt: String?
)

data class CommunityDashboardStats(
    @SerializedName("total_active_alerts") val totalActiveAlerts: Int,
    @SerializedName("critical_alerts") val criticalAlerts: Int,
    @SerializedName("active_recalls") val activeRecalls: Int,
    @SerializedName("active_outbreaks") val activeOutbreaks: Int,
    @SerializedName("active_advisories") val activeAdvisories: Int,
    @SerializedName("active_poison_alerts") val activePoisonAlerts: Int,
    @SerializedName("total_guidelines") val totalGuidelines: Int,
    @SerializedName("user_reports_30d") val userReports30d: Int,
    @SerializedName("unread_alerts") val unreadAlerts: Int,
    @SerializedName("bookmarked_alerts") val bookmarkedAlerts: Int,
    @SerializedName("latest_outbreaks") val latestOutbreaks: List<CommunityHealthAlert>,
    @SerializedName("latest_recalls") val latestRecalls: List<CommunityHealthAlert>,
    @SerializedName("latest_advisories") val latestAdvisories: List<CommunityHealthAlert>
)

data class AlertCategoryInfo(
    val id: String,
    val name: String,
    val description: String,
    val icon: String
)

data class AlertSourceInfo(
    val id: String,
    val name: String,
    @SerializedName("full_name") val fullName: String,
    val url: String,
    val country: String?
)

data class AlertSubscription(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    val categories: List<String>?,
    val sources: List<String>?,
    val countries: List<String>?,
    val severities: List<String>?,
    @SerializedName("push_enabled") val pushEnabled: Boolean,
    @SerializedName("email_enabled") val emailEnabled: Boolean,
    @SerializedName("sms_enabled") val smsEnabled: Boolean,
    @SerializedName("created_at") val createdAt: String?
)

// ── User Role ──────────────────────────────────────────────────

data class RoleCatalogEntry(
    val id: String,
    val name: String,
    val category: String,
    val description: String?
)

data class RoleCategoryInfo(
    val id: String,
    val name: String,
    val roles: List<RoleCatalogEntry>
)

data class ProfessionalProfile(
    val id: Int,
    @SerializedName("role_assignment_id") val roleAssignmentId: Int,
    @SerializedName("license_number") val licenseNumber: String?,
    @SerializedName("license_state") val licenseState: String?,
    @SerializedName("license_country") val licenseCountry: String?,
    @SerializedName("license_expiry") val licenseExpiry: String?,
    @SerializedName("npi_number") val npiNumber: String?,
    @SerializedName("dea_number") val deaNumber: String?,
    @SerializedName("board_certifications") val boardCertifications: List<String>?,
    @SerializedName("medical_school") val medicalSchool: String?,
    val degree: String?,
    @SerializedName("graduation_year") val graduationYear: Int?,
    @SerializedName("residency_program") val residencyProgram: String?,
    @SerializedName("fellowship_program") val fellowshipProgram: String?,
    val specialty: String?,
    @SerializedName("sub_specialty") val subSpecialty: String?,
    @SerializedName("years_of_experience") val yearsOfExperience: Int?,
    @SerializedName("practice_name") val practiceName: String?,
    @SerializedName("practice_type") val practiceType: String?,
    @SerializedName("practice_address") val practiceAddress: String?,
    @SerializedName("practice_phone") val practicePhone: String?,
    @SerializedName("practice_email") val practiceEmail: String?,
    @SerializedName("practice_website") val practiceWebsite: String?,
    @SerializedName("accepting_patients") val acceptingPatients: Boolean?,
    @SerializedName("hospital_affiliations") val hospitalAffiliations: List<String>?,
    val department: String?,
    val title: String?,
    @SerializedName("clinical_languages") val clinicalLanguages: List<String>?,
    @SerializedName("telemedicine_available") val telemedicineAvailable: Boolean?,
    @SerializedName("telemedicine_platforms") val telemedicinePlatforms: List<String>?,
    @SerializedName("verification_status") val verificationStatus: String?,
    @SerializedName("verification_date") val verificationDate: String?,
    @SerializedName("professional_bio") val professionalBio: String?,
    val publications: List<String>?,
    @SerializedName("research_interests") val researchInterests: List<String>?,
    @SerializedName("created_at") val createdAt: String?,
    @SerializedName("updated_at") val updatedAt: String?
)

data class RoleAssignment(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    val role: String,
    @SerializedName("is_primary") val isPrimary: Boolean,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("granted_at") val grantedAt: String?,
    @SerializedName("professional_profile") val professionalProfile: ProfessionalProfile?
)

data class UserPersonaSummary(
    @SerializedName("user_id") val userId: Int,
    @SerializedName("full_name") val fullName: String,
    val email: String,
    @SerializedName("primary_role") val primaryRole: String,
    @SerializedName("active_roles") val activeRoles: List<String>,
    @SerializedName("role_details") val roleDetails: List<RoleAssignment>,
    @SerializedName("is_healthcare_professional") val isHealthcareProfessional: Boolean,
    @SerializedName("role_categories") val roleCategories: List<String>,
    val permissions: List<String>
)

// Health Sync Models

data class SyncConnection(
    val id: Int,
    val platform: String,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("enabled_data_types") val enabledDataTypes: List<String>?,
    @SerializedName("last_sync_at") val lastSyncAt: String?,
    @SerializedName("last_sync_status") val lastSyncStatus: String?,
    @SerializedName("last_sync_records") val lastSyncRecords: Int?,
    @SerializedName("last_sync_duplicates") val lastSyncDuplicates: Int?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
)

data class SyncBatchResponse(
    val total: Int,
    val created: Int,
    val duplicates: Int,
    val errors: Int,
    val results: List<SyncRecordResult>
)

data class SyncRecordResult(
    @SerializedName("external_id") val externalId: String,
    val status: String,
    @SerializedName("target_table") val targetTable: String?,
    @SerializedName("target_record_id") val targetRecordId: Int?,
    val error: String?
)

data class SyncStatusResponse(
    val platform: String,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("last_sync_at") val lastSyncAt: String?,
    @SerializedName("last_sync_status") val lastSyncStatus: String?,
    @SerializedName("last_sync_records") val lastSyncRecords: Int?,
    @SerializedName("last_sync_duplicates") val lastSyncDuplicates: Int?,
    @SerializedName("total_synced_records") val totalSyncedRecords: Int,
    @SerializedName("records_by_type") val recordsByType: Map<String, Int>
)

// Calendar Event
data class CalendarEvent(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    val title: String,
    val description: String?,
    val category: String,
    @SerializedName("event_date") val eventDate: String,
    @SerializedName("start_time") val startTime: String?,
    @SerializedName("end_time") val endTime: String?,
    @SerializedName("all_day") val allDay: Boolean,
    val recurrence: String?,
    @SerializedName("recurrence_end_date") val recurrenceEndDate: String?,
    val status: String,
    val location: String?,
    @SerializedName("reminder_minutes") val reminderMinutes: Int?,
    @SerializedName("metadata_json") val metadataJson: String?,
    val priority: String?,
    val notes: String?,
    val color: String?,
    @SerializedName("completed_at") val completedAt: String?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
)

data class CalendarCategoryInfo(
    val key: String,
    val label: String,
    val icon: String,
    val color: String
)

// Telehealth
data class TelehealthSession(
    val id: Int,
    @SerializedName("session_code") val sessionCode: String,
    val title: String?,
    @SerializedName("session_type") val sessionType: String,
    val status: String,
    @SerializedName("scheduled_start") val scheduledStart: String,
    @SerializedName("scheduled_end") val scheduledEnd: String?,
    @SerializedName("actual_start") val actualStart: String?,
    @SerializedName("actual_end") val actualEnd: String?,
    @SerializedName("duration_minutes") val durationMinutes: Int?,
    @SerializedName("created_by_id") val createdById: Int,
    @SerializedName("provider_id") val providerId: Int?,
    @SerializedName("reason_for_visit") val reasonForVisit: String?,
    @SerializedName("chief_complaint") val chiefComplaint: String?,
    val specialty: String?,
    val priority: String?,
    @SerializedName("recording_enabled") val recordingEnabled: Boolean,
    @SerializedName("transcription_enabled") val transcriptionEnabled: Boolean,
    @SerializedName("screen_sharing_enabled") val screenSharingEnabled: Boolean,
    @SerializedName("chat_enabled") val chatEnabled: Boolean,
    @SerializedName("waiting_room_enabled") val waitingRoomEnabled: Boolean,
    @SerializedName("connection_quality") val connectionQuality: String?,
    @SerializedName("patient_satisfaction") val patientSatisfaction: Int?,
    @SerializedName("cancellation_reason") val cancellationReason: String?,
    @SerializedName("follow_up_needed") val followUpNeeded: Boolean,
    @SerializedName("follow_up_notes") val followUpNotes: String?,
    @SerializedName("follow_up_date") val followUpDate: String?,
    val participants: List<TelehealthParticipant>?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
) {
    val displayTitle: String get() = title ?: reasonForVisit ?: "Telehealth Visit"
    val isJoinable: Boolean get() = status in listOf("scheduled", "waiting", "in_progress")
}

data class TelehealthParticipant(
    val id: Int,
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("user_id") val userId: Int,
    val role: String,
    val status: String,
    @SerializedName("camera_enabled") val cameraEnabled: Boolean,
    @SerializedName("microphone_enabled") val microphoneEnabled: Boolean,
    @SerializedName("created_at") val createdAt: String
)

data class TelehealthNote(
    val id: Int,
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("author_id") val authorId: Int,
    @SerializedName("note_type") val noteType: String,
    val content: String,
    @SerializedName("diagnosis_codes") val diagnosisCodes: String?,
    @SerializedName("procedure_codes") val procedureCodes: String?,
    @SerializedName("is_private") val isPrivate: Boolean,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
)

data class TelehealthTranscript(
    val id: Int,
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("speaker_id") val speakerId: Int?,
    val content: String,
    val language: String,
    val confidence: Double?,
    @SerializedName("sequence_number") val sequenceNumber: Int,
    @SerializedName("created_at") val createdAt: String
)

data class TelehealthRTCConfig(
    @SerializedName("ice_servers") val iceServers: List<ICEServer>,
    @SerializedName("session_code") val sessionCode: String,
    @SerializedName("user_id") val userId: Int,
    val role: String
)

data class ICEServer(
    val urls: List<String>,
    val username: String?,
    val credential: String?
)

// ── Messaging Models ──

data class Conversation(
    val id: Int,
    @SerializedName("conversation_type") val conversationType: String,
    val title: String?,
    val description: String?,
    @SerializedName("created_by") val createdBy: Int,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("is_urgent") val isUrgent: Boolean,
    val specialty: String?,
    val priority: String?,
    @SerializedName("last_message_at") val lastMessageAt: String?,
    @SerializedName("last_message_preview") val lastMessagePreview: String?,
    @SerializedName("unread_count") val unreadCount: Int?,
    val members: List<ConversationMember>?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String?
) {
    val displayTitle: String
        get() = title ?: when (conversationType) {
            "direct" -> "Direct Message"
            "clinical" -> "Clinical Channel"
            "group" -> "Group Chat"
            "care_team" -> "Care Team"
            else -> "Conversation"
        }
}

data class ConversationMember(
    val id: Int,
    @SerializedName("conversation_id") val conversationId: Int,
    @SerializedName("user_id") val userId: Int,
    val role: String,
    @SerializedName("is_muted") val isMuted: Boolean,
    @SerializedName("joined_at") val joinedAt: String
)

data class ConversationMessage(
    val id: Int,
    @SerializedName("conversation_id") val conversationId: Int,
    @SerializedName("sender_id") val senderId: Int,
    @SerializedName("message_type") val messageType: String,
    val content: String?,
    @SerializedName("is_edited") val isEdited: Boolean,
    @SerializedName("is_deleted") val isDeleted: Boolean,
    @SerializedName("is_clinical") val isClinical: Boolean,
    @SerializedName("is_priority") val isPriority: Boolean,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String?
)

data class CommunityPost(
    val id: Int,
    @SerializedName("author_id") val authorId: Int,
    val content: String,
    val visibility: String,
    val topic: String?,
    @SerializedName("health_category") val healthCategory: String?,
    val hashtags: String?,
    @SerializedName("is_anonymous") val isAnonymous: Boolean,
    @SerializedName("is_pinned") val isPinned: Boolean,
    @SerializedName("is_edited") val isEdited: Boolean,
    @SerializedName("like_count") val likeCount: Int,
    @SerializedName("reply_count") val replyCount: Int,
    @SerializedName("repost_count") val repostCount: Int,
    @SerializedName("view_count") val viewCount: Int,
    @SerializedName("user_liked") val userLiked: Boolean?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String?
)

data class PostReply(
    val id: Int,
    @SerializedName("post_id") val postId: Int,
    @SerializedName("author_id") val authorId: Int,
    val content: String,
    @SerializedName("is_edited") val isEdited: Boolean,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String?
)

data class UserFollow(
    val id: Int,
    @SerializedName("follower_id") val followerId: Int,
    @SerializedName("following_id") val followingId: Int,
    @SerializedName("created_at") val createdAt: String
)

data class LikeResponse(
    val id: Int,
    @SerializedName("post_id") val postId: Int,
    @SerializedName("user_id") val userId: Int,
    val reaction: String,
    @SerializedName("created_at") val createdAt: String
)

// ── Insurance Models ──

data class InsurancePlan(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    val region: String,
    @SerializedName("country_code") val countryCode: String,
    @SerializedName("country_name") val countryName: String,
    @SerializedName("provider_code") val providerCode: String,
    @SerializedName("provider_name") val providerName: String,
    @SerializedName("policy_number") val policyNumber: String? = null,
    @SerializedName("group_number") val groupNumber: String? = null,
    @SerializedName("member_id") val memberId: String? = null,
    @SerializedName("plan_name") val planName: String? = null,
    @SerializedName("plan_type") val planType: String? = null,
    @SerializedName("coverage_start") val coverageStart: String? = null,
    @SerializedName("coverage_end") val coverageEnd: String? = null,
    @SerializedName("is_primary") val isPrimary: Boolean = false,
    @SerializedName("is_active") val isActive: Boolean = true,
    @SerializedName("subscriber_name") val subscriberName: String? = null,
    @SerializedName("subscriber_relationship") val subscriberRelationship: String? = null,
    @SerializedName("insurance_phone") val insurancePhone: String? = null,
    val notes: String? = null,
    @SerializedName("created_at") val createdAt: String = ""
)

data class InsuranceCountry(
    val code: String,
    val name: String
)

data class InsuranceProvider(
    val code: String,
    val name: String
)

// ── Physician Directory ──

data class Physician(
    val id: Int,
    @SerializedName("user_id") val userId: Int? = null,
    @SerializedName("full_name") val fullName: String,
    val specialty: String,
    @SerializedName("specialty_category") val specialtyCategory: String? = null,
    val credentials: String? = null,
    @SerializedName("npi_number") val npiNumber: String? = null,
    @SerializedName("facility_name") val facilityName: String? = null,
    @SerializedName("address_line1") val addressLine1: String? = null,
    val city: String? = null,
    @SerializedName("state_province") val stateProvince: String? = null,
    @SerializedName("postal_code") val postalCode: String? = null,
    val country: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val phone: String? = null,
    val fax: String? = null,
    val email: String? = null,
    val website: String? = null,
    @SerializedName("operating_hours") val operatingHours: String? = null,
    @SerializedName("languages_spoken") val languagesSpoken: String? = null,
    @SerializedName("accepting_new_patients") val acceptingNewPatients: Boolean = true,
    @SerializedName("telehealth_available") val telehealthAvailable: Boolean = false,
    @SerializedName("insurance_accepted") val insuranceAccepted: String? = null,
    @SerializedName("average_rating") val averageRating: Double? = null,
    @SerializedName("review_count") val reviewCount: Int = 0,
    @SerializedName("is_verified") val isVerified: Boolean = false,
    val source: String? = null,
    val status: String? = null,
    @SerializedName("created_at") val createdAt: String = ""
) {
    val locationDisplay: String
        get() = listOfNotNull(city, stateProvince, country).joinToString(", ")
}

data class SavedPhysician(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("physician_id") val physicianId: Int,
    val nickname: String? = null,
    val notes: String? = null,
    @SerializedName("is_primary_care") val isPrimaryCare: Boolean = false,
    @SerializedName("relationship_type") val relationshipType: String? = null,
    val physician: Physician? = null,
    @SerializedName("created_at") val createdAt: String = ""
)

data class PhysicianReview(
    val id: Int,
    @SerializedName("physician_id") val physicianId: Int,
    @SerializedName("user_id") val userId: Int,
    val rating: Int,
    val title: String? = null,
    @SerializedName("review_text") val reviewText: String? = null,
    @SerializedName("is_anonymous") val isAnonymous: Boolean = false,
    @SerializedName("reviewer_name") val reviewerName: String? = null,
    @SerializedName("created_at") val createdAt: String = ""
)

data class SpecialtyCategoriesResponse(
    val categories: Map<String, List<String>>
)

data class GeoSearchResult(
    val physician: Physician,
    @SerializedName("distance_km") val distanceKm: Double
)

data class NearbySearchResponse(
    val results: List<GeoSearchResult>,
    val total: Int,
    @SerializedName("search_lat") val searchLat: Double,
    @SerializedName("search_lon") val searchLon: Double,
    @SerializedName("radius_km") val radiusKm: Double
)

// ── Elimination Models ────────────────────────────────────────────────────────

data class BowelMovement(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("log_date") val logDate: String,
    @SerializedName("log_time") val logTime: String? = null,
    @SerializedName("bristol_scale") val bristolScale: Int? = null,
    val color: String? = null,
    val consistency: String? = null,
    val size: String? = null,
    @SerializedName("blood_present") val bloodPresent: Boolean? = null,
    @SerializedName("mucus_present") val mucusPresent: Boolean? = null,
    @SerializedName("undigested_food") val undigestedFood: Boolean? = null,
    @SerializedName("pain_level") val painLevel: Int? = null,
    val straining: Boolean? = null,
    val urgency: Boolean? = null,
    @SerializedName("duration_minutes") val durationMinutes: Int? = null,
    val location: String? = null,
    @SerializedName("associated_symptoms") val associatedSymptoms: String? = null,
    val notes: String? = null,
    @SerializedName("created_at") val createdAt: String = ""
)

data class UrinationLog(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("log_date") val logDate: String,
    @SerializedName("log_time") val logTime: String? = null,
    val color: String? = null,
    val clarity: String? = null,
    val odor: String? = null,
    @SerializedName("volume_ml") val volumeMl: Int? = null,
    @SerializedName("stream_strength") val streamStrength: String? = null,
    @SerializedName("pain_level") val painLevel: Int? = null,
    @SerializedName("burning_sensation") val burningSensation: Boolean? = null,
    val urgency: Boolean? = null,
    @SerializedName("frequency_increased") val frequencyIncreased: Boolean? = null,
    @SerializedName("blood_present") val bloodPresent: Boolean? = null,
    val location: String? = null,
    val nighttime: Boolean? = null,
    val notes: String? = null,
    @SerializedName("created_at") val createdAt: String = ""
)

data class VomitingLog(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("log_date") val logDate: String,
    @SerializedName("log_time") val logTime: String? = null,
    val volume: String? = null,
    val color: String? = null,
    val consistency: String? = null,
    @SerializedName("contains_food") val containsFood: Boolean? = null,
    @SerializedName("contains_bile") val containsBile: Boolean? = null,
    @SerializedName("contains_blood") val containsBlood: Boolean? = null,
    @SerializedName("nausea_before") val nauseaBefore: Boolean? = null,
    @SerializedName("nausea_after") val nauseaAfter: Boolean? = null,
    val projectile: Boolean? = null,
    val trigger: String? = null,
    @SerializedName("time_since_last_meal_hours") val timeSinceLastMealHours: Double? = null,
    @SerializedName("relief_after") val reliefAfter: Boolean? = null,
    val fever: Boolean? = null,
    val diarrhea: Boolean? = null,
    val headache: Boolean? = null,
    val dizziness: Boolean? = null,
    val notes: String? = null,
    @SerializedName("created_at") val createdAt: String = ""
)

// ── Flowsheet Lifecycle ─────────────────────────────────────────────────────

enum class FlowsheetStatus(val value: String) {
    DRAFT("draft"),
    SUBMITTED("submitted"),
    SIGNED("signed"),
    COUNTERSIGNED("countersigned"),
    REVIEWED("reviewed"),
    LOCKED("locked");

    companion object {
        fun fromString(value: String?): FlowsheetStatus? =
            entries.firstOrNull { it.value == value }
    }
}

// ── Clinical Notes ──────────────────────────────────────────────────────────

data class ClinicalNote(
    val id: Int,
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("author_id") val authorId: Int,
    @SerializedName("note_type") val noteType: String,
    @SerializedName("note_text") val noteText: String,
    @SerializedName("note_hash") val noteHash: String?,
    @SerializedName("created_at") val createdAt: String
)

data class ClinicalNoteCreate(
    @SerializedName("note_type") val noteType: String,
    @SerializedName("note_text") val noteText: String
)

// ── Flowsheet Lifecycle Requests / Responses ────────────────────────────────

data class FlowsheetSignRequest(
    @SerializedName("signature_image") val signatureImage: String
)

data class FlowsheetActionResponse(
    val status: String,
    val message: String,
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("payload_hash") val payloadHash: String? = null,
    @SerializedName("signed_at") val signedAt: String? = null
)

// ── Blockchain ──────────────────────────────────────────────────────────────

data class BlockRecord(
    val id: Int,
    @SerializedName("block_uid") val blockUid: String,
    val index: Int,
    val timestamp: String,
    @SerializedName("chain_type") val chainType: String,
    val action: String,
    val data: Map<String, Any?>?,
    @SerializedName("previous_hash") val previousHash: String,
    val hash: String,
    val nonce: String?,
    @SerializedName("actor_id") val actorId: Int?,
    @SerializedName("entity_type") val entityType: String?,
    @SerializedName("entity_id") val entityId: Int?,
    @SerializedName("merkle_root") val merkleRoot: String?,
    val signature: String?,
    @SerializedName("blockchain_tx_hash") val blockchainTxHash: String?,
    @SerializedName("blockchain_block_num") val blockchainBlockNum: Int?,
    @SerializedName("created_at") val createdAt: String?
)

data class BlockchainVerifyResponse(
    val valid: Boolean,
    @SerializedName("on_chain_data") val onChainData: String? = null,
    val expected: String? = null,
    val block: Int? = null,
    val message: String? = null
)

// ── System ID ───────────────────────────────────────────────────────────────

data class SystemIdResponse(
    @SerializedName("system_id") val systemId: String,
    val masked: String,
    val segments: Map<String, String>,
    val valid: Boolean
)
