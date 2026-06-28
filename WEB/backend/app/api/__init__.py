"""API router aggregation."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.nutrition import router as nutrition_router
from app.api.fitness import router as fitness_router
from app.api.labs import router as labs_router
from app.api.medications import router as medications_router
from app.api.mood import router as mood_router
from app.api.lifestyle import router as lifestyle_router
from app.api.ai import router as ai_router
from app.api.personalization import router as personalization_router
from app.api.privacy import router as privacy_router
from app.api.chronic_conditions import router as chronic_conditions_router
from app.api.ehr import router as ehr_router
from app.api.media import router as media_router
from app.api.mental_health import router as mental_health_router
from app.api.community_health import router as community_health_router
from app.api.user_roles import router as user_roles_router
from app.api.health_sync import router as health_sync_router
from app.api.calendar import router as calendar_router
from app.api.telehealth import router as telehealth_router
from app.api.messaging import router as messaging_router
from app.api.insurance import router as insurance_router
from app.api.diagnostics import router as diagnostics_router
from app.api.blockchain import router as blockchain_router
from app.api.physicians import router as physicians_router
from app.api.lab_charts import router as lab_charts_router
from app.api.wellness import router as wellness_router
from app.api.planners import router as planners_router
from app.api.image_ai import router as image_ai_router
from app.api.pdf_tools import router as pdf_tools_router
from app.api.peritoneal_dialysis import router as pd_router
from app.api.advanced_directives import router as advanced_directives_router
from app.api.fda_recalls import router as fda_recalls_router
from app.api.clinician_dashboard import router as clinician_dashboard_router
from app.api.data_sharing import router as data_sharing_router
from app.api.notifications import router as notifications_router
from app.api.chart_dashboard import router as chart_dashboard_router
from app.api.pharmacy import router as pharmacy_router
from app.api.pantry import router as pantry_router
from app.api.elimination import router as elimination_router
from app.api.symptoms import router as symptoms_router
from app.api.sleep import router as sleep_router
from app.api.vitals import router as vitals_router
from app.api.insights import router as insights_router
from app.api.ground_truth import router as ground_truth_router
from app.api.ai_learning import router as ai_learning_router
from app.api.firebase_sync import router as firebase_sync_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(nutrition_router, prefix="/nutrition", tags=["Nutrition"])
router.include_router(fitness_router, prefix="/fitness", tags=["Fitness"])
router.include_router(labs_router, prefix="/labs", tags=["Labs / EHR"])
router.include_router(medications_router, prefix="/medications", tags=["Medications"])
router.include_router(mood_router, prefix="/mood", tags=["Mood / Mental Health"])
router.include_router(lifestyle_router, prefix="/lifestyle", tags=["Lifestyle"])
router.include_router(ai_router, prefix="/ai", tags=["AI Assistant"])
router.include_router(personalization_router, tags=["Personalization"])
router.include_router(privacy_router, tags=["Privacy & Compliance"])
router.include_router(chronic_conditions_router, prefix="/chronic", tags=["Chronic Disease Management"])
router.include_router(ehr_router, tags=["EHR"])
router.include_router(media_router, tags=["Media"])
router.include_router(mental_health_router, prefix="/mental-health", tags=["Mental Health"])
router.include_router(community_health_router, prefix="/community", tags=["Community Health"])
router.include_router(user_roles_router, prefix="/users", tags=["User Roles & Personas"])
router.include_router(health_sync_router, prefix="/sync", tags=["Health Data Sync"])
router.include_router(calendar_router, prefix="/calendar", tags=["Calendar"])
router.include_router(telehealth_router, prefix="/telehealth", tags=["Telehealth"])
router.include_router(messaging_router, prefix="/messaging", tags=["Messaging"])
router.include_router(insurance_router, prefix="/insurance", tags=["Insurance"])
router.include_router(diagnostics_router, prefix="/diagnostics", tags=["Diagnostics Engine"])
router.include_router(blockchain_router, prefix="/blockchain", tags=["Blockchain Ledger"])
router.include_router(physicians_router, prefix="/physicians", tags=["Physician Directory"])
router.include_router(lab_charts_router, prefix="/lab-charts", tags=["Lab Comparison Charts"])
router.include_router(wellness_router, prefix="/wellness", tags=["Wellness & Health"])
router.include_router(planners_router, prefix="/planners", tags=["Meal & Exercise Planners"])
router.include_router(image_ai_router, prefix="/image-ai", tags=["Image AI"])
router.include_router(pdf_tools_router, prefix="/pdf", tags=["PDF Tools"])
router.include_router(pd_router, prefix="/pd", tags=["Peritoneal Dialysis"])
router.include_router(advanced_directives_router, prefix="/advanced-directives", tags=["Advanced Directives"])
router.include_router(fda_recalls_router, prefix="/fda-recalls", tags=["FDA Food Recalls"])
router.include_router(clinician_dashboard_router, prefix="/clinician-dashboard", tags=["Clinician Dashboard"])
router.include_router(data_sharing_router, prefix="/data-sharing", tags=["Data Sharing"])
router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
router.include_router(chart_dashboard_router, prefix="/chart-dashboard", tags=["Chart Dashboard"])
router.include_router(pharmacy_router, prefix="/pharmacy", tags=["Pharmacy"])
router.include_router(pantry_router, prefix="/pantry", tags=["Pantry"])
router.include_router(elimination_router, prefix="/elimination", tags=["Elimination"])
router.include_router(symptoms_router, prefix="/symptoms", tags=["Symptoms"])
router.include_router(sleep_router, prefix="/sleep", tags=["Sleep"])
router.include_router(vitals_router, prefix="/vitals", tags=["Vitals"])
router.include_router(insights_router, prefix="/insights", tags=["Insights — Patterns & Forecasts"])
router.include_router(ground_truth_router, prefix="/ground-truth", tags=["Ground Truths — Genetics & Environment"])
router.include_router(ai_learning_router, prefix="/ai", tags=["AI Learning & Intelligence"])
router.include_router(firebase_sync_router, prefix="/firebase", tags=["Firebase Sync"])
