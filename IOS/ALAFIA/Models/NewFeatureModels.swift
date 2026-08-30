import Foundation

// MARK: - Lab Charts

struct LabChartPoint: Codable {
    let date: String
    let value: Double
    let referenceLow: Double?
    let referenceHigh: Double?

    enum CodingKeys: String, CodingKey {
        case date, value
        case referenceLow = "reference_low"
        case referenceHigh = "reference_high"
    }
}

struct LabChartSeries: Codable {
    let testName: String
    let unit: String?
    let data: [LabChartPoint]

    enum CodingKeys: String, CodingKey {
        case testName = "test_name"
        case unit, data
    }
}

struct LabChartGroup: Codable {
    let name: String
    let series: [LabChartSeries]

    enum CodingKeys: String, CodingKey {
        case name = "group_name"
        case series
    }
}

struct LabChartGroupsResponse: Codable {
    let groups: [LabChartGroup]
}

// MARK: - Wellness

struct WellnessScore: Codable, Identifiable {
    let id: Int
    let userId: Int
    let scoreDate: String
    // Every score is OPTIONAL because the API has always allowed null, and now
    // returns it deliberately: a domain with no data is UNKNOWN, not zero.
    // Declared non-null, one null failed the decode for the whole response —
    // the score screen would have gone blank rather than saying what was
    // missing. Match the model to the schema, not to the rows you happened to
    // see (canon 3aj).
    let overallScore: Double?
    let nutritionScore: Double?
    let fitnessScore: Double?
    let sleepScore: Double?
    let moodScore: Double?
    let vitalsScore: Double?
    let medicationAdherenceScore: Double?
    /// How much of the intended picture had data behind it (0-1).
    let confidence: Double?
    /// Domains excluded from the score for lack of data.
    let componentsUnknown: [String]?
    let explanation: String?
    let recommendations: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case scoreDate = "score_date"
        case overallScore = "overall_score"
        case nutritionScore = "nutrition_score"
        case fitnessScore = "fitness_score"
        case sleepScore = "sleep_score"
        case moodScore = "mood_score"
        case vitalsScore = "vitals_score"
        case medicationAdherenceScore = "medication_adherence_score"
        case confidence
        case componentsUnknown = "components_unknown"
        case explanation, recommendations
        case createdAt = "created_at"
    }
}

struct TrendDataPoint: Codable {
    let date: String
    let value: Double
    let label: String?
}

struct TrendStream: Codable {
    let name: String
    let data: [TrendDataPoint]
    let trend: String?
}

struct HealthTrendResponse: Codable {
    let overallSummary: String?
    let streams: [TrendStream]
    let correlations: [String]?
    let suggestions: [String]?

    enum CodingKeys: String, CodingKey {
        case overallSummary = "overall_summary"
        case streams, correlations, suggestions
    }
}

struct RecommendationItem: Codable {
    let category: String
    let title: String
    let description: String
    let priority: String
    let action: String?
}

struct DailyRecommendationsResponse: Codable {
    let date: String
    let recommendations: [RecommendationItem]
}

struct HealthImprovementsResponse: Codable {
    let summary: String?
    let wellnessScore: Double?
    let nutritionImprovements: [String]?
    let fitnessImprovements: [String]?
    let sleepImprovements: [String]?
    let moodImprovements: [String]?
    let medicalImprovements: [String]?

    enum CodingKeys: String, CodingKey {
        case summary
        case wellnessScore = "wellness_score"
        case nutritionImprovements = "nutrition_improvements"
        case fitnessImprovements = "fitness_improvements"
        case sleepImprovements = "sleep_improvements"
        case moodImprovements = "mood_improvements"
        case medicalImprovements = "medical_improvements"
    }
}

// MARK: - Planners

struct MealItem: Codable {
    let name: String
    let calories: Int?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
    let description: String?

    enum CodingKeys: String, CodingKey {
        case name, calories, description
        case proteinG = "protein_g"
        case carbsG = "carbs_g"
        case fatG = "fat_g"
    }
}

struct DayMeals: Codable {
    let breakfast: [MealItem]?
    let lunch: [MealItem]?
    let dinner: [MealItem]?
    let snacks: [MealItem]?
}

struct MealPlanResponse: Codable, Identifiable {
    let id: Int
    let planName: String
    let dietaryPattern: String?
    let startDate: String?
    let endDate: String?
    let planData: [String: DayMeals]?
    let shoppingList: [String]?
    let advice: String?
    let totalDailyCalories: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case planName = "plan_name"
        case dietaryPattern = "dietary_pattern"
        case startDate = "start_date"
        case endDate = "end_date"
        case planData = "plan_data"
        case shoppingList = "shopping_list"
        case advice
        case totalDailyCalories = "total_daily_calories"
    }
}

struct MealPlanRequest: Codable {
    let dietaryPattern: String
    let dailyCalorieTarget: Int?
    let allergies: String?
    let preferences: String?

    enum CodingKeys: String, CodingKey {
        case dietaryPattern = "dietary_pattern"
        case dailyCalorieTarget = "daily_calorie_target"
        case allergies, preferences
    }
}

struct ExerciseItem: Codable {
    let name: String
    let durationMinutes: Int?
    let description: String?
    let muscleGroups: [String]?
    let sets: Int?
    let reps: Int?

    enum CodingKeys: String, CodingKey {
        case name, description, sets, reps
        case durationMinutes = "duration_minutes"
        case muscleGroups = "muscle_groups"
    }
}

struct ExercisePlanResponse: Codable, Identifiable {
    let id: Int
    let planName: String
    let fitnessLevel: String?
    let startDate: String?
    let endDate: String?
    let planData: [String: [ExerciseItem]]?
    let advice: String?
    let weeklyMinutesTarget: Int?

    enum CodingKeys: String, CodingKey {
        case id, advice
        case planName = "plan_name"
        case fitnessLevel = "fitness_level"
        case startDate = "start_date"
        case endDate = "end_date"
        case planData = "plan_data"
        case weeklyMinutesTarget = "weekly_minutes_target"
    }
}

struct ExercisePlanRequest: Codable {
    let fitnessLevel: String
    let weeklyMinutesTarget: Int?
    let limitations: String?

    enum CodingKeys: String, CodingKey {
        case fitnessLevel = "fitness_level"
        case weeklyMinutesTarget = "weekly_minutes_target"
        case limitations
    }
}

// MARK: - Image AI

struct FoodItemResult: Codable {
    let name: String
    let calories: Int?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
    let servingSize: String?

    enum CodingKeys: String, CodingKey {
        case name, calories
        case proteinG = "protein_g"
        case carbsG = "carbs_g"
        case fatG = "fat_g"
        case servingSize = "serving_size"
    }
}

struct NutritionFromImageResponse: Codable {
    let foodItems: [FoodItemResult]
    let totalCalories: Int?
    let totalProteinG: Double?
    let totalCarbsG: Double?
    let totalFatG: Double?
    let confidenceNote: String?

    enum CodingKeys: String, CodingKey {
        case foodItems = "food_items"
        case totalCalories = "total_calories"
        case totalProteinG = "total_protein_g"
        case totalCarbsG = "total_carbs_g"
        case totalFatG = "total_fat_g"
        case confidenceNote = "confidence_note"
    }
}

struct MedicationImageField: Codable {
    let label: String?
    let value: String?
}

