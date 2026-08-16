package com.alafia.android.models

import com.google.gson.annotations.SerializedName

// ── Lab Charts ──────────────────────────────────────────────────────────────

data class LabChartPoint(
    val date: String,
    val value: Double,
    @SerializedName("reference_low") val referenceLow: Double? = null,
    @SerializedName("reference_high") val referenceHigh: Double? = null
)

data class LabChartSeries(
    @SerializedName("test_name") val testName: String,
    val unit: String? = null,
    @SerializedName("reference_low") val referenceLow: Double? = null,
    @SerializedName("reference_high") val referenceHigh: Double? = null,
    val data: List<LabChartPoint> = emptyList()
)

data class LabChartGroup(
    @SerializedName("group_name") val name: String,
    val series: List<LabChartSeries> = emptyList()
)

// ── Wellness ────────────────────────────────────────────────────────────────

data class WellnessScore(
    val id: Int,
    @SerializedName("user_id") val userId: Int? = null,
    @SerializedName("score_date") val scoreDate: String? = null,
    @SerializedName("overall_score") val overallScore: Double,
    @SerializedName("nutrition_score") val nutritionScore: Double? = null,
    @SerializedName("fitness_score") val fitnessScore: Double? = null,
    @SerializedName("sleep_score") val sleepScore: Double? = null,
    @SerializedName("mood_score") val moodScore: Double? = null,
    @SerializedName("vitals_score") val vitalsScore: Double? = null,
    @SerializedName("medication_adherence_score") val medicationAdherenceScore: Double? = null,
    val explanation: String? = null,
    val recommendations: String? = null
)

data class TrendDataPoint(
    val date: String,
    val value: Double,
    val label: String? = null
)

data class TrendStream(
    val name: String,
    val data: List<TrendDataPoint> = emptyList(),
    val trend: String? = null
)

data class HealthTrendResponse(
    @SerializedName("overall_summary") val overallSummary: String? = null,
    val streams: List<TrendStream> = emptyList(),
    val correlations: List<String>? = null,
    val suggestions: List<String>? = null
)

data class RecommendationItem(
    val category: String,
    val title: String,
    val description: String,
    val priority: String,
    val action: String? = null
)

data class DailyRecommendationsResponse(
    val date: String,
    val recommendations: List<RecommendationItem> = emptyList()
)

data class HealthImprovementsResponse(
    val summary: String? = null,
    @SerializedName("wellness_score") val wellnessScore: Double? = null,
    @SerializedName("nutrition_improvements") val nutritionImprovements: List<String>? = null,
    @SerializedName("fitness_improvements") val fitnessImprovements: List<String>? = null,
    @SerializedName("sleep_improvements") val sleepImprovements: List<String>? = null,
    @SerializedName("mood_improvements") val moodImprovements: List<String>? = null,
    @SerializedName("medical_improvements") val medicalImprovements: List<String>? = null
)

// ── Planners ────────────────────────────────────────────────────────────────

data class MealItem(
    val name: String,
    val calories: Int? = null,
    @SerializedName("protein_g") val proteinG: Double? = null,
    @SerializedName("carbs_g") val carbsG: Double? = null,
    @SerializedName("fat_g") val fatG: Double? = null,
    val description: String? = null
)

data class DayMeals(
    val breakfast: List<MealItem>? = null,
    val lunch: List<MealItem>? = null,
    val dinner: List<MealItem>? = null,
    val snacks: List<MealItem>? = null
)

data class MealPlanResponse(
    val id: Int,
    @SerializedName("plan_name") val planName: String,
    @SerializedName("dietary_pattern") val dietaryPattern: String? = null,
    @SerializedName("start_date") val startDate: String? = null,
    @SerializedName("end_date") val endDate: String? = null,
    @SerializedName("plan_data") val planData: Map<String, DayMeals>? = null,
    @SerializedName("shopping_list") val shoppingList: List<String>? = null,
    val advice: String? = null,
    @SerializedName("total_daily_calories") val totalDailyCalories: Int? = null
)

data class MealPlanRequest(
    @SerializedName("dietary_pattern") val dietaryPattern: String,
    @SerializedName("daily_calorie_target") val dailyCalorieTarget: Int? = null,
    val allergies: String? = null,
    val preferences: String? = null
)

data class ExerciseItem(
    val name: String,
    @SerializedName("duration_minutes") val durationMinutes: Int? = null,
    val description: String? = null,
    @SerializedName("muscle_groups") val muscleGroups: List<String>? = null,
    val sets: Int? = null,
    val reps: Int? = null
)

data class ExercisePlanResponse(
    val id: Int,
    @SerializedName("plan_name") val planName: String,
    @SerializedName("fitness_level") val fitnessLevel: String? = null,
    @SerializedName("start_date") val startDate: String? = null,
    @SerializedName("end_date") val endDate: String? = null,
    @SerializedName("plan_data") val planData: Map<String, List<ExerciseItem>>? = null,
    val advice: String? = null,
    @SerializedName("weekly_minutes_target") val weeklyMinutesTarget: Int? = null
)

data class ExercisePlanRequest(
    @SerializedName("fitness_level") val fitnessLevel: String,
    @SerializedName("weekly_minutes_target") val weeklyMinutesTarget: Int? = null,
    val limitations: String? = null
)

