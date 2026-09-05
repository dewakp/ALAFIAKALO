"""AI Learning Engine — RLAIF Collective Learning + GlobalKnowledge Evidence Base.

Three responsibilities:
1. GlobalKnowledge seeding: pre-loads ESRD/CKD clinical guidelines into the DB
   so specialist agents can cite them as evidence.
2. RLAIF cycle: aggregates user feedback (was_helpful, was_followed) from
   AIInteraction records → discovers patterns via LLM → writes CollectiveInsight
   rows → injected into future system prompts.
3. Outcome reward: after was_followed=True, compares pre/post biomarker trends
   to compute recommendation_quality_score.
"""

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.ai_memory import AIInteraction, CollectiveInsight, GlobalKnowledge, LearningEvent
from app.models.labs import LabResult
from app.models.user import User

router = APIRouter()

# ── ESRD/CKD Evidence Base ─────────────────────────────────────────────────────
# 20 evidence-based clinical facts pre-loaded into GlobalKnowledge.
# Specialist agents query these at prompt-build time and inject them as
# "EVIDENCE NOTES" so responses cite real guidelines (KDOQI, KDIGO, etc.).

ESRD_EVIDENCE_BASE = [
    # ── NEPHROLOGY ───────────────────────────────────────────────────────────
    {
        "knowledge_type": "guideline",
        "domain": "nephrology",
        "topic": "dialysis_adequacy",
        "title": "KDOQI: Hemodialysis Adequacy Minimum Targets",
        "summary": (
            "Single-pool KtV (spKtV) ≥1.2 per session is the minimum target (KDOQI). "
            "URR ≥65% is the equivalent target. KtV <1.0 = severely inadequate dialysis. "
            "DOPPS data: each 0.1 rise in KtV is associated with a ~7% reduction in mortality."
        ),
        "key_points": [
            "spKtV ≥1.2 minimum; URR ≥65% equivalent",
            "KtV <1.0 = severely inadequate, urgent review needed",
            "Target KtV 1.4–1.5 in practice for safety margin",
            "DOPPS: 7% mortality reduction per 0.1 KtV increase",
        ],
        "source_organization": "KDOQI / DOPPS",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "nephrology",
        "topic": "phosphorus_management",
        "title": "KDIGO 2017: Phosphorus Target for Dialysis Patients",
        "summary": (
            "Target serum phosphorus <5.5 mg/dL (KDIGO 2017). Values >5.5 mg/dL drive secondary "
            "hyperparathyroidism and vascular calcification. Values >7.0 mg/dL are crisis level. "
            "Both dietary restriction (<1,000 mg/day) and phosphate binders taken WITH meals are required."
        ),
        "key_points": [
            "Target: <5.5 mg/dL",
            ">5.5 = elevated; >7.0 = crisis — urgent review",
            "Binders (Sevelamer, CaCO₃) must be taken at the START of each meal",
            "Additive phosphates in processed foods (E450–452) are most bioavailable — read labels",
        ],
        "source_organization": "KDIGO CKD-MBD 2017",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "nephrology",
        "topic": "potassium_management",
        "title": "Hyperkalemia Critical Thresholds in ESRD",
        "summary": (
            "Pre-dialysis K⁺ target: 3.5–5.5 mEq/L. K⁺ >5.5 mEq/L = hyperkalemia, arrhythmia risk — "
            "urgent dietary review. K⁺ >6.5 mEq/L = EMERGENCY, immediate contact with care team. "
            "Dietary restriction: <2,000–3,000 mg/day of potassium."
        ),
        "key_points": [
            "Target K⁺: 3.5–5.5 mEq/L",
            ">5.5 = URGENT (arrhythmia risk)",
            ">6.5 = EMERGENCY — call care team immediately",
            "Restrict: bananas, oranges, tomatoes, potatoes, avocado, beans, dairy, salt substitutes (KCl)",
            "Dietary K⁺ limit: 2,000–3,000 mg/day",
        ],
        "source_organization": "KDOQI / KDIGO",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "nephrology",
        "topic": "pth_bone_disease",
        "title": "KDIGO CKD-MBD: PTH Target and Bone Disease",
        "summary": (
            "Intact PTH (iPTH) target for dialysis patients: 150–600 pg/mL (KDIGO 2017). "
            "iPTH <150 = adynamic bone disease (fracture risk, bone pain). "
            "iPTH >600 = secondary hyperparathyroidism (bone resorption, vascular calcification). "
            "Calcium target: 8.4–9.5 mg/dL. Phosphorus and active Vitamin D directly control PTH secretion."
        ),
        "key_points": [
            "iPTH target: 150–600 pg/mL",
            "<150 = adynamic bone disease (oversuppressed)",
            ">600 = secondary hyperparathyroidism",
            "Ca target: 8.4–9.5 mg/dL",
            "Treat high phosphorus first — it drives secondary HPT",
        ],
        "source_organization": "KDIGO CKD-MBD 2017",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "nephrology",
        "topic": "anemia_management",
        "title": "KDIGO 2012: Anemia of CKD — Hemoglobin and Iron Targets",
        "summary": (
            "Hemoglobin target for dialysis patients: 10–11.5 g/dL. Avoid Hb >13 g/dL (thrombosis risk). "
            "Ferritin >200 µg/L and TSAT >20% are required before starting ESA therapy. "
            "IV iron is preferred over oral iron in HD patients (oral iron is poorly absorbed due to uremia). "
            "Hb <8 g/dL = severe anemia, exercise is contraindicated."
        ),
        "key_points": [
            "Hb target: 10–11.5 g/dL",
            "Hb >13: avoid (increased thrombosis/stroke risk with ESA)",
            "Ferritin <200 µg/L or TSAT <20% = iron deficient",
            "IV iron preferred in HD patients",
            "Hb <8 g/dL = contraindication to aerobic exercise",
        ],
        "source_organization": "KDIGO Anemia 2012",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "nephrology",
        "topic": "albumin_nutritional_status",
        "title": "KDOQI 2020: Albumin as Nutritional Marker in ESRD",
        "summary": (
            "Serum albumin <3.5 g/dL = significant malnutrition. Albumin <3.0 g/dL = severe malnutrition, "
            "strong mortality predictor. Target albumin: >4.0 g/dL. HD patients need 1.2 g/kg/day protein "
            "(NOT the 0.6–0.8g/kg of pre-dialysis CKD — dialysis is catabolic and dialysate removes amino acids)."
        ),
        "key_points": [
            "Albumin target: >4.0 g/dL",
            "<3.5 = malnutrition; <3.0 = severe malnutrition",
            "HD protein needs: 1.2–1.4 g/kg/day (higher than pre-dialysis CKD)",
            "Low albumin predicts hospitalisation and mortality",
        ],
        "source_organization": "KDOQI Nutrition 2020",
        "evidence_level": "high",
    },

    # ── RENAL NUTRITION ──────────────────────────────────────────────────────
    {
        "knowledge_type": "guideline",
        "domain": "renal_nutrition",
        "topic": "potassium_restricted_diet",
        "title": "Renal Diet: Dietary Potassium Restriction for HD Patients",
        "summary": (
            "HD patients should limit potassium to 2,000–3,000 mg/day. "
            "Highest-K foods: bananas (422mg), avocado (708mg), potato (897mg), sweet potato (540mg), "
            "spinach (839mg raw), beans (717mg/cup). Leaching vegetables (boil in large water, discard water) "
            "reduces potassium by 50–70%. Salt substitutes contain KCl — completely avoid."
        ),
        "key_points": [
            "Limit: 2,000–3,000 mg/day",
            "Leaching reduces K by 50–70% (boil, discard water, rinse)",
            "Salt substitutes = KCl — dangerous for ESRD patients",
            "Potassium accumulates between sessions — spread intake across the day",
            "Frozen vegetables have less K than canned (canning leaches K into brine, which is then discarded)",
        ],
        "source_organization": "NKF / Renal Dietitians Australasia",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "renal_nutrition",
        "topic": "phosphorus_restricted_diet",
        "title": "Renal Diet: Phosphorus Restriction and Phosphate Binder Timing",
        "summary": (
            "Limit phosphorus to 800–1,000 mg/day. Worst offenders: dairy products, cola drinks, "
            "processed meats containing additive phosphates (listed as E450, E451, E452 in ingredients — "
            "most bioavailable form), whole grains, nuts, seeds, beer. "
            "Phosphate binders MUST be taken at the START of each meal (first bite), not before or after."
        ),
        "key_points": [
            "Limit: 800–1,000 mg/day",
            "Additive phosphates (E450–452 in processed foods) = 100% absorbed vs 40–60% from natural sources",
            "Sevelamer preferred (no calcium/aluminium load)",
            "Binders with meals only — not fasting or post-meal",
            "Vegetable protein (plant-based) has less bioavailable phosphorus than animal protein",
        ],
        "source_organization": "KDOQI Nutrition / Journal of Renal Nutrition",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "renal_nutrition",
        "topic": "fluid_restriction",
        "title": "Fluid Management: Interdialytic Weight Gain Targets",
        "summary": (
            "Target interdialytic weight gain: <1.5 kg/day, <3 kg/session. "
            "Weight gain >3 kg/session is associated with haemodynamic instability during dialysis. "
            "Total fluid intake = urine output + 500–750 mL (insensible losses). "
            "Reducing sodium intake (<2g/day) reduces thirst and is the most effective intervention for fluid control."
        ),
        "key_points": [
            "Target: <1.5 kg/day, <3 kg/session",
            ">3 kg: high risk for intradialytic hypotension",
            "Fluid = all liquids: soup, ice cream, gelatin, fruit juices",
            "Low sodium (<2g/day) is the most effective thirst/fluid management strategy",
            "Track daily weight same time each morning",
        ],
        "source_organization": "KDOQI 2015",
        "evidence_level": "high",
    },

    # ── CARDIOLOGY ───────────────────────────────────────────────────────────
    {
        "knowledge_type": "guideline",
        "domain": "cardiology",
        "topic": "bp_target_dialysis",
        "title": "KDIGO 2021: Blood Pressure Targets in HD Patients",
        "summary": (
            "Pre-dialysis BP target: <140/90 mmHg. Post-dialysis: <130/80 mmHg. "
            "Interdialytic hypertension (BP rises between sessions) is linked to sodium/fluid excess. "
            "ESRD patients have 10–20× higher cardiovascular mortality than the general population. "
            "ACE inhibitors and ARBs reduce LV hypertrophy and mortality independent of BP effect."
        ),
        "key_points": [
            "Pre-HD BP target: <140/90 mmHg",
            "Post-HD target: <130/80 mmHg",
            "ESRD cardiovascular mortality: 10–20× general population",
            "ACE-I/ARBs reduce LVH independently of BP (use them)",
            "Home BP self-monitoring preferred — clinic BP is unreliable in HD patients",
        ],
        "source_organization": "KDIGO BP 2021 / AHA",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "research_finding",
        "domain": "cardiology",
        "topic": "lv_hypertrophy_esrd",
        "title": "Left Ventricular Hypertrophy: Prevalence and Drivers in ESRD",
        "summary": (
            "LVH is present in ~75% of dialysis patients at initiation and is the strongest single predictor "
            "of cardiac death in ESRD. Key drivers: hypertension (pressure overload), fluid overload "
            "(volume overload → increased preload), anaemia (high-output state), AV fistula "
            "(left-to-right shunt contributing to LV dilation). Treating all four causes regresses LVH."
        ),
        "key_points": [
            "LVH prevalence in ESRD: ~75% at dialysis start",
            "LVH = strongest individual predictor of CV death in ESRD",
            "Drivers: HTN + fluid + anaemia + AVF (all four must be addressed)",
            "Every 10 mmHg BP reduction → significant LVH regression",
            "Correcting anaemia (Hb to 10–11.5) reduces cardiac output burden",
        ],
        "source_organization": "USRDS / DOPPS / Zoccali et al. NEJM",
        "evidence_level": "high",
    },

    # ── MENTAL HEALTH ────────────────────────────────────────────────────────
    {
        "knowledge_type": "research_finding",
        "domain": "mental_health",
        "topic": "depression_dialysis",
        "title": "Depression in Dialysis Patients: Prevalence and Impact",
        "summary": (
            "Depression affects 25–40% of dialysis patients — 5× higher than the general population. "
            "Depressed dialysis patients have 1.5–2× higher mortality risk. Depression strongly predicts "
            "non-adherence to dialysis schedule, dietary restrictions, and medications. "
            "PHQ-9 ≥10 = moderate depression. CBT is first-line before pharmacotherapy."
        ),
        "key_points": [
            "Prevalence: 25–40% in dialysis vs ~8% general population",
            "PHQ-9 ≥10 = moderate depression requiring clinical attention",
            "Depression → 1.5–2× mortality increase",
            "Non-adherence is often depression as root cause — not wilfulness",
            "CBT and behavioural activation are first-line treatments",
        ],
        "source_organization": "KDQOL / DOPPS / APA",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "best_practice",
        "domain": "mental_health",
        "topic": "coping_strategies_esrd",
        "title": "Evidence-Based Coping Strategies for ESRD and Chronic Illness",
        "summary": (
            "Most effective psychological interventions for ESRD: 1) Behavioural Activation — scheduling "
            "enjoyable activities despite fatigue; 2) Cognitive Restructuring — challenging catastrophising "
            "thoughts; 3) Acceptance and Commitment Therapy (ACT) — accept illness, commit to valued life; "
            "4) Peer support — HD patients benefit significantly from kidney disease community; "
            "5) Meaning-Making — finding purpose beyond the illness."
        ),
        "key_points": [
            "Behavioural activation: 1–2 enjoyable activities/week regardless of energy level",
            "Social support: 50% lower depression risk with strong social ties",
            "Sleep hygiene: 60–80% of ESRD patients have sleep disorders (RLS, apnea)",
            "Fatigue pacing: plan activities for the day after dialysis — not the dialysis day",
            "Peer support groups are the most effective non-pharmacological intervention",
        ],
        "source_organization": "APA / Cochrane / KDQOL",
        "evidence_level": "moderate",
    },

    # ── EXERCISE PHYSIOLOGY ──────────────────────────────────────────────────
    {
        "knowledge_type": "guideline",
        "domain": "exercise_physiology",
        "topic": "intradialytic_exercise",
        "title": "Cochrane 2022: Intradialytic Exercise Safety and Efficacy",
        "summary": (
            "Exercise DURING the first 2 hours of a 4-hour HD session is safe and beneficial. "
            "Benefits: improves KtV by 5–10% (enhanced solute mobilisation from tissue compartments), "
            "reduces post-dialysis fatigue by ~30%, improves cardiovascular fitness, muscle strength. "
            "Stationary cycling on the dialysis chair is the most practical modality. "
            "Contraindications: systolic BP <90 pre-exercise, recent vascular access surgery (<6 weeks)."
        ),
        "key_points": [
            "Safe timing: first 2 hours of HD session only",
            "Improves KtV by 5–10% (better toxin clearance)",
            "Reduces post-dialysis fatigue by ~30%",
            "Best modality: stationary bike on the dialysis chair",
            "Avoid: exercise on the fistula arm; stop if BP drops >20 mmHg",
        ],
        "source_organization": "Cochrane Systematic Review 2022 / DOPPS",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "guideline",
        "domain": "exercise_physiology",
        "topic": "exercise_safety_esrd",
        "title": "ACSM: Exercise Safety Guidelines for ESRD Patients",
        "summary": (
            "Absolute contraindications: uncontrolled hypertension (>180/110 mmHg), severe anaemia "
            "(Hb <8 g/dL), recent cardiac event (<6 weeks), active vascular access infection. "
            "The fistula arm must NOT be used for heavy resistance exercise, blood pressure measurement, "
            "or IV access. Recommended intensity: RPE 12–14 (moderate). "
            "Non-dialysis days are preferred for higher-intensity sessions than HD days."
        ),
        "key_points": [
            "Stop if BP >180/110 or if systolic drops >20 mmHg during exercise",
            "Hb <8 g/dL = defer exercise until anaemia is treated",
            "NEVER stress the fistula arm",
            "RPE 12–14 (moderate) is the safe zone",
            "Non-dialysis days preferred for higher-intensity work",
        ],
        "source_organization": "ACSM / Renal Rehabilitation Guidelines",
        "evidence_level": "high",
    },

    # ── DIALYSIS NURSING ─────────────────────────────────────────────────────
    {
        "knowledge_type": "guideline",
        "domain": "dialysis_nursing",
        "topic": "vascular_access_care",
        "title": "KDOQI 2019: AV Fistula Self-Care and Monitoring",
        "summary": (
            "AV fistula (AVF) is gold-standard access. Daily self-monitoring: feel the thrill (vibration) "
            "and listen for the bruit (humming sound) every morning. Change in thrill/bruit = possible stenosis — "
            "notify the dialysis team immediately. NEVER allow BP cuff, blood draw, or IV line in the fistula arm. "
            "Avoid constrictive clothing, watches, sleeping on the fistula arm. "
            "AVF takes 3–6 months to mature; early access is the most common cause of failure."
        ),
        "key_points": [
            "Daily check: feel thrill (vibration), listen for bruit (hum)",
            "Loss of thrill/bruit = call dialysis centre immediately",
            "NEVER: BP cuff, blood draw, or IV in the fistula arm",
            "NEVER: sleep on fistula arm or wear tight watches",
            "Maturation: 3–6 months before first cannulation",
        ],
        "source_organization": "KDOQI Vascular Access 2019",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "best_practice",
        "domain": "dialysis_nursing",
        "topic": "interdialytic_monitoring",
        "title": "Interdialytic Weight Monitoring and Fluid Safety Alerts",
        "summary": (
            "Weigh every morning at the same time, same scale, after waking and voiding but before eating. "
            "Alert care team if: >2 kg gain in one day, shortness of breath at rest or lying flat, "
            "ankle/leg swelling, inability to lie flat (orthopnea). "
            "Post-dialysis hypotension (systolic <90 mmHg or drop >20 mmHg) is the most common HD complication — "
            "suggests fluid was removed too aggressively or dry weight needs adjustment."
        ),
        "key_points": [
            "Daily weight → alert if >2 kg gain/day or >3 kg total since last session",
            "Alert: shortness of breath at rest or lying flat",
            "Alert: ankle/leg swelling that wasn't there before",
            "Post-HD hypotension: systolic <90 or >20 mmHg drop",
            "Cramps during HD = fluid removal too fast or electrolyte imbalance",
        ],
        "source_organization": "ANNA Renal Nursing Standards 2023",
        "evidence_level": "high",
    },

    # ── GENERAL PRACTICE ─────────────────────────────────────────────────────
    {
        "knowledge_type": "best_practice",
        "domain": "general_practice",
        "topic": "polypharmacy_esrd",
        "title": "Medication Safety and Polypharmacy in ESRD",
        "summary": (
            "Dialysis patients take an average of 10–15 medications daily. Critical safety concerns: "
            "NSAIDs are CONTRAINDICATED in patients with residual renal function (accelerate CKD progression). "
            "ACE-I and ARBs raise serum potassium — titrate carefully. Some drugs are dialysed out and need "
            "supplemental post-HD dosing (certain antibiotics, some antiepileptics). "
            "QT-prolonging drugs are particularly dangerous with electrolyte abnormalities (K⁺, Mg²⁺)."
        ),
        "key_points": [
            "NSAIDs: CONTRAINDICATED if residual renal function remains",
            "ACE-I/ARBs + high K⁺ diet = dangerous hyperkalaemia combination",
            "Post-HD supplemental dosing: required for some antibiotics (vancomycin, acyclovir)",
            "QT prolongation risk: amplified by K⁺ <3.5 or Mg²⁺ <0.8",
            "Medication reconciliation at every clinical visit",
        ],
        "source_organization": "KDOQI / FDA Renal Dosing Database / BNF Renal",
        "evidence_level": "high",
    },
    {
        "knowledge_type": "research_finding",
        "domain": "general_practice",
        "topic": "sleep_esrd",
        "title": "Sleep Disorders in ESRD: 60–80% Prevalence",
        "summary": (
            "Sleep disorders affect 60–80% of dialysis patients. Most common: restless legs syndrome (RLS) — "
            "linked to iron deficiency and uraemia; obstructive sleep apnea (worsened by fluid overload causing "
            "upper airway oedema); insomnia. RLS improvement correlates strongly with correction of iron "
            "deficiency (ferritin, TSAT). Sleep deprivation worsens fatigue, depression, and dialysis tolerance."
        ),
        "key_points": [
            "Sleep disorders: 60–80% in ESRD vs ~15% general population",
            "RLS: treat iron deficiency first (ferritin, TSAT)",
            "Fluid overload causes pharyngeal oedema → worsens sleep apnea",
            "Dialysis schedule (Mon/Wed/Fri) fragments sleep patterns",
            "Poor sleep → worse fatigue, lower mood, poorer dietary adherence",
        ],
        "source_organization": "KDQOL / AASM / DOPPS Sleep Data",
        "evidence_level": "moderate",
    },
]


