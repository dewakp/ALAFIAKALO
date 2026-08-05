import Foundation

// MARK: - Nutrition Log (from DB)

struct NutritionLog: Codable, Identifiable {
    let id: Int
    let userId: Int
    let logDate: String
    let mealType: String
    let foodName: String
    let servingSize: String?
    let fdcId: Int?

    /// pending | done | failed | skipped. Nutrients are filled in AFTER the meal
    /// is saved, so a fresh entry arrives with no values and status "pending" —
    /// show that rather than a blank, which reads as "zero calories".
    /// Optional so payloads from an older backend still decode.
    let nutrientStatus: String?
    var nutrientsPending: Bool { nutrientStatus == "pending" }

    // Macronutrients
    let calories: Double?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
    let fiberG: Double?
    let sugarG: Double?

    // Fats
    let saturatedFatG: Double?
    let transFatG: Double?
    let monounsaturatedFatG: Double?
    let polyunsaturatedFatG: Double?
    let omega3G: Double?
    let omega6G: Double?
    let cholesterolMg: Double?

    // Minerals
    let sodiumMg: Double?
    let potassiumMg: Double?
    let calciumMg: Double?
    let ironMg: Double?
    let magnesiumMg: Double?
    let zincMg: Double?
    let phosphorusMg: Double?
    let copperMg: Double?
    let manganeseMg: Double?
    let seleniumMcg: Double?
    let iodineMcg: Double?

    // Vitamins
    let vitaminAIu: Double?
    let vitaminCMg: Double?
    let vitaminDIu: Double?
    let vitaminEMg: Double?
    let vitaminKMcg: Double?
    let vitaminB1ThiamineMg: Double?
    let vitaminB2RiboflavinMg: Double?
    let vitaminB3NiacinMg: Double?
    let vitaminB5PantothenicAcidMg: Double?
    let vitaminB6Mg: Double?
    let vitaminB7BiotinMcg: Double?
    let vitaminB9FolateMcg: Double?
    let vitaminB12Mcg: Double?
    let cholineMg: Double?

    // Other
    let waterMl: Double?
    let caffeineMg: Double?
    let alcoholG: Double?

    let extendedNutrients: [String: Double]?
    let notes: String?
    let startTime: String?
    let endTime: String?
    let preMealWeightKg: Double?
    let postMealWeightKg: Double?
    let foodImageUris: String?
    let recipeUrl: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, calories, notes
        case userId = "user_id"
        case logDate = "log_date"
        case mealType = "meal_type"
        case foodName = "food_name"
        case servingSize = "serving_size"
        case fdcId = "fdc_id"
        case nutrientStatus = "nutrient_status"
        case proteinG = "protein_g"
        case carbsG = "carbs_g"
        case fatG = "fat_g"
        case fiberG = "fiber_g"
        case sugarG = "sugar_g"
        case saturatedFatG = "saturated_fat_g"
        case transFatG = "trans_fat_g"
        case monounsaturatedFatG = "monounsaturated_fat_g"
        case polyunsaturatedFatG = "polyunsaturated_fat_g"
        case omega3G = "omega3_g"
        case omega6G = "omega6_g"
        case cholesterolMg = "cholesterol_mg"
        case sodiumMg = "sodium_mg"
        case potassiumMg = "potassium_mg"
        case calciumMg = "calcium_mg"
        case ironMg = "iron_mg"
        case magnesiumMg = "magnesium_mg"
        case zincMg = "zinc_mg"
        case phosphorusMg = "phosphorus_mg"
        case copperMg = "copper_mg"
        case manganeseMg = "manganese_mg"
        case seleniumMcg = "selenium_mcg"
        case iodineMcg = "iodine_mcg"
        case vitaminAIu = "vitamin_a_iu"
        case vitaminCMg = "vitamin_c_mg"
        case vitaminDIu = "vitamin_d_iu"
        case vitaminEMg = "vitamin_e_mg"
        case vitaminKMcg = "vitamin_k_mcg"
        case vitaminB1ThiamineMg = "vitamin_b1_thiamine_mg"
        case vitaminB2RiboflavinMg = "vitamin_b2_riboflavin_mg"
        case vitaminB3NiacinMg = "vitamin_b3_niacin_mg"
        case vitaminB5PantothenicAcidMg = "vitamin_b5_pantothenic_acid_mg"
        case vitaminB6Mg = "vitamin_b6_mg"
        case vitaminB7BiotinMcg = "vitamin_b7_biotin_mcg"
        case vitaminB9FolateMcg = "vitamin_b9_folate_mcg"
        case vitaminB12Mcg = "vitamin_b12_mcg"
        case cholineMg = "choline_mg"
        case waterMl = "water_ml"
        case caffeineMg = "caffeine_mg"
        case alcoholG = "alcohol_g"
        case extendedNutrients = "extended_nutrients"
        case startTime = "start_time"
        case endTime = "end_time"
        case preMealWeightKg = "pre_meal_weight_kg"
        case postMealWeightKg = "post_meal_weight_kg"
        case foodImageUris = "food_image_uris"
        case recipeUrl = "recipe_url"
        case createdAt = "created_at"
    }
}