// ── Image AI ────────────────────────────────────────────────────────────────

data class FoodItemResult(
    val name: String,
    val calories: Int? = null,
    @SerializedName("protein_g") val proteinG: Double? = null,
    @SerializedName("carbs_g") val carbsG: Double? = null,
    @SerializedName("fat_g") val fatG: Double? = null,
    @SerializedName("serving_size") val servingSize: String? = null
)

data class NutritionFromImageResponse(
    @SerializedName("food_items") val foodItems: List<FoodItemResult> = emptyList(),
    @SerializedName("total_calories") val totalCalories: Int? = null,
    @SerializedName("total_protein_g") val totalProteinG: Double? = null,
    @SerializedName("total_carbs_g") val totalCarbsG: Double? = null,
    @SerializedName("total_fat_g") val totalFatG: Double? = null,
    @SerializedName("confidence_note") val confidenceNote: String? = null
)

data class MedicationImageField(
    val label: String? = null,
    val value: String? = null
)

data class MedicationFromImageResponse(
    @SerializedName("medication_name") val medicationName: String? = null,
    val dosage: String? = null,
    val instructions: String? = null,
    @SerializedName("ndc_code") val ndcCode: String? = null,
    val manufacturer: String? = null,
    val fields: List<MedicationImageField> = emptyList(),
    val notes: String? = null
)

data class DosageVerificationRequest(
    @SerializedName("medication_name") val medicationName: String,
    val dosage: String,
    val frequency: String? = null
)

data class DosageVerificationResponse(
    @SerializedName("medication_name") val medicationName: String? = null,
    val dosage: String? = null,
    @SerializedName("is_typical") val isTypical: Boolean? = null,
    val feedback: String? = null,
    @SerializedName("typical_range") val typicalRange: String? = null,
    val precautions: List<String> = emptyList()
)

// ── PDF Tools ───────────────────────────────────────────────────────────────

data class LabReportItem(
    @SerializedName("test_name") val testName: String? = null,
    val value: String? = null,
    val unit: String? = null,
    @SerializedName("reference_range") val referenceRange: String? = null,
    @SerializedName("is_abnormal") val isAbnormal: Boolean? = null
)

data class LabReportParseResponse(
    @SerializedName("patient_name") val patientName: String? = null,
    @SerializedName("report_date") val reportDate: String? = null,
    @SerializedName("lab_name") val labName: String? = null,
    @SerializedName("ordering_physician") val orderingPhysician: String? = null,
    val items: List<LabReportItem>? = null,
    @SerializedName("raw_text_preview") val rawTextPreview: String? = null
)

data class FlowsheetRequest(
    @SerializedName("session_type") val sessionType: String,
    val days: Int = 30
)

data class FlowsheetResponse(
    val title: String? = null,
    @SerializedName("generated_at") val generatedAt: String? = null,
    val content: String? = null,
    @SerializedName("session_count") val sessionCount: Int? = null
)

// ── Peritoneal Dialysis ─────────────────────────────────────────────────────

data class PDExchange(
    val id: Int? = null,
    @SerializedName("exchange_number") val exchangeNumber: Int,
    @SerializedName("start_time") val startTime: String? = null,
    @SerializedName("drain_start_time") val drainStartTime: String? = null,
    @SerializedName("drain_end_time") val drainEndTime: String? = null,
    @SerializedName("fill_end_time") val fillEndTime: String? = null,
    @SerializedName("solution_type") val solutionType: String? = null,
    @SerializedName("inflow_volume_ml") val inflowVolumeMl: Int? = null,
    @SerializedName("outflow_volume_ml") val outflowVolumeMl: Int? = null,
    @SerializedName("uf_ml") val ufMl: Int? = null,
    @SerializedName("effluent_clarity") val effluentClarity: String? = null,
    @SerializedName("effluent_color") val effluentColor: String? = null
)

data class PDSession(
    val id: Int,
    @SerializedName("user_id") val userId: Int? = null,
    @SerializedName("session_date") val sessionDate: String,
    val modality: String,
    @SerializedName("pre_weight_kg") val preWeightKg: Double? = null,
    @SerializedName("post_weight_kg") val postWeightKg: Double? = null,
    @SerializedName("pre_bp_systolic") val preBpSystolic: Int? = null,
    @SerializedName("pre_bp_diastolic") val preBpDiastolic: Int? = null,
    @SerializedName("post_bp_systolic") val postBpSystolic: Int? = null,
    @SerializedName("post_bp_diastolic") val postBpDiastolic: Int? = null,
    @SerializedName("temperature_c") val temperatureC: Double? = null,
    @SerializedName("exit_site_status") val exitSiteStatus: String? = null,
    @SerializedName("total_uf_ml") val totalUfMl: Int? = null,
    val exchanges: List<PDExchange>? = null,
    val notes: String? = null,
    @SerializedName("created_at") val createdAt: String? = null
)