# ── Service functions ─────────────────────────────────────────────────────────

async def seed_global_knowledge(db: AsyncSession) -> int:
    """
    Insert ESRD_EVIDENCE_BASE entries into global_knowledge if not already present.
    Idempotent: skips entries where (domain, topic) already exists.
    Returns the number of new entries inserted.
    """
    inserted = 0
    for item in ESRD_EVIDENCE_BASE:
        existing = await db.execute(
            select(GlobalKnowledge).where(
                GlobalKnowledge.domain == item["domain"],
                GlobalKnowledge.topic == item["topic"],
            )
        )
        if existing.scalar_one_or_none():
            continue
        gk = GlobalKnowledge(
            knowledge_type=item["knowledge_type"],
            domain=item["domain"],
            topic=item["topic"],
            title=item["title"],
            summary=item["summary"],
            key_points=item.get("key_points"),
            source_organization=item["source_organization"],
            evidence_level=item["evidence_level"],
            is_active=True,
        )
        db.add(gk)
        inserted += 1
    if inserted:
        await db.commit()
    return inserted


async def fetch_domain_knowledge(domain: str, db: AsyncSession, limit: int = 3) -> list[GlobalKnowledge]:
    """Return active GlobalKnowledge entries for a given specialist domain."""
    result = await db.execute(
        select(GlobalKnowledge)
        .where(GlobalKnowledge.domain == domain, GlobalKnowledge.is_active == True)
        .order_by(desc(GlobalKnowledge.relevance_score))
        .limit(limit)
    )
    return result.scalars().all()


