package com.alafia.android.api

import com.alafia.android.models.*
import com.alafia.android.schemas.*
import okhttp3.MultipartBody
import retrofit2.http.*

interface ApiService {

    // Auth Endpoints
    @GET("auth/csrf-cookie")
    suspend fun getCsrfCookie(): retrofit2.Response<Void>

    @FormUrlEncoded
    @POST("auth/login")
    suspend fun login(
        @Field("username") username: String,
        @Field("password") password: String,
        @Header("X-CSRF-Token") csrfToken: String? = null,
        @Header("Cookie") csrfCookie: String? = null,
    ): LoginResponse

    @POST("auth/register")
    suspend fun register(@Body request: RegisterRequest): UserSchema

    @POST("auth/refresh")
    suspend fun refreshToken(@Body request: RefreshTokenRequest): LoginResponse

    /** Exchange a Firebase Auth ID token (native phone-OTP / Google / Apple
     *  sign-in flow) for ALAFIA JWTs. Provider SDK flows are wired separately. */
    @POST("auth/firebase")
    suspend fun loginWithFirebase(@Body request: FirebaseTokenRequest): LoginResponse

    @POST("auth/password-reset/request")
    suspend fun requestPasswordReset(@Body request: PasswordResetRequest): PasswordResetResponse

    @POST("auth/password-reset/confirm")
    suspend fun confirmPasswordReset(@Body request: PasswordResetConfirm): PasswordResetResponse

    // User Endpoints
    @GET("users/me")
    suspend fun getCurrentUser(): UserSchema

    @PATCH("users/me")
    suspend fun updateUser(@Body updates: UserUpdateRequest): UserSchema

