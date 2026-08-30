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
    # pending | done | failed | skipped — tells the client whether nutrient
    # values are still arriving, so it shows a placeholder rather than a
    # misleading zero.
    nutrient_status: str = "skipped"
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
    #: THIS patient's own daily figure, from `compute_goals` (KDOQI 2020 for
    #: CKD). Distinct from `rda`, which is the general-population reference —
    #: a dialysis patient's potassium ceiling is nothing like the DV, and the
    #: diary used to colour cells against hardcoded thresholds like 1000 mg of
    #: phosphorus for everyone.
    goal: float | None = None
    #: "target" (aim to reach) or "limit" (stay under). None when no goal.
    goal_kind: str | None = None


class NutrientCatalogPage(BaseModel):
    """One page of the nutrient catalog.

    The catalog is 116 nutrients and grows with USDA's; the diary was rendering
    a hand-written list of 15. Paginated so a client can show all of them
    without a single enormous response or a second, divergent list.
    """
    items: list[NutrientCatalogItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    #: Every category present, so a client can offer them without hardcoding.
    categories: list[str]


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


class DialysisBalance(BaseModel):
    intake: float           # what was eaten, in the goal's own unit
    delta: float            # signed: negative removed by treatment, positive gained
    net: float              # intake + delta — the body's actual balance
    modelled_mg: float      # raw model output, before any gating
    direction: str          # "removed" | "gained" | "none"
    calibrated: bool        # fitted against this patient's own bloods?
    reasons: list[str] = []
    #: Set when removal was modelled but deliberately not counted — a high
    #: serum value or no recent draw to confirm it.
    withheld: str | None = None


class DialysisDaySummary(BaseModel):
    had_dialysis: bool
    session_count: int
    modelled_mg: dict[str, float] = {}
    notes: list[str] = []


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

    # Present only on a day with a completed dialysis session.
    #
    # The LIMIT never moves for a treatment — KDOQI's figures already assume the
    # patient is on dialysis, so raising them would count that clearance twice.
    # What a session changes is the day's balance: potassium eaten in the
    # morning may be gone by the afternoon, and calcium the patient never ate
    # crosses in from the dialysate and is retained.
    #
    # `current` stays dietary intake so the intake-versus-limit comparison is
    # unchanged; `net` is reported beside it, never in place of it.
    dialysis_balance: DialysisBalance | None = None


class GoalProgressResponse(BaseModel):
    date: date
    profile_complete: bool  # False when biology is incomplete (generic goals)
    energy_kcal: float
    conditions: list[str]   # condition flags considered, e.g. ["ckd", "dialysis"]
    goals: list[NutrientGoalProgress]
    dialysis: DialysisDaySummary | None = None


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
