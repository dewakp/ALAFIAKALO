package com.alafia.android.schemas

import com.google.gson.annotations.SerializedName

// Auth Schemas
data class LoginRequest(
    val username: String,  // Backend uses OAuth2PasswordRequestForm which uses 'username' field
    val password: String
)

data class LoginResponse(
    val access_token: String,
    val token_type: String,
    val refresh_token: String? = null
)

data class RegisterRequest(
    val email: String,
    val password: String,
    val full_name: String,
    val date_of_birth: String? = null,
    val gender: String? = null
)

data class UserSchema(
    val id: Int,
    val email: String,
    val full_name: String,
    val date_of_birth: String? = null,
    val gender: String? = null,
    val gender_at_birth: String? = null,
    val profile_picture_url: String? = null,
    val blood_type: String? = null,
    val insurance_id: String? = null,
    val insurance_provider: String? = null,
    val insurance_country: String? = null,
    val height_cm: Double? = null,
    val current_weight_kg: Double? = null,
    val target_weight_kg: Double? = null,
    val locale: String? = null,
    val timezone: String? = null,
    val country: String? = null,
    val preferred_units: String? = null,
    val preferred_language: String? = null,
    val allergies: String? = null,
    val food_intolerances: String? = null,
    val dietary_restrictions: String? = null,
    val dietary_preferences: String? = null,
    val family_history: String? = null,
    val activity_level: String? = null,
    val fitness_goals: String? = null,
    val preferred_activities: String? = null,
    val exercise_frequency_per_week: Int? = null,
    val smoking_status: String? = null,
    val alcohol_consumption: String? = null,
    val sleep_schedule: String? = null,
    val occupation: String? = null,
    val stress_level: String? = null,
    val ai_coaching_enabled: Boolean? = null,
    val ai_persona: String? = null,
    val ai_personality_preference: String? = null,
    val ai_language_complexity: String? = null,
    val data_sharing_consent: Boolean? = null,
    val ai_training_consent: Boolean? = null,
    val is_active: Boolean = true,
    val is_superuser: Boolean = false,
    val primary_role: String? = null,
    val active_roles: List<String>? = null,
    val is_healthcare_professional: Boolean? = null
)

/** Partial update payload — only non-null fields are sent. */
data class UserUpdateRequest(
    val full_name: String? = null,
    val date_of_birth: String? = null,
    val gender: String? = null,
    val gender_at_birth: String? = null,
    val blood_type: String? = null,
    val profile_picture_url: String? = null,
    val insurance_id: String? = null,
    val insurance_provider: String? = null,
    val insurance_country: String? = null,
    val height_cm: Double? = null,
    val current_weight_kg: Double? = null,
    val target_weight_kg: Double? = null,
    val locale: String? = null,
    val timezone: String? = null,
    val country: String? = null,
    val preferred_units: String? = null,
    val preferred_language: String? = null,
    val allergies: String? = null,
    val food_intolerances: String? = null,
    val dietary_restrictions: String? = null,
    val dietary_preferences: String? = null,
    val family_history: String? = null,
    val activity_level: String? = null,
    val fitness_goals: String? = null,
    val preferred_activities: String? = null,
    val exercise_frequency_per_week: Int? = null,
    val smoking_status: String? = null,
    val alcohol_consumption: String? = null,
    val sleep_schedule: String? = null,
    val occupation: String? = null,
    val stress_level: String? = null,
    val ai_coaching_enabled: Boolean? = null,
    val ai_persona: String? = null,
    val ai_personality_preference: String? = null,
    val ai_language_complexity: String? = null,
    val data_sharing_consent: Boolean? = null,
    val ai_training_consent: Boolean? = null
)

// Token Refresh
data class RefreshTokenRequest(
    val refresh_token: String
)

// Password Reset
data class PasswordResetRequest(
    val email: String
)

data class PasswordResetConfirm(
    val token: String,
    val new_password: String
)

data class PasswordResetResponse(
    val message: String,
    val reset_token: String? = null
)

// Fitness Schemas
data class FitnessLogRequest(
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
    val notes: String?
)