data class PDSessionCreate(
    @SerializedName("condition_id") val conditionId: Int? = null,
    @SerializedName("session_date") val sessionDate: String,
    val modality: String,
    @SerializedName("pre_weight_kg") val preWeightKg: Double? = null,
    @SerializedName("post_weight_kg") val postWeightKg: Double? = null,
    @SerializedName("pre_bp_systolic") val preBpSystolic: Int? = null,
    @SerializedName("pre_bp_diastolic") val preBpDiastolic: Int? = null,
    @SerializedName("post_bp_systolic") val postBpSystolic: Int? = null,
    @SerializedName("post_bp_diastolic") val postBpDiastolic: Int? = null,
    @SerializedName("temperature_c") val temperatureC: Double? = null,
    @SerializedName("exit_site_status") val exitSiteStatus: String? = null,
    val notes: String? = null,
    val exchanges: List<PDExchange>? = null
)

// ── Advanced Directives ─────────────────────────────────────────────────────

data class AdvancedDirective(
    val id: Int? = null,
    @SerializedName("primary_agent_name") val primaryAgentName: String? = null,
    @SerializedName("primary_agent_relationship") val primaryAgentRelationship: String? = null,
    @SerializedName("primary_agent_phone") val primaryAgentPhone: String? = null,
    @SerializedName("primary_agent_email") val primaryAgentEmail: String? = null,
    @SerializedName("alternate_agent_name") val alternateAgentName: String? = null,
    @SerializedName("alternate_agent_relationship") val alternateAgentRelationship: String? = null,
    @SerializedName("alternate_agent_phone") val alternateAgentPhone: String? = null,
    @SerializedName("organ_donation") val organDonation: String? = null,
    @SerializedName("life_support") val lifeSupport: String? = null,
    val cpr: String? = null,
    val ventilator: String? = null,
    @SerializedName("feeding_tube") val feedingTube: String? = null,
    @SerializedName("dialysis_directive") val dialysisDirective: String? = null,
    @SerializedName("blood_transfusion") val bloodTransfusion: String? = null,
    @SerializedName("document_signed") val documentSigned: Boolean? = null,
    @SerializedName("document_date") val documentDate: String? = null,
    @SerializedName("additional_instructions") val additionalInstructions: String? = null
)

// ── FDA Recalls ─────────────────────────────────────────────────────────────

data class FDARecallItem(
    // Global recalls schema (US openFDA food+drug, Health Canada, UK FSA)
    @SerializedName("product_type") val productType: String? = null,   // "food" | "drug"
    val source: String? = null,                                        // issuing authority
    val url: String? = null,                                           // official notice link
    @SerializedName("recall_number") val recallNumber: String? = null,
    @SerializedName("product_description") val productDescription: String? = null,
    val reason: String? = null,
    val classification: String? = null,
    val status: String? = null,
    @SerializedName("recall_initiation_date") val recallInitiationDate: String? = null,
    @SerializedName("report_date") val reportDate: String? = null,
    @SerializedName("recalling_firm") val recallingFirm: String? = null,
    val city: String? = null,
    val state: String? = null,
    val country: String? = null,
    val distribution: String? = null,
    @SerializedName("voluntary_mandated") val voluntaryMandated: String? = null,
    val states: List<String> = emptyList(),     // US state codes reached
    val countries: List<String> = emptyList(),  // ISO-2 countries reached
    val nationwide: Boolean = false
)

data class FDARecallResponse(
    val total: Int,
    val results: List<FDARecallItem> = emptyList()
)

// ── Facilities Directory ────────────────────────────────────────────────────

data class Facility(
    val id: Int,
    val name: String,
    @SerializedName("facility_type") val facilityType: String,
    val phone: String? = null,
    val website: String? = null,
    @SerializedName("address_line1") val addressLine1: String? = null,
    val city: String? = null,
    @SerializedName("state_province") val stateProvince: String? = null,
    @SerializedName("postal_code") val postalCode: String? = null,
    val country: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null
)

// ── Disease Surveillance ────────────────────────────────────────────────────

data class SurveillanceDisease(
    val id: String,
    val label: String,
    val icon: String,
    val category: String
)

data class SurveillanceCountry(
    val iso2: String,
    val name: String,
    val region: String? = null,
    val outward: Double? = null,                              // WHO indicator value
    @SerializedName("outward_year") val outwardYear: Int? = null,
    val inward: Int = 0                                       // ALAFIA symptom activity
)

data class SurveillanceGlobal(
    val disease: SurveillanceDisease,
    val days: Int,
    val countries: List<SurveillanceCountry> = emptyList(),
    @SerializedName("inward_total") val inwardTotal: Int = 0
)

// ── Composite Weight Series ─────────────────────────────────────────────────

data class WeightSeriesPoint(
    val date: String,
    val value: Double,
    val min: Double,
    val max: Double,
    val count: Int,
    @SerializedName("rolling_7d") val rolling7d: Double,
    val sources: Map<String, Int> = emptyMap()
)

data class WeightSeriesSummary(
    val count: Int,
    val avg: Double? = null,
    val stddev: Double? = null,
    val min: Double? = null,
    val max: Double? = null,
    val sources: Map<String, Int> = emptyMap(),
    val trend: String = "stable",
    @SerializedName("dry_weight_kg") val dryWeightKg: Double? = null,
    @SerializedName("profile_current_weight_kg") val profileCurrentWeightKg: Double? = null,
    @SerializedName("profile_target_weight_kg") val profileTargetWeightKg: Double? = null
)