async def run_rlaif_cycle(user_id: int, db: AsyncSession) -> dict:
    """
    RLAIF learning cycle:
    1. Load helpful AIInteraction records for this user
    2. Group by category
    3. Use Ollama to extract the pattern that made responses helpful
    4. Write or update CollectiveInsight rows (scoped to this user)
    5. Write LearningEvent audit entries
    Returns a summary dict.
    """
    # Load helpful interactions
    helpful_result = await db.execute(
        select(AIInteraction)
        .where(AIInteraction.user_id == user_id, AIInteraction.was_helpful == True)
        .order_by(desc(AIInteraction.created_at))
        .limit(50)
    )
    helpful = helpful_result.scalars().all()

    # Group by category
    category_groups: dict[str, list[AIInteraction]] = defaultdict(list)
    for ix in helpful:
        category_groups[ix.category].append(ix)

    insights_created = 0
    insights_updated = 0

    for category, interactions in category_groups.items():
        # Build examples list for Ollama
        examples = [
            f"Q: {ix.user_request[:200]}\nA: {ix.ai_response[:400]}"
            for ix in interactions[:5]
            if ix.user_request and ix.ai_response
        ]
        if not examples:
            continue

        # Ask Ollama to extract the response pattern
        pattern_description = await _extract_pattern_via_llm(category, examples)

        # Scope insight to this specific user via applicable_demographics
        existing_result = await db.execute(
            select(CollectiveInsight).where(
                CollectiveInsight.category == category,
                CollectiveInsight.pattern_type == "user_preference",
            )
        )
        # Filter by user_id in applicable_demographics after fetch (JSON field)
        all_for_cat = existing_result.scalars().all()
        existing = next(
            (c for c in all_for_cat if (c.applicable_demographics or {}).get("user_id") == user_id),
            None,
        )

        confidence = min(0.4 + len(interactions) * 0.06, 0.95)

        if existing:
            existing.pattern_description = pattern_description
            existing.positive_feedback_count = len(interactions)
            existing.sample_size = len(interactions)
            existing.confidence_level = confidence
            existing.last_validated_at = datetime.now(timezone.utc)
            insights_updated += 1
        else:
            insight = CollectiveInsight(
                category=category,
                pattern_type="user_preference",
                pattern_name=f"{category.title()} Preference — User {user_id}",
                pattern_description=pattern_description,
                pattern_data={"user_id": user_id, "example_count": len(interactions)},
                sample_size=len(interactions),
                confidence_level=confidence,
                applicable_demographics={"user_id": user_id},
                applicable_conditions={},
                positive_feedback_count=len(interactions),
                negative_feedback_count=0,
                is_active=True,
            )
            db.add(insight)

            # Audit trail
            db.add(LearningEvent(
                event_type="insight_discovered",
                intelligence_level="individual",
                user_id=user_id,
                description=(
                    f"RLAIF: discovered '{category}' preference pattern from "
                    f"{len(interactions)} positive interactions."
                ),
                data_snapshot={"category": category, "examples": len(interactions)},
            ))
            insights_created += 1

    await db.commit()
    return {
        "insights_created": insights_created,
        "insights_updated": insights_updated,
        "categories_processed": list(category_groups.keys()),
        "total_interactions_analysed": len(helpful),
    }


