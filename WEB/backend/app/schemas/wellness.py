"""Wellness schemas — scores, trends, recommendations, planners."""

from datetime import date, datetime
from typing import Any
from pydantic import BaseModel


# ── HEBCS / Ω Wellness Score ──────────────────────────────────
class HEBCSBiomarkerDetail(BaseModel):
    name: str
    value: float | None = None
    score: float | None = None
    weight: float
    opt_range: list[float | None]
    #: "measured" (a lab reported it) or "derived" (computed from other labs —
    #: nPCR from urea kinetics). A computed marker must never be shown to a
    #: clinician as though a lab had reported it.
    source: str | None = None
    #: "reported" (a lab stated this range) or "published_band" (the framework's
    #: constant, specific to no one). A constant must never pass for a range
    #: someone measured.
    band_source: str | None = None


class HEBCSPathwayResult(BaseModel):
    score: float | None = None
    weight: float
    #: Fraction of this pathway's biomarker WEIGHT that was actually measured.
    #: A pathway renormalised over part of its evidence is not the same claim as
    #: one computed from all of it — Nutritional reading 100% off albumin and BUN
    #: alone, with nPCR missing, is how a malnourished patient saw "Nutrition
    #: 100%". The number now travels with what it rests on.
    coverage: float = 0.0
    #: Coverage once computed markers count. Kept separate so `coverage` never
    #: quietly absorbs an estimate.
    coverage_with_derived: float = 0.0
    measured: int = 0
    derived: int = 0
    expected: int = 0
    biomarkers: list[HEBCSBiomarkerDetail] = []


class HEBCSScoreResponse(BaseModel):
    """HEBCS Ω score — trapezoidal biomarker scoring across 7 ESRD pathways."""
    computed_at: datetime
    lab_date_used: date | None = None
    #: None when NO pathway scored. A patient with no labs must not be handed a
    #: number; 0.5 used to be returned, which reads as "50% well".
    omega: float | None = None                # ∈ (0, 1)
    omega_pct: float | None = None            # Ω × 100, interpretable 0–100
    data_coverage: float                      # fraction of expected biomarkers with values
    pathways: dict[str, HEBCSPathwayResult]
    #: Pathways with no usable biomarker at all. Omega is a weighted geometric
    #: mean over the pathways that scored, so an unmeasured one simply vanishes
    #: from a number presented as whole-patient. Naming them is the difference
    #: between a score and a claim.
    unscored_pathways: list[str] = []
    interpretation: str


# ── HEBCS What-If Simulator ────────────────────────────────────
class WhatIfRequest(BaseModel):
    """Hypothetical biomarker overrides for What-If scenario analysis.
    Any field left None will use the patient's most recent real value.
    """
    scenario_name: str = "custom"
    # Key biomarkers that patients can realistically influence
    Phosphorus: float | None = None        # mg/dL — dietary restriction
    Potassium: float | None = None         # mEq/L — dietary restriction
    Albumin: float | None = None           # g/dL — nutrition intervention
    Hemoglobin: float | None = None        # g/dL — ESA therapy
    Ferritin: float | None = None          # µg/L — iron supplementation
    KtV_Dialysis_Adequacy: float | None = None   # dialysis session length/frequency
    URR_Urea_Reduction_Ratio: float | None = None
    # Additional metabolic markers
    Glucose: float | None = None
    Sodium: float | None = None
    Calcium: float | None = None
    PTH_Intact: float | None = None        # pg/mL — vitamin D / cinacalcet

    def to_biomarker_dict(self) -> dict[str, float]:
        """Convert request to {test_name: value} dict, skipping None fields."""
        mapping = {
            "Phosphorus": self.Phosphorus,
            "Potassium": self.Potassium,
            "Albumin": self.Albumin,
            "Hemoglobin": self.Hemoglobin,
            "Ferritin": self.Ferritin,
            "KtV (Dialysis Adequacy)": self.KtV_Dialysis_Adequacy,
            "URR (Urea Reduction Ratio)": self.URR_Urea_Reduction_Ratio,
            "Glucose": self.Glucose,
            "Sodium": self.Sodium,
            "Calcium": self.Calcium,
            "PTH (Intact)": self.PTH_Intact,
        }
        return {k: v for k, v in mapping.items() if v is not None}


