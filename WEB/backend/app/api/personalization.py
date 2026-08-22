"""Personalization and AI recommendations API."""

from datetime import datetime
from typing import Optional, List
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# get_sync_db, not get_db: get_db yields an AsyncSession, and every path in this
# router -- and all of ai_engine -- uses the SYNC ORM API (db.query, db.commit,
# db.refresh). The `db: Session` annotation converts nothing; it only made the
# mismatch look deliberate. The result was
# `AttributeError: 'AsyncSession' object has no attribute 'query'`, so these
# endpoints could never have worked. Nobody noticed because the api_key gate
# above them returned 503 before execution ever reached a query.
from app.core.database import get_sync_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.ai_engine import AIPersonalizationEngine
from app.services.alafia_model_service import ALAFIAModelError
from app.services.ai_memory_service import AIMemoryService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/personalization", tags=["Personalization"])


# Schemas
class UserProfileUpdate(BaseModel):
    """Update user profile with personalization data."""
    height_cm: Optional[float] = None
    current_weight_kg: Optional[float] = None
    target_weight_kg: Optional[float] = None
    blood_type: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None
    country: Optional[str] = None
    preferred_units: Optional[str] = Field(None, pattern="^(metric|imperial)$")
    preferred_language: Optional[str] = None
    allergies: Optional[List[str]] = None
    food_intolerances: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None
    dietary_preferences: Optional[List[str]] = None
    family_history: Optional[dict] = None
    activity_level: Optional[str] = Field(None, pattern="^(sedentary|lightly_active|moderately_active|very_active|extremely_active)$")
    fitness_goals: Optional[List[str]] = None
    preferred_activities: Optional[List[str]] = None
    exercise_frequency_per_week: Optional[int] = Field(None, ge=0, le=14)
    smoking_status: Optional[str] = Field(None, pattern="^(never|former|current)$")
    alcohol_consumption: Optional[str] = Field(None, pattern="^(none|occasional|moderate|heavy)$")
    sleep_schedule: Optional[str] = Field(None, pattern="^(early_bird|night_owl|shift_worker)$")
    occupation: Optional[str] = None
    stress_level: Optional[str] = Field(None, pattern="^(low|moderate|high)$")
    ai_personality_preference: Optional[str] = Field(None, pattern="^(supportive|motivational|clinical|casual)$")
    ai_language_complexity: Optional[str] = Field(None, pattern="^(simple|moderate|technical)$")
    ai_coaching_enabled: Optional[bool] = None
    data_sharing_consent: Optional[bool] = None
    ai_training_consent: Optional[bool] = None


class UserProfileResponse(BaseModel):
    """User profile response."""
    id: int
    email: str
    full_name: str
    date_of_birth: Optional[str]
    gender: Optional[str]
    gender_at_birth: Optional[str]
    height_cm: Optional[float]
    current_weight_kg: Optional[float]
    target_weight_kg: Optional[float]
    blood_type: Optional[str]
    locale: Optional[str]
    timezone: Optional[str]
    country: Optional[str]
    preferred_units: Optional[str]
    preferred_language: Optional[str]
    allergies: Optional[List[str]]
    food_intolerances: Optional[List[str]]
    dietary_restrictions: Optional[List[str]]
    dietary_preferences: Optional[List[str]]
    family_history: Optional[dict]
    activity_level: Optional[str]
    fitness_goals: Optional[List[str]]
    preferred_activities: Optional[List[str]]
    exercise_frequency_per_week: Optional[int]
    smoking_status: Optional[str]
    alcohol_consumption: Optional[str]
    sleep_schedule: Optional[str]
    occupation: Optional[str]
    stress_level: Optional[str]
    ai_personality_preference: Optional[str]
    ai_language_complexity: Optional[str]
    ai_coaching_enabled: bool
    
    class Config:
        from_attributes = True


class RecommendationRequest(BaseModel):
    """Request for AI recommendations."""
    type: str = Field(..., pattern="^(nutrition|fitness|sleep|wellness)$")
    specific_request: Optional[str] = Field(None, max_length=500)
    days_context: Optional[int] = Field(30, ge=7, le=90)


class RecommendationResponse(BaseModel):
    """AI recommendation response."""
    type: str
    recommendations: str
    generated_at: str
    based_on_days: int


class SymptomAnalysisRequest(BaseModel):
    """Request for symptom analysis."""
    symptoms_description: str = Field(..., min_length=10, max_length=1000)