async def compute_outcome_reward(interaction_id: int, user_id: int, db: AsyncSession) -> float | None:
    """
    Outcome-based reward shaping:
    After a recommendation is marked was_followed=True, look at the patient's labs
    in the ~30 days following the interaction date and compare to the 30 days before.
    Returns a quality score (0–1) if measurable improvement found, else None.
    """
    # Load the interaction
    ix_result = await db.execute(
        select(AIInteraction).where(
            AIInteraction.id == interaction_id,
            AIInteraction.user_id == user_id,
        )
    )
    ix = ix_result.scalar_one_or_none()
    if not ix:
        return None

    interaction_date = ix.created_at
    if not interaction_date:
        return None

    # Determine which biomarkers to check based on category
    CATEGORY_BIOMARKERS = {
        "nutrition": ["Phosphorus", "Potassium", "Albumin"],
        "fitness": ["Hemoglobin", "BUN", "Albumin"],
        "labs": ["KtV", "URR", "Phosphorus", "Potassium", "PTH"],
        "medications": ["Phosphorus", "Potassium", "Hemoglobin"],
        "general": ["Albumin", "Phosphorus", "Hemoglobin"],
    }
    biomarkers = CATEGORY_BIOMARKERS.get(ix.category, CATEGORY_BIOMARKERS["general"])

    from datetime import timedelta

    before_start = interaction_date - timedelta(days=30)
    after_end = interaction_date + timedelta(days=30)

    # Pull labs before and after
    before_result = await db.execute(
        select(LabResult)
        .where(
            LabResult.user_id == user_id,
            LabResult.test_name.in_(biomarkers),
            LabResult.test_date >= before_start,
            LabResult.test_date < interaction_date,
        )
        .order_by(LabResult.test_name, desc(LabResult.test_date))
    )
    after_result = await db.execute(
        select(LabResult)
        .where(
            LabResult.user_id == user_id,
            LabResult.test_name.in_(biomarkers),
            LabResult.test_date > interaction_date,
            LabResult.test_date <= after_end,
        )
        .order_by(LabResult.test_name, desc(LabResult.test_date))
    )

    before_labs = {r.test_name: r.value for r in before_result.scalars().all()}
    after_labs = {r.test_name: r.value for r in after_result.scalars().all()}

    if not before_labs or not after_labs:
        return None

    # Compute improvement score
    # "Improvement" means moving toward target ranges for each biomarker
    TARGET_RANGES = {
        "Phosphorus": (2.5, 5.5),   # lower is better if high
        "Potassium": (3.5, 5.5),    # target range
        "Albumin": (3.5, 5.0),      # higher is better
        "Hemoglobin": (10.0, 11.5), # target range
        "KtV": (1.2, 2.0),          # higher is better up to 2
        "URR": (65.0, 90.0),        # higher is better up to 90
        "PTH": (150.0, 600.0),      # target range
        "BUN": (10.0, 60.0),        # lower is better if high
    }

    improvements = 0
    total = 0
    for name in biomarkers:
        if name not in before_labs or name not in after_labs:
            continue
        try:
            before_val = float(before_labs[name])
            after_val = float(after_labs[name])
        except (ValueError, TypeError):
            continue
        total += 1
        if name in TARGET_RANGES:
            lo, hi = TARGET_RANGES[name]
            before_dist = max(0, before_val - hi) + max(0, lo - before_val)
            after_dist = max(0, after_val - hi) + max(0, lo - after_val)
            if after_dist < before_dist:
                improvements += 1

    if total == 0:
        return None

    score = improvements / total  # fraction of measured biomarkers that improved

    # Write a learning event for the outcome
    db.add(LearningEvent(
        event_type="outcome_measured",
        intelligence_level="individual",
        user_id=user_id,
        description=(
            f"Outcome reward for interaction #{interaction_id} ({ix.category}): "
            f"{improvements}/{total} biomarkers improved → score {score:.2f}"
        ),
        data_snapshot={
            "interaction_id": interaction_id,
            "biomarkers_checked": biomarkers,
            "before": {k: str(v) for k, v in before_labs.items()},
            "after": {k: str(v) for k, v in after_labs.items()},
            "improvements": improvements,
            "total": total,
        },
        confidence_change=score,
    ))
    await db.commit()
    return score