class WhatIfPathwayDelta(BaseModel):
    baseline_score: float | None = None
    scenario_score: float | None = None
    delta: float | None = None


class WhatIfResponse(BaseModel):
    scenario_name: str
    baseline_omega: float
    scenario_omega: float
    delta_omega: float          # scenario_omega − baseline_omega
    delta_pct: float            # percentage-point change × 100
    pathway_deltas: dict[str, WhatIfPathwayDelta]
    overridden_biomarkers: list[str]
    interpretation: str


# ── Wellness Score ────────────────────────────────────────────
class WellnessScoreResponse(BaseModel):
    id: int | None = None
    user_id: int | None = None
    score_date: date
    #: None when NOTHING was measured. A 0 — or the old default of ~50 — for a
    #: patient we have no data on is a claim we cannot support.
    overall_score: float | None = None
    nutrition_score: float | None = None
    fitness_score: float | None = None
    sleep_score: float | None = None
    mood_score: float | None = None
    vitals_score: float | None = None
    medication_adherence_score: float | None = None
    #: Fraction of the intended picture that had data behind it.
    confidence: float | None = None
    #: Domains with no data. They are excluded from the score rather than
    #: scored 0, so naming them is what stops the number reading as a verdict
    #: on domains nobody measured.
    components_unknown: list[str] = []
    #: Per-domain working: which nutrients fell short, which drugs were not
    #: logged, why BMI was excluded. A number is never the whole message.
    detail: dict | None = None
    explanation: str | None = None
    recommendations: str | None = None
    created_at: datetime | None = None
    model_config = {"from_attributes": True}


# ── Health Trend Analysis ────────────────────────────────────
class TrendDataPoint(BaseModel):
    date: str
    value: float | None = None
    label: str | None = None


class TrendStream(BaseModel):
    name: str
    data: list[TrendDataPoint] = []
    trend: str | None = None  # improving, declining, stable
    change_pct: float | None = None


class HealthTrendResponse(BaseModel):
    overall_summary: str
    streams: list[TrendStream] = []
    correlations: list[str] = []
    suggestions: list[str] = []


# ── Daily Recommendations ────────────────────────────────────
class RecommendationItem(BaseModel):
    category: str
    title: str
    description: str
    priority: str = "medium"  # low, medium, high
    action: str | None = None


class DailyRecommendationsResponse(BaseModel):
    date: str
    recommendations: list[RecommendationItem] = []
    nutrition: list[RecommendationItem] = []
    fitness: list[RecommendationItem] = []
    sleep: list[RecommendationItem] = []
    medication: list[RecommendationItem] = []
    mood: list[RecommendationItem] = []
    hydration: list[RecommendationItem] = []
    general: list[RecommendationItem] = []


# ── Health Improvements ──────────────────────────────────────
class HealthImprovementsResponse(BaseModel):
    summary: str
    wellness_score: float | None = None
    nutrition_improvements: list[str] = []
    fitness_improvements: list[str] = []
    sleep_improvements: list[str] = []
    mood_improvements: list[str] = []
    medical_improvements: list[str] = []


# ── Lab Comparison Charts ────────────────────────────────────
class LabChartPoint(BaseModel):
    date: str
    value: float | None = None


class LabChartSeries(BaseModel):
    test_name: str
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    data: list[LabChartPoint] = []


class LabChartGroup(BaseModel):
    group_name: str
    series: list[LabChartSeries] = []


LAB_CHART_GROUPS = {
    "Lipid Panel": ["Total Cholesterol", "LDL", "HDL", "Triglycerides", "LDL Cholesterol", "HDL Cholesterol"],
    "Kidney Function": ["BUN", "Creatinine", "eGFR", "GFR", "Potassium", "Phosphorus", "Calcium"],
    "Metabolic / Electrolytes": ["Glucose", "Sodium", "Potassium", "Chloride", "CO2", "Calcium", "Phosphate", "Magnesium"],
    "CBC": ["WBC", "RBC", "Hemoglobin", "Hematocrit", "Platelets", "MCV", "MCH", "MCHC", "RDW"],
    "Iron / Anemia": ["Iron", "Serum Iron", "Ferritin", "TIBC", "Transferrin Saturation", "Transferrin Sat"],
    "TSH": ["TSH"],
    "Liver Enzymes": ["AST", "ALT", "ALP", "Alkaline Phosphatase", "Bilirubin", "Total Bilirubin", "Albumin", "Total Protein"],
}