struct MedicationFromImageResponse: Codable {
    let medicationName: String?
    let dosage: String?
    let instructions: String?
    let ndcCode: String?
    let manufacturer: String?
    let fields: [MedicationImageField]
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case medicationName = "medication_name"
        case dosage, instructions, manufacturer, fields, notes
        case ndcCode = "ndc_code"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        medicationName = try c.decodeIfPresent(String.self, forKey: .medicationName)
        dosage = try c.decodeIfPresent(String.self, forKey: .dosage)
        instructions = try c.decodeIfPresent(String.self, forKey: .instructions)
        ndcCode = try c.decodeIfPresent(String.self, forKey: .ndcCode)
        manufacturer = try c.decodeIfPresent(String.self, forKey: .manufacturer)
        fields = try c.decodeIfPresent([MedicationImageField].self, forKey: .fields) ?? []
        notes = try c.decodeIfPresent(String.self, forKey: .notes)
    }
}

struct DosageVerificationRequest: Codable {
    let medicationName: String
    let dosage: String
    let frequency: String?

    enum CodingKeys: String, CodingKey {
        case medicationName = "medication_name"
        case dosage, frequency
    }
}

struct DosageVerificationResponse: Codable {
    let medicationName: String?
    let dosage: String?
    let isTypical: Bool?
    let feedback: String?
    let typicalRange: String?
    let precautions: [String]

    enum CodingKeys: String, CodingKey {
        case medicationName = "medication_name"
        case dosage, feedback, precautions
        case isTypical = "is_typical"
        case typicalRange = "typical_range"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        medicationName = try c.decodeIfPresent(String.self, forKey: .medicationName)
        dosage = try c.decodeIfPresent(String.self, forKey: .dosage)
        isTypical = try c.decodeIfPresent(Bool.self, forKey: .isTypical)
        feedback = try c.decodeIfPresent(String.self, forKey: .feedback)
        typicalRange = try c.decodeIfPresent(String.self, forKey: .typicalRange)
        precautions = try c.decodeIfPresent([String].self, forKey: .precautions) ?? []
    }
}

// MARK: - PDF Tools

/// One staged reading. `itemId` is what the confirm call selects on, so a
/// patient can import some rows and leave others.
struct LabReportItem: Codable, Identifiable {
    let testName: String?
    let value: String?
    let unit: String?
    let referenceRange: String?
    let isAbnormal: Bool?
    let category: String?
    let testDate: String?
    let confidence: Double?
    /// What the document literally said, kept so a wrong normalization is visible.
    let sourceLabel: String?
    /// "new" | "duplicate" | "conflict"
    let dedupeStatus: String?
    let itemId: Int?
    let accepted: Bool?
    let note: String?

    var id: Int { itemId ?? 0 }
    var isDuplicate: Bool { dedupeStatus == "duplicate" }
    var isConflict: Bool { dedupeStatus == "conflict" }

    enum CodingKeys: String, CodingKey {
        case value, unit, category, note, confidence
        case testName = "test_name"
        case referenceRange = "reference_range"
        case isAbnormal = "is_abnormal"
        case testDate = "test_date"
        case sourceLabel = "source_label"
        case dedupeStatus = "dedupe_status"
        case itemId = "item_id"
        case accepted
    }
}

struct LabReportParseResponse: Codable {
    let patientName: String?
    let reportDate: String?
    let labName: String?
    let orderingPhysician: String?
    let items: [LabReportItem]?
    let rawTextPreview: String?
    let parsingNotes: [String]?

    // Import + classification context.
    let importId: Int?
    let docType: String?
    let docTypeConfidence: Double?
    let confidence: Double?
    /// nil when this document type can be read but not imported yet.
    let targetTable: String?
    let pageCount: Int?
    /// Set when nothing could be read. Must be shown — an empty item list and a
    /// failed parse mean opposite things.
    let error: String?
    let alreadyImported: Bool?

    var canImport: Bool { targetTable != nil && importId != nil }

    enum CodingKeys: String, CodingKey {
        case items, error, confidence
        case patientName = "patient_name"
        case reportDate = "report_date"
        case labName = "lab_name"
        case orderingPhysician = "ordering_physician"
        case rawTextPreview = "raw_text_preview"
        case parsingNotes = "parsing_notes"
        case importId = "import_id"
        case docType = "doc_type"
        case docTypeConfidence = "doc_type_confidence"
        case targetTable = "target_table"
        case pageCount = "page_count"
        case alreadyImported = "already_imported"
    }
}

struct ConfirmImportResponse: Codable {
    let importId: Int?
    let status: String?
    let imported: [String: Int]?
    let totalImported: Int?
    let message: String?

    enum CodingKeys: String, CodingKey {
        case status, imported, message
        case importId = "import_id"
        case totalImported = "total_imported"
    }
}

struct FlowsheetResponse: Codable {
    let title: String?
    let generatedAt: String?
    let content: String?
    let sessionCount: Int?
    let pdfUrl: String?

    enum CodingKeys: String, CodingKey {
        case title, content
        case generatedAt = "generated_at"
        case sessionCount = "session_count"
        case pdfUrl = "pdf_url"
    }
}

// MARK: - Peritoneal Dialysis

struct PDExchange: Codable, Identifiable {
    let id: Int?
    let exchangeNumber: Int
    let startTime: String?
    let drainStartTime: String?
    let drainEndTime: String?
    let fillEndTime: String?
    let solutionType: String?
    let inflowVolumeMl: Int?
    let outflowVolumeMl: Int?
    let ufMl: Int?
    let dwellTimeMinutes: Int?
    let effluentClarity: String?
    let effluentColor: String?

    enum CodingKeys: String, CodingKey {
        case id
        case exchangeNumber = "exchange_number"
        case startTime = "start_time"
        case drainStartTime = "drain_start_time"
        case drainEndTime = "drain_end_time"
        case fillEndTime = "fill_end_time"
        case solutionType = "solution_type"
        case inflowVolumeMl = "inflow_volume_ml"
        case outflowVolumeMl = "outflow_volume_ml"
        case ufMl = "uf_ml"
        case dwellTimeMinutes = "dwell_time_minutes"
        case effluentClarity = "effluent_clarity"
        case effluentColor = "effluent_color"
    }
}

struct PDSession: Codable, Identifiable {
    let id: Int
    let userId: Int?
    let conditionId: Int?
    let sessionDate: String
    let modality: String
    let preWeightKg: Double?
    let postWeightKg: Double?
    let preBpSystolic: Int?
    let preBpDiastolic: Int?
    let postBpSystolic: Int?
    let postBpDiastolic: Int?
    let temperatureC: Double?
    let exitSiteStatus: String?
    let machineType: String?
    let totalVolumeMl: Int?
    let fillVolumeMl: Int?
    let cycles: Int?
    let therapyTimeMinutes: Int?
    let lastFillMl: Int?
    let totalUfMl: Int?
    let complications: String?
    let notes: String?
    let exchanges: [PDExchange]?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, modality, cycles, complications, notes, exchanges
        case userId = "user_id"
        case conditionId = "condition_id"
        case sessionDate = "session_date"
        case preWeightKg = "pre_weight_kg"
        case postWeightKg = "post_weight_kg"
        case preBpSystolic = "pre_bp_systolic"
        case preBpDiastolic = "pre_bp_diastolic"
        case postBpSystolic = "post_bp_systolic"
        case postBpDiastolic = "post_bp_diastolic"
        case temperatureC = "temperature_c"
        case exitSiteStatus = "exit_site_status"
        case machineType = "machine_type"
        case totalVolumeMl = "total_volume_ml"
        case fillVolumeMl = "fill_volume_ml"
        case therapyTimeMinutes = "therapy_time_minutes"
        case lastFillMl = "last_fill_ml"
        case totalUfMl = "total_uf_ml"
        case createdAt = "created_at"
    }
}