class SymptomAnalysisResponse(BaseModel):
    """Symptom analysis response."""
    analysis: str
    disclaimer: str
    generated_at: str


# Endpoints
@router.get("/profile", response_model=UserProfileResponse)
async def get_personalized_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Get user's complete personalization profile."""
    # Parse JSON fields
    profile = UserProfileResponse.model_validate(current_user)
    
    # Parse JSON string fields to lists/dicts
    if current_user.allergies:
        profile.allergies = json.loads(current_user.allergies)
    if current_user.food_intolerances:
        profile.food_intolerances = json.loads(current_user.food_intolerances)
    if current_user.dietary_restrictions:
        profile.dietary_restrictions = json.loads(current_user.dietary_restrictions)
    if current_user.dietary_preferences:
        profile.dietary_preferences = json.loads(current_user.dietary_preferences)
    if current_user.family_history:
        profile.family_history = json.loads(current_user.family_history)
    if current_user.fitness_goals:
        profile.fitness_goals = json.loads(current_user.fitness_goals)
    if current_user.preferred_activities:
        profile.preferred_activities = json.loads(current_user.preferred_activities)
    
    return profile


@router.put("/profile", response_model=UserProfileResponse)
async def update_personalized_profile(
    profile_update: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Update user's personalization profile."""
    update_data = profile_update.model_dump(exclude_unset=True)
    
    # Convert lists/dicts to JSON strings for storage
    if "allergies" in update_data:
        update_data["allergies"] = json.dumps(update_data["allergies"])
    if "food_intolerances" in update_data:
        update_data["food_intolerances"] = json.dumps(update_data["food_intolerances"])
    if "dietary_restrictions" in update_data:
        update_data["dietary_restrictions"] = json.dumps(update_data["dietary_restrictions"])
    if "dietary_preferences" in update_data:
        update_data["dietary_preferences"] = json.dumps(update_data["dietary_preferences"])
    if "family_history" in update_data:
        update_data["family_history"] = json.dumps(update_data["family_history"])
    if "fitness_goals" in update_data:
        update_data["fitness_goals"] = json.dumps(update_data["fitness_goals"])
    if "preferred_activities" in update_data:
        update_data["preferred_activities"] = json.dumps(update_data["preferred_activities"])
    
    # Update user object
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    db.commit()
    db.refresh(current_user)
    
    return await get_personalized_profile(current_user, db)


@router.post("/recommendations", response_model=RecommendationResponse)
async def get_ai_recommendations(
    request: RecommendationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Get personalized AI recommendations.
    
    Requires AI coaching to be enabled and API keys configured.
    """
    if not current_user.ai_coaching_enabled:
        raise HTTPException(
            status_code=status. HTTP_403_FORBIDDEN,
            detail="AI coaching is not enabled for this user"
        )
    
    # Initialize AI engine with memory
    ai_engine = AIPersonalizationEngine(db=db)
    
    try:
        recommendations = await ai_engine.generate_personalized_recommendations(
            user=current_user,
            db=db,
            recommendation_type=request.type,
            specific_request=request.specific_request
        )
        
        return RecommendationResponse(**recommendations)

    except ALAFIAModelError as e:
        # The model really is unreachable. Say so, and say why. The old code
        # could not tell "no provider configured" from "provider errored",
        # because it never asked the provider at all.
        logger.error("%s failed -- model unavailable: %s", "Failed to generate recommendations", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The AI service is temporarily unavailable: {e}",
        )
    except Exception as e:
        logger.exception("%s failed", "Failed to generate recommendations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendations: {str(e)}"
        )


@router.post("/analyze-symptoms", response_model=SymptomAnalysisResponse)
async def analyze_symptoms(
    request: SymptomAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Analyze symptoms with user's health context.
    
    DISCLAIMER: This is NOT a diagnostic tool. Always consult healthcare professionals.
    """
    if not current_user.ai_coaching_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI coaching is not enabled for this user"
        )
    
    ai_engine = AIPersonalizationEngine(db=db)
    
    try:
        analysis = await ai_engine.analyze_symptoms(
            user=current_user,
            db=db,
            symptoms_description=request.symptoms_description
        )
        
        return SymptomAnalysisResponse(**analysis)

    except ALAFIAModelError as e:
        # The model really is unreachable. Say so, and say why. The old code
        # could not tell "no provider configured" from "provider errored",
        # because it never asked the provider at all.
        logger.error("%s failed -- model unavailable: %s", "Failed to analyze symptoms", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The AI service is temporarily unavailable: {e}",
        )
    except Exception as e:
        logger.exception("%s failed", "Failed to analyze symptoms")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze symptoms: {str(e)}"
        )