# ── Meal Planner ─────────────────────────────────────────────
class MealItem(BaseModel):
    name: str
    description: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None


class DayMeals(BaseModel):
    day: str
    breakfast: MealItem | None = None
    morning_snack: MealItem | None = None
    lunch: MealItem | None = None
    afternoon_snack: MealItem | None = None
    dinner: MealItem | None = None


class MealPlanRequest(BaseModel):
    dietary_pattern: str = "balanced"
    days: int = 7
    daily_calorie_target: float | None = None
    restrictions: list[str] = []
    preferences: list[str] = []


class MealPlanResponse(BaseModel):
    id: int | None = None
    plan_name: str
    dietary_pattern: str
    start_date: date
    end_date: date
    weekly_plan: list[DayMeals] = []
    shopping_list: list[str] = []
    advice: str | None = None
    total_daily_calories: float | None = None
    created_at: datetime | None = None
    model_config = {"from_attributes": True}


# ── AI Meal Suggestions (goals + pantry aware) ───────────────
class MealSuggestionRequest(BaseModel):
    """Conversational meal-planner input (matches the AI Meal Planner UI)."""
    health_goals: str = ""
    preferences: str | None = None     # likes / dislikes, free text
    pantry_items: str | None = None    # comma/newline list of on-hand ingredients
    count: int = 3                     # how many meal suggestions to return


class MealSuggestion(BaseModel):
    name: str
    meal_type: str = "meal"            # breakfast | lunch | dinner | snack | meal
    description: str = ""
    ingredients: list[str] = []
    pantry_used: list[str] = []        # which of the user's pantry items it uses
    missing_items: list[str] = []      # ingredients to buy (not in the pantry)
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    rationale: str = ""                # why it fits the patient's goals / labs / conditions


class MealSuggestionsResponse(BaseModel):
    goals: str = ""
    suggestions: list[MealSuggestion] = []
    shopping_list: list[str] = []      # aggregated unique missing items across suggestions
    advice: str = ""
    used_ai: bool = True
    pantry_saved: int = 0              # # of pantry items persisted to the profile


# ── Exercise Planner ─────────────────────────────────────────
class ExerciseItem(BaseModel):
    name: str
    type: str  # warmup, cardio, strength, flexibility, cooldown
    duration_minutes: int | None = None
    sets: int | None = None
    reps: int | None = None
    notes: str | None = None


class DayWorkout(BaseModel):
    day: str
    focus: str  # upper_body, lower_body, cardio, rest, full_body
    exercises: list[ExerciseItem] = []
    total_minutes: int | None = None


class ExercisePlanRequest(BaseModel):
    fitness_level: str = "moderate"
    days: int = 7
    weekly_minutes_target: int | None = None
    goals: list[str] = []
    preferred_activities: list[str] = []
    conditions: list[str] = []


class ExercisePlanResponse(BaseModel):
    id: int | None = None
    plan_name: str
    fitness_level: str
    start_date: date
    end_date: date
    weekly_plan: list[DayWorkout] = []
    advice: str | None = None
    weekly_minutes_target: int | None = None
    created_at: datetime | None = None
    model_config = {"from_attributes": True}


# ── Image AI ─────────────────────────────────────────────────
class NutritionFromImageResponse(BaseModel):
    food_items: list[dict] = []
    total_calories: float | None = None
    total_protein_g: float | None = None
    total_carbs_g: float | None = None
    total_fat_g: float | None = None
    notes: str | None = None


class MedicationFromImageResponse(BaseModel):
    medication_name: str | None = None
    dosage: str | None = None
    instructions: str | None = None
    ndc_code: str | None = None
    manufacturer: str | None = None
    fields: list[dict] = []
    notes: str | None = None


class DosageVerificationRequest(BaseModel):
    medication_name: str
    dosage: str
    frequency: str | None = None


class DosageVerificationResponse(BaseModel):
    medication_name: str
    dosage: str
    is_typical: bool
    feedback: str
    typical_range: str | None = None
    precautions: list[str] = []