struct PDSessionCreate: Codable {
    let conditionId: Int?
    let sessionDate: String
    let modality: String
    let preWeightKg: Double?
    let postWeightKg: Double?
    let preBpSystolic: Int?
    let preBpDiastolic: Int?
    let postBpSystolic: Int?
    let postBpDiastolic: Int?
    let temperatureC: Double?
    let exitSiteStatus: String?
    let machineType: String?
    let totalVolumeMl: Int?
    let fillVolumeMl: Int?
    let cycles: Int?
    let therapyTimeMinutes: Int?
    let lastFillMl: Int?
    let complications: String?
    let notes: String?
    let exchanges: [PDExchange]?

    enum CodingKeys: String, CodingKey {
        case modality, cycles, complications, notes, exchanges
        case conditionId = "condition_id"
        case sessionDate = "session_date"
        case preWeightKg = "pre_weight_kg"
        case postWeightKg = "post_weight_kg"
        case preBpSystolic = "pre_bp_systolic"
        case preBpDiastolic = "pre_bp_diastolic"
        case postBpSystolic = "post_bp_systolic"
        case postBpDiastolic = "post_bp_diastolic"
        case temperatureC = "temperature_c"
        case exitSiteStatus = "exit_site_status"
        case machineType = "machine_type"
        case totalVolumeMl = "total_volume_ml"
        case fillVolumeMl = "fill_volume_ml"
        case therapyTimeMinutes = "therapy_time_minutes"
        case lastFillMl = "last_fill_ml"
    }
}

// MARK: - Advanced Directives

struct AdvancedDirective: Codable, Identifiable {
    let id: Int?
    let userId: Int?
    let primaryAgentName: String?
    let primaryAgentRelationship: String?
    let primaryAgentPhone: String?
    let primaryAgentEmail: String?
    let primaryAgentAddress: String?
    let alternateAgentName: String?
    let alternateAgentRelationship: String?
    let alternateAgentPhone: String?
    let alternateAgentEmail: String?
    let alternateAgentAddress: String?
    let organDonation: String?
    let organDonationPreferences: String?
    let lifeSupport: String?
    let cpr: String?
    let ventilator: String?
    let feedingTube: String?
    let dialysisDirective: String?
    let bloodTransfusion: String?
    let documentSigned: Bool?
    let documentDate: String?
    let witnessName: String?
    let notarized: Bool?
    let documentLocation: String?
    let additionalInstructions: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, cpr, ventilator, notarized
        case userId = "user_id"
        case primaryAgentName = "primary_agent_name"
        case primaryAgentRelationship = "primary_agent_relationship"
        case primaryAgentPhone = "primary_agent_phone"
        case primaryAgentEmail = "primary_agent_email"
        case primaryAgentAddress = "primary_agent_address"
        case alternateAgentName = "alternate_agent_name"
        case alternateAgentRelationship = "alternate_agent_relationship"
        case alternateAgentPhone = "alternate_agent_phone"
        case alternateAgentEmail = "alternate_agent_email"
        case alternateAgentAddress = "alternate_agent_address"
        case organDonation = "organ_donation"
        case organDonationPreferences = "organ_donation_preferences"
        case lifeSupport = "life_support"
        case feedingTube = "feeding_tube"
        case dialysisDirective = "dialysis_directive"
        case bloodTransfusion = "blood_transfusion"
        case documentSigned = "document_signed"
        case documentDate = "document_date"
        case witnessName = "witness_name"
        case documentLocation = "document_location"
        case additionalInstructions = "additional_instructions"
        case createdAt = "created_at"
    }
}

// MARK: - FDA Recalls

struct FDARecallItem: Codable {
    // Global recalls schema (US openFDA food+drug, Health Canada, UK FSA)
    let productType: String?          // "food" | "drug"
    let source: String?               // issuing authority
    let url: String?                  // official notice link
    let recallNumber: String?
    let productDescription: String?
    let reason: String?
    let classification: String?
    let status: String?
    let recallInitiationDate: String?
    let reportDate: String?
    let recallingFirm: String?
    let city: String?
    let state: String?
    let country: String?
    let distribution: String?
    let voluntaryMandated: String?
    let states: [String]?             // US state codes reached
    let countries: [String]?          // ISO-2 countries reached
    let nationwide: Bool?

    enum CodingKeys: String, CodingKey {
        case reason, classification, status, city, state, country, source, url
        case distribution, states, countries, nationwide
        case productType = "product_type"
        case recallNumber = "recall_number"
        case productDescription = "product_description"
        case recallInitiationDate = "recall_initiation_date"
        case reportDate = "report_date"
        case recallingFirm = "recalling_firm"
        case voluntaryMandated = "voluntary_mandated"
    }
}

struct FDARecallResponse: Codable {
    let total: Int
    let results: [FDARecallItem]
}

// MARK: - Recipe URL Analysis (third meal input: URL / description / photo)

struct RecipeAnalyzeRequest: Codable {
    let url: String
    var servings: Int?
}

struct RecipeAnalyzeResponse: Codable {
    let name: String
    let url: String
    let servings: Int
    let ingredients: [String]
    let perServing: [String: Double]
    let total: [String: Double]
    let totalWeightG: Double
    let source: String        // "published" | "estimated"
    let learned: Bool

    enum CodingKeys: String, CodingKey {
        case name, url, servings, ingredients, total, source, learned
        case perServing = "per_serving"
        case totalWeightG = "total_weight_g"
    }
}

// MARK: - Elimination Photo Analysis (stool / urine / vomit)

struct EliminationSuggested: Codable {
    let color: String?
    let bristolScale: Int?
    let consistency: String?
    let bloodPresent: Bool?
    let mucusPresent: Bool?

    enum CodingKeys: String, CodingKey {
        case color, consistency
        case bristolScale = "bristol_scale"
        case bloodPresent = "blood_present"
        case mucusPresent = "mucus_present"
    }
}

struct EliminationFromImageResponse: Codable {
    let eventType: String
    let description: String
    let suggested: EliminationSuggested
    let flags: [String]
    let disclaimer: String?

    enum CodingKeys: String, CodingKey {
        case description, suggested, flags, disclaimer
        case eventType = "event_type"
    }
}

// MARK: - Facilities Directory

struct Facility: Codable, Identifiable {
    let id: Int
    let name: String
    let facilityType: String
    let phone: String?
    let website: String?
    let addressLine1: String?
    let city: String?
    let stateProvince: String?
    let postalCode: String?
    let country: String?
    let latitude: Double?
    let longitude: Double?

    enum CodingKeys: String, CodingKey {
        case id, name, phone, website, city, country, latitude, longitude
        case facilityType = "facility_type"
        case addressLine1 = "address_line1"
        case stateProvince = "state_province"
        case postalCode = "postal_code"
    }
}

// MARK: - Disease Surveillance

struct SurveillanceDisease: Codable, Identifiable {
    let id: String
    let label: String
    let icon: String
    let category: String
}