data class WeightSeriesResponse(
    val label: String,
    val unit: String,
    val days: Int,
    val points: List<WeightSeriesPoint> = emptyList(),
    val summary: WeightSeriesSummary
)

// ── Firebase token exchange (phone / Google / Apple sign-in) ────────────────

data class FirebaseTokenRequest(
    @SerializedName("id_token") val idToken: String
)

// ── Food photo labeling (visual memory) ─────────────────────────────────────

data class FoodLabelRequest(
    @SerializedName("image_base64") val imageBase64: String,
    val foods: String? = null,
    @SerializedName("recipe_url") val recipeUrl: String? = null
)

// ── Recipe URL analysis (third meal input: URL / description / photo) ───────

data class RecipeAnalyzeRequest(
    val url: String,
    val servings: Int? = null
)

data class RecipeAnalyzeResponse(
    val name: String,
    val url: String,
    val servings: Int,
    val ingredients: List<String> = emptyList(),
    @SerializedName("per_serving") val perServing: Map<String, Double> = emptyMap(),
    val total: Map<String, Double> = emptyMap(),
    @SerializedName("total_weight_g") val totalWeightG: Double = 0.0,
    val source: String = "estimated",
    val learned: Boolean = false
)

// ── Elimination photo analysis (stool / urine / vomit) ──────────────────────

data class EliminationImageRequest(
    @SerializedName("event_type") val eventType: String,   // bowel | urination | vomiting
    @SerializedName("image_base64") val imageBase64: String
)

data class EliminationSuggested(
    val color: String? = null,
    @SerializedName("bristol_scale") val bristolScale: Int? = null,
    val consistency: String? = null,
    @SerializedName("blood_present") val bloodPresent: Boolean? = null,
    @SerializedName("mucus_present") val mucusPresent: Boolean? = null
)

data class EliminationFromImageResponse(
    @SerializedName("event_type") val eventType: String = "bowel",
    val description: String = "",
    val suggested: EliminationSuggested = EliminationSuggested(),
    val flags: List<String> = emptyList(),
    val disclaimer: String? = null
)

// ── Data Sharing ────────────────────────────────────────────────────────────

data class DataGrant(
    val id: Int,
    @SerializedName("grantee_email") val granteeEmail: String? = null,
    @SerializedName("grantee_display_name") val granteeDisplayName: String? = null,
    @SerializedName("data_type") val dataType: String,
    @SerializedName("can_read") val canRead: Boolean,
    @SerializedName("can_write") val canWrite: Boolean,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("expires_at") val expiresAt: String? = null,
    @SerializedName("created_at") val createdAt: String? = null
)

data class DataGrantCreate(
    @SerializedName("grantee_email") val granteeEmail: String,
    @SerializedName("data_type") val dataType: String,
    @SerializedName("can_read") val canRead: Boolean = true,
    @SerializedName("can_write") val canWrite: Boolean = false,
    @SerializedName("expires_at") val expiresAt: String? = null
)

data class DataShareInvitation(
    val id: Int,
    @SerializedName("recipient_email") val recipientEmail: String? = null,
    @SerializedName("data_types") val dataTypes: List<String>? = null,
    val message: String? = null,
    val status: String,
    @SerializedName("created_at") val createdAt: String? = null
)

data class DataShareInvitationCreate(
    @SerializedName("recipient_email") val recipientEmail: String,
    @SerializedName("data_types") val dataTypes: List<String>,
    val message: String? = null
)

// ── Clinician Dashboard ─────────────────────────────────────────────────────

// Mirrors app/schemas/wellness.py::PatientSummary. The previous shape here
// (patient_id / display_name / shared_data_types) matched no field the API has
// ever returned, so every patient decoded as an empty row.
data class ClinicianVitals(
    val date: String? = null,
    val bp: String? = null,
    val hr: Int? = null,
    @SerializedName("weight_kg") val weightKg: Double? = null
)

data class ClinicianMood(
    val date: String? = null,
    val score: Int? = null
)

data class ClinicianLabItem(
    val name: String? = null,
    val value: String? = null,
    val unit: String? = null,
    val date: String? = null,
    @SerializedName("is_abnormal") val isAbnormal: Boolean = false
)

data class PatientSummary(
    @SerializedName("user_id") val userId: Int,
    @SerializedName("full_name") val fullName: String = "",
    val email: String? = null,
    @SerializedName("latest_vitals") val latestVitals: ClinicianVitals? = null,
    @SerializedName("latest_mood") val latestMood: ClinicianMood? = null,
    @SerializedName("latest_labs") val latestLabs: List<ClinicianLabItem> = emptyList(),
    val conditions: List<String> = emptyList(),
    val medications: List<String> = emptyList(),
    val permissions: List<String> = emptyList(),
    @SerializedName("last_activity") val lastActivity: String? = null
)

data class ClinicianDashboardResponse(
    val role: String? = null,
    @SerializedName("patient_count") val patientCount: Int = 0,
    val patients: List<PatientSummary> = emptyList()
)

// ── Chart Dashboard ──────────────────────────────

data class ChartDatasetInfo(
    val key: String,
    val label: String,
    val unit: String
)

data class ChartDataPoint(
    val date: String,
    val value: Double? = null,
    val min: Double? = null,
    val max: Double? = null,
    val count: Int? = null
)

