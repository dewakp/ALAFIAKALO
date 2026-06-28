"""Nutrition schemas — comprehensive 150+ nutrient support."""

from datetime import date, datetime, time
from typing import Any
from pydantic import BaseModel


# ── All nutrient fields (matching NutritionLog model columns) ──

_NUTRIENT_FIELDS = {
    # Macronutrients
    "calories": (float | None, None),
    "protein_g": (float | None, None),
    "carbs_g": (float | None, None),
    "fat_g": (float | None, None),
    "fiber_g": (float | None, None),
    "sugar_g": (float | None, None),
    # Fats
    "saturated_fat_g": (float | None, None),
    "trans_fat_g": (float | None, None),
    "monounsaturated_fat_g": (float | None, None),
    "polyunsaturated_fat_g": (float | None, None),
    "omega3_g": (float | None, None),
    "omega6_g": (float | None, None),
    "cholesterol_mg": (float | None, None),
    # Minerals
    "sodium_mg": (float | None, None),
    "potassium_mg": (float | None, None),
    "calcium_mg": (float | None, None),
    "iron_mg": (float | None, None),
    "magnesium_mg": (float | None, None),
    "zinc_mg": (float | None, None),
    "phosphorus_mg": (float | None, None),
    "copper_mg": (float | None, None),
    "manganese_mg": (float | None, None),
    "selenium_mcg": (float | None, None),
    "iodine_mcg": (float | None, None),
    # Vitamins
    "vitamin_a_iu": (float | None, None),
    "vitamin_c_mg": (float | None, None),
    "vitamin_d_iu": (float | None, None),
    "vitamin_e_mg": (float | None, None),
    "vitamin_k_mcg": (float | None, None),
    "vitamin_b1_thiamine_mg": (float | None, None),
    "vitamin_b2_riboflavin_mg": (float | None, None),
    "vitamin_b3_niacin_mg": (float | None, None),
    "vitamin_b5_pantothenic_acid_mg": (float | None, None),
    "vitamin_b6_mg": (float | None, None),
    "vitamin_b7_biotin_mcg": (float | None, None),
    "vitamin_b9_folate_mcg": (float | None, None),
    "vitamin_b12_mcg": (float | None, None),
    "choline_mg": (float | None, None),
    # Other
    "water_ml": (float | None, None),
    "caffeine_mg": (float | None, None),
    "alcohol_g": (float | None, None),
}


class NutritionLogCreate(BaseModel):
    log_date: date
    meal_type: str
    food_name: str
    serving_size: str | None = None
    fdc_id: int | None = None  # USDA FoodData Central ID for provenance

    # All nutrient fields
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    monounsaturated_fat_g: float | None = None
    polyunsaturated_fat_g: float | None = None
    omega3_g: float | None = None
    omega6_g: float | None = None
    cholesterol_mg: float | None = None
    sodium_mg: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    magnesium_mg: float | None = None
    zinc_mg: float | None = None
    phosphorus_mg: float | None = None
    copper_mg: float | None = None
    manganese_mg: float | None = None
    selenium_mcg: float | None = None
    iodine_mcg: float | None = None
    vitamin_a_iu: float | None = None
    vitamin_c_mg: float | None = None
    vitamin_d_iu: float | None = None
    vitamin_e_mg: float | None = None
    vitamin_k_mcg: float | None = None
    vitamin_b1_thiamine_mg: float | None = None
    vitamin_b2_riboflavin_mg: float | None = None
    vitamin_b3_niacin_mg: float | None = None
    vitamin_b5_pantothenic_acid_mg: float | None = None
    vitamin_b6_mg: float | None = None
    vitamin_b7_biotin_mcg: float | None = None
    vitamin_b9_folate_mcg: float | None = None
    vitamin_b12_mcg: float | None = None
    choline_mg: float | None = None
    water_ml: float | None = None
    caffeine_mg: float | None = None
    alcohol_g: float | None = None

    # Meal timing and pre/post weights (from Firebase)
    start_time: time | None = None
    end_time: time | None = None
    pre_meal_weight_kg: float | None = None
    post_meal_weight_kg: float | None = None
    food_image_uris: str | None = None
    recipe_url: str | None = None

    # Extended nutrients stored as JSON blob
    extended_nutrients: dict[str, Any] | None = None
    notes: str | None = None


class NutritionLogUpdate(BaseModel):
    log_date: date | None = None
    meal_type: str | None = None
    food_name: str | None = None
    serving_size: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    monounsaturated_fat_g: float | None = None
    polyunsaturated_fat_g: float | None = None
    omega3_g: float | None = None
    omega6_g: float | None = None
    cholesterol_mg: float | None = None
    sodium_mg: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    magnesium_mg: float | None = None
    zinc_mg: float | None = None
    phosphorus_mg: float | None = None
    copper_mg: float | None = None
    manganese_mg: float | None = None
    selenium_mcg: float | None = None
    iodine_mcg: float | None = None
    vitamin_a_iu: float | None = None
    vitamin_c_mg: float | None = None
    vitamin_d_iu: float | None = None
    vitamin_e_mg: float | None = None
    vitamin_k_mcg: float | None = None
    vitamin_b1_thiamine_mg: float | None = None
    vitamin_b2_riboflavin_mg: float | None = None
    vitamin_b3_niacin_mg: float | None = None
    vitamin_b5_pantothenic_acid_mg: float | None = None
    vitamin_b6_mg: float | None = None
    vitamin_b7_biotin_mcg: float | None = None
    vitamin_b9_folate_mcg: float | None = None
    vitamin_b12_mcg: float | None = None
    choline_mg: float | None = None
    water_ml: float | None = None
    caffeine_mg: float | None = None
    alcohol_g: float | None = None
    start_time: time | None = None
    end_time: time | None = None
    pre_meal_weight_kg: float | None = None
    post_meal_weight_kg: float | None = None
    food_image_uris: str | None = None
    recipe_url: str | None = None
    extended_nutrients: dict[str, Any] | None = None
    notes: str | None = None


class NutritionLogResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    meal_type: str
    food_name: str
    serving_size: str | None = None
    fdc_id: int | None = None

    # All nutrient columns
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    monounsaturated_fat_g: float | None = None
    polyunsaturated_fat_g: float | None = None
    omega3_g: float | None = None
    omega6_g: float | None = None
    cholesterol_mg: float | None = None
    sodium_mg: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    magnesium_mg: float | None = None
    zinc_mg: float | None = None
    phosphorus_mg: float | None = None
    copper_mg: float | None = None
    manganese_mg: float | None = None
    selenium_mcg: float | None = None
    iodine_mcg: float | None = None
    vitamin_a_iu: float | None = None
    vitamin_c_mg: float | None = None
    vitamin_d_iu: float | None = None
    vitamin_e_mg: float | None = None
    vitamin_k_mcg: float | None = None
    vitamin_b1_thiamine_mg: float | None = None
    vitamin_b2_riboflavin_mg: float | None = None
    vitamin_b3_niacin_mg: float | None = None
    vitamin_b5_pantothenic_acid_mg: float | None = None
    vitamin_b6_mg: float | None = None
    vitamin_b7_biotin_mcg: float | None = None
    vitamin_b9_folate_mcg: float | None = None
    vitamin_b12_mcg: float | None = None
    choline_mg: float | None = None
    water_ml: float | None = None
    caffeine_mg: float | None = None
    alcohol_g: float | None = None
    start_time: time | None = None
    end_time: time | None = None
    pre_meal_weight_kg: float | None = None
    post_meal_weight_kg: float | None = None
    food_image_uris: str | None = None
    recipe_url: str | None = None
    extended_nutrients: dict[str, Any] | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── USDA Food Search schemas ──

class USDAFoodNutrient(BaseModel):
    key: str
    name: str
    unit: str
    value: float
    rda: float | None = None
    percent_dv: float | None = None
    category: str


class USDAFoodResult(BaseModel):
    fdc_id: int
    description: str
    brand_owner: str | None = None
    data_type: str | None = None
    serving_size: float | None = None
    serving_size_unit: str | None = None
    nutrients: dict[str, float]


class USDAFoodDetail(BaseModel):
    fdc_id: int
    description: str
    brand_owner: str | None = None
    data_type: str | None = None
    food_category: str | None = None
    nutrients: dict[str, float]
    portions: list[dict] = []
    nutrient_breakdown: list[USDAFoodNutrient] = []


class NutrientCatalogItem(BaseModel):
    key: str
    name: str
    unit: str
    usda_id: int | None = None
    rda: float | None = None
    category: str


class DailySummary(BaseModel):
    date: date
    total_calories: float
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    meal_count: int
    nutrients: list[USDAFoodNutrient]  # aggregated with %DV
    # Each entry: {medication_name, dose, nutrients: {key: value}}
    medication_nutrient_contributions: list[dict[str, Any]] = []


# ── Personalized daily nutrient goals ──


class NutrientGoalProgress(BaseModel):
    key: str
    name: str
    unit: str
    current: float          # running total for the day
    goal: float             # personalized target or limit
    kind: str               # "target" (reach) | "limit" (stay under)
    pct: float              # current / goal * 100
    status: str             # target: low|ok|over ; limit: ok|warning|over
    priority: int           # lower = show first (condition-driven)
    rationale: str


class GoalProgressResponse(BaseModel):
    date: date
    profile_complete: bool  # False when biology is incomplete (generic goals)
    energy_kcal: float
    conditions: list[str]   # condition flags considered, e.g. ["ckd", "dialysis"]
    goals: list[NutrientGoalProgress]


# ── Nutrient estimation schemas ──


class NutrientEstimateRequest(BaseModel):
    food_name: str
    serving_size: str | None = None


class NutrientEstimateResponse(BaseModel):
    source: str | None  # "usda", "ai", or None
    fdc_id: int | None = None
    ai_model: str | None = None
    food_name: str
    serving_size: str | None = None
    serving_weight_g: float | None = None
    confidence: float
    nutrients: dict[str, float]
    cached: bool


# ── Meal-level estimation schemas (NLM parse → per-item scale → aggregate) ──


class MealEstimateRequest(BaseModel):
    """Free-text meal description to parse and estimate nutrients for."""

    description: str
    # If both are provided the aggregated result is saved as a NutritionLog.
    log_date: date | None = None
    meal_type: str | None = None


class MealComponentResult(BaseModel):
    """Nutrient estimate for one parsed food item, scaled to its actual quantity."""

    food_name: str
    qty_g: float
    qty_text: str                   # human-readable quantity (e.g. "1.5 cup")
    source: str | None = None       # "usda", "ai", or None
    fdc_id: int | None = None
    confidence: float = 0.0
    nutrients_scaled: dict[str, float] = {}  # per-item nutrients at actual qty


class MealEstimateResponse(BaseModel):
    """Aggregate meal-level nutrient result with per-component breakdown."""

    description: str
    components: list[MealComponentResult]
    aggregate_nutrients: dict[str, float]   # summed across all components
    total_weight_g: float
    log_id: int | None = None               # set when saved to NutritionLog