async def _extract_pattern_via_llm(category: str, examples: list[str]) -> str:
    """Ask Ollama to extract the common pattern from helpful examples. Falls back gracefully."""
    prompt = (
        f"Here are {len(examples)} health Q&A exchanges that a user found helpful:\n\n"
        + "\n---\n".join(examples)
        + "\n\nIn 2 sentences, describe the COMMUNICATION PATTERN that made these responses effective. "
        "Focus on: specificity vs. generality, clinical detail level, emotional tone, actionability. "
        "Be concise and generalizable (not patient-specific)."
    )
    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
    try:
        content = (await alafia_chat(
            [{"role": "user", "content": prompt}], temperature=0.5, max_tokens=512,
        )).strip()
        if content:
            return content
    except ALAFIAModelError:
        pass
    return f"User found {len(examples)} {category}-category responses helpful — specific, data-driven answers are preferred."


# ── API endpoints ─────────────────────────────────────────────────────────────

@router.post("/knowledge/seed")
async def seed_knowledge(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Seed the ESRD/CKD evidence base into GlobalKnowledge. Idempotent."""
    inserted = await seed_global_knowledge(db)
    return {"message": f"Seeded {inserted} new knowledge entries.", "total_available": len(ESRD_EVIDENCE_BASE)}


@router.post("/learn/trigger")
async def trigger_learning(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger RLAIF learning cycle for the current user."""
    result = await run_rlaif_cycle(current_user.id, db)
    return result


@router.get("/learn/insights")
async def list_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return collective insights learned for the current user."""
    result = await db.execute(
        select(CollectiveInsight)
        .where(CollectiveInsight.is_active == True)
        .order_by(desc(CollectiveInsight.confidence_level))
        .limit(20)
    )
    insights = result.scalars().all()
    return [
        {
            "id": ci.id,
            "category": ci.category,
            "pattern_name": ci.pattern_name,
            "pattern_description": ci.pattern_description,
            "confidence_level": ci.confidence_level,
            "sample_size": ci.sample_size,
            "positive_feedback_count": ci.positive_feedback_count,
            "last_validated_at": ci.last_validated_at.isoformat() if ci.last_validated_at else None,
        }
        for ci in insights
        if (ci.applicable_demographics or {}).get("user_id") == current_user.id
    ]


@router.get("/learn/knowledge")
async def list_knowledge(
    domain: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return GlobalKnowledge entries, optionally filtered by domain."""
    query = select(GlobalKnowledge).where(GlobalKnowledge.is_active == True)
    if domain:
        query = query.where(GlobalKnowledge.domain == domain)
    result = await db.execute(query.order_by(GlobalKnowledge.domain, GlobalKnowledge.topic))
    entries = result.scalars().all()
    return [
        {
            "id": gk.id,
            "domain": gk.domain,
            "topic": gk.topic,
            "title": gk.title,
            "summary": gk.summary,
            "key_points": gk.key_points,
            "source_organization": gk.source_organization,
            "evidence_level": gk.evidence_level,
        }
        for gk in entries
    ]