data class ChartDataSeries(
    val label: String,
    val unit: String,
    val domain: String,
    val points: List<ChartDataPoint> = emptyList()
)

data class ChartSummaryResponse(
    val key: String,
    val label: String,
    val unit: String,
    val days: Int,
    val avg: Double? = null,
    val min: Double? = null,
    val max: Double? = null,
    val count: Int = 0,
    val stddev: Double? = null,
    val trend: String = "stable"
)

// ── Pharmacy ────────────────────────────────────────

data class PharmacyPrescription(
    val id: Int,
    @SerializedName("patient_id") val patientId: Int,
    @SerializedName("prescriber_id") val prescriberId: Int,
    @SerializedName("medication_name") val medicationName: String,
    @SerializedName("rxnorm_code") val rxnormCode: String? = null,
    val dosage: String? = null,
    @SerializedName("dosage_unit") val dosageUnit: String? = null,
    val strength: String? = null,
    val form: String? = null,
    val route: String? = null,
    val frequency: String? = null,
    @SerializedName("duration_days") val durationDays: Int? = null,
    val quantity: Int? = null,
    @SerializedName("refills_authorized") val refillsAuthorized: Int = 0,
    @SerializedName("refills_remaining") val refillsRemaining: Int = 0,
    val diagnosis: String? = null,
    val instructions: String? = null,
    @SerializedName("pharmacy_notes") val pharmacyNotes: String? = null,
    @SerializedName("substitution_allowed") val substitutionAllowed: Boolean = true,
    @SerializedName("prescribed_date") val prescribedDate: String? = null,
    @SerializedName("expiry_date") val expiryDate: String? = null,
    val status: String = "pending",
    @SerializedName("is_controlled_substance") val isControlledSubstance: Boolean = false,
    @SerializedName("medication_id") val medicationId: Int? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("patient_name") val patientName: String? = null,
    @SerializedName("prescriber_name") val prescriberName: String? = null,
    @SerializedName("dispense_count") val dispenseCount: Int? = null
)

data class PrescriptionCreateRequest(
    @SerializedName("patient_id") val patientId: Int,
    @SerializedName("medication_name") val medicationName: String,
    val dosage: String? = null,
    @SerializedName("dosage_unit") val dosageUnit: String? = null,
    val frequency: String? = null,
    val quantity: Int? = null,
    @SerializedName("refills_authorized") val refillsAuthorized: Int = 0,
    val diagnosis: String? = null,
    val instructions: String? = null,
    @SerializedName("substitution_allowed") val substitutionAllowed: Boolean = true
)

data class PharmacyDispense(
    val id: Int,
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("pharmacist_id") val pharmacistId: Int,
    @SerializedName("quantity_dispensed") val quantityDispensed: Int? = null,
    @SerializedName("days_supply") val daysSupply: Int? = null,
    @SerializedName("ndc_code") val ndcCode: String? = null,
    @SerializedName("lot_number") val lotNumber: String? = null,
    val manufacturer: String? = null,
    @SerializedName("is_generic") val isGeneric: Boolean = false,
    @SerializedName("interactions_checked") val interactionsChecked: Boolean = false,
    @SerializedName("allergy_checked") val allergyChecked: Boolean = false,
    @SerializedName("counseling_provided") val counselingProvided: Boolean = false,
    @SerializedName("clinical_notes") val clinicalNotes: String? = null,
    val status: String = "pending_review",
    @SerializedName("dispensed_at") val dispensedAt: String? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("pharmacist_name") val pharmacistName: String? = null,
    @SerializedName("medication_name") val medicationName: String? = null
)

data class DispenseCreateRequest(
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("quantity_dispensed") val quantityDispensed: Int? = null,
    @SerializedName("days_supply") val daysSupply: Int? = null,
    @SerializedName("ndc_code") val ndcCode: String? = null,
    @SerializedName("lot_number") val lotNumber: String? = null,
    val manufacturer: String? = null,
    @SerializedName("is_generic") val isGeneric: Boolean = false,
    @SerializedName("interactions_checked") val interactionsChecked: Boolean = false,
    @SerializedName("allergy_checked") val allergyChecked: Boolean = false,
    @SerializedName("counseling_provided") val counselingProvided: Boolean = false,
    @SerializedName("clinical_notes") val clinicalNotes: String? = null
)

data class PharmacyAdherenceLog(
    val id: Int,
    @SerializedName("patient_id") val patientId: Int,
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("scheduled_time") val scheduledTime: String,
    @SerializedName("actual_time") val actualTime: String? = null,
    val status: String = "taken",
    @SerializedName("dose_taken") val doseTaken: String? = null,
    val notes: String? = null,
    @SerializedName("side_effects_reported") val sideEffectsReported: String? = null,
    @SerializedName("mood_before") val moodBefore: Int? = null,
    @SerializedName("mood_after") val moodAfter: Int? = null,
    @SerializedName("pain_before") val painBefore: Int? = null,
    @SerializedName("pain_after") val painAfter: Int? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("medication_name") val medicationName: String? = null
)

