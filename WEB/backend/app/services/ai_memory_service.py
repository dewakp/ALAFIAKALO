"""AI Memory and Learning Service."""

from datetime import datetime, timedelta, date, timezone
from typing import List, Dict, Any, Optional
from collections import Counter

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.user import User
from app.models.ai_memory import (
    UserMemory, CollectiveInsight, GlobalKnowledge,
    AIInteraction
)
from app.models.nutrition import NutritionLog
from app.models.fitness import FitnessLog
from app.models.mood import MoodEntry
from app.models.sleep import SleepLog
from app.models.privacy import PrivacySettings


# Nutrients / fitness metrics aggregated into anonymized demographic baselines.
_BASELINE_NUTRIENTS = [
    "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g",
    "saturated_fat_g", "sodium_mg", "potassium_mg", "phosphorus_mg",
]
_BASELINE_FITNESS = ["duration_minutes", "calories_burned", "steps"]


def _age_range(dob_str: Optional[str]) -> Optional[str]:
    """Bucket an exact DOB into a coarse age range (removes a quasi-identifier)."""
    if not dob_str:
        return None
    try:
        dob = datetime.strptime(dob_str[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    age = (datetime.now() - dob).days // 365
    for hi, label in ((18, "under_18"), (25, "18-24"), (35, "25-34"),
                      (45, "35-44"), (55, "45-54"), (65, "55-64")):
        if age < hi:
            return label
    return "65_plus"


def _baseline_confidence(n: int) -> float:
    """Confidence grows with cohort size (0.45 at n=1 → ~0.9 at n=50)."""
    return round(min(0.95, 0.4 + 0.6 * n / (n + 10)), 2)


class AIMemoryService:
    """Service for managing AI memory and learning."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== INDIVIDUAL USER INTELLIGENCE ====================
    
    def learn_from_user_data(self, user_id: int, days: int = 90) -> List[UserMemory]:
        """
        Analyze user's data and create/update memories.
        
        Discovers patterns like:
        - Preferred meal times
        - Optimal workout times
        - Sleep patterns
        - Food preferences and aversions
        - Activity preferences
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        memories_created = []
        
        # Learn nutrition patterns
        nutrition_memories = self._learn_nutrition_patterns(user_id, cutoff_date)
        memories_created.extend(nutrition_memories)
        
        # Learn fitness patterns
        fitness_memories = self._learn_fitness_patterns(user_id, cutoff_date)
        memories_created.extend(fitness_memories)
        
        # Learn mood patterns
        mood_memories = self._learn_mood_patterns(user_id, cutoff_date)
        memories_created.extend(mood_memories)
        
        # Learn sleep patterns
        sleep_memories = self._learn_sleep_patterns(user_id, cutoff_date)
        memories_created.extend(sleep_memories)
        
        self.db.commit()
        return memories_created
    
    def _learn_nutrition_patterns(self, user_id: int, cutoff_date: datetime) -> List[UserMemory]:
        """Learn nutrition preferences and patterns."""
        memories = []
        
        # Get nutrition logs
        logs = self.db.query(NutritionLog).filter(
            NutritionLog.user_id == user_id,
            NutritionLog.consumed_at >= cutoff_date
        ).all()
        
        if len(logs) < 7:  # Need at least a week of data
            return memories
        
        # Learn meal timing preferences
        meal_times = {}
        for log in logs:
            meal_type = log.meal_type
            hour = log.consumed_at.hour
            if meal_type not in meal_times:
                meal_times[meal_type] = []
            meal_times[meal_type].append(hour)
        
        for meal_type, hours in meal_times.items():
            if len(hours) >= 5:  # At least 5 occurrences
                avg_hour = sum(hours) / len(hours)
                std_dev = (sum((h - avg_hour) ** 2 for h in hours) / len(hours)) ** 0.5
                
                if std_dev < 2:  # Consistent timing (within 2 hours)
                    memory = self._create_or_update_memory(
                        user_id=user_id,
                        category="nutrition",
                        subcategory="meal_timing",
                        insight_key=f"preferred_{meal_type}_time",
                        insight_value=f"User consistently eats {meal_type} around {int(avg_hour)}:00",
                        insight_data={"avg_hour": avg_hour, "std_dev": std_dev},
                        confidence_score=min(0.9, 0.5 + (len(hours) / 30)),
                        evidence_count=len(hours)
                    )
                    memories.append(memory)
        
        # Learn calorie patterns
        daily_calories = {}
        for log in logs:
            date = log.consumed_at.date()
            daily_calories[date] = daily_calories.get(date, 0) + (log.calories_kcal or 0)
        
        if daily_calories:
            avg_calories = sum(daily_calories.values()) / len(daily_calories)
            memory = self._create_or_update_memory(
                user_id=user_id,
                category="nutrition",
                subcategory="calorie_pattern",
                insight_key="avg_daily_calories",
                insight_value=f"User averages {int(avg_calories)} calories per day",
                insight_data={"avg_calories": avg_calories, "days_tracked": len(daily_calories)},
                confidence_score=min(0.95, 0.6 + (len(daily_calories) / 90)),
                evidence_count=len(daily_calories)
            )
            memories.append(memory)
        
        return memories
    
    def _learn_fitness_patterns(self, user_id: int, cutoff_date: datetime) -> List[UserMemory]:
        """Learn fitness preferences and patterns."""
        memories = []
        
        logs = self.db.query(FitnessLog).filter(
            FitnessLog.user_id == user_id,
            FitnessLog.performed_at >= cutoff_date
        ).all()
        
        if len(logs) < 5:
            return memories
        
        # Learn preferred workout days
        weekday_counts = Counter(log.performed_at.weekday() for log in logs)
        if weekday_counts:
            top_days = weekday_counts.most_common(3)
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            preferred_days = [day_names[day] for day, count in top_days if count >= 3]
            
            if preferred_days:
                memory = self._create_or_update_memory(
                    user_id=user_id,
                    category="fitness",
                    subcategory="workout_schedule",
                    insight_key="preferred_workout_days",
                    insight_value=f"User prefers working out on {', '.join(preferred_days)}",
                    insight_data={"days": preferred_days, "counts": dict(top_days)},
                    confidence_score=0.7 + (len(logs) / 100),
                    evidence_count=len(logs)
                )
                memories.append(memory)
        
        # Learn preferred workout times
        workout_hours = [log.performed_at.hour for log in logs]
        if workout_hours:
            avg_hour = sum(workout_hours) / len(workout_hours)
            time_of_day = "morning" if avg_hour < 12 else "afternoon" if avg_hour < 17 else "evening"
            
            memory = self._create_or_update_memory(
                user_id=user_id,
                category="fitness",
                subcategory="workout_schedule",
                insight_key="preferred_workout_time",
                insight_value=f"User prefers {time_of_day} workouts (around {int(avg_hour)}:00)",
                insight_data={"avg_hour": avg_hour, "time_of_day": time_of_day},
                confidence_score=0.75,
                evidence_count=len(workout_hours)
            )
            memories.append(memory)
        
        # Learn activity preferences
        activity_counts = Counter(log.activity_type for log in logs)
        if activity_counts:
            top_activities = activity_counts.most_common(3)
            memory = self._create_or_update_memory(
                user_id=user_id,
                category="fitness",
                subcategory="activity_preferences",
                insight_key="preferred_activities",
                insight_value=f"User's favorite activities: {', '.join(act for act, _ in top_activities)}",
                insight_data={"activities": dict(top_activities)},
                confidence_score=0.85,
                evidence_count=sum(activity_counts.values())
            )
            memories.append(memory)
        
        return memories
    
    def _learn_mood_patterns(self, user_id: int, cutoff_date: datetime) -> List[UserMemory]:
        """Learn mood and energy patterns."""
        memories = []
        
        entries = self.db.query(MoodEntry).filter(
            MoodEntry.user_id == user_id,
            MoodEntry.recorded_at >= cutoff_date
        ).all()
        
        if len(entries) < 7:
            return memories
        
        # Learn mood trends
        avg_mood = sum(e.mood_score for e in entries if e.mood_score) / len([e for e in entries if e.mood_score])
        avg_energy = sum(e.energy_level for e in entries if e.energy_level) / len([e for e in entries if e.energy_level])
        avg_stress = sum(e.stress_level for e in entries if e.stress_level) / len([e for e in entries if e.stress_level])
        
        mood_assessment = "positive" if avg_mood >= 7 else "neutral" if avg_mood >= 5 else "needs_attention"
        energy_assessment = "high" if avg_energy >= 7 else "moderate" if avg_energy >= 5 else "low"
        
        memory = self._create_or_update_memory(
            user_id=user_id,
            category="mood",
            subcategory="baseline",
            insight_key="mood_baseline",
            insight_value=f"User's baseline: {mood_assessment} mood, {energy_assessment} energy",
            insight_data={
                "avg_mood": avg_mood,
                "avg_energy": avg_energy,
                "avg_stress": avg_stress,
                "entries_count": len(entries)
            },
            confidence_score=0.8,
            evidence_count=len(entries)
        )
        memories.append(memory)
        
        return memories
    
    def _learn_sleep_patterns(self, user_id: int, cutoff_date: datetime) -> List[UserMemory]:
        """Learn sleep preferences and patterns."""
        memories = []
        
        logs = self.db.query(SleepLog).filter(
            SleepLog.user_id == user_id,
            SleepLog.bedtime >= cutoff_date
        ).all()
        
        if len(logs) < 7:
            return memories
        
        # Learn sleep schedule
        bedtimes = [log.bedtime.hour + log.bedtime.minute / 60 for log in logs]
        avg_bedtime = sum(bedtimes) / len(bedtimes)
        
        # Determine chronotype
        if avg_bedtime < 22:
            chronotype = "early_bird"
        elif avg_bedtime > 24:
            chronotype = "night_owl"
        else:
            chronotype = "intermediate"
        
        memory = self._create_or_update_memory(
            user_id=user_id,
            category="sleep",
            subcategory="chronotype",
            insight_key="sleep_chronotype",
            insight_value=f"User is a {chronotype.replace('_', ' ')} (bedtime ~{int(avg_bedtime)}:00)",
            insight_data={"avg_bedtime": avg_bedtime, "chronotype": chronotype},
            confidence_score=0.85,
            evidence_count=len(bedtimes)
        )
        memories.append(memory)
        
        return memories
    
    def _create_or_update_memory(
        self,
        user_id: int,
        category: str,
        subcategory: str,
        insight_key: str,
        insight_value: str,
        insight_data: dict,
        confidence_score: float,
        evidence_count: int
    ) -> UserMemory:
        """Create new memory or update existing one."""
        existing = self.db.query(UserMemory).filter(
            UserMemory.user_id == user_id,
            UserMemory.category == category,
            UserMemory.insight_key == insight_key
        ).first()
        
        if existing:
            existing.insight_value = insight_value
            existing.insight_data = insight_data
            existing.confidence_score = min(1.0, confidence_score)
            existing.evidence_count = evidence_count
            existing.last_confirmed_at = datetime.now()
            existing.updated_at = datetime.now()
            return existing
        else:
            memory = UserMemory(
                user_id=user_id,
                category=category,
                subcategory=subcategory,
                insight_key=insight_key,
                insight_value=insight_value,
                insight_data=insight_data,
                confidence_score=min(1.0, confidence_score),
                evidence_count=evidence_count,
                last_confirmed_at=datetime.now()
            )
            self.db.add(memory)
            return memory
    
    def get_user_memories(
        self, 
        user_id: int, 
        category: Optional[str] = None,
        min_confidence: float = 0.5
    ) -> List[UserMemory]:
        """Retrieve user's learned memories."""
        query = self.db.query(UserMemory).filter(
            UserMemory.user_id == user_id,
            UserMemory.confidence_score >= min_confidence,
            UserMemory.is_actionable == True
        )
        
        if category:
            query = query.filter(UserMemory.category == category)
        
        return query.order_by(desc(UserMemory.priority), desc(UserMemory.confidence_score)).all()
    
    # ==================== COLLECTIVE USER INTELLIGENCE ====================
    
    def discover_collective_patterns(self, category: str, min_users: int = 10) -> List[CollectiveInsight]:
        """
        Discover patterns across all users.
        
        Example patterns:
        - "Users who eat breakfast within 1 hour of waking report 15% higher energy levels"
        - "Morning workouts correlate with better sleep quality"
        - "High protein breakfast reduces afternoon energy crashes"
        """
        # This is a simplified implementation
        # In production, use proper statistical analysis
        
        insights = []
        
        if category == "nutrition":
            insights.extend(self._discover_nutrition_patterns(min_users))
        elif category == "fitness":
            insights.extend(self._discover_fitness_patterns(min_users))
        
        self.db.commit()
        return insights
    
    # ── Demographic baselines (the privacy-preserving learning loop) ──────────

    def _demographic_bucket(self, user: User) -> Dict[str, Any]:
        """Coarse, non-identifying demographic key for cohort aggregation."""
        return {
            "age_range": _age_range(getattr(user, "date_of_birth", None)),
            "gender_at_birth": getattr(user, "gender_at_birth", None),
            "activity_level": getattr(user, "activity_level", None),
        }

    def _has_collective_consent(self, user_id: int) -> bool:
        """True if the user permits anonymized cross-user learning."""
        ps = self.db.query(PrivacySettings).filter(PrivacySettings.user_id == user_id).first()
        if ps is None:
            return False  # privacy-safe default: no consent record → don't aggregate
        return bool(ps.allow_collective_insights or ps.allow_anonymized_analytics)

    def _user_daily_means(self, model, fields: List[str], user_id: int, days: int = 90) -> Dict[str, float]:
        """Average per-active-day value for `fields` from the user's logs."""
        cutoff = date.today() - timedelta(days=days)
        rows = self.db.query(model).filter(
            model.user_id == user_id, model.log_date >= cutoff
        ).all()
        if not rows:
            return {}
        days_logged = len({r.log_date for r in rows}) or 1
        totals: Dict[str, float] = {}
        for r in rows:
            for k in fields:
                v = getattr(r, k, None)
                if isinstance(v, (int, float)):
                    totals[k] = totals.get(k, 0) + v
        return {k: round(v / days_logged, 1) for k, v in totals.items()}

    def _find_baseline(self, category: str, bucket: Dict[str, Any]) -> Optional[CollectiveInsight]:
        rows = self.db.query(CollectiveInsight).filter(
            CollectiveInsight.category == category,
            CollectiveInsight.pattern_type == "demographic_baseline",
        ).all()
        for ci in rows:
            if (ci.applicable_demographics or {}) == bucket:
                return ci
        return None

    def _new_baseline(self, category: str, bucket: Dict[str, Any], means: Dict[str, float], n: int) -> CollectiveInsight:
        label = "/".join(str(bucket.get(k) or "all") for k in ("age_range", "gender_at_birth", "activity_level"))
        ci = CollectiveInsight(
            category=category,
            pattern_type="demographic_baseline",
            pattern_name=f"{category.title()} baseline · {label}",
            pattern_description=(
                f"Anonymized average daily {category} intake aggregated across "
                f"consenting users in this demographic cohort."
            ),
            pattern_data={"means": means},
            sample_size=n,
            confidence_level=_baseline_confidence(n),
            effect_size=None,
            applicable_demographics=bucket,
            is_active=True,
        )
        self.db.add(ci)
        return ci

    def merge_demographic_baseline(self, user: User, category: str = "nutrition") -> Optional[CollectiveInsight]:
        """Fold ONE user's de-identified daily means into the cohort baseline.

        This is the contribution side of the learning loop: when a user leaves
        (account deletion) or opts in, their statistical footprint is merged into
        the matching demographic CollectiveInsight via a running mean — preserving
        population value while discarding all PII. Consent-gated; returns the
        updated/created insight or None.
        """
        if not self._has_collective_consent(user.id):
            return None
        model, fields = (NutritionLog, _BASELINE_NUTRIENTS) if category == "nutrition" else (FitnessLog, _BASELINE_FITNESS)
        means = self._user_daily_means(model, fields, user.id)
        if not means:
            return None

        bucket = self._demographic_bucket(user)
        ci = self._find_baseline(category, bucket)
        if ci is None:
            return self._new_baseline(category, bucket, means, n=1)

        old = (ci.pattern_data or {}).get("means", {})
        n = ci.sample_size or 1
        merged: Dict[str, float] = {}
        for k in set(old) | set(means):
            ov, nv = old.get(k), means.get(k)
            if ov is None:
                merged[k] = nv
            elif nv is None:
                merged[k] = ov
            else:
                merged[k] = round((ov * n + nv) / (n + 1), 1)
        ci.pattern_data = {"means": merged}          # reassign → SQLAlchemy tracks change
        ci.sample_size = n + 1
        ci.confidence_level = _baseline_confidence(ci.sample_size)
        ci.last_validated_at = datetime.now(timezone.utc)
        return ci

    def _discover_baselines(self, category: str, model, fields: List[str], min_users: int) -> List[CollectiveInsight]:
        """Recompute authoritative demographic baselines from all consenting users."""
        users = self.db.query(User).filter(User.is_active == True).all()  # noqa: E712
        cohorts: Dict[tuple, Dict[str, Any]] = {}
        for u in users:
            if not self._has_collective_consent(u.id):
                continue
            means = self._user_daily_means(model, fields, u.id)
            if not means:
                continue
            bucket = self._demographic_bucket(u)
            key = (bucket["age_range"], bucket["gender_at_birth"], bucket["activity_level"])
            acc = cohorts.setdefault(key, {"sum": {}, "n": 0, "bucket": bucket})
            for k, v in means.items():
                acc["sum"][k] = acc["sum"].get(k, 0) + v
            acc["n"] += 1

        insights: List[CollectiveInsight] = []
        for acc in cohorts.values():
            if acc["n"] < min_users:
                continue
            cohort_means = {k: round(v / acc["n"], 1) for k, v in acc["sum"].items()}
            ci = self._find_baseline(category, acc["bucket"])
            if ci is None:
                ci = self._new_baseline(category, acc["bucket"], cohort_means, acc["n"])
            else:
                ci.pattern_data = {"means": cohort_means}
                ci.sample_size = acc["n"]
                ci.confidence_level = _baseline_confidence(acc["n"])
                ci.last_validated_at = datetime.now(timezone.utc)
            insights.append(ci)
        return insights

    def _discover_nutrition_patterns(self, min_users: int) -> List[CollectiveInsight]:
        """Aggregate anonymized daily-nutrition baselines per demographic cohort."""
        return self._discover_baselines("nutrition", NutritionLog, _BASELINE_NUTRIENTS, min_users)

    def _discover_fitness_patterns(self, min_users: int) -> List[CollectiveInsight]:
        """Aggregate anonymized daily-activity baselines per demographic cohort."""
        return self._discover_baselines("fitness", FitnessLog, _BASELINE_FITNESS, min_users)
    
    def get_applicable_insights(
        self, 
        user: User, 
        category: str,
        limit: int = 5
    ) -> List[CollectiveInsight]:
        """Get collective insights applicable to this user."""
        query = self.db.query(CollectiveInsight).filter(
            CollectiveInsight.category == category,
            CollectiveInsight.is_active == True,
            CollectiveInsight.confidence_level >= 0.7
        )
        
        # Filter by demographics if available
        # (simplified - in production, use JSON queries)
        
        return query.order_by(
            desc(CollectiveInsight.confidence_level),
            desc(CollectiveInsight.sample_size)
        ).limit(limit).all()
    
    # ==================== GLOBAL INTELLIGENCE ====================
    
    def add_global_knowledge(
        self,
        knowledge_type: str,
        domain: str,
        topic: str,
        title: str,
        summary: str,
        source_organization: str,
        evidence_level: str,
        **kwargs
    ) -> GlobalKnowledge:
        """Add knowledge from external authoritative sources."""
        knowledge = GlobalKnowledge(
            knowledge_type=knowledge_type,
            domain=domain,
            topic=topic,
            title=title,
            summary=summary,
            source_organization=source_organization,
            evidence_level=evidence_level,
            **kwargs
        )
        self.db.add(knowledge)
        self.db.commit()
        return knowledge
    
    def get_relevant_knowledge(
        self,
        domain: str,
        topics: List[str],
        limit: int = 5
    ) -> List[GlobalKnowledge]:
        """Get relevant global knowledge for given topics."""
        query = self.db.query(GlobalKnowledge).filter(
            GlobalKnowledge.domain == domain,
            GlobalKnowledge.topic.in_(topics),
            GlobalKnowledge.is_active == True
        )
        
        return query.order_by(
            desc(GlobalKnowledge.relevance_score),
            desc(GlobalKnowledge.publication_date)
        ).limit(limit).all()
    
    # ==================== INTERACTION TRACKING ====================
    
    def record_interaction(
        self,
        user_id: int,
        interaction_type: str,
        category: str,
        user_request: Optional[str],
        ai_response: str,
        context_used: dict,
        llm_provider: str,
        llm_model: str,
        **kwargs
    ) -> AIInteraction:
        """Record an AI interaction for learning."""
        interaction = AIInteraction(
            user_id=user_id,
            interaction_type=interaction_type,
            category=category,
            user_request=user_request,
            ai_response=ai_response,
            context_used=context_used,
            llm_provider=llm_provider,
            llm_model=llm_model,
            **kwargs
        )
        self.db.add(interaction)
        self.db.commit()
        return interaction
    
    def update_interaction_feedback(
        self,
        interaction_id: int,
        was_helpful: bool,
        user_feedback: Optional[str] = None,
        was_followed: Optional[bool] = None
    ) -> AIInteraction:
        """Update interaction with user feedback."""
        interaction = self.db.query(AIInteraction).get(interaction_id)
        if interaction:
            interaction.was_helpful = was_helpful
            interaction.user_feedback = user_feedback
            interaction.was_followed = was_followed
            interaction.feedback_received_at = datetime.now()
            
            # Derive sentiment from helpfulness
            interaction.user_sentiment = "positive" if was_helpful else "negative"
            
            self.db.commit()
        
        return interaction
    
    def get_interaction_history(
        self,
        user_id: int,
        interaction_type: Optional[str] = None,
        limit: int = 20
    ) -> List[AIInteraction]:
        """Get user's interaction history."""
        query = self.db.query(AIInteraction).filter(
            AIInteraction.user_id == user_id
        )
        
        if interaction_type:
            query = query.filter(AIInteraction.interaction_type == interaction_type)
        
        return query.order_by(desc(AIInteraction.created_at)).limit(limit).all()