    // Fitness Endpoints
    @GET("fitness")
    suspend fun getFitnessLogs(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<FitnessLogResponse>

    @POST("fitness")
    suspend fun createFitnessLog(@Body request: FitnessLogRequest): FitnessLogResponse

    @GET("fitness/{id}")
    suspend fun getFitnessLog(@Path("id") id: Int): FitnessLogResponse

    @PUT("fitness/{id}")
    suspend fun updateFitnessLog(
        @Path("id") id: Int,
        @Body request: FitnessLogRequest
    ): FitnessLogResponse

    @DELETE("fitness/{id}")
    suspend fun deleteFitnessLog(@Path("id") id: Int)

    // Mood Endpoints
    @GET("mood/")
    suspend fun getMoodEntries(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<MoodEntry>

    @POST("mood/")
    suspend fun createMoodEntry(@Body request: MoodEntryRequest): MoodEntry

    @PUT("mood/{id}")
    suspend fun updateMoodEntry(
        @Path("id") id: Int,
        @Body request: MoodEntryRequest
    ): MoodEntry

    @DELETE("mood/{id}")
    suspend fun deleteMoodEntry(@Path("id") id: Int)

    // Nutrition Endpoints
    @GET("nutrition")
    suspend fun getNutritionLogs(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<NutritionLog>

    @POST("nutrition")
    suspend fun createNutritionLog(@Body request: NutritionLogRequest): NutritionLog

    @PUT("nutrition/{id}")
    suspend fun updateNutritionLog(
        @Path("id") id: Int,
        @Body request: NutritionLogRequest
    ): NutritionLog

    @DELETE("nutrition/{id}")
    suspend fun deleteNutritionLog(@Path("id") id: Int)

    @GET("nutrition/food-search")
    suspend fun searchUSDAFoods(
        @Query("q") query: String,
        @Query("page_size") pageSize: Int = 15
    ): List<USDAFoodResult>

    @GET("nutrition/food/{fdcId}")
    suspend fun getUSDAFoodDetail(@Path("fdcId") fdcId: Int): USDAFoodDetail

    @GET("nutrition/daily-summary")
    suspend fun getNutritionDailySummary(@Query("date") date: String): DailySummary

    @GET("nutrition/goal-progress")
    suspend fun getNutritionGoalProgress(@Query("date") date: String): GoalProgressResponse

    // Labs Endpoints
    @GET("labs")
    suspend fun getLabResults(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<LabResult>

    @POST("labs")
    suspend fun createLabResult(@Body request: LabResultRequest): LabResult

    @PUT("labs/{id}")
    suspend fun updateLabResult(
        @Path("id") id: Int,
        @Body request: LabResultRequest
    ): LabResult

    @DELETE("labs/{id}")
    suspend fun deleteLabResult(@Path("id") id: Int)

    // Medications Endpoints
    @GET("medications")
    suspend fun getMedications(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<Medication>

    @POST("medications")
    suspend fun createMedication(@Body request: MedicationRequest): Medication

    @PUT("medications/{id}")
    suspend fun updateMedication(
        @Path("id") id: Int,
        @Body request: MedicationRequest
    ): Medication

    @DELETE("medications/{id}")
    suspend fun deleteMedication(@Path("id") id: Int)

    // Medication dose logs ("taken" events)
    @POST("medications/dose-logs")
    suspend fun logMedicationDose(@Body request: MedicationDoseLogRequest): MedicationDoseLog

    @GET("medications/dose-logs")
    suspend fun getMedicationDoseLogs(
        @Query("log_date") logDate: String? = null,
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null
    ): List<MedicationDoseLog>

    @DELETE("medications/dose-logs/{id}")
    suspend fun deleteMedicationDoseLog(@Path("id") id: Int)

    // Lifestyle Endpoints
    @GET("lifestyle")
    suspend fun getLifestyleEntries(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<LifestyleEntry>

    @POST("lifestyle")
    suspend fun createLifestyleEntry(@Body request: LifestyleEntryRequest): LifestyleEntry

    @PUT("lifestyle/{id}")
    suspend fun updateLifestyleEntry(
        @Path("id") id: Int,
        @Body request: LifestyleEntryRequest
    ): LifestyleEntry

    @DELETE("lifestyle/{id}")
    suspend fun deleteLifestyleEntry(@Path("id") id: Int)

    // AI Endpoints
    @POST("ai/chat")
    suspend fun aiChat(@Body request: AIRequest): AIResponse

    @GET("ai/personas")
    suspend fun getAIPersonas(): List<AIPersona>

    @POST("ai/route")
    suspend fun routePrompt(@Body request: AIRouteRequest): AIRouteResponse

    @Multipart
    @POST("ai/vision")
    suspend fun routeVision(@Part file: MultipartBody.Part): AIVisionResponse

    // Privacy Endpoints
    @GET("privacy/settings")
    suspend fun getPrivacySettings(): PrivacySettings

    @PUT("privacy/settings")
    suspend fun updatePrivacySettings(@Body settings: Map<String, Any>): PrivacySettings

    @POST("privacy/export")
    suspend fun requestDataExport(@Query("export_format") format: String = "json")

    @POST("privacy/delete-account")
    suspend fun requestAccountDeletion()

    // Chronic Conditions Endpoints
    @GET("chronic/conditions")
    suspend fun getChronicConditions(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 100,
        @Query("is_active") isActive: Boolean? = null
    ): List<ChronicCondition>

    @GET("chronic/conditions/{id}")
    suspend fun getChronicCondition(@Path("id") id: Int): ChronicCondition

    @POST("chronic/conditions")
    suspend fun createChronicCondition(@Body condition: Map<String, Any?>): ChronicCondition

    @PUT("chronic/conditions/{id}")
    suspend fun updateChronicCondition(
        @Path("id") id: Int,
        @Body condition: Map<String, Any?>
    ): ChronicCondition

    @DELETE("chronic/conditions/{id}")
    suspend fun deleteChronicCondition(@Path("id") id: Int)

    // Therapy Sessions Endpoints
    @GET("chronic/therapy-sessions")
    suspend fun getTherapySessions(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 100,
        @Query("condition_id") conditionId: Int? = null,
        @Query("therapy_type") therapyType: String? = null
    ): List<TherapySession>

    @GET("chronic/therapy-sessions/{id}")
    suspend fun getTherapySession(@Path("id") id: Int): TherapySession

    @POST("chronic/therapy-sessions")
    suspend fun createTherapySession(@Body session: Map<String, Any?>): TherapySession

    @PUT("chronic/therapy-sessions/{id}")
    suspend fun updateTherapySession(
        @Path("id") id: Int,
        @Body session: Map<String, Any?>
    ): TherapySession

    @DELETE("chronic/therapy-sessions/{id}")
    suspend fun deleteTherapySession(@Path("id") id: Int)

    // Intradialytic Readings
    @GET("chronic/therapy-sessions/{id}/readings")
    suspend fun getIntradialyticReadings(@Path("id") sessionId: Int): List<IntradialyticReading>

    @POST("chronic/therapy-sessions/{id}/readings")
    suspend fun createIntradialyticReading(
        @Path("id") sessionId: Int,
        @Body reading: Map<String, Any?>
    ): IntradialyticReading

    @DELETE("chronic/readings/{id}")
    suspend fun deleteIntradialyticReading(@Path("id") id: Int)

    // HD Summary
    @GET("chronic/hd-summary")
    suspend fun getHDSummary(@Query("days") days: Int = 90): HDSummary

    // Mental Health Endpoints
    @GET("mental-health/stats")
    suspend fun getMentalHealthStats(): MentalHealthStats

    @GET("mental-health/assessments")
    suspend fun getAssessments(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<MentalHealthAssessment>

    @POST("mental-health/assessments")
    suspend fun createAssessment(@Body request: AssessmentRequest): MentalHealthAssessment

    @DELETE("mental-health/assessments/{id}")
    suspend fun deleteAssessment(@Path("id") id: Int)

    @GET("mental-health/breathing/exercises")
    suspend fun getBreathingExercises(): List<BreathingExerciseInfo>

    @GET("mental-health/breathing/sessions")
    suspend fun getBreathingSessions(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<BreathingSessionResponse>

    @POST("mental-health/breathing/sessions")
    suspend fun createBreathingSession(@Body request: BreathingSessionRequest): BreathingSessionResponse

    @GET("mental-health/gratitude")
    suspend fun getGratitudeEntries(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<GratitudeEntryResponse>

    @POST("mental-health/gratitude")
    suspend fun createGratitude(@Body request: GratitudeRequest): GratitudeEntryResponse

    @DELETE("mental-health/gratitude/{id}")
    suspend fun deleteGratitude(@Path("id") id: Int)

    // Community Health Endpoints
    @GET("community/dashboard")
    suspend fun getCommunityDashboard(): CommunityDashboardStats

    @GET("community/alerts")
    suspend fun getCommunityAlerts(
        @Query("category") category: String? = null,
        @Query("source") source: String? = null,
        @Query("severity") severity: String? = null,
        @Query("country") country: String? = null,
        @Query("search") search: String? = null,
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<CommunityHealthAlert>

    @GET("community/alerts/{id}")
    suspend fun getCommunityAlert(@Path("id") id: Int): CommunityHealthAlert

    @POST("community/alerts/{id}/bookmark")
    suspend fun toggleAlertBookmark(@Path("id") id: Int): Map<String, Any>

    @GET("community/guidelines")
    suspend fun getCommunityGuidelines(
        @Query("category") category: String? = null,
        @Query("source") source: String? = null,
        @Query("search") search: String? = null,
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<HealthGuideline>

    @GET("community/guidelines/{id}")
    suspend fun getCommunityGuideline(@Path("id") id: Int): HealthGuideline

    @GET("community/reports")
    suspend fun getCommunityReports(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 50
    ): List<CommunityHealthReport>

    @POST("community/reports")
    suspend fun createCommunityReport(@Body request: CommunityReportRequest): CommunityHealthReport

    @DELETE("community/reports/{id}")
    suspend fun deleteCommunityReport(@Path("id") id: Int)

    @GET("community/categories")
    suspend fun getCommunityCategories(): List<AlertCategoryInfo>

    @GET("community/sources")
    suspend fun getCommunitySources(): List<AlertSourceInfo>

    @GET("community/subscriptions")
    suspend fun getCommunitySubscriptions(): AlertSubscription

    @PUT("community/subscriptions")
    suspend fun updateCommunitySubscriptions(@Body request: CommunitySubscriptionRequest): AlertSubscription

    @POST("community/seed")
    suspend fun seedCommunityData(): Map<String, String>

    // ── User Role ──────────────────────────────────────────────

    @GET("users/roles/catalog")
    suspend fun getRoleCatalog(): List<RoleCategoryInfo>

    @GET("users/roles/categories")
    suspend fun getRoleCategories(): List<Map<String, Any>>

    @GET("users/roles/me")
    suspend fun getMyPersona(): UserPersonaSummary

    @GET("users/roles")
    suspend fun getMyRoles(): List<RoleAssignment>

    @POST("users/roles")
    suspend fun addRole(@Body request: RoleAssignmentRequest): RoleAssignment

    @DELETE("users/roles/{id}")
    suspend fun removeRole(@Path("id") id: Int)

    @PUT("users/roles/{id}/primary")
    suspend fun setPrimaryRole(@Path("id") id: Int): RoleAssignment

    @GET("users/roles/{id}/profile")
    suspend fun getProfessionalProfile(@Path("id") id: Int): ProfessionalProfile

    @PUT("users/roles/{id}/profile")
    suspend fun upsertProfessionalProfile(
        @Path("id") id: Int,
        @Body request: ProfessionalProfileRequest
    ): ProfessionalProfile

    // ── Health Data Sync ──────────────────────────────────────

    @POST("sync/connections")
    suspend fun createSyncConnection(@Body request: SyncConnectionRequest): SyncConnection

    @GET("sync/connections")
    suspend fun getSyncConnections(): List<SyncConnection>

    @PATCH("sync/connections/{platform}")
    suspend fun updateSyncConnection(
        @Path("platform") platform: String,
        @Body request: Map<String, Any?>
    ): SyncConnection

    @DELETE("sync/connections/{platform}")
    suspend fun deleteSyncConnection(@Path("platform") platform: String)

    @POST("sync/ingest")
    suspend fun syncIngest(@Body request: SyncBatchRequest): SyncBatchResponse

    @GET("sync/status/{platform}")
    suspend fun getSyncStatus(@Path("platform") platform: String): SyncStatusResponse

    // ── Calendar ──────────────────────────────────────────────

    @GET("calendar/")
    suspend fun getCalendarEvents(
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null,
        @Query("category") category: String? = null,
        @Query("status") status: String? = null,
        @Query("limit") limit: Int = 500
    ): List<CalendarEvent>

    @POST("calendar/")
    suspend fun createCalendarEvent(@Body request: CalendarEventRequest): CalendarEvent

    @GET("calendar/{id}")
    suspend fun getCalendarEvent(@Path("id") id: Int): CalendarEvent

    @PATCH("calendar/{id}")
    suspend fun updateCalendarEvent(
        @Path("id") id: Int,
        @Body request: CalendarEventUpdateRequest
    ): CalendarEvent

    @DELETE("calendar/{id}")
    suspend fun deleteCalendarEvent(@Path("id") id: Int)

    @PATCH("calendar/{id}/complete")
    suspend fun completeCalendarEvent(@Path("id") id: Int): CalendarEvent

    @GET("calendar/categories/list")
    suspend fun getCalendarCategories(): List<CalendarCategoryInfo>

    // ── Telehealth ──────────────────────────────────────────────

    @GET("telehealth/sessions")
    suspend fun getTelehealthSessions(
        @Query("status") status: String? = null,
        @Query("limit") limit: Int = 100
    ): List<TelehealthSession>

    @POST("telehealth/sessions")
    suspend fun createTelehealthSession(@Body request: TelehealthSessionRequest): TelehealthSession

    @GET("telehealth/sessions/{id}")
    suspend fun getTelehealthSession(@Path("id") id: Int): TelehealthSession

    @PATCH("telehealth/sessions/{id}")
    suspend fun updateTelehealthSession(
        @Path("id") id: Int, @Body request: TelehealthStatusRequest
    ): TelehealthSession

    @PATCH("telehealth/sessions/{id}/start")
    suspend fun startTelehealthSession(@Path("id") id: Int): TelehealthSession

    @PATCH("telehealth/sessions/{id}/end")
    suspend fun endTelehealthSession(@Path("id") id: Int): TelehealthSession

    @PATCH("telehealth/sessions/{id}/join")
    suspend fun joinTelehealthSession(@Path("id") id: Int): TelehealthParticipant

    @PATCH("telehealth/sessions/{id}/leave")
    suspend fun leaveTelehealthSession(@Path("id") id: Int): TelehealthParticipant

    @GET("telehealth/sessions/{id}/notes")
    suspend fun getTelehealthNotes(@Path("id") id: Int): List<TelehealthNote>

    @POST("telehealth/sessions/{id}/notes")
    suspend fun createTelehealthNote(
        @Path("id") id: Int, @Body request: TelehealthNoteRequest
    ): TelehealthNote

    @DELETE("telehealth/sessions/{id}/notes/{noteId}")
    suspend fun deleteTelehealthNote(@Path("id") id: Int, @Path("noteId") noteId: Int)

    @GET("telehealth/sessions/{id}/transcripts")
    suspend fun getTelehealthTranscripts(@Path("id") id: Int): List<TelehealthTranscript>

    @GET("telehealth/sessions/{id}/rtc-config")
    suspend fun getTelehealthRTCConfig(@Path("id") id: Int): TelehealthRTCConfig

    // ── Messaging ──

    @GET("messaging/conversations")
    suspend fun getConversations(@Query("conversation_type") type: String? = null): List<Conversation>

    @POST("messaging/conversations")
    suspend fun createConversation(@Body request: CreateConversationRequest): Conversation

    @GET("messaging/conversations/{id}")
    suspend fun getConversation(@Path("id") id: Int): Conversation

    @GET("messaging/conversations/{id}/messages")
    suspend fun getMessages(@Path("id") id: Int): List<ConversationMessage>

    @POST("messaging/conversations/{id}/messages")
    suspend fun sendMessage(@Path("id") id: Int, @Body request: SendMessageRequest): ConversationMessage

    @POST("messaging/conversations/{id}/read")
    suspend fun markConversationRead(@Path("id") id: Int): Map<String, String>

    // ── Community Feed ──

    @GET("messaging/feed")
    suspend fun getFeed(@Query("topic") topic: String? = null): List<CommunityPost>

    @POST("messaging/feed")
    suspend fun createPost(@Body request: CreatePostRequest): CommunityPost

    @GET("messaging/feed/{id}")
    suspend fun getPost(@Path("id") id: Int): CommunityPost

    @GET("messaging/feed/{id}/replies")
    suspend fun getReplies(@Path("id") id: Int): List<PostReply>

    @POST("messaging/feed/{id}/replies")
    suspend fun createReply(@Path("id") id: Int, @Body request: CreateReplyRequest): PostReply

    @POST("messaging/feed/{id}/like")
    suspend fun likePost(@Path("id") id: Int, @Query("reaction") reaction: String = "like"): LikeResponse

    @DELETE("messaging/feed/{id}/like")
    suspend fun unlikePost(@Path("id") id: Int)

    @POST("messaging/follow/{userId}")
    suspend fun followUser(@Path("userId") userId: Int): UserFollow

    @DELETE("messaging/follow/{userId}")
    suspend fun unfollowUser(@Path("userId") userId: Int)

    // ── Insurance ──

    @GET("insurance/regions")
    suspend fun getInsuranceRegions(): Map<String, List<InsuranceCountry>>

    @GET("insurance/providers/{countryCode}")
    suspend fun getInsuranceProviders(@Path("countryCode") countryCode: String): List<InsuranceProvider>

    @GET("insurance/")
    suspend fun getInsurancePlans(): List<InsurancePlan>

    @POST("insurance/")
    suspend fun createInsurancePlan(@Body body: InsuranceCreateRequest): InsurancePlan

    @DELETE("insurance/{id}")
    suspend fun deleteInsurancePlan(@Path("id") id: Int)

    @POST("insurance/{id}/set-primary")
    suspend fun setInsurancePrimary(@Path("id") id: Int): InsurancePlan

    // ── Physician Directory ──

    @GET("physicians/specialties")
    suspend fun getPhysicianSpecialties(): SpecialtyCategoriesResponse

    @GET("physicians/")
    suspend fun getPhysicians(
        @Query("q") q: String? = null,
        @Query("specialty") specialty: String? = null,
        @Query("specialty_category") specialtyCategory: String? = null,
        @Query("city") city: String? = null
    ): List<Physician>

    @GET("physicians/{id}")
    suspend fun getPhysician(@Path("id") id: Int): Physician

    @POST("physicians/")
    suspend fun createPhysician(@Body body: PhysicianCreateRequest): Physician

    @DELETE("physicians/{id}")
    suspend fun deletePhysician(@Path("id") id: Int)

    @GET("physicians/nearby")
    suspend fun getPhysiciansNearby(
        @Query("lat") lat: Double,
        @Query("lon") lon: Double,
        @Query("radius_km") radiusKm: Double = 50.0
    ): NearbySearchResponse

    @GET("physicians/saved/")
    suspend fun getSavedPhysicians(): List<SavedPhysician>

    @POST("physicians/saved/")
    suspend fun savePhysician(@Body body: SavePhysicianRequest): SavedPhysician

    @DELETE("physicians/saved/{id}")
    suspend fun unsavePhysician(@Path("id") id: Int)

    @GET("physicians/{id}/reviews")
    suspend fun getPhysicianReviews(@Path("id") id: Int): List<PhysicianReview>

    @POST("physicians/{id}/reviews")
    suspend fun createPhysicianReview(@Path("id") id: Int, @Body body: PhysicianReviewRequest): PhysicianReview

    // ── Lab Charts ────────────────────────────────────
    @GET("lab-charts/groups")
    suspend fun getLabChartGroups(): List<LabChartGroup>

    // ── Wellness ─────────────────────────────────────
    @GET("wellness/score")
    suspend fun getWellnessScore(): WellnessScore

    @GET("wellness/score/history")
    suspend fun getWellnessScoreHistory(@Query("days") days: Int = 30): List<WellnessScore>

    @GET("wellness/trends")
    suspend fun getHealthTrends(@Query("days") days: Int = 90): HealthTrendResponse

    @GET("wellness/recommendations")
    suspend fun getDailyRecommendations(): DailyRecommendationsResponse

    @GET("wellness/improvements")
    suspend fun getHealthImprovements(): HealthImprovementsResponse
    @GET("wellness/omega")
    suspend fun getHEBCSScore(): HEBCSScoreResponse

    @POST("wellness/whatif")
    suspend fun whatIfScenario(@Body request: WhatIfRequest): WhatIfResponse
    // ── Planners ─────────────────────────────────────
    @POST("planners/meal-plan")
    suspend fun createMealPlan(@Body request: MealPlanRequest): MealPlanResponse

    @GET("planners/meal-plans")
    suspend fun getMealPlans(): List<MealPlanResponse>

    @POST("planners/exercise-plan")
    suspend fun createExercisePlan(@Body request: ExercisePlanRequest): ExercisePlanResponse

    @GET("planners/exercise-plans")
    suspend fun getExercisePlans(): List<ExercisePlanResponse>

    // ── Image AI ─────────────────────────────────────
    @Multipart
    @POST("image-ai/nutrition-from-image")
    suspend fun nutritionFromImage(@Part file: MultipartBody.Part): NutritionFromImageResponse

    /** Teach ALAFIA the ground-truth foods for a photo (visual memory) —
     *  the same meal is recognized instantly in future photos. Ground truth
     *  can be a foods string or a recipe URL. */
    @POST("image-ai/label")
    suspend fun labelFoodImage(@Body body: FoodLabelRequest): NutritionFromImageResponse

    /** Analyze a recipe URL: structured recipe → per-serving nutrition
     *  (published nutrition is learned server-side under the dish name). */
    @POST("nutrition/recipe-analyze")
    suspend fun analyzeRecipeUrl(@Body body: RecipeAnalyzeRequest): RecipeAnalyzeResponse

    @Multipart
    @POST("image-ai/medication-from-image")
    suspend fun medicationFromImage(@Part file: MultipartBody.Part): MedicationFromImageResponse

    /** Analyze an elimination photo (stool / urine / vomit) → suggested log
     *  fields (Bristol scale, color, blood/mucus) + attention flags. Not a diagnosis. */
    @POST("image-ai/elimination-from-image")
    suspend fun eliminationFromImage(@Body body: EliminationImageRequest): EliminationFromImageResponse

    @POST("image-ai/verify-dosage")
    suspend fun verifyDosage(@Body request: DosageVerificationRequest): DosageVerificationResponse

    // ── PDF Tools ────────────────────────────────────
    @Multipart
    @POST("pdf/parse-lab-report")
    suspend fun parseLabReport(@Part file: MultipartBody.Part): LabReportParseResponse

    @POST("pdf/generate-flowsheet")
    suspend fun generateFlowsheet(@Body request: FlowsheetRequest): FlowsheetResponse

    // ── Peritoneal Dialysis ──────────────────────────
    @GET("pd/sessions")
    suspend fun getPDSessions(): List<PDSession>

    @POST("pd/sessions")
    suspend fun createPDSession(@Body request: PDSessionCreate): PDSession

    @DELETE("pd/sessions/{id}")
    suspend fun deletePDSession(@Path("id") id: Int)

    // ── Advanced Directives ──────────────────────────
    @GET("advanced-directives/")
    suspend fun getAdvancedDirective(): AdvancedDirective

    @POST("advanced-directives/")
    suspend fun createAdvancedDirective(@Body body: AdvancedDirective): AdvancedDirective

    @PUT("advanced-directives/")
    suspend fun updateAdvancedDirective(@Body body: AdvancedDirective): AdvancedDirective

    @DELETE("advanced-directives/")
    suspend fun deleteAdvancedDirective()

    // ── FDA Recalls (global: US food+drug, Canada, UK) ──
    @GET("fda-recalls/")
    suspend fun searchFDARecalls(
        @Query("search_term") searchTerm: String? = null,
        @Query("days") days: Int = 90,
        @Query("limit") limit: Int = 10,
        @Query("kind") kind: String = "both"
    ): FDARecallResponse

    @GET("fda-recalls/recent")
    suspend fun getRecentFDARecalls(@Query("kind") kind: String = "both"): FDARecallResponse

    // ── Facilities Directory ─────────────────────────
    @GET("facilities/")
    suspend fun getFacilities(
        @Query("search") search: String? = null,
        @Query("facility_type") facilityType: String? = null,
        @Query("limit") limit: Int = 50
    ): List<Facility>

    @GET("facilities/{id}/clinicians")
    suspend fun getFacilityClinicians(@Path("id") id: Int): List<Map<String, Any?>>

    // ── Disease Surveillance ─────────────────────────
    @GET("surveillance/diseases")
    suspend fun getSurveillanceDiseases(): List<SurveillanceDisease>

    @GET("surveillance/global")
    suspend fun getSurveillanceGlobal(
        @Query("disease") disease: String,
        @Query("days") days: Int = 90,
        @Query("view") view: String = "both"
    ): SurveillanceGlobal

    // ── Composite Weight Series ──────────────────────
    @GET("chart-dashboard/weight-series")
    suspend fun getWeightSeries(
        @Query("days") days: Int = 90,
        @Query("aggregation") aggregation: String = "daily"
    ): WeightSeriesResponse

    // ── Data Sharing ─────────────────────────────────
    @GET("data-sharing/grants")
    suspend fun getDataGrants(): List<DataGrant>

    @POST("data-sharing/grants")
    suspend fun createDataGrant(@Body body: DataGrantCreate): DataGrant

    @DELETE("data-sharing/grants/{id}")
    suspend fun deleteDataGrant(@Path("id") id: Int)

    @GET("data-sharing/types")
    suspend fun getDataSharingTypes(): List<String>

    @GET("data-sharing/invitations")
    suspend fun getDataShareInvitations(): List<DataShareInvitation>

    @POST("data-sharing/invitations")
    suspend fun createDataShareInvitation(@Body body: DataShareInvitationCreate): DataShareInvitation

    @POST("data-sharing/invitations/{id}/accept")
    suspend fun acceptDataShareInvitation(@Path("id") id: Int): DataShareInvitation

    @POST("data-sharing/invitations/{id}/decline")
    suspend fun declineDataShareInvitation(@Path("id") id: Int): DataShareInvitation

    // ── Clinician Dashboard ──────────────────────────
    @GET("clinician-dashboard/")
    suspend fun getClinicianDashboard(): ClinicianDashboardResponse

    // ── Chart Dashboard ──────────────────────────────
    @GET("chart-dashboard/datasets")
    suspend fun getChartDatasets(): Map<String, List<ChartDatasetInfo>>

    @GET("chart-dashboard/data")
    suspend fun getChartData(
        @Query("datasets") datasets: String,
        @Query("days") days: Int = 90,
        @Query("aggregation") aggregation: String = "daily"
    ): Map<String, ChartDataSeries>

    @GET("chart-dashboard/summary")
    suspend fun getChartSummary(
        @Query("dataset") dataset: String,
        @Query("days") days: Int = 90
    ): ChartSummaryResponse

    // ── Pharmacy ─────────────────────────────────────

    @GET("pharmacy/prescriptions")
    suspend fun getPrescriptions(): List<PharmacyPrescription>

    @POST("pharmacy/prescriptions")
    suspend fun createPrescription(@Body request: PrescriptionCreateRequest): PharmacyPrescription

    @GET("pharmacy/prescriptions/{id}")
    suspend fun getPrescription(@Path("id") id: Int): PharmacyPrescription

    @PATCH("pharmacy/prescriptions/{id}")
    suspend fun updatePrescription(
        @Path("id") id: Int,
        @Body request: Map<String, Any?>
    ): PharmacyPrescription

    @DELETE("pharmacy/prescriptions/{id}")
    suspend fun deletePrescription(@Path("id") id: Int)

    @GET("pharmacy/queue")
    suspend fun getPharmacyQueue(): List<PharmacyPrescription>

    @GET("pharmacy/dispenses")
    suspend fun getDispenses(): List<PharmacyDispense>

    @POST("pharmacy/dispenses")
    suspend fun createDispense(@Body request: DispenseCreateRequest): PharmacyDispense

    @PATCH("pharmacy/dispenses/{id}")
    suspend fun updateDispense(
        @Path("id") id: Int,
        @Body request: Map<String, Any?>
    ): PharmacyDispense

    @GET("pharmacy/adherence")
    suspend fun getAdherenceLogs(): List<PharmacyAdherenceLog>

    @POST("pharmacy/adherence")
    suspend fun createAdherenceLog(@Body request: AdherenceLogCreateRequest): PharmacyAdherenceLog

    @GET("pharmacy/adherence/report")
    suspend fun getAdherenceReport(
        @Query("prescription_id") prescriptionId: Int? = null
    ): PharmacyAdherenceReport

    @GET("pharmacy/schedules")
    suspend fun getPharmacySchedules(): List<PharmacySchedule>

    @POST("pharmacy/schedules")
    suspend fun createPharmacySchedule(@Body request: ScheduleCreateRequest): PharmacySchedule

    @PATCH("pharmacy/schedules/{id}")
    suspend fun updatePharmacySchedule(
        @Path("id") id: Int,
        @Body request: Map<String, Any?>
    ): PharmacySchedule

    @DELETE("pharmacy/schedules/{id}")
    suspend fun deletePharmacySchedule(@Path("id") id: Int)

    @GET("pharmacy/refills")
    suspend fun getRefillRequests(): List<PharmacyRefillRequest>

    @POST("pharmacy/refills")
    suspend fun createRefillRequest(@Body request: RefillCreateRequest): PharmacyRefillRequest

    @PATCH("pharmacy/refills/{id}")
    suspend fun updateRefillRequest(
        @Path("id") id: Int,
        @Body request: Map<String, Any?>
    ): PharmacyRefillRequest

    @GET("pharmacy/impact/{rxId}")
    suspend fun getMedicationImpact(@Path("rxId") rxId: Int): MedicationImpactResponse

    // ── Pantry ──────────────────────────────────────────

    @GET("pantry")
    suspend fun getPantryItems(): List<PantryItem>

    @POST("pantry")
    suspend fun createPantryItem(@Body request: PantryItemCreate): PantryItem

    @PUT("pantry/{id}")
    suspend fun updatePantryItem(@Path("id") id: Int, @Body request: PantryItemCreate): PantryItem

    @DELETE("pantry/{id}")
    suspend fun deletePantryItem(@Path("id") id: Int)

    // Elimination Endpoints
    @GET("elimination/bowel")
    suspend fun getBowelMovements(
        @Query("limit") limit: Int = 100,
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null
    ): List<BowelMovement>

    @POST("elimination/bowel")
    suspend fun createBowelMovement(@Body request: BowelMovementRequest): BowelMovement

    @DELETE("elimination/bowel/{id}")
    suspend fun deleteBowelMovement(@Path("id") id: Int)

    @GET("elimination/vomiting")
    suspend fun getVomitingLogs(
        @Query("limit") limit: Int = 100,
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null
    ): List<VomitingLog>

    @POST("elimination/vomiting")
    suspend fun createVomitingLog(@Body request: VomitingLogRequest): VomitingLog

    @DELETE("elimination/vomiting/{id}")
    suspend fun deleteVomitingLog(@Path("id") id: Int)

    @GET("elimination/urination")
    suspend fun getUrinationLogs(
        @Query("limit") limit: Int = 100,
        @Query("start_date") startDate: String? = null,
        @Query("end_date") endDate: String? = null
    ): List<UrinationLog>

    @POST("elimination/urination")
    suspend fun createUrinationLog(@Body request: UrinationLogRequest): UrinationLog

    @DELETE("elimination/urination/{id}")
    suspend fun deleteUrinationLog(@Path("id") id: Int)

    // ── Flowsheet Lifecycle ─────────────────────────────────────────────────

    @POST("chronic/therapy-sessions/{id}/submit")
    suspend fun submitFlowsheet(@Path("id") sessionId: Int): FlowsheetActionResponse

    @POST("chronic/therapy-sessions/{id}/sign")
    suspend fun signFlowsheet(
        @Path("id") sessionId: Int,
        @Body request: FlowsheetSignRequest
    ): FlowsheetActionResponse

    @POST("chronic/therapy-sessions/{id}/countersign")
    suspend fun countersignFlowsheet(
        @Path("id") sessionId: Int,
        @Body request: FlowsheetSignRequest
    ): FlowsheetActionResponse

    @POST("chronic/therapy-sessions/{id}/review")
    suspend fun reviewFlowsheet(@Path("id") sessionId: Int): FlowsheetActionResponse

    @POST("chronic/therapy-sessions/{id}/lock")
    suspend fun lockFlowsheet(@Path("id") sessionId: Int): FlowsheetActionResponse

    // ── Clinical Notes ──────────────────────────────────────────────────────

    @GET("chronic/therapy-sessions/{id}/notes")
    suspend fun getClinicalNotes(@Path("id") sessionId: Int): List<ClinicalNote>

    @POST("chronic/therapy-sessions/{id}/notes")
    suspend fun createClinicalNote(
        @Path("id") sessionId: Int,
        @Body note: ClinicalNoteCreate
    ): ClinicalNote

    // ── Blockchain ──────────────────────────────────────────────────────────

    @GET("blockchain/verify/on-chain/{blockUid}")
    suspend fun verifyOnChainAnchor(@Path("blockUid") blockUid: String): BlockchainVerifyResponse

    // ── System ID ───────────────────────────────────────────────────────────

    @GET("auth/me/system-id")
    suspend fun getSystemId(): SystemIdResponse

    // ── Subscription / Billing (ALAFIA Plus) ──────────────────────────────────

    @GET("subscription/plans")
    suspend fun getSubscriptionPlans(): SubscriptionPlans

    @GET("subscription/status")
    suspend fun getSubscriptionStatus(): SubscriptionStatus

    /** Verify a Google Play purchase server-side; the backend records the
     *  entitlement and returns the updated status. */
    @POST("subscription/verify/google")
    suspend fun verifyGooglePurchase(@Body request: GoogleVerifyRequest): SubscriptionStatus
}