data class AdherenceLogCreateRequest(
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("scheduled_time") val scheduledTime: String,
    val status: String = "taken",
    @SerializedName("dose_taken") val doseTaken: String? = null,
    val notes: String? = null,
    @SerializedName("side_effects_reported") val sideEffectsReported: String? = null,
    @SerializedName("mood_before") val moodBefore: Int? = null,
    @SerializedName("mood_after") val moodAfter: Int? = null
)

data class PharmacyAdherenceReport(
    @SerializedName("prescription_id") val prescriptionId: Int? = null,
    @SerializedName("patient_id") val patientId: Int,
    @SerializedName("medication_name") val medicationName: String? = null,
    @SerializedName("total_scheduled") val totalScheduled: Int = 0,
    @SerializedName("total_taken") val totalTaken: Int = 0,
    @SerializedName("total_missed") val totalMissed: Int = 0,
    @SerializedName("total_skipped") val totalSkipped: Int = 0,
    @SerializedName("total_late") val totalLate: Int = 0,
    @SerializedName("adherence_rate") val adherenceRate: Double = 0.0,
    @SerializedName("avg_delay_minutes") val avgDelayMinutes: Double? = null,
    @SerializedName("streak_current") val streakCurrent: Int = 0,
    @SerializedName("streak_longest") val streakLongest: Int = 0,
    @SerializedName("common_side_effects") val commonSideEffects: List<String> = emptyList()
)

data class PharmacySchedule(
    val id: Int,
    @SerializedName("patient_id") val patientId: Int,
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("time_of_day") val timeOfDay: String,
    @SerializedName("days_of_week") val daysOfWeek: String? = null,
    @SerializedName("dose_label") val doseLabel: String? = null,
    @SerializedName("is_active") val isActive: Boolean = true,
    @SerializedName("reminder_minutes_before") val reminderMinutesBefore: Int = 15,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("medication_name") val medicationName: String? = null
)

data class ScheduleCreateRequest(
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("time_of_day") val timeOfDay: String,
    @SerializedName("days_of_week") val daysOfWeek: String? = null,
    @SerializedName("dose_label") val doseLabel: String? = null,
    @SerializedName("reminder_minutes_before") val reminderMinutesBefore: Int = 15
)

data class PharmacyRefillRequest(
    val id: Int,
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("patient_id") val patientId: Int,
    @SerializedName("requested_by_id") val requestedById: Int,
    @SerializedName("approved_by_id") val approvedById: Int? = null,
    val status: String = "requested",
    @SerializedName("quantity_requested") val quantityRequested: Int? = null,
    val notes: String? = null,
    @SerializedName("denial_reason") val denialReason: String? = null,
    @SerializedName("requested_at") val requestedAt: String? = null,
    @SerializedName("resolved_at") val resolvedAt: String? = null,
    @SerializedName("medication_name") val medicationName: String? = null
)

data class RefillCreateRequest(
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("quantity_requested") val quantityRequested: Int? = null,
    val notes: String? = null
)

data class MedicationImpactResponse(
    @SerializedName("prescription_id") val prescriptionId: Int,
    @SerializedName("medication_name") val medicationName: String,
    @SerializedName("patient_id") val patientId: Int,
    @SerializedName("analysis_period_days") val analysisPeriodDays: Int,
    @SerializedName("adherence_rate") val adherenceRate: Double,
    @SerializedName("doses_taken") val dosesTaken: Int,
    @SerializedName("doses_missed") val dosesMissed: Int,
    @SerializedName("avg_mood_before") val avgMoodBefore: Double? = null,
    @SerializedName("avg_mood_after") val avgMoodAfter: Double? = null,
    @SerializedName("mood_trend") val moodTrend: String? = null,
    @SerializedName("reported_side_effects") val reportedSideEffects: List<String> = emptyList(),
    @SerializedName("side_effect_frequency") val sideEffectFrequency: Map<String, Int>? = null,
    @SerializedName("effectiveness_score") val effectivenessScore: Double? = null,
    @SerializedName("tolerability_score") val tolerabilityScore: Double? = null,
    @SerializedName("ai_summary") val aiSummary: String? = null
)

// ── Pantry ──────────────────────────────────────────

data class PantryItem(
    val id: Int,
    @SerializedName("user_id") val userId: Int,
    val name: String,
    val category: String,
    val quantity: Float,
    val unit: String,
    val location: String,
    @SerializedName("expiration_date") val expirationDate: String? = null,
    val notes: String? = null,
    @SerializedName("auto_replenish") val autoReplenish: Boolean = false,
    @SerializedName("low_threshold") val lowThreshold: Float? = null,
    @SerializedName("created_at") val createdAt: String = "",
    @SerializedName("updated_at") val updatedAt: String = ""
)

data class PantryItemCreate(
    val name: String,
    val category: String,
    val quantity: Float,
    val unit: String,
    val location: String,
    @SerializedName("expiration_date") val expirationDate: String? = null,
    val notes: String? = null
)

// ── HEBCS Ω (Wellness Tensor / Clinical Biomarker Score) ────────────────────

data class HEBCSBiomarkerScore(
    val name: String,
    val value: Double? = null,
    val score: Double? = null,
    val weight: Double,
    @SerializedName("opt_range") val optRange: List<Double>? = null
)

data class HEBCSPathwayScore(
    val score: Double? = null,
    val weight: Double,
    val biomarkers: List<HEBCSBiomarkerScore> = emptyList()
)