struct SurveillanceCountry: Codable, Identifiable {
    var id: String { iso2 }
    let iso2: String
    let name: String
    let region: String?
    let outward: Double?         // WHO indicator value
    let outwardYear: Int?
    let inward: Int              // ALAFIA patient symptom activity

    enum CodingKeys: String, CodingKey {
        case iso2, name, region, outward, inward
        case outwardYear = "outward_year"
    }
}

struct SurveillanceGlobal: Codable {
    let disease: SurveillanceDisease
    let days: Int
    let countries: [SurveillanceCountry]
    let inwardTotal: Int

    enum CodingKeys: String, CodingKey {
        case disease, days, countries
        case inwardTotal = "inward_total"
    }
}

// MARK: - Composite Weight Series

struct WeightSeriesPoint: Codable, Identifiable {
    var id: String { date }
    let date: String
    let value: Double
    let min: Double
    let max: Double
    let count: Int
    let rolling7d: Double
    let sources: [String: Int]

    enum CodingKeys: String, CodingKey {
        case date, value, min, max, count, sources
        case rolling7d = "rolling_7d"
    }
}

struct WeightSeriesSummary: Codable {
    let count: Int
    let avg: Double?
    let stddev: Double?
    let min: Double?
    let max: Double?
    let sources: [String: Int]
    let trend: String
    let dryWeightKg: Double?
    let profileCurrentWeightKg: Double?
    let profileTargetWeightKg: Double?

    enum CodingKeys: String, CodingKey {
        case count, avg, stddev, min, max, sources, trend
        case dryWeightKg = "dry_weight_kg"
        case profileCurrentWeightKg = "profile_current_weight_kg"
        case profileTargetWeightKg = "profile_target_weight_kg"
    }
}

struct WeightSeriesResponse: Codable {
    let label: String
    let unit: String
    let days: Int
    let points: [WeightSeriesPoint]
    let summary: WeightSeriesSummary
}

// MARK: - Data Sharing

struct DataGrant: Codable, Identifiable {
    let id: Int
    let ownerUserId: Int?
    let granteeUserId: Int?
    let granteeEmail: String?
    let granteeDisplayName: String?
    let dataType: String
    let canRead: Bool
    let canWrite: Bool
    let isActive: Bool
    let expiresAt: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case ownerUserId = "owner_user_id"
        case granteeUserId = "grantee_user_id"
        case granteeEmail = "grantee_email"
        case granteeDisplayName = "grantee_display_name"
        case dataType = "data_type"
        case canRead = "can_read"
        case canWrite = "can_write"
        case isActive = "is_active"
        case expiresAt = "expires_at"
        case createdAt = "created_at"
    }
}

struct DataGrantCreate: Codable {
    let granteeEmail: String
    let dataType: String
    let canRead: Bool
    let canWrite: Bool
    let expiresAt: String?

    enum CodingKeys: String, CodingKey {
        case granteeEmail = "grantee_email"
        case dataType = "data_type"
        case canRead = "can_read"
        case canWrite = "can_write"
        case expiresAt = "expires_at"
    }
}

struct DataShareInvitation: Codable, Identifiable {
    let id: Int
    let senderUserId: Int?
    let recipientEmail: String?
    let recipientUserId: Int?
    let dataTypes: [String]?
    let message: String?
    let status: String
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, message, status
        case senderUserId = "sender_user_id"
        case recipientEmail = "recipient_email"
        case recipientUserId = "recipient_user_id"
        case dataTypes = "data_types"
        case createdAt = "created_at"
    }
}

// MARK: - Clinician Dashboard

struct ClinicianVitals: Codable {
    let date: String?
    let bp: String?
    let hr: Int?
    let weightKg: Double?

    enum CodingKeys: String, CodingKey {
        case date, bp, hr
        case weightKg = "weight_kg"
    }
}

struct ClinicianMood: Codable {
    let date: String?
    let score: Int?
}

struct ClinicianLabItem: Codable, Identifiable {
    var id: String { (name ?? "") + (date ?? UUID().uuidString) }
    let name: String?
    let value: String?
    let unit: String?
    let date: String?
    /// Optional so a backend that predates the flag still decodes.
    let isAbnormal: Bool?

    enum CodingKeys: String, CodingKey {
        case name, value, unit, date
        case isAbnormal = "is_abnormal"
    }
}

struct PatientSummary: Codable, Identifiable {
    var id: Int { userId }
    let userId: Int
    let fullName: String
    let email: String?
    let latestVitals: ClinicianVitals?
    let latestMood: ClinicianMood?
    let latestLabs: [ClinicianLabItem]?
    let conditions: [String]?
    let medications: [String]?
    let permissions: [String]?
    let lastActivity: String?

    enum CodingKeys: String, CodingKey {
        case email, conditions, medications, permissions
        case userId = "user_id"
        case fullName = "full_name"
        case latestVitals = "latest_vitals"
        case latestMood = "latest_mood"
        case latestLabs = "latest_labs"
        case lastActivity = "last_activity"
    }
}

struct ClinicianDashboardResponse: Codable {
    let role: String?
    let patientCount: Int?
    let patients: [PatientSummary]

    enum CodingKeys: String, CodingKey {
        case role, patients
        case patientCount = "patient_count"
    }
}

// MARK: - Intradialytic Reading

struct IntradialyticReading: Codable, Identifiable {
    let id: Int
    let sessionId: Int
    let userId: Int
    /// Optional: a source flowsheet often leaves the time blank. It used to be
    /// non-optional, which is why the API padded nulls with "" and the importer
    /// wrote 00:00:00 — both inventing a value so a type would be satisfied.
    let readingTime: String?
    let readingNumber: Int?
    let systolicBp: Int?
    let diastolicBp: Int?
    let pulse: Int?
    let meanArterialPressure: Double?
    let dialysateRate: Double?
    let dialysateVolumeRemaining: Double?
    let ufRate: Double?
    let ufVolumeRemoved: Double?
    let bloodFlowRate: Double?
    let arterialPressure: Double?
    let venousPressure: Double?
    let effluentPressure: Double?
    let accessState: String?
    let salineAmount: String?
    let remarks: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, pulse, remarks
        case sessionId = "session_id"
        case userId = "user_id"
        case readingTime = "reading_time"
        case readingNumber = "reading_number"
        case systolicBp = "systolic_bp"
        case diastolicBp = "diastolic_bp"
        case meanArterialPressure = "mean_arterial_pressure"
        case dialysateRate = "dialysate_rate"
        case dialysateVolumeRemaining = "dialysate_volume_remaining"
        case ufRate = "uf_rate"
        case ufVolumeRemoved = "uf_volume_removed"
        case bloodFlowRate = "blood_flow_rate"
        case arterialPressure = "arterial_pressure"
        case venousPressure = "venous_pressure"
        case effluentPressure = "effluent_pressure"
        case accessState = "access_state"
        case salineAmount = "saline_amount"
        case createdAt = "created_at"
    }
}

struct IntradialyticReadingCreate: Codable {
    let sessionId: Int
    /// Optional: a blank time is sent as null so "not stated" survives as not
    /// stated. Defaulting it to 00:00 is how 3664 rows (22.6% of the table) came
    /// to look like measured midnight readings.
    let readingTime: String?
    var readingNumber: Int? = nil
    let systolicBp: Int?
    let diastolicBp: Int?
    let pulse: Int?
    let meanArterialPressure: Double?
    let dialysateRate: Double?
    let dialysateVolumeRemaining: Double?
    let ufRate: Double?
    let ufVolumeRemoved: Double?
    let bloodFlowRate: Double?
    let arterialPressure: Double?
    let venousPressure: Double?
    let effluentPressure: Double?
    let accessState: String?
    let salineAmount: String?
    let remarks: String?