# ── PDF Tools / document import ──────────────────────────────
#
# Field names here are the ones web, iOS and Android already decode. They were
# previously served under different names (doctor_name, raw_text, items[].name),
# so every client rendered blanks even when a parse succeeded.

class LabReportItem(BaseModel):
    test_name: str
    value: str | None = None          # string: carries "< 9" and "Error" intact
    unit: str | None = None
    reference_range: str | None = None
    is_abnormal: bool | None = None
    category: str | None = None
    test_date: str | None = None
    confidence: float | None = None
    source_label: str | None = None   # what the document literally said
    dedupe_status: str | None = None  # new | duplicate | conflict
    item_id: int | None = None
    accepted: bool | None = None
    note: str | None = None


class LabReportParseResponse(BaseModel):
    patient_name: str | None = None
    report_date: str | None = None
    lab_name: str | None = None
    ordering_physician: str | None = None
    items: list[LabReportItem] = []
    raw_text_preview: str | None = None
    parsing_notes: list[str] = []

    # Import + classification context.
    import_id: int | None = None
    doc_type: str | None = None
    doc_type_confidence: float | None = None
    confidence: float | None = None
    target_table: str | None = None
    page_count: int | None = None
    #: Set when nothing could be read. Clients must show this rather than an
    #: empty table — an error and an empty result mean opposite things.
    error: str | None = None
    already_imported: bool = False


class DocumentImportSummary(BaseModel):
    id: int
    filename: str | None = None
    doc_type: str | None = None
    status: str
    page_count: int | None = None
    parse_confidence: float | None = None
    report_date: str | None = None
    lab_name: str | None = None
    item_count: int = 0
    new_count: int = 0
    duplicate_count: int = 0
    conflict_count: int = 0
    created_at: str | None = None
    error_detail: str | None = None


class DocumentImportDetail(DocumentImportSummary):
    patient_name: str | None = None
    ordering_provider: str | None = None
    target_table: str | None = None
    layout_kind: str | None = None
    extraction_method: str | None = None
    notes: list[str] = []
    items: list[LabReportItem] = []


class ConfirmImportRequest(BaseModel):
    #: Item ids to write. Omit to use the staged decisions, which already
    #: exclude duplicates.
    accepted_item_ids: list[int] | None = None


class ConfirmImportResponse(BaseModel):
    import_id: int
    status: str
    imported: dict[str, int] = {}
    total_imported: int = 0
    message: str | None = None


class FlowsheetPDFRequest(BaseModel):
    session_type: str = "hemodialysis"   # hemodialysis, peritoneal_dialysis
    days: int = 30
    #: Optional: render one session instead of a date range.
    session_id: int | None = None
    include_vitals_chart: bool = True


class FlowsheetResponse(BaseModel):
    title: str
    generated_at: str
    content: str
    session_count: int
    #: Where to fetch the same report as a PDF.
    pdf_url: str | None = None


# ── FDA Recalls ──────────────────────────────────────────────
class FDARecallItem(BaseModel):
    product_type: str = "food"   # "food" | "drug"
    source: str = "openFDA (US)"  # issuing authority
    url: str | None = None        # link to the official notice
    recall_number: str | None = None
    reason: str | None = None
    status: str | None = None
    distribution: str | None = None
    product_description: str | None = None
    recalling_firm: str | None = None
    recall_initiation_date: str | None = None
    report_date: str | None = None
    classification: str | None = None
    voluntary_mandated: str | None = None
    # Geographic coverage (for the map overlay)
    city: str | None = None
    state: str | None = None
    country: str | None = None
    states: list[str] = []      # US state codes parsed from the distribution pattern
    countries: list[str] = []   # all ISO-2 countries the recall reached (incl. source)
    nationwide: bool = False


class FDARecallResponse(BaseModel):
    total: int = 0
    results: list[FDARecallItem] = []


# ── Clinician Dashboard ─────────────────────────────────────
class PatientSummary(BaseModel):
    user_id: int
    full_name: str
    email: str | None = None
    latest_vitals: dict | None = None
    latest_mood: dict | None = None
    latest_labs: list[dict] = []
    conditions: list[str] = []
    medications: list[str] = []
    permissions: list[str] = []
    last_activity: str | None = None


class ClinicianDashboardResponse(BaseModel):
    role: str
    patient_count: int = 0
    patients: list[PatientSummary] = []