data class HEBCSScoreResponse(
    @SerializedName("computed_at") val computedAt: String? = null,
    @SerializedName("lab_date_used") val labDateUsed: String? = null,
    val omega: Double,
    @SerializedName("omega_pct") val omegaPct: Double,
    @SerializedName("data_coverage") val dataCoverage: Double,
    val pathways: Map<String, HEBCSPathwayScore> = emptyMap(),
    val interpretation: String? = null
)

data class WhatIfPathwayDelta(
    @SerializedName("baseline_score") val baselineScore: Double? = null,
    @SerializedName("scenario_score") val scenarioScore: Double? = null,
    val delta: Double? = null
)

data class WhatIfResponse(
    @SerializedName("scenario_name") val scenarioName: String,
    @SerializedName("baseline_omega") val baselineOmega: Double,
    @SerializedName("scenario_omega") val scenarioOmega: Double,
    @SerializedName("delta_omega") val deltaOmega: Double,
    @SerializedName("delta_pct") val deltaPct: Double,
    @SerializedName("pathway_deltas") val pathwayDeltas: Map<String, WhatIfPathwayDelta> = emptyMap(),
    @SerializedName("overridden_biomarkers") val overriddenBiomarkers: List<String> = emptyList(),
    val interpretation: String
)

data class WhatIfRequest(
    @SerializedName("scenario_name") val scenarioName: String = "custom",
    @SerializedName("Phosphorus") val phosphorus: Double? = null,
    @SerializedName("Potassium") val potassium: Double? = null,
    @SerializedName("Albumin") val albumin: Double? = null,
    @SerializedName("Hemoglobin") val hemoglobin: Double? = null,
    @SerializedName("Ferritin") val ferritin: Double? = null,
    @SerializedName("KtV_Dialysis_Adequacy") val ktv: Double? = null,
    @SerializedName("PTH_Intact") val pthIntact: Double? = null,
    @SerializedName("Calcium") val calcium: Double? = null,
    @SerializedName("Glucose") val glucose: Double? = null,
    @SerializedName("Sodium") val sodium: Double? = null
)

// ── Subscription / Billing (ALAFIA Membership) ────────────────────────────────────

data class SubscriptionRailPrice(
    val provider: String,
    @SerializedName("price_usd") val priceUsd: Double,
    @SerializedName("store_product_id") val storeProductId: String? = null
)

data class SubscriptionPlans(
    @SerializedName("product_name") val productName: String,
    val plan: String,
    val currency: String = "USD",
    val interval: String = "month",
    val rails: List<SubscriptionRailPrice> = emptyList()
)

data class SubscriptionStatus(
    val status: String,
    val provider: String,
    val plan: String,
    val entitled: Boolean,
    @SerializedName("product_name") val productName: String,
    @SerializedName("price_usd") val priceUsd: Double? = null,
    @SerializedName("current_period_end") val currentPeriodEnd: String? = null,
    @SerializedName("cancel_at_period_end") val cancelAtPeriodEnd: Boolean = false
)

data class GoogleVerifyRequest(
    @SerializedName("purchase_token") val purchaseToken: String,
    @SerializedName("product_id") val productId: String,
    @SerializedName("order_id") val orderId: String? = null
)

// ── Clinician patient board ──────────────────────────────
// Mirrors app/services/patient_board.py. Summary items and table cells are
// deliberately heterogeneous (a lab value is "4.2" or "NEG", a count is an Int,
// `danger` is a Bool), so values arrive as Any? and are formatted for display
// rather than forced into one concrete type.

data class BoardItem(
    val label: String = "",
    val value: Any? = null,
    val unit: String? = null,
    val danger: Boolean = false,
    val note: String? = null
) {
    /** Trailing ".0" on whole numbers is Gson's doing, not the API's. */
    fun displayValue(): String? {
        val v = value ?: return null
        val s = when (v) {
            is Double -> if (v == Math.floor(v) && !v.isInfinite()) v.toLong().toString()
                         else String.format("%.2f", v).trimEnd('0').trimEnd('.')
            else -> v.toString()
        }
        return if (unit.isNullOrEmpty()) s else "$s $unit"
    }
}

data class BoardCard(
    val key: String = "",
    val label: String = "",
    val icon: String = "",
    val shared: Boolean = false,
    val items: List<BoardItem> = emptyList(),
    val count: Int? = null,
    @SerializedName("last_updated") val lastUpdated: String? = null,
    @SerializedName("empty_reason") val emptyReason: String? = null
)

data class BoardPatient(
    @SerializedName("user_id") val userId: Int = 0,
    @SerializedName("full_name") val fullName: String? = null,
    val email: String? = null
)

data class PatientBoardResponse(
    val patient: BoardPatient = BoardPatient(),
    val permissions: List<String> = emptyList(),
    val cards: List<BoardCard> = emptyList()
)

data class TrendPoint(val date: String = "", val value: Double? = null)

data class TrendSeries(
    val label: String = "",
    val unit: String? = null,
    val points: List<TrendPoint> = emptyList()
)

data class BoardColumn(val key: String = "", val label: String = "")