    enum CodingKeys: String, CodingKey {
        case pulse, remarks
        case sessionId = "session_id"
        case readingTime = "reading_time"
        case readingNumber = "reading_number"
        case systolicBp = "systolic_bp"
        case diastolicBp = "diastolic_bp"
        case meanArterialPressure = "mean_arterial_pressure"
        case dialysateRate = "dialysate_rate"
        case dialysateVolumeRemaining = "dialysate_volume_remaining"
        case ufRate = "uf_rate"
        case ufVolumeRemoved = "uf_volume_removed"
        case bloodFlowRate = "blood_flow_rate"
        case arterialPressure = "arterial_pressure"
        case venousPressure = "venous_pressure"
        case effluentPressure = "effluent_pressure"
        case accessState = "access_state"
        case salineAmount = "saline_amount"
    }
}

// MARK: - HD Summary

struct HDSummary: Codable {
    let totalSessions: Int
    let periodDays: Int
    let avgPreWeightKg: Double?
    let avgPostWeightKg: Double?
    let avgFluidRemovedMl: Double?
    let avgDurationMin: Double?
    let sessionsWithReadings: Int?

    enum CodingKeys: String, CodingKey {
        case totalSessions = "total_sessions"
        case periodDays = "period_days"
        case avgPreWeightKg = "avg_pre_weight_kg"
        case avgPostWeightKg = "avg_post_weight_kg"
        case avgFluidRemovedMl = "avg_fluid_removed_ml"
        case avgDurationMin = "avg_duration_min"
        case sessionsWithReadings = "sessions_with_readings"
    }
}

// MARK: - Therapy Sessions (Hemodialysis / Chemotherapy / Generic)

/// `clinical_notes` arrives as EITHER a string or a list of note records.
///
/// On a completed flowsheet the backend sends a LIST — clinical notes are their
/// own append-only rows, not a column on the session. `clinicalNotes: String?`
/// therefore hit a `typeMismatch`, the whole session list failed to decode, and
/// the screen showed "No hemodialysis sessions in this period" beneath a summary
/// reading "12 Sessions".
///
/// CLAUDE.md §3aa twice over: the array shape is named there as a known
/// production failure, and an error must never be rendered as an empty state.
/// The web client already guards this; iOS did not.
struct FlexibleNotes: Codable {
    let text: String?
    let notes: [ClinicalNote]

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            text = nil; notes = []
        } else if let string = try? container.decode(String.self) {
            text = string; notes = []
        } else if let list = try? container.decode([ClinicalNote].self) {
            text = nil; notes = list
        } else {
            // Unknown shape: decode to empty rather than failing the WHOLE
            // session list over one field.
            text = nil; notes = []
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let text { try container.encode(text) } else { try container.encode(notes) }
    }
}

struct TherapySession: Codable, Identifiable {
    let id: Int
    let userId: Int?
    let conditionId: Int?
    let therapyType: String
    let therapyName: String?
    let sessionNumber: Int?
    let totalSessionsPlanned: Int?
    let scheduledDate: String
    let actualStartTime: String?
    let actualEndTime: String?
    let durationMinutes: Int?
    let status: String
    let facilityName: String?
    let facilityAddress: String?
    let attendingPhysician: String?
    let attendingNurse: String?
    // Dialysis
    let dialysisAccessType: String?
    let dryWeightKg: Double?
    let previousPostWeightKg: Double?
    let preDialysisWeightKg: Double?
    let postDialysisWeightKg: Double?
    let fluidRemovedMl: Double?
    let fluidToRemoveKg: Double?
    let bloodFlowRate: Double?
    let dialysateFlowRate: Double?
    // HD-specific
    let dayOfWeek: String?
    let rnReviewer: String?
    let dialysateVolumeLiters: Double?
    let dialysateLactateMeq: Double?
    let dialysatePotassiumMeq: Double?
    let sakNumber: Int?
    let needleGauge: String?
    let needleLength: Double?
    let buttonholeTechnique: Bool?
    // Standing BP
    let preStandingSystolicBp: Int?
    let preStandingDiastolicBp: Int?
    let preStandingHeartRate: Int?
    let postStandingSystolicBp: Int?
    let postStandingDiastolicBp: Int?
    let postStandingHeartRate: Int?
    // Equipment
    let cartridgeLot: String?
    let sakLot: String?
    let cyclerNumber: String?
    let warmerSerial: String?
    let controlPanelSerial: String?
    // Pre-treatment symptoms
    let preShortnessOfBreath: Bool?
    let preSwelling: Bool?
    let preChangeInMobility: Bool?
    let preDigestionProblems: Bool?
    let preHospErSinceLast: Bool?
    // Access assessment
    let accessThrillBruit: Bool?
    let accessRednessDrainage: Bool?
    // Post-treatment totals
    let totalDialysateLiters: Double?
    let totalUfLiters: Double?
    let totalBloodVolumeProcessed: Double?
    let dialyzerAppearance: String?
    let postBleedingStopTime: String?
    let postBruising: Bool?
    let postInfiltration: Bool?
    let postShortnessOfBreath: Bool?
    let postSwelling: Bool?
    let postDigestionProblems: Bool?
    let postAccessThrillBruit: Bool?
    // Machine maintenance
    let purificationPakChange: Bool?
    let airFilterCleaned: Bool?
    let wasteLineBleachDisinfection: Bool?
    let sakUseNumber: Int?
    let totalChloramineLevel: Double?
    let alarmTestCompleted: Bool?
    let labTubesDrawn: String?
    // Chemo
    let drugsAdministered: String?
    let dosage: String?
    let routeOfAdministration: String?
    // Vitals
    let preSystolicBp: Int?
    let preDiastolicBp: Int?
    let postSystolicBp: Int?
    let postDiastolicBp: Int?
    let preHeartRate: Int?
    let postHeartRate: Int?
    let preTemperature: Double?
    let postTemperature: Double?
    let oxygenSaturation: Int?
    // Outcomes
    let sideEffects: String?
    let adverseReactions: String?
    let complications: String?
    let patientTolerance: String?
    /// Raw field: a string on some payloads, a list of notes on a completed
    /// flowsheet. Read `clinicalNotes` (computed below) instead.
    let clinicalNotesRaw: FlexibleNotes?
    let patientNotes: String?
    let nextSessionScheduled: String?
    let createdAt: String?
    let updatedAt: String?
    // Intradialytic readings
    let intradialyticReadings: [IntradialyticReading]?
    // Flowsheet lifecycle fields
    let flowsheetStatus: String?
    let signatureImage: String?
    let signedAt: String?
    let signedBy: Int?
    let countersignedAt: String?
    let countersignedBy: Int?
    let reviewedAt: String?
    let reviewedBy: Int?
    let payloadHash: String?
    let clinicalNotesList: [ClinicalNote]?

    /// The notes as text, whichever shape the backend sent. Five call sites
    /// already read this as `String?`; keeping the name means the decoding fix
    /// does not ripple into the views.
    var clinicalNotes: String? {
        if let text = clinicalNotesRaw?.text, !text.isEmpty { return text }
        let joined = (clinicalNotesRaw?.notes ?? [])
            .map(\.noteText)
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
        return joined.isEmpty ? nil : joined
    }