// MARK: - Create request

struct NutritionLogCreate: Encodable {
    let logDate: String
    let mealType: String
    let foodName: String
    var servingSize: String?
    var fdcId: Int?
    var calories: Double?
    var proteinG: Double?
    var carbsG: Double?
    var fatG: Double?
    var notes: String?
    var startTime: String?
    var endTime: String?
    var preMealWeightKg: Double?
    var postMealWeightKg: Double?
    var recipeUrl: String?

    enum CodingKeys: String, CodingKey {
        case logDate = "log_date"
        case mealType = "meal_type"
        case foodName = "food_name"
        case servingSize = "serving_size"
        case fdcId = "fdc_id"
        case calories
        case proteinG = "protein_g"
        case carbsG = "carbs_g"
        case fatG = "fat_g"
        case notes
        case startTime = "start_time"
        case endTime = "end_time"
        case preMealWeightKg = "pre_meal_weight_kg"
        case postMealWeightKg = "post_meal_weight_kg"
        case recipeUrl = "recipe_url"
    }
}

// MARK: - USDA Food Search

struct USDAFoodResult: Codable, Identifiable {
    var id: Int { fdcId }
    let fdcId: Int
    let description: String
    let brandOwner: String?
    let dataType: String?
    let servingSize: Double?
    let servingSizeUnit: String?
    let nutrients: [String: Double]

    enum CodingKeys: String, CodingKey {
        case fdcId = "fdc_id"
        case description
        case brandOwner = "brand_owner"
        case dataType = "data_type"
        case servingSize = "serving_size"
        case servingSizeUnit = "serving_size_unit"
        case nutrients
    }
}

struct USDAFoodNutrient: Codable, Identifiable {
    var id: String { key }
    let key: String
    let name: String
    let unit: String
    let value: Double
    let rda: Double?
    let percentDv: Double?
    let category: String

    enum CodingKeys: String, CodingKey {
        case key, name, unit, value, rda, category
        case percentDv = "percent_dv"
    }
}

struct FoodPortion: Codable {
    let description: String?
    let gramWeight: Double?
    let amount: Double?

    enum CodingKeys: String, CodingKey {
        case description
        case gramWeight = "gram_weight"
        case amount
    }
}

struct USDAFoodDetail: Codable {
    let fdcId: Int
    let description: String
    let brandOwner: String?
    let dataType: String?
    let foodCategory: String?
    let nutrients: [String: Double]
    let portions: [FoodPortion]
    let nutrientBreakdown: [USDAFoodNutrient]

    enum CodingKeys: String, CodingKey {
        case fdcId = "fdc_id"
        case description
        case brandOwner = "brand_owner"
        case dataType = "data_type"
        case foodCategory = "food_category"
        case nutrients, portions
        case nutrientBreakdown = "nutrient_breakdown"
    }
}

struct DailySummary: Codable {
    let date: String
    let totalCalories: Double
    let totalProteinG: Double
    let totalCarbsG: Double
    let totalFatG: Double
    let mealCount: Int
    let nutrients: [USDAFoodNutrient]

    enum CodingKeys: String, CodingKey {
        case date
        case totalCalories = "total_calories"
        case totalProteinG = "total_protein_g"
        case totalCarbsG = "total_carbs_g"
        case totalFatG = "total_fat_g"
        case mealCount = "meal_count"
        case nutrients
    }
}

// MARK: - Personalized daily nutrient goals (/nutrition/goal-progress)

struct NutrientGoalProgress: Codable, Identifiable {
    var id: String { key }
    let key: String
    let name: String
    let unit: String
    let current: Double
    let goal: Double
    let kind: String      // "target" (reach) | "limit" (stay under)
    let pct: Double
    let status: String    // low | ok | warning | over
    let priority: Int
    let rationale: String
}

struct GoalProgressResponse: Codable {
    let date: String
    let profileComplete: Bool
    let energyKcal: Double
    let conditions: [String]
    let goals: [NutrientGoalProgress]

    enum CodingKeys: String, CodingKey {
        case date, conditions, goals
        case profileComplete = "profile_complete"
        case energyKcal = "energy_kcal"
    }
}