data class PatientCategoryResponse(
    val patient: BoardPatient = BoardPatient(),
    val key: String = "",
    val label: String = "",
    val icon: String = "",
    val days: Int = 90,
    val series: List<TrendSeries> = emptyList(),
    val columns: List<BoardColumn> = emptyList(),
    val rows: List<Map<String, Any?>> = emptyList()
)

// ── Physician view of one therapy session ───────────────────────────────────
//
// Served by the clinician-scoped route. `/chronic/therapy-sessions/*` filters by
// the CALLER's user id, so a physician opening a patient's session got a 404 from
// it — including from /review, the endpoint written for physicians.

data class TherapySessionDetailDto(
    val id: Int,
    val date: String?,
    val therapy: String?,
    val name: String?,
    val status: String?,
    @SerializedName("facility_name") val facilityName: String?,
    @SerializedName("attending_physician") val attendingPhysician: String?,
    @SerializedName("attending_nurse") val attendingNurse: String?,
    @SerializedName("dialysis_access_type") val dialysisAccessType: String?,
    @SerializedName("duration_minutes") val durationMinutes: Int?,
    @SerializedName("pre_dialysis_weight_kg") val preDialysisWeightKg: Double?,
    @SerializedName("post_dialysis_weight_kg") val postDialysisWeightKg: Double?,
    @SerializedName("dry_weight_kg") val dryWeightKg: Double?,
    @SerializedName("fluid_removed_ml") val fluidRemovedMl: Double?,
    @SerializedName("blood_flow_rate") val bloodFlowRate: Double?,
    @SerializedName("pre_systolic_bp") val preSystolicBp: Int?,
    @SerializedName("pre_diastolic_bp") val preDiastolicBp: Int?,
    @SerializedName("post_systolic_bp") val postSystolicBp: Int?,
    @SerializedName("post_diastolic_bp") val postDiastolicBp: Int?,
    @SerializedName("pre_heart_rate") val preHeartRate: Int?,
    @SerializedName("post_heart_rate") val postHeartRate: Int?,
    val complications: String?,
    @SerializedName("adverse_reactions") val adverseReactions: String?,
    @SerializedName("patient_tolerance") val patientTolerance: String?,
    @SerializedName("patient_notes") val patientNotes: String?
)

data class TherapySessionNote(
    val id: Int,
    @SerializedName("author_role") val authorRole: String?,
    @SerializedName("note_type") val noteType: String?,
    @SerializedName("note_text") val noteText: String,
    @SerializedName("created_at") val createdAt: String?
)

/** Who has attested to this record — reported even when empty, so the physician
 *  can see they are signing on top of an unsigned flowsheet. */
data class SessionSignoff(
    @SerializedName("flowsheet_status") val flowsheetStatus: String?,
    @SerializedName("signed_at") val signedAt: String?,
    @SerializedName("signed_by") val signedBy: Int?,
    @SerializedName("countersigned_at") val countersignedAt: String?,
    @SerializedName("countersigned_by") val countersignedBy: Int?,
    @SerializedName("reviewed_at") val reviewedAt: String?,
    @SerializedName("reviewed_by") val reviewedBy: Int?,
    @SerializedName("payload_hash") val payloadHash: String?
) {
    val isReviewed: Boolean get() = flowsheetStatus == "reviewed" || reviewedAt != null
}

data class TherapySessionReport(
    val patient: BoardPatient,
    val session: TherapySessionDetailDto,
    val readings: List<com.alafia.android.models.IntradialyticReading> = emptyList(),
    val notes: List<TherapySessionNote> = emptyList(),
    val signoff: SessionSignoff
)

data class SessionReviewResponse(
    val id: Int,
    val signoff: SessionSignoff,
    val message: String?
)

data class TherapySummary(
    @SerializedName("period_days") val periodDays: Int,
    @SerializedName("total_sessions") val totalSessions: Int,
    @SerializedName("total_sessions_all_time") val totalSessionsAllTime: Int,
    @SerializedName("avg_pre_weight_kg") val avgPreWeightKg: Double?,
    @SerializedName("avg_post_weight_kg") val avgPostWeightKg: Double?,
    @SerializedName("avg_fluid_removed_ml") val avgFluidRemovedMl: Double?,
    @SerializedName("avg_duration_min") val avgDurationMin: Double?,
    @SerializedName("earliest_session") val earliestSession: String?,
    @SerializedName("latest_session") val latestSession: String?
)

data class IntegrityBlock(
    @SerializedName("block_uid") val blockUid: String,
    val index: Int,
    val action: String,
    val event: String?,
    @SerializedName("actor_id") val actorId: Int?,
    @SerializedName("recorded_at") val recordedAt: String?,
    val hash: String?,
    @SerializedName("previous_hash") val previousHash: String?,
    val anchored: Boolean,
    @SerializedName("tx_hash") val txHash: String?,
    @SerializedName("block_number") val blockNumber: Int?
)

/** payloadMatches is null when the record was never signed — a different fact
 *  from "does not match". */
data class SessionIntegrity(
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("payload_hash") val payloadHash: String?,
    @SerializedName("payload_matches") val payloadMatches: Boolean?,
    @SerializedName("chain_intact") val chainIntact: Boolean?,
    @SerializedName("anchored_count") val anchoredCount: Int,
    val trail: List<IntegrityBlock> = emptyList()
)