data class FitnessLogResponse(
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

// Mood Schemas
data class MoodEntryRequest(
    @SerializedName("entry_date") val entryDate: String,
    @SerializedName("mood_score") val moodScore: Int,
    @SerializedName("energy_level") val energyLevel: Int? = null,
    @SerializedName("stress_level") val stressLevel: Int? = null,
    @SerializedName("anxiety_level") val anxietyLevel: Int? = null,
    @SerializedName("sleep_quality") val sleepQuality: Int? = null,
    @SerializedName("sleep_hours") val sleepHours: Double? = null,
    val emotions: String? = null,
    val triggers: String? = null,
    @SerializedName("coping_strategies") val copingStrategies: String? = null,
    val gratitude: String? = null,
    @SerializedName("journal_entry") val journalEntry: String? = null
)

// Nutrition Schemas
data class NutritionLogRequest(
    @SerializedName("log_date") val logDate: String,
    @SerializedName("meal_type") val mealType: String,
    @SerializedName("food_name") val foodName: String,
    @SerializedName("serving_size") val servingSize: String? = null,
    @SerializedName("fdc_id") val fdcId: Int? = null,
    val calories: Float? = null,
    @SerializedName("protein_g") val proteinG: Float? = null,
    @SerializedName("carbs_g") val carbsG: Float? = null,
    @SerializedName("fat_g") val fatG: Float? = null,
    val notes: String? = null,
    @SerializedName("start_time") val startTime: String? = null,
    @SerializedName("end_time") val endTime: String? = null,
    @SerializedName("pre_meal_weight_kg") val preMealWeightKg: Float? = null,
    @SerializedName("post_meal_weight_kg") val postMealWeightKg: Float? = null,
    @SerializedName("recipe_url") val recipeUrl: String? = null
)

// Medications Schemas
data class MedicationRequest(
    val name: String,
    val dosage: String,
    val frequency: String,
    val reason: String,
    val start_date: String,
    val end_date: String?,
    val notes: String?
)

// Medication dose log ("taken" event) — POST /medications/dose-logs
data class MedicationDoseLogRequest(
    val medication_name: String,
    val log_date: String,
    val dose_amount: Double,
    val dose_unit: String,
    val medication_id: Int? = null,
    val notes: String? = null
)

// Labs Schemas
data class LabResultRequest(
    val test_date: String,
    val test_name: String,
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
    val notes: String? = null
)

// Lifestyle Schemas
data class LifestyleEntryRequest(
    val log_date: String,
    val category: String,
    val value: String,
    val notes: String?
)

// AI Schemas
data class ChatMessage(
    val role: String,
    val content: String
)

data class AIRequest(
    val query: String,
    val messages: List<ChatMessage> = emptyList(),
    val persona: String? = null
)

data class AIResponse(
    val response: String,
    val timestamp: String? = null,
    val persona: String? = null
)

data class AIPersona(
    val key: String,
    val title: String,
    val origin: String,
    val region: String,
    val greeting: String,
    val description: String
)

// Mental Health Schemas
data class AssessmentRequest(
    @SerializedName("assessment_date") val assessmentDate: String,
    @SerializedName("assessment_type") val assessmentType: String,
    @SerializedName("phq_interest") val phqInterest: Int? = null,
    @SerializedName("phq_feeling_down") val phqFeelingDown: Int? = null,
    @SerializedName("phq_sleep") val phqSleep: Int? = null,
    @SerializedName("phq_energy") val phqEnergy: Int? = null,
    @SerializedName("phq_appetite") val phqAppetite: Int? = null,
    @SerializedName("phq_self_esteem") val phqSelfEsteem: Int? = null,
    @SerializedName("phq_concentration") val phqConcentration: Int? = null,
    @SerializedName("phq_psychomotor") val phqPsychomotor: Int? = null,
    @SerializedName("phq_suicidal_ideation") val phqSuicidalIdeation: Int? = null,
    @SerializedName("gad_nervous") val gadNervous: Int? = null,
    @SerializedName("gad_uncontrollable_worry") val gadUncontrollableWorry: Int? = null,
    @SerializedName("gad_excessive_worry") val gadExcessiveWorry: Int? = null,
    @SerializedName("gad_trouble_relaxing") val gadTroubleRelaxing: Int? = null,
    @SerializedName("gad_restless") val gadRestless: Int? = null,
    @SerializedName("gad_irritable") val gadIrritable: Int? = null,
    @SerializedName("gad_afraid") val gadAfraid: Int? = null,
    @SerializedName("who5_cheerful") val who5Cheerful: Int? = null,
    @SerializedName("who5_calm") val who5Calm: Int? = null,
    @SerializedName("who5_active") val who5Active: Int? = null,
    @SerializedName("who5_rested") val who5Rested: Int? = null,
    @SerializedName("who5_interesting") val who5Interesting: Int? = null
)

data class BreathingSessionRequest(
    @SerializedName("session_date") val sessionDate: String,
    @SerializedName("exercise_type") val exerciseType: String,
    @SerializedName("duration_seconds") val durationSeconds: Int,
    @SerializedName("mood_before") val moodBefore: Int? = null,
    @SerializedName("mood_after") val moodAfter: Int? = null
)

data class GratitudeRequest(
    @SerializedName("entry_date") val entryDate: String,
    @SerializedName("item_1") val item1: String,
    @SerializedName("item_2") val item2: String? = null,
    @SerializedName("item_3") val item3: String? = null,
    val reflection: String? = null
)

// ─── Community Health Schemas ────────────────────────────────────────

data class CommunityReportRequest(
    @SerializedName("report_type") val reportType: String,
    val title: String,
    val description: String,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @SerializedName("location_name") val locationName: String? = null,
    val country: String? = null,
    val region: String? = null,
    @SerializedName("symptoms_reported") val symptomsReported: List<String>? = null,
    @SerializedName("number_affected") val numberAffected: Int? = null,
    @SerializedName("onset_date") val onsetDate: String? = null,
    @SerializedName("product_involved") val productInvolved: String? = null,
    val severity: String = "moderate"
)

data class CommunitySubscriptionRequest(
    val categories: List<String>? = null,
    val sources: List<String>? = null,
    val countries: List<String>? = null,
    val severities: List<String>? = null,
    @SerializedName("push_enabled") val pushEnabled: Boolean = true,
    @SerializedName("email_enabled") val emailEnabled: Boolean = false,
    @SerializedName("sms_enabled") val smsEnabled: Boolean = false
)

// ── User Role ──────────────────────────────────────────────────

data class RoleAssignmentRequest(
    val role: String,
    @SerializedName("is_primary") val isPrimary: Boolean = false
)

data class ProfessionalProfileRequest(
    @SerializedName("license_number") val licenseNumber: String? = null,
    @SerializedName("license_state") val licenseState: String? = null,
    @SerializedName("license_country") val licenseCountry: String? = null,
    @SerializedName("license_expiry") val licenseExpiry: String? = null,
    @SerializedName("npi_number") val npiNumber: String? = null,
    @SerializedName("dea_number") val deaNumber: String? = null,
    @SerializedName("board_certifications") val boardCertifications: List<String>? = null,
    @SerializedName("medical_school") val medicalSchool: String? = null,
    val degree: String? = null,
    @SerializedName("graduation_year") val graduationYear: Int? = null,
    @SerializedName("residency_program") val residencyProgram: String? = null,
    @SerializedName("fellowship_program") val fellowshipProgram: String? = null,
    val specialty: String? = null,
    @SerializedName("sub_specialty") val subSpecialty: String? = null,
    @SerializedName("years_of_experience") val yearsOfExperience: Int? = null,
    @SerializedName("practice_name") val practiceName: String? = null,
    @SerializedName("practice_type") val practiceType: String? = null,
    @SerializedName("practice_address") val practiceAddress: String? = null,
    @SerializedName("practice_phone") val practicePhone: String? = null,
    @SerializedName("practice_email") val practiceEmail: String? = null,
    @SerializedName("practice_website") val practiceWebsite: String? = null,
    @SerializedName("accepting_patients") val acceptingPatients: Boolean? = null,
    @SerializedName("hospital_affiliations") val hospitalAffiliations: List<String>? = null,
    val department: String? = null,
    val title: String? = null,
    @SerializedName("clinical_languages") val clinicalLanguages: List<String>? = null,
    @SerializedName("telemedicine_available") val telemedicineAvailable: Boolean? = null,
    @SerializedName("telemedicine_platforms") val telemedicinePlatforms: List<String>? = null,
    @SerializedName("professional_bio") val professionalBio: String? = null,
    val publications: List<String>? = null,
    @SerializedName("research_interests") val researchInterests: List<String>? = null
)

// Health Sync Schemas

data class SyncConnectionRequest(
    val platform: String,
    @SerializedName("enabled_data_types") val enabledDataTypes: List<String>? = null
)

data class SyncRecordRequest(
    @SerializedName("external_id") val externalId: String,
    @SerializedName("data_type") val dataType: String,
    @SerializedName("source_timestamp") val sourceTimestamp: String,
    val data: Map<String, Any?>
)

data class SyncBatchRequest(
    val platform: String,
    val records: List<SyncRecordRequest>
)

// Calendar Schemas

data class CalendarEventRequest(
    val title: String,
    val description: String? = null,
    val category: String = "appointment",
    @SerializedName("event_date") val eventDate: String,
    @SerializedName("start_time") val startTime: String? = null,
    @SerializedName("end_time") val endTime: String? = null,
    @SerializedName("all_day") val allDay: Boolean = false,
    val recurrence: String? = null,
    @SerializedName("recurrence_end_date") val recurrenceEndDate: String? = null,
    val location: String? = null,
    @SerializedName("reminder_minutes") val reminderMinutes: Int? = null,
    val priority: String? = null,
    val notes: String? = null,
    val color: String? = null
)

data class CalendarEventUpdateRequest(
    val title: String? = null,
    val description: String? = null,
    val category: String? = null,
    @SerializedName("event_date") val eventDate: String? = null,
    @SerializedName("start_time") val startTime: String? = null,
    @SerializedName("end_time") val endTime: String? = null,
    @SerializedName("all_day") val allDay: Boolean? = null,
    val recurrence: String? = null,
    val status: String? = null,
    val location: String? = null,
    @SerializedName("reminder_minutes") val reminderMinutes: Int? = null,
    val priority: String? = null,
    val notes: String? = null,
    val color: String? = null
)

// Telehealth Schemas

data class TelehealthSessionRequest(
    @SerializedName("session_type") val sessionType: String = "video",
    val title: String? = null,
    @SerializedName("scheduled_start") val scheduledStart: String,
    @SerializedName("scheduled_end") val scheduledEnd: String? = null,
    @SerializedName("reason_for_visit") val reasonForVisit: String? = null,
    @SerializedName("chief_complaint") val chiefComplaint: String? = null,
    val specialty: String? = null,
    val priority: String = "routine",
    @SerializedName("provider_id") val providerId: Int? = null,
    @SerializedName("transcription_enabled") val transcriptionEnabled: Boolean = true,
    @SerializedName("chat_enabled") val chatEnabled: Boolean = true,
    @SerializedName("recording_enabled") val recordingEnabled: Boolean = false,
    @SerializedName("waiting_room_enabled") val waitingRoomEnabled: Boolean = true
)

data class TelehealthStatusRequest(
    val status: String
)

data class TelehealthNoteRequest(
    @SerializedName("note_type") val noteType: String = "general",
    val content: String
)

// ── Messaging Schemas ──

data class CreateConversationRequest(
    @SerializedName("conversation_type") val conversationType: String,
    val title: String? = null,
    val description: String? = null,
    @SerializedName("member_ids") val memberIds: List<Int>,
    val specialty: String? = null,
    val priority: String? = null,
    @SerializedName("is_urgent") val isUrgent: Boolean = false
)

data class SendMessageRequest(
    val content: String,
    @SerializedName("message_type") val messageType: String = "text",
    @SerializedName("is_clinical") val isClinical: Boolean = false,
    @SerializedName("is_priority") val isPriority: Boolean = false
)

data class CreatePostRequest(
    val content: String,
    val visibility: String = "public",
    val topic: String? = null,
    @SerializedName("health_category") val healthCategory: String? = null,
    val hashtags: String? = null,
    @SerializedName("is_anonymous") val isAnonymous: Boolean = false
)

data class CreateReplyRequest(
    val content: String
)

// ── Insurance Schemas ──

data class InsuranceCreateRequest(
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
    val notes: String? = null
)

// ── Physician Directory Schemas ──

data class PhysicianCreateRequest(
    @SerializedName("full_name") val fullName: String,
    val specialty: String,
    val credentials: String? = null,
    @SerializedName("npi_number") val npiNumber: String? = null,
    @SerializedName("facility_name") val facilityName: String? = null,
    @SerializedName("address_line1") val addressLine1: String? = null,
    val city: String? = null,
    @SerializedName("state_province") val stateProvince: String? = null,
    @SerializedName("postal_code") val postalCode: String? = null,
    val country: String? = null,
    val phone: String? = null,
    val email: String? = null,
    val website: String? = null,
    @SerializedName("accepting_new_patients") val acceptingNewPatients: Boolean = true,
    @SerializedName("telehealth_available") val telehealthAvailable: Boolean = false,
    @SerializedName("languages_spoken") val languagesSpoken: String? = null
)

data class SavePhysicianRequest(
    @SerializedName("physician_id") val physicianId: Int,
    val nickname: String? = null,
    val notes: String? = null,
    @SerializedName("is_primary_care") val isPrimaryCare: Boolean = false,
    @SerializedName("relationship_type") val relationshipType: String? = null
)

data class PhysicianReviewRequest(
    val rating: Int,
    val title: String? = null,
    @SerializedName("review_text") val reviewText: String? = null,
    @SerializedName("is_anonymous") val isAnonymous: Boolean = false
)

// ── Elimination Schemas ───────────────────────────────────────────────────────

data class BowelMovementRequest(
    @SerializedName("log_date") val logDate: String,
    @SerializedName("log_time") val logTime: String? = null,
    @SerializedName("bristol_scale") val bristolScale: Int? = null,
    val color: String? = null,
    val consistency: String? = null,
    @SerializedName("blood_present") val bloodPresent: Boolean? = null,
    @SerializedName("mucus_present") val mucusPresent: Boolean? = null,
    @SerializedName("pain_level") val painLevel: Int? = null,
    val straining: Boolean? = null,
    val urgency: Boolean? = null,
    val notes: String? = null
)

data class UrinationLogRequest(
    @SerializedName("log_date") val logDate: String,
    @SerializedName("log_time") val logTime: String? = null,
    val color: String? = null,
    val clarity: String? = null,
    @SerializedName("volume_ml") val volumeMl: Int? = null,
    @SerializedName("pain_level") val painLevel: Int? = null,
    @SerializedName("burning_sensation") val burningSensation: Boolean? = null,
    val urgency: Boolean? = null,
    @SerializedName("blood_present") val bloodPresent: Boolean? = null,
    val nighttime: Boolean? = null,
    val notes: String? = null
)

data class VomitingLogRequest(
    @SerializedName("log_date") val logDate: String,
    @SerializedName("log_time") val logTime: String? = null,
    val volume: String? = null,
    @SerializedName("contains_food") val containsFood: Boolean? = null,
    @SerializedName("contains_bile") val containsBile: Boolean? = null,
    @SerializedName("contains_blood") val containsBlood: Boolean? = null,
    @SerializedName("nausea_before") val nauseaBefore: Boolean? = null,
    @SerializedName("nausea_after") val nauseaAfter: Boolean? = null,
    val projectile: Boolean? = null,
    val trigger: String? = null,
    @SerializedName("relief_after") val reliefAfter: Boolean? = null,
    val fever: Boolean? = null,
    val dizziness: Boolean? = null,
    val notes: String? = null
)
