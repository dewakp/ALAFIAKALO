"""AIOrchestration Engine for personalized health recommendations."""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.user import User
from app.models.nutrition import NutritionLog
from app.models.fitness import FitnessLog
from app.models.mood import MoodEntry
from app.models.sleep import SleepLog
from app.models.vitals import VitalsLog
from app.models.conditions import HealthCondition, SymptomLog, IllnessLog
from app.models.medications import Medication
from app.services.ai_memory_service import AIMemoryService


class AIPersonalizationEngine:
    """Proprietary LLM-based personalization engine with memory and learning."""
    
    def __init__(self, api_key: Optional[str] = None, provider: Optional[str] = None, db: Optional[Session] = None):
        """
        Initialize AI engine.

        Args:
            api_key: unused; kept so existing call sites keep working.
            provider: label only — the actual provider is chosen by ALAFIAModel.
            db: Database session for memory access

        This class used to call OpenAI directly, and carried `api_key` and
        `api_url` for that. Every call now goes through `_call_llm` →
        `alafia_chat` (the ALAFIAModel router), so those fields were dead. They
        were not harmless: `/personalization/*` gated on `if not
        ai_engine.api_key` and therefore returned
        "AI service is not configured" in production for 27 days, on a
        deployment whose LLM (Ollama) needs no API key at all. Asking whether a
        provider-specific key exists is the wrong question — CLAUDE.md §3 says
        provider strategy is a backend concern.
        """
        self.db = db
        self.memory_service = AIMemoryService(db) if db else None
        # Recorded on stored interactions. Reported by ALAFIAModel rather than
        # assumed: prod was labelling Ollama answers "openai"/"gpt-4-turbo-preview".
        self.provider = provider or os.getenv("ALAFIA_LLM_PROVIDER", "alafia-model")
        self.model = os.getenv("OLLAMA_MODEL", "unknown")
    
    async def _call_llm(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """Call the LLM through the ALAFIAModel router (Ollama → OpenAI fallback).

        Routing every call through ALAFIAModel keeps the backend vendor-agnostic:
        the underlying model can change without touching this call site.
        """
        from app.services.alafia_model_service import alafia_chat
        return await alafia_chat(messages, temperature=temperature, max_tokens=max_tokens)
    
    def _build_user_context(self, user: User, db: Session, days: int = 30) -> Dict[str, Any]:
        """Build comprehensive user context from all available data."""
        context = {
            "demographics": {
                "age": self._calculate_age(user.date_of_birth),
                "gender": user.gender,
                "gender_at_birth": user.gender_at_birth,
                "height_cm": user.height_cm,
                "current_weight_kg": user.current_weight_kg,
                "target_weight_kg": user.target_weight_kg,
                "bmi": self._calculate_bmi(user.height_cm, user.current_weight_kg),
                "blood_type": user.blood_type
            },
            "location_culture": {
                "locale": user.locale,
                "timezone": user.timezone,
                "country": user.country,
                "preferred_units": user.preferred_units,
                "preferred_language": user.preferred_language
            },
            "health_profile": {
                "allergies": json.loads(user.allergies) if user.allergies else [],
                "food_intolerances": json.loads(user.food_intolerances) if user.food_intolerances else [],
                "dietary_restrictions": json.loads(user.dietary_restrictions) if user.dietary_restrictions else [],
                "dietary_preferences": json.loads(user.dietary_preferences) if user.dietary_preferences else [],
                "chronic_conditions": self._get_active_conditions(user, db),
                "family_history": json.loads(user.family_history) if user.family_history else {}
            },
            "fitness_profile": {
                "activity_level": user.activity_level,
                "fitness_goals": json.loads(user.fitness_goals) if user.fitness_goals else [],
                "preferred_activities": json.loads(user.preferred_activities) if user.preferred_activities else [],
                "exercise_frequency_per_week": user.exercise_frequency_per_week
            },
            "lifestyle": {
                "smoking_status": user.smoking_status,
                "alcohol_consumption": user.alcohol_consumption,
                "sleep_schedule": user.sleep_schedule,
                "occupation": user.occupation,
                "stress_level": user.stress_level
            },
            "ai_preferences": {
                "personality": user.ai_personality_preference or "supportive",
                "language_complexity": user.ai_language_complexity or "moderate"
            }
        }
        
        # Add recent health data
        cutoff_date = datetime.now() - timedelta(days=days)
        
        context["recent_data"] = {
            "nutrition": self._summarize_nutrition(user.id, db, cutoff_date),
            "fitness": self._summarize_fitness(user.id, db, cutoff_date),
            "mood": self._summarize_mood(user.id, db, cutoff_date),
            "sleep": self._summarize_sleep(user.id, db, cutoff_date),
            "vitals": self._get_latest_vitals(user.id, db),
            "symptoms": self._get_recent_symptoms(user.id, db, cutoff_date),
            "medications": self._get_current_medications(user.id, db)
        }
        
        # Add AI memories (individual intelligence)
        if self.memory_service:
            memories = self.memory_service.get_user_memories(user.id, min_confidence=0.6)
            context["learned_patterns"] = {
                f"{m.category}_{m.subcategory}_{m.insight_key}": {
                    "insight": m.insight_value,
                    "confidence": m.confidence_score,
                    "evidence": m.evidence_count
                }
                for m in memories[:10]  # Top 10 most relevant
            }
            
            # Add collective insights (all users intelligence)
            collective_insights = self.memory_service.get_applicable_insights(
                user, category="general", limit=5
            )
            context["collective_wisdom"] = [
                {
                    "pattern": insight.pattern_name,
                    "description": insight.pattern_description,
                    "confidence": insight.confidence_level,
                    "based_on_users": insight.sample_size
                }
                for insight in collective_insights
            ]
            
            # Add relevant global knowledge
            relevant_knowledge = self.memory_service.get_relevant_knowledge(
                domain="general",
                topics=["nutrition", "fitness", "sleep"],
                limit=3
            )
            context["expert_knowledge"] = [
                {
                    "title": k.title,
                    "summary": k.summary,
                    "source": k.source_organization,
                    "evidence_level": k.evidence_level
                }
                for k in relevant_knowledge
            ]
        
        return context
    
    def _calculate_age(self, date_of_birth: Optional[str]) -> Optional[int]:
        """Calculate age from date of birth."""
        if not date_of_birth:
            return None
        try:
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d")
            today = datetime.now()
            return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except:
            return None
    
    def _calculate_bmi(self, height_cm: Optional[float], weight_kg: Optional[float]) -> Optional[float]:
        """Calculate BMI."""
        if not height_cm or not weight_kg:
            return None
        height_m = height_cm / 100
        return round(weight_kg / (height_m ** 2), 1)
    
    def _get_active_conditions(self, user: User, db: Session) -> List[Dict[str, Any]]:
        """Get active health conditions.

        Goes through clinical_sources because conditions live in TWO tables and
        this used to read only `health_conditions` — which has no writer, so the
        AI believed every patient had zero conditions. An ESRD patient's coach
        did not know they had ESRD.
        """
        from app.services import clinical_sources

        conditions = clinical_sources.conditions_sync(db, user.id, active_only=True)

        return [
            {
                "name": c.name,
                "category": c.category,
                "severity": c.severity,
                "since": c.diagnosed,
                # The coded diagnosis disambiguates a free-text name the
                # patient typed ("kidney problem") into a specific entity.
                "icd11": c.icd11_code,
                "icd11_title": c.icd11_title,
            }
            for c in conditions
        ]
    
    def _summarize_nutrition(self, user_id: int, db: Session, cutoff_date: datetime) -> Dict[str, Any]:
        """Summarize recent nutrition data."""
        logs = db.query(NutritionLog).filter(
            NutritionLog.user_id == user_id,
            NutritionLog.consumed_at >= cutoff_date
        ).all()
        
        if not logs:
            return {"status": "no_data"}
        
        total_days = len(set(log.consumed_at.date() for log in logs))
        avg_calories = sum(log.calories_kcal or 0 for log in logs) / total_days if total_days > 0 else 0
        avg_protein = sum(log.protein_g or 0 for log in logs) / total_days if total_days > 0 else 0
        avg_carbs = sum(log.carbohydrates_g or 0 for log in logs) / total_days if total_days > 0 else 0
        avg_fat = sum(log.total_fat_g or 0 for log in logs) / total_days if total_days > 0 else 0
        
        return {
            "days_tracked": total_days,
            "avg_daily_calories": round(avg_calories, 0),
            "avg_daily_protein_g": round(avg_protein, 1),
            "avg_daily_carbs_g": round(avg_carbs, 1),
            "avg_daily_fat_g": round(avg_fat, 1),
            "macros_ratio": f"{round(avg_protein*4/avg_calories*100 if avg_calories else 0)}% protein, "
                           f"{round(avg_carbs*4/avg_calories*100 if avg_calories else 0)}% carbs, "
                           f"{round(avg_fat*9/avg_calories*100 if avg_calories else 0)}% fat"
        }
    
    def _summarize_fitness(self, user_id: int, db: Session, cutoff_date: datetime) -> Dict[str, Any]:
        """Summarize recent fitness data."""
        logs = db.query(FitnessLog).filter(
            FitnessLog.user_id == user_id,
            FitnessLog.performed_at >= cutoff_date
        ).all()
        
        if not logs:
            return {"status": "no_data"}
        
        total_days = len(set(log.performed_at.date() for log in logs))
        workouts_per_week = len(logs) / (total_days / 7) if total_days > 0 else 0
        avg_duration = sum(log.duration_minutes or 0 for log in logs) / len(logs) if logs else 0
        
        activities = {}
        for log in logs:
            activities[log.activity_type] = activities.get(log.activity_type, 0) + 1
        
        return {
            "days_with_activity": total_days,
            "workouts_per_week": round(workouts_per_week, 1),
            "avg_duration_minutes": round(avg_duration, 0),
            "top_activities": sorted(activities.items(), key=lambda x: x[1], reverse=True)[:3]
        }
    
    def _summarize_mood(self, user_id: int, db: Session, cutoff_date: datetime) -> Dict[str, Any]:
        """Summarize recent mood data."""
        entries = db.query(MoodEntry).filter(
            MoodEntry.user_id == user_id,
            MoodEntry.recorded_at >= cutoff_date
        ).all()
        
        if not entries:
            return {"status": "no_data"}
        
        avg_mood = sum(e.mood_score for e in entries if e.mood_score) / len(entries) if entries else 0
        avg_energy = sum(e.energy_level for e in entries if e.energy_level) / len(entries) if entries else 0
        avg_stress = sum(e.stress_level for e in entries if e.stress_level) / len(entries) if entries else 0
        
        return {
            "entries_count": len(entries),
            "avg_mood_score": round(avg_mood, 1),
            "avg_energy_level": round(avg_energy, 1),
            "avg_stress_level": round(avg_stress, 1),
            "trend": "improving" if len(entries) >= 2 and entries[-1].mood_score > entries[0].mood_score else "stable"
        }
    
    def _summarize_sleep(self, user_id: int, db: Session, cutoff_date: datetime) -> Dict[str, Any]:
        """Summarize recent sleep data."""
        logs = db.query(SleepLog).filter(
            SleepLog.user_id == user_id,
            SleepLog.bedtime >= cutoff_date
        ).all()
        
        if not logs:
            return {"status": "no_data"}
        
        avg_hours = sum(log.total_hours or 0 for log in logs) / len(logs) if logs else 0
        avg_quality = sum(log.quality_score or 0 for log in logs if log.quality_score) / len([l for l in logs if l.quality_score]) if any(l.quality_score for l in logs) else 0
        
        return {
            "nights_tracked": len(logs),
            "avg_hours_per_night": round(avg_hours, 1),
            "avg_quality_score": round(avg_quality, 1),
            "consistency": "good" if max(abs(log.total_hours - avg_hours) for log in logs if log.total_hours) < 2 else "variable"
        }
    
    def _get_latest_vitals(self, user_id: int, db: Session) -> Dict[str, Any]:
        """Get latest vital signs."""
        latest = db.query(VitalsLog).filter(
            VitalsLog.user_id == user_id
        ).order_by(desc(VitalsLog.recorded_at)).first()
        
        if not latest:
            return {"status": "no_data"}
        
        return {
            "recorded_at": latest.recorded_at.isoformat(),
            "blood_pressure": f"{latest.systolic_bp}/{latest.diastolic_bp}" if latest.systolic_bp else None,
            "heart_rate_bpm": latest.heart_rate_bpm,
            "weight_kg": latest.weight_kg,
            "body_fat_pct": latest.body_fat_pct,
            "bmi": latest.bmi
        }
    
    def _get_recent_symptoms(self, user_id: int, db: Session, cutoff_date: datetime) -> List[Dict[str, Any]]:
        """Get recent symptoms."""
        symptoms = db.query(SymptomLog).filter(
            SymptomLog.user_id == user_id,
            SymptomLog.started_at >= cutoff_date
        ).order_by(desc(SymptomLog.started_at)).limit(5).all()
        
        return [
            {
                "symptom": s.symptom_name,
                "severity": s.severity_level,
                "body_part": s.body_part,
                "started": s.started_at.isoformat()
            }
            for s in symptoms
        ]
    
    def _get_current_medications(self, user_id: int, db: Session) -> List[Dict[str, Any]]:
        """Get current medications."""
        meds = db.query(Medication).filter(
            Medication.user_id == user_id,
            Medication.status == "active"
        ).all()
        
        return [
            {
                "name": m.medication_name,
                "dosage": m.dosage,
                "frequency": m.frequency
            }
            for m in meds
        ]
    
    async def generate_personalized_recommendations(
        self, 
        user: User, 
        db: Session, 
        recommendation_type: str,
        specific_request: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate personalized recommendations using LLM.
        
        Args:
            user: User object
            db: Database session
            recommendation_type: Type of recommendations (nutrition, fitness, sleep, wellness)
            specific_request: Optional specific question/request from user
        
        Returns:
            Dict with recommendations and reasoning
        """
        context = self._build_user_context(user, db)
        
        system_prompt = self._get_system_prompt(context["ai_preferences"]["personality"])
        user_prompt = self._build_recommendation_prompt(context, recommendation_type, specific_request)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        start_time = datetime.now()
        response = await self._call_llm(messages, temperature=0.7)
        response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Record this interaction for learning
        if self.memory_service:
            self.memory_service.record_interaction(
                user_id=user.id,
                interaction_type="recommendation",
                category=recommendation_type,
                user_request=specific_request,
                ai_response=response,
                context_used=context,
                llm_provider=self.provider,
                llm_model=self.model,
                response_time_ms=response_time_ms
            )
        
        return {
            "type": recommendation_type,
            "recommendations": response,
            "generated_at": datetime.now().isoformat(),
            "based_on_days": 30
        }
    
    def _get_system_prompt(self, personality: str) -> str:
        """Get system prompt based on personality preference."""
        base = """You are ALAFIA's AI health coach, analyzing comprehensive health data to provide personalized recommendations. 
Always prioritize safety - if you detect concerning patterns, recommend consulting healthcare professionals.
Consider allergies, restrictions, and chronic conditions in all recommendations.
Be evidence-based but acknowledge individual variation."""
        
        personalities = {
            "supportive": base + "\n\nUse an empathetic, encouraging tone. Focus on progress and celebrate small wins.",
            "motivational": base + "\n\nUse an energetic, inspiring tone. Challenge the user to push boundaries while staying safe.",
            "clinical": base + "\n\nUse a professional, medical tone. Cite research and use precise terminology.",
            "casual": base + "\n\nUse a friendly, conversational tone. Keep things simple and relatable."
        }
        
        return personalities.get(personality, personalities["supportive"])
    
    def _build_recommendation_prompt(
        self, 
        context: Dict[str, Any], 
        rec_type: str, 
        specific_request: Optional[str]
    ) -> str:
        """Build user prompt for recommendations."""
        prompt = f"""Provide personalized {rec_type} recommendations for this user:

USER PROFILE:
{json.dumps(context, indent=2, default=str)}

"""
        if specific_request:
            prompt += f"\nSPECIFIC REQUEST: {specific_request}\n"
        
        prompts = {
            "nutrition": """Provide:
1. Daily calorie and macro targets (considering goals, activity level, restrictions)
2. Specific food recommendations (considering allergies, intolerances, dietary restrictions)
3. Meal timing suggestions (based on sleep schedule, fitness routine)
4. Micronutrient focus areas (based on recent nutrition data gaps)
5. Hydration recommendations""",
            
            "fitness": """Provide:
1. Weekly exercise plan (frequency, duration, intensity based on current level and goals)
2. Specific workout types (considering preferences, conditions, recent activity)
3. Progressive overload strategy (if muscle gain is a goal)
4. Recovery recommendations (based on age, stress level, sleep quality)
5. Injury prevention tips (especially for chronic conditions)""",
            
            "sleep": """Provide:
1. Optimal sleep schedule (based on chronotype, occupation, recent sleep data)
2. Sleep environment optimization (temperature, noise, light)
3. Pre-sleep routine recommendations (caffeine cutoff, screen time, relaxation)
4. Sleep quality improvement strategies (based on recent sleep tracking)
5. Addressing specific issues (if awakening frequently, etc.)""",
            
            "wellness": """Provide:
1. Stress management techniques (based on stress level, occupation)
2. Mood improvement strategies (based on recent mood trends)
3. Lifestyle modifications (smoking/alcohol if applicable)
4. Social connection recommendations
5. Mindfulness or mental health practices"""
        }
        
        prompt += prompts.get(rec_type, "Provide comprehensive health recommendations based on the user's profile and recent data.")
        
        prompt += """\n\nFormat your response as actionable recommendations with clear reasoning.
If you see any concerning patterns (e.g., symptoms, vital signs), recommend professional medical consultation."""
        
        return prompt
    
    async def analyze_symptoms(self, user: User, db: Session, symptoms_description: str) -> Dict[str, Any]:
        """
        Analyze symptoms with context from user's health profile.
        
        IMPORTANT: This is NOT a diagnostic tool. Always recommend professional consultation.
        """
        context = self._build_user_context(user, db, days=90)
        
        system_prompt = """You are a health information assistant. You do NOT diagnose conditions.
Your role is to help users understand possible connections between symptoms and existing conditions,
identify patterns, and determine urgency of professional consultation.
Always recommend seeing a healthcare provider for proper diagnosis."""
        
        user_prompt = f"""USER HEALTH CONTEXT:
{json.dumps(context, indent=2, default=str)}

CURRENT SYMPTOMS:
{symptoms_description}

Provide:
1. Possible connections to existing conditions or medications
2. Urgency assessment (seek immediate care, schedule appointment soon, monitor)
3. Questions to ask healthcare provider
4. Self-care measures (only if appropriate and safe)
5. Red flags to watch for

IMPORTANT: Emphasize this is not a diagnosis and professional evaluation is needed."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = await self._call_llm(messages, temperature=0.5)
        
        return {
            "analysis": response,
            "disclaimer": "This analysis is for informational purposes only and is not a medical diagnosis. Please consult a healthcare professional for proper evaluation.",
            "generated_at": datetime.now().isoformat()
        }