@router.get("/health-score")
async def get_health_score(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Calculate overall health score based on recent tracking data.
    
    Score components:
    - Nutrition adherence (25%)
    - Fitness consistency (25%)
    - Sleep quality (20%)
    - Mood stability (15%)
    - Vital signs (15%)
    """
    ai_engine = AIPersonalizationEngine(db=db)
    context = ai_engine._build_user_context(current_user, db, days=30)
    
    scores = {
        "nutrition": 0,
        "fitness": 0,
        "sleep": 0,
        "mood": 0,
        "vitals": 0
    }
    
    # Nutrition score (0-100)
    nutrition_data = context["recent_data"]["nutrition"]
    if nutrition_data.get("status") != "no_data":
        # Score based on consistency and balance
        days_tracked = nutrition_data.get("days_tracked", 0)
        scores["nutrition"] = min(100, (days_tracked / 30) * 100)
    
    # Fitness score (0-100)
    fitness_data = context["recent_data"]["fitness"]
    if fitness_data.get("status") != "no_data":
        workouts_per_week = fitness_data.get("workouts_per_week", 0)
        # Optimal is 3-5 workouts per week
        if workouts_per_week >= 3 and workouts_per_week <= 5:
            scores["fitness"] = 100
        elif workouts_per_week < 3:
            scores["fitness"] = (workouts_per_week / 3) * 100
        else:
            scores["fitness"] = max(60, 100 - ((workouts_per_week - 5) * 10))
    
    # Sleep score (0-100)
    sleep_data = context["recent_data"]["sleep"]
    if sleep_data.get("status") != "no_data":
        avg_hours = sleep_data.get("avg_hours_per_night", 0)
        quality = sleep_data.get("avg_quality_score", 0)
        # Optimal is 7-9 hours
        if avg_hours >= 7 and avg_hours <= 9:
            hours_score = 100
        elif avg_hours < 7:
            hours_score = (avg_hours / 7) * 100
        else:
            hours_score = max(60, 100 - ((avg_hours - 9) * 20))
        
        scores["sleep"] = (hours_score * 0.6) + (quality * 10 * 0.4)
    
    # Mood score (0-100)
    mood_data = context["recent_data"]["mood"]
    if mood_data.get("status") != "no_data":
        avg_mood = mood_data.get("avg_mood_score", 0)
        avg_energy = mood_data.get("avg_energy_level", 0)
        avg_stress = mood_data.get("avg_stress_level", 0)
        
        scores["mood"] = (avg_mood * 10 * 0.4) + (avg_energy * 10 * 0.3) + ((10 - avg_stress) * 10 * 0.3)
    
    # Vitals score (0-100)
    vitals_data = context["recent_data"]["vitals"]
    if vitals_data.get("status") != "no_data":
        # Simple score based on BMI being in healthy range
        bmi = vitals_data.get("bmi")
        if bmi:
            if bmi >= 18.5 and bmi < 25:
                scores["vitals"] = 100
            elif bmi >= 25 and bmi < 30:
                scores["vitals"] = 75
            elif bmi >= 17 and bmi < 18.5:
                scores["vitals"] = 75
            else:
                scores["vitals"] = 50
    
    # Calculate weighted overall score
    weights = {
        "nutrition": 0.25,
        "fitness": 0.25,
        "sleep": 0.20,
        "mood": 0.15,
        "vitals": 0.15
    }
    
    overall_score = sum(scores[key] * weights[key] for key in scores)
    
    return {
        "overall_score": round(overall_score, 1),
        "component_scores": {k: round(v, 1) for k, v in scores.items()},
        "grade": _get_grade(overall_score),
        "calculated_at": datetime.now().isoformat()
    }


def _get_grade(score: float) -> str:
    """Convert score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


# ==================== AI MEMORY & LEARNING ENDPOINTS ====================

@router.post("/learn-from-data")
async def learn_from_user_data(
    days: int = 90,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Trigger AI to learn from user's data and create memories.
    
    Analyzes recent data (default 90 days) to discover patterns and preferences.
    """
    memory_service = AIMemoryService(db)
    memories = memory_service.learn_from_user_data(current_user.id, days=days)
    
    return {
        "memories_created": len(memories),
        "categories": list(set(m.category for m in memories)),
        "message": f"AI learned {len(memories)} new insights from your data"
    }


@router.get("/memories")
async def get_my_memories(
    category: Optional[str] = None,
    min_confidence: float = 0.5,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Get AI's learned memories about the user.
    
    These are patterns and preferences the AI has discovered from your data.
    """
    memory_service = AIMemoryService(db)
    memories = memory_service.get_user_memories(
        current_user.id,
        category=category,
        min_confidence=min_confidence
    )
    
    return {
        "total_memories": len(memories),
        "memories": [
            {
                "category": m.category,
                "subcategory": m.subcategory,
                "insight": m.insight_value,
                "confidence": m.confidence_score,
                "evidence_count": m.evidence_count,
                "learned_at": m.created_at.isoformat(),
                "last_confirmed": m.last_confirmed_at.isoformat() if m.last_confirmed_at else None
            }
            for m in memories
        ]
    }


@router.get("/interaction-history")
async def get_interaction_history(
    interaction_type: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Get history of AI interactions.
    
    Shows past recommendations, analyses, and your feedback on them.
    """
    memory_service = AIMemoryService(db)
    interactions = memory_service.get_interaction_history(
        current_user.id,
        interaction_type=interaction_type,
        limit=limit
    )
    
    return {
        "total": len(interactions),
        "interactions": [
            {
                "id": i.id,
                "type": i.interaction_type,
                "category": i.category,
                "request": i.user_request,
                "response_preview": i.ai_response[:200] + "..." if len(i.ai_response) > 200 else i.ai_response,
                "was_helpful": i.was_helpful,
                "was_followed": i.was_followed,
                "created_at": i.created_at.isoformat(),
                "model_used": f"{i.llm_provider}/{i.llm_model}"
            }
            for i in interactions
        ]
    }


@router.post("/interactions/{interaction_id}/feedback")
async def provide_interaction_feedback(
    interaction_id: int,
    was_helpful: bool,
    user_feedback: Optional[str] = None,
    was_followed: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Provide feedback on an AI recommendation.
    
    This helps the AI learn and improve future recommendations.
    """
    memory_service = AIMemoryService(db)
    
    # Verify the interaction belongs to the user
    from app.models.ai_memory import AIInteraction
    interaction = db.query(AIInteraction).filter(
        AIInteraction.id == interaction_id,
        AIInteraction.user_id == current_user.id
    ).first()
    
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")
    
    updated = memory_service.update_interaction_feedback(
        interaction_id=interaction_id,
        was_helpful=was_helpful,
        user_feedback=user_feedback,
        was_followed=was_followed
    )
    
    return {
        "message": "Thank you for your feedback!",
        "interaction_id": updated.id,
        "sentiment": updated.user_sentiment
    }


@router.get("/collective-insights")
async def get_collective_insights(
    category: Optional[str] = None,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Get insights learned from all ALAFIA users.
    
    These are anonymized patterns discovered across the user base.
    Requires data_sharing_consent to be enabled.
    """
    if not current_user.data_sharing_consent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data sharing consent required to view collective insights"
        )
    
    memory_service = AIMemoryService(db)
    insights = memory_service.get_applicable_insights(
        user=current_user,
        category=category or "general",
        limit=limit
    )
    
    return {
        "total": len(insights),
        "insights": [
            {
                "pattern_name": i.pattern_name,
                "description": i.pattern_description,
                "category": i.category,
                "confidence_level": i.confidence_level,
                "based_on_users": i.sample_size,
                "effect_size": i.effect_size,
                "discovered_at": i.discovered_at.isoformat(),
                "times_applied": i.times_applied,
                "positive_feedback": i.positive_feedback_count,
                "negative_feedback": i.negative_feedback_count
            }
            for i in insights
        ]
    }


@router.get("/global-knowledge")
async def get_global_knowledge(
    domain: str,
    topics: List[str] = [],
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Get evidence-based health knowledge from authoritative sources.
    
    This is curated knowledge from WHO, NIH, medical journals, etc.
    """
    memory_service = AIMemoryService(db)
    knowledge = memory_service.get_relevant_knowledge(
        domain=domain,
        topics=topics if topics else ["general"],
        limit=limit
    )
    
    return {
        "total": len(knowledge),
        "knowledge_items": [
            {
                "title": k.title,
                "summary": k.summary,
                "domain": k.domain,
                "topic": k.topic,
                "source": k.source_organization,
                "evidence_level": k.evidence_level,
                "source_url": k.source_url,
                "publication_date": k.publication_date.isoformat() if k.publication_date else None,
                "times_referenced": k.times_referenced
            }
            for k in knowledge
        ]
    }