    /// The structured notes, when the backend sent the list form.
    var clinicalNoteRecords: [ClinicalNote] { clinicalNotesRaw?.notes ?? [] }

    enum CodingKeys: String, CodingKey {
        case id, status, dosage, complications
        case userId = "user_id"
        case conditionId = "condition_id"
        case therapyType = "therapy_type"
        case therapyName = "therapy_name"
        case sessionNumber = "session_number"
        case totalSessionsPlanned = "total_sessions_planned"
        case scheduledDate = "scheduled_date"
        case actualStartTime = "actual_start_time"
        case actualEndTime = "actual_end_time"
        case durationMinutes = "duration_minutes"
        case facilityName = "facility_name"
        case facilityAddress = "facility_address"
        case attendingPhysician = "attending_physician"
        case attendingNurse = "attending_nurse"
        case dialysisAccessType = "dialysis_access_type"
        case dryWeightKg = "dry_weight_kg"
        case previousPostWeightKg = "previous_post_weight_kg"
        case preDialysisWeightKg = "pre_dialysis_weight_kg"
        case postDialysisWeightKg = "post_dialysis_weight_kg"
        case fluidRemovedMl = "fluid_removed_ml"
        case fluidToRemoveKg = "fluid_to_remove_kg"
        case bloodFlowRate = "blood_flow_rate"
        case dialysateFlowRate = "dialysate_flow_rate"
        case dayOfWeek = "day_of_week"
        case rnReviewer = "rn_reviewer"
        case dialysateVolumeLiters = "dialysate_volume_liters"
        case dialysateLactateMeq = "dialysate_lactate_meq"
        case dialysatePotassiumMeq = "dialysate_potassium_meq"
        case sakNumber = "sak_number"
        case needleGauge = "needle_gauge"
        case needleLength = "needle_length"
        case buttonholeTechnique = "buttonhole_technique"
        case preStandingSystolicBp = "pre_standing_systolic_bp"
        case preStandingDiastolicBp = "pre_standing_diastolic_bp"
        case preStandingHeartRate = "pre_standing_heart_rate"
        case postStandingSystolicBp = "post_standing_systolic_bp"
        case postStandingDiastolicBp = "post_standing_diastolic_bp"
        case postStandingHeartRate = "post_standing_heart_rate"
        case cartridgeLot = "cartridge_lot"
        case sakLot = "sak_lot"
        case cyclerNumber = "cycler_number"
        case warmerSerial = "warmer_serial"
        case controlPanelSerial = "control_panel_serial"
        case preShortnessOfBreath = "pre_shortness_of_breath"
        case preSwelling = "pre_swelling"
        case preChangeInMobility = "pre_change_in_mobility"
        case preDigestionProblems = "pre_digestion_problems"
        case preHospErSinceLast = "pre_hosp_er_since_last"
        case accessThrillBruit = "access_thrill_bruit"
        case accessRednessDrainage = "access_redness_drainage"
        case totalDialysateLiters = "total_dialysate_liters"
        case totalUfLiters = "total_uf_liters"
        case totalBloodVolumeProcessed = "total_blood_volume_processed"
        case dialyzerAppearance = "dialyzer_appearance"
        case postBleedingStopTime = "post_bleeding_stop_time"
        case postBruising = "post_bruising"
        case postInfiltration = "post_infiltration"
        case postShortnessOfBreath = "post_shortness_of_breath"
        case postSwelling = "post_swelling"
        case postDigestionProblems = "post_digestion_problems"
        case postAccessThrillBruit = "post_access_thrill_bruit"
        case purificationPakChange = "purification_pak_change"
        case airFilterCleaned = "air_filter_cleaned"
        case wasteLineBleachDisinfection = "waste_line_bleach_disinfection"
        case sakUseNumber = "sak_use_number"
        case totalChloramineLevel = "total_chloramine_level"
        case alarmTestCompleted = "alarm_test_completed"
        case labTubesDrawn = "lab_tubes_drawn"
        case drugsAdministered = "drugs_administered"
        case routeOfAdministration = "route_of_administration"
        case preSystolicBp = "pre_systolic_bp"
        case preDiastolicBp = "pre_diastolic_bp"
        case postSystolicBp = "post_systolic_bp"
        case postDiastolicBp = "post_diastolic_bp"
        case preHeartRate = "pre_heart_rate"
        case postHeartRate = "post_heart_rate"
        case preTemperature = "pre_temperature"
        case postTemperature = "post_temperature"
        case oxygenSaturation = "oxygen_saturation"
        case sideEffects = "side_effects"
        case adverseReactions = "adverse_reactions"
        case patientTolerance = "patient_tolerance"
        case clinicalNotesRaw = "clinical_notes"
        case patientNotes = "patient_notes"
        case nextSessionScheduled = "next_session_scheduled"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case intradialyticReadings = "intradialytic_readings"
        case flowsheetStatus = "flowsheet_status"
        case signatureImage = "signature_image"
        case signedAt = "signed_at"
        case signedBy = "signed_by"
        case countersignedAt = "countersigned_at"
        case countersignedBy = "countersigned_by"
        case reviewedAt = "reviewed_at"
        case reviewedBy = "reviewed_by"
        case payloadHash = "payload_hash"
        case clinicalNotesList = "clinical_notes_list"
    }
}

struct TherapySessionCreate: Codable {
    let therapyType: String
    let scheduledDate: String
    let status: String
    var therapyName: String? = nil
    var sessionNumber: Int? = nil
    var totalSessionsPlanned: Int? = nil
    var durationMinutes: Int? = nil
    var actualStartTime: String? = nil
    var actualEndTime: String? = nil
    var facilityName: String? = nil
    var attendingPhysician: String? = nil
    var attendingNurse: String? = nil
    // Dialysis
    var dialysisAccessType: String? = nil
    var dryWeightKg: Double? = nil
    var previousPostWeightKg: Double? = nil
    var preDialysisWeightKg: Double? = nil
    var postDialysisWeightKg: Double? = nil
    var fluidRemovedMl: Double? = nil
    var fluidToRemoveKg: Double? = nil
    var bloodFlowRate: Double? = nil
    var dialysateFlowRate: Double? = nil
    // HD-specific
    var dayOfWeek: String? = nil
    var rnReviewer: String? = nil
    var dialysateVolumeLiters: Double? = nil
    var dialysateLactateMeq: Double? = nil
    var dialysatePotassiumMeq: Double? = nil
    var sakNumber: Int? = nil
    var needleGauge: String? = nil
    var needleLength: Double? = nil
    var buttonholeTechnique: Bool? = nil
    // Standing BP
    var preStandingSystolicBp: Int? = nil
    var preStandingDiastolicBp: Int? = nil
    var preStandingHeartRate: Int? = nil
    var postStandingSystolicBp: Int? = nil
    var postStandingDiastolicBp: Int? = nil
    var postStandingHeartRate: Int? = nil
    // Equipment
    var cartridgeLot: String? = nil
    var sakLot: String? = nil
    var cyclerNumber: String? = nil
    var warmerSerial: String? = nil
    var controlPanelSerial: String? = nil
    // Pre-treatment symptoms
    var preShortnessOfBreath: Bool? = nil
    var preSwelling: Bool? = nil
    var preChangeInMobility: Bool? = nil
    var preDigestionProblems: Bool? = nil
    var preHospErSinceLast: Bool? = nil
    // Access assessment
    var accessThrillBruit: Bool? = nil
    var accessRednessDrainage: Bool? = nil
    // Post-treatment totals
    var totalDialysateLiters: Double? = nil
    var totalUfLiters: Double? = nil
    var totalBloodVolumeProcessed: Double? = nil
    var dialyzerAppearance: String? = nil
    var postBleedingStopTime: String? = nil
    var postBruising: Bool? = nil
    var postInfiltration: Bool? = nil
    var postShortnessOfBreath: Bool? = nil
    var postSwelling: Bool? = nil
    var postDigestionProblems: Bool? = nil
    var postAccessThrillBruit: Bool? = nil
    // Machine maintenance
    var purificationPakChange: Bool? = nil
    var airFilterCleaned: Bool? = nil
    var wasteLineBleachDisinfection: Bool? = nil
    var sakUseNumber: Int? = nil
    var totalChloramineLevel: Double? = nil
    var alarmTestCompleted: Bool? = nil
    var labTubesDrawn: String? = nil
    // Chemo
    var drugsAdministered: String? = nil
    var dosage: String? = nil
    var routeOfAdministration: String? = nil
    // Vitals
    var preSystolicBp: Int? = nil
    var preDiastolicBp: Int? = nil
    var postSystolicBp: Int? = nil
    var postDiastolicBp: Int? = nil
    var preHeartRate: Int? = nil
    var postHeartRate: Int? = nil
    var preTemperature: Double? = nil
    var postTemperature: Double? = nil
    var oxygenSaturation: Int? = nil
    // Outcomes
    var sideEffects: String? = nil
    var adverseReactions: String? = nil
    var patientTolerance: String? = nil
    var clinicalNotes: String? = nil
    var patientNotes: String? = nil

    enum CodingKeys: String, CodingKey {
        case status, dosage
        case therapyType = "therapy_type"
        case scheduledDate = "scheduled_date"
        case therapyName = "therapy_name"
        case sessionNumber = "session_number"
        case totalSessionsPlanned = "total_sessions_planned"
        case durationMinutes = "duration_minutes"
        case actualStartTime = "actual_start_time"
        case actualEndTime = "actual_end_time"
        case facilityName = "facility_name"
        case attendingPhysician = "attending_physician"
        case attendingNurse = "attending_nurse"
        case dialysisAccessType = "dialysis_access_type"
        case dryWeightKg = "dry_weight_kg"
        case previousPostWeightKg = "previous_post_weight_kg"
        case preDialysisWeightKg = "pre_dialysis_weight_kg"
        case postDialysisWeightKg = "post_dialysis_weight_kg"
        case fluidRemovedMl = "fluid_removed_ml"
        case fluidToRemoveKg = "fluid_to_remove_kg"
        case bloodFlowRate = "blood_flow_rate"
        case dialysateFlowRate = "dialysate_flow_rate"
        case dayOfWeek = "day_of_week"
        case rnReviewer = "rn_reviewer"
        case dialysateVolumeLiters = "dialysate_volume_liters"
        case dialysateLactateMeq = "dialysate_lactate_meq"
        case dialysatePotassiumMeq = "dialysate_potassium_meq"
        case sakNumber = "sak_number"
        case needleGauge = "needle_gauge"
        case needleLength = "needle_length"
        case buttonholeTechnique = "buttonhole_technique"
        case preStandingSystolicBp = "pre_standing_systolic_bp"
        case preStandingDiastolicBp = "pre_standing_diastolic_bp"
        case preStandingHeartRate = "pre_standing_heart_rate"
        case postStandingSystolicBp = "post_standing_systolic_bp"
        case postStandingDiastolicBp = "post_standing_diastolic_bp"
        case postStandingHeartRate = "post_standing_heart_rate"
        case cartridgeLot = "cartridge_lot"
        case sakLot = "sak_lot"
        case cyclerNumber = "cycler_number"
        case warmerSerial = "warmer_serial"
        case controlPanelSerial = "control_panel_serial"
        case preShortnessOfBreath = "pre_shortness_of_breath"
        case preSwelling = "pre_swelling"
        case preChangeInMobility = "pre_change_in_mobility"
        case preDigestionProblems = "pre_digestion_problems"
        case preHospErSinceLast = "pre_hosp_er_since_last"
        case accessThrillBruit = "access_thrill_bruit"
        case accessRednessDrainage = "access_redness_drainage"
        case totalDialysateLiters = "total_dialysate_liters"
        case totalUfLiters = "total_uf_liters"
        case totalBloodVolumeProcessed = "total_blood_volume_processed"
        case dialyzerAppearance = "dialyzer_appearance"
        case postBleedingStopTime = "post_bleeding_stop_time"
        case postBruising = "post_bruising"
        case postInfiltration = "post_infiltration"
        case postShortnessOfBreath = "post_shortness_of_breath"
        case postSwelling = "post_swelling"
        case postDigestionProblems = "post_digestion_problems"
        case postAccessThrillBruit = "post_access_thrill_bruit"
        case purificationPakChange = "purification_pak_change"
        case airFilterCleaned = "air_filter_cleaned"
        case wasteLineBleachDisinfection = "waste_line_bleach_disinfection"
        case sakUseNumber = "sak_use_number"
        case totalChloramineLevel = "total_chloramine_level"
        case alarmTestCompleted = "alarm_test_completed"
        case labTubesDrawn = "lab_tubes_drawn"
        case drugsAdministered = "drugs_administered"
        case routeOfAdministration = "route_of_administration"
        case preSystolicBp = "pre_systolic_bp"
        case preDiastolicBp = "pre_diastolic_bp"
        case postSystolicBp = "post_systolic_bp"
        case postDiastolicBp = "post_diastolic_bp"
        case preHeartRate = "pre_heart_rate"
        case postHeartRate = "post_heart_rate"
        case preTemperature = "pre_temperature"
        case postTemperature = "post_temperature"
        case oxygenSaturation = "oxygen_saturation"
        case sideEffects = "side_effects"
        case adverseReactions = "adverse_reactions"
        case patientTolerance = "patient_tolerance"
        case clinicalNotes = "clinical_notes"
        case patientNotes = "patient_notes"
    }
}

// MARK: - Notifications

struct AppNotification: Codable, Identifiable {
    let id: Int
    let userId: Int
    let category: String
    let priority: String
    let title: String
    let message: String
    let actionUrl: String?
    let metadata: String?
    var isRead: Bool
    let readAt: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case category, priority, title, message
        case actionUrl = "action_url"
        case metadata
        case isRead = "is_read"
        case readAt = "read_at"
        case createdAt = "created_at"
    }
}

struct NotificationPreference: Codable, Identifiable {
    let id: Int
    let userId: Int
    let category: String
    var enabled: Bool
    var inApp: Bool
    var push: Bool
    var email: Bool
    var sms: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case category, enabled
        case inApp = "in_app"
        case push, email, sms
    }
}

struct UnreadCountResponse: Codable {
    let count: Int
}

struct NotificationPreferenceUpdate: Codable {
    var enabled: Bool?
    var inApp: Bool?
    var push: Bool?
    var email: Bool?
    var sms: Bool?

    enum CodingKeys: String, CodingKey {
        case enabled
        case inApp = "in_app"
        case push, email, sms
    }
}

// MARK: - HEBCS Ω (Wellness Tensor / Clinical Biomarker Score)

struct HEBCSBiomarkerScore: Codable {
    let name: String
    let value: Double?
    let score: Double?
    let weight: Double
    let optRange: [Double]?

    enum CodingKeys: String, CodingKey {
        case name, value, score, weight
        case optRange = "opt_range"
    }
}

struct HEBCSPathwayScore: Codable {
    let score: Double?
    let weight: Double
    let biomarkers: [HEBCSBiomarkerScore]
}

struct HEBCSScoreResponse: Codable {
    let computedAt: String?
    let labDateUsed: String?
    let omega: Double
    /// nil when NO pathway scored — a patient with no labs must not be handed
    /// a number. Declared non-optional, one null failed the whole decode.
    let omegaPct: Double?
    let dataCoverage: Double
    let pathways: [String: HEBCSPathwayScore]
    let interpretation: String?

    enum CodingKeys: String, CodingKey {
        case computedAt = "computed_at"
        case labDateUsed = "lab_date_used"
        case omega
        case omegaPct = "omega_pct"
        case dataCoverage = "data_coverage"
        case pathways, interpretation
    }
}

struct WhatIfPathwayDelta: Codable {
    let baselineScore: Double?
    let scenarioScore: Double?
    let delta: Double?

    enum CodingKeys: String, CodingKey {
        case baselineScore = "baseline_score"
        case scenarioScore = "scenario_score"
        case delta
    }
}

struct WhatIfResponse: Codable {
    let scenarioName: String
    let baselineOmega: Double
    let scenarioOmega: Double
    let deltaOmega: Double
    let deltaPct: Double
    let pathwayDeltas: [String: WhatIfPathwayDelta]
    let overriddenBiomarkers: [String]
    let interpretation: String

    enum CodingKeys: String, CodingKey {
        case scenarioName = "scenario_name"
        case baselineOmega = "baseline_omega"
        case scenarioOmega = "scenario_omega"
        case deltaOmega = "delta_omega"
        case deltaPct = "delta_pct"
        case pathwayDeltas = "pathway_deltas"
        case overriddenBiomarkers = "overridden_biomarkers"
        case interpretation
    }
}

struct WhatIfRequest: Codable {
    var scenarioName: String = "custom"
    var Phosphorus: Double?
    var Potassium: Double?
    var Albumin: Double?
    var Hemoglobin: Double?
    var Ferritin: Double?
    var KtV_Dialysis_Adequacy: Double?
    var PTH_Intact: Double?
    var Calcium: Double?
    var Glucose: Double?
    var Sodium: Double?

    enum CodingKeys: String, CodingKey {
        case scenarioName = "scenario_name"
        case Phosphorus, Potassium, Albumin, Hemoglobin, Ferritin
        case KtV_Dialysis_Adequacy
        case PTH_Intact
        case Calcium, Glucose, Sodium
    }
}

// MARK: - Flowsheet Lifecycle

enum FlowsheetStatus: String, Codable, CaseIterable {
    case draft
    case submitted
    case signed
    case countersigned
    case reviewed
    case locked

    var displayName: String {
        rawValue.capitalized
    }

    var color: String {
        switch self {
        case .draft: return "gray"
        case .submitted: return "blue"
        case .signed: return "orange"
        case .countersigned: return "purple"
        case .reviewed: return "teal"
        case .locked: return "green"
        }
    }
}

// MARK: - Clinical Notes

struct ClinicalNote: Codable, Identifiable {
    let id: Int
    let sessionId: Int
    let authorId: Int
    let noteType: String
    let noteText: String
    let noteHash: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case sessionId = "session_id"
        case authorId = "author_id"
        case noteType = "note_type"
        case noteText = "note_text"
        case noteHash = "note_hash"
        case createdAt = "created_at"
    }
}

struct ClinicalNoteCreate: Codable {
    let noteType: String
    let noteText: String

    enum CodingKeys: String, CodingKey {
        case noteType = "note_type"
        case noteText = "note_text"
    }
}

// MARK: - Flowsheet Actions

struct FlowsheetSignRequest: Codable {
    let signatureImage: String

    enum CodingKeys: String, CodingKey {
        case signatureImage = "signature_image"
    }
}

struct FlowsheetActionResponse: Codable {
    let status: String
    let message: String
    let sessionId: Int
    let payloadHash: String?
    let signedAt: String?

    enum CodingKeys: String, CodingKey {
        case status, message
        case sessionId = "session_id"
        case payloadHash = "payload_hash"
        case signedAt = "signed_at"
    }
}

// MARK: - Blockchain

struct BlockRecord: Codable, Identifiable {
    let id: Int
    let blockUid: String
    let index: Int
    let timestamp: String
    let chainType: String
    let action: String
    let previousHash: String
    let hash: String
    let nonce: String?
    let actorId: Int?
    let entityType: String?
    let entityId: Int?
    let merkleRoot: String?
    let signature: String?
    let blockchainTxHash: String?
    let blockchainBlockNum: Int?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, index, timestamp, action, hash, nonce, signature
        case blockUid = "block_uid"
        case chainType = "chain_type"
        case previousHash = "previous_hash"
        case actorId = "actor_id"
        case entityType = "entity_type"
        case entityId = "entity_id"
        case merkleRoot = "merkle_root"
        case blockchainTxHash = "blockchain_tx_hash"
        case blockchainBlockNum = "blockchain_block_num"
        case createdAt = "created_at"
    }
}

struct BlockchainVerifyResponse: Codable {
    let valid: Bool
    let onChainData: String?
    let expected: String?
    let block: Int?
    let message: String?

    enum CodingKeys: String, CodingKey {
        case valid, expected, block, message
        case onChainData = "on_chain_data"
    }
}

// MARK: - System ID

struct SystemIdResponse: Codable {
    let systemId: String
    let masked: String
    let segments: [String: String]
    let valid: Bool

    enum CodingKeys: String, CodingKey {
        case masked, segments, valid
        case systemId = "system_id"
    }
}

// MARK: - Subscription / Billing (ALAFIA Membership)

struct SubscriptionRailPrice: Codable {
    let provider: String
    let priceUsd: Double
    let storeProductId: String?

    enum CodingKeys: String, CodingKey {
        case provider
        case priceUsd = "price_usd"
        case storeProductId = "store_product_id"
    }
}

struct SubscriptionPlans: Codable {
    let productName: String
    let plan: String
    let currency: String
    let interval: String
    let rails: [SubscriptionRailPrice]

    enum CodingKeys: String, CodingKey {
        case productName = "product_name"
        case plan, currency, interval, rails
    }
}

struct SubscriptionStatus: Codable {
    let status: String
    let provider: String
    let plan: String
    let entitled: Bool
    let productName: String
    let priceUsd: Double?
    let currentPeriodEnd: String?
    let cancelAtPeriodEnd: Bool

    enum CodingKeys: String, CodingKey {
        case status, provider, plan, entitled
        case productName = "product_name"
        case priceUsd = "price_usd"
        case currentPeriodEnd = "current_period_end"
        case cancelAtPeriodEnd = "cancel_at_period_end"
    }
}

struct AppleVerifyRequest: Codable {
    let signedTransaction: String?
    let receiptData: String?
    let transactionId: String?

    enum CodingKeys: String, CodingKey {
        case signedTransaction = "signed_transaction"
        case receiptData = "receipt_data"
        case transactionId = "transaction_id"
    }
}
