"""AI Memory and Intelligence Models."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean, JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserMemory(Base):
    """
    Individual user intelligence - AI learns from each user's patterns and preferences.
    
    Stores insights, patterns, and learned preferences specific to each user.
    """
    __tablename__ = "user_memories"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    # Memory categorization
    category: Mapped[str] = mapped_column(String(50), index=True)  # nutrition, fitness, sleep, mood, health, preference
    subcategory: Mapped[Optional[str]] = mapped_column(String(50))  # breakfast_preference, workout_time, sleep_pattern, etc.
    
    # Memory content
    insight_key: Mapped[str] = mapped_column(String(100), index=True)  # unique key like "preferred_breakfast_time"
    insight_value: Mapped[str] = mapped_column(Text)  # "User prefers eating breakfast between 7-8am"
    insight_data: Mapped[Optional[dict]] = mapped_column(JSON)  # structured data supporting the insight
    
    # Learning metrics
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)  # 0-1, how confident is this insight
    evidence_count: Mapped[int] = mapped_column(Integer, default=1)  # how many data points support this
    last_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Actionability
    is_actionable: Mapped[bool] = mapped_column(Boolean, default=True)  # can be used in recommendations
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1-10, importance in recommendations
    
    # Metadata
    learned_from_period: Mapped[Optional[str]] = mapped_column(String(100))  # "Jan 2024 - Feb 2024"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    user = relationship("User", back_populates="ai_memories")
    
    __table_args__ = (
        Index('idx_user_category_key', 'user_id', 'category', 'insight_key'),
    )


class CollectiveInsight(Base):
    """
    All users intelligence - aggregate patterns learned from the entire user base.
    
    Stores anonymized insights discovered across all users to improve recommendations.
    """
    __tablename__ = "collective_insights"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Insight classification
    category: Mapped[str] = mapped_column(String(50), index=True)  # nutrition, fitness, sleep, correlations
    pattern_type: Mapped[str] = mapped_column(String(100), index=True)  # success_pattern, warning_pattern, correlation
    
    # Pattern description
    pattern_name: Mapped[str] = mapped_column(String(200))  # "High protein breakfast improves energy"
    pattern_description: Mapped[str] = mapped_column(Text)  # detailed description
    pattern_data: Mapped[dict] = mapped_column(JSON)  # statistical data, conditions, thresholds
    
    # Statistical validation
    sample_size: Mapped[int] = mapped_column(Integer)  # how many users contribute to this pattern
    confidence_level: Mapped[float] = mapped_column(Float)  # statistical confidence (0-1)
    effect_size: Mapped[Optional[float]] = mapped_column(Float)  # magnitude of the pattern
    p_value: Mapped[Optional[float]] = mapped_column(Float)  # statistical significance
    
    # Applicability
    applicable_demographics: Mapped[Optional[dict]] = mapped_column(JSON)  # age_range, gender, activity_level, etc.
    applicable_conditions: Mapped[Optional[dict]] = mapped_column(JSON)  # conditions where this applies
    
    # Usage tracking
    times_applied: Mapped[int] = mapped_column(Integer, default=0)  # how often used in recommendations
    positive_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    last_validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    __table_args__ = (
        Index('idx_category_active', 'category', 'is_active'),
    )


class GlobalKnowledge(Base):
    """
    Global intelligence - curated knowledge from medical research, health organizations, etc.
    
    Stores evidence-based health knowledge from external authoritative sources.
    """
    __tablename__ = "global_knowledge"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Knowledge classification
    knowledge_type: Mapped[str] = mapped_column(String(50), index=True)  # guideline, research_finding, best_practice, warning
    domain: Mapped[str] = mapped_column(String(50), index=True)  # nutrition, fitness, sleep, mental_health, medical
    topic: Mapped[str] = mapped_column(String(200), index=True)  # specific topic like "vitamin_d_deficiency"
    
    # Content
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)  # concise summary for AI context
    full_content: Mapped[Optional[str]] = mapped_column(Text)  # detailed information
    key_points: Mapped[Optional[list]] = mapped_column(JSON)  # bullet points for quick reference
    
    # Evidence and credibility
    source_organization: Mapped[str] = mapped_column(String(200))  # WHO, NIH, AHA, etc.
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    evidence_level: Mapped[str] = mapped_column(String(20))  # high, moderate, low, expert_opinion
    publication_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Applicability
    applies_to_demographics: Mapped[Optional[dict]] = mapped_column(JSON)  # age ranges, gender, etc.
    contraindications: Mapped[Optional[list]] = mapped_column(JSON)  # when NOT to apply this
    
    # Usage tracking
    times_referenced: Mapped[int] = mapped_column(Integer, default=0)
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0)  # 0-1, how relevant/current
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    __table_args__ = (
        Index('idx_domain_topic_active', 'domain', 'topic', 'is_active'),
    )


class AIInteraction(Base):
    """
    Track all AI interactions for learning and improvement.
    
    Stores every AI recommendation with user feedback to enable continuous learning.
    """
    __tablename__ = "ai_interactions"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    # Interaction details
    interaction_type: Mapped[str] = mapped_column(String(50), index=True)  # recommendation, symptom_analysis, question
    category: Mapped[str] = mapped_column(String(50))  # nutrition, fitness, sleep, wellness
    
    # Request & Response
    user_request: Mapped[Optional[str]] = mapped_column(Text)  # what user asked
    ai_response: Mapped[str] = mapped_column(Text)  # what AI recommended
    context_used: Mapped[dict] = mapped_column(JSON)  # snapshot of context used for this recommendation
    
    # Outcome tracking
    was_helpful: Mapped[Optional[bool]] = mapped_column(Boolean)  # user feedback
    user_feedback: Mapped[Optional[str]] = mapped_column(Text)  # additional comments
    was_followed: Mapped[Optional[bool]] = mapped_column(Boolean)  # did user act on recommendation
    outcome_measured: Mapped[Optional[dict]] = mapped_column(JSON)  # quantifiable outcomes if tracked
    
    # Learning signals
    user_sentiment: Mapped[Optional[str]] = mapped_column(String(20))  # positive, neutral, negative
    recommendation_quality_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 computed score
    
    # Metadata
    llm_provider: Mapped[str] = mapped_column(String(20))  # openai, anthropic
    llm_model: Mapped[str] = mapped_column(String(50))  # gpt-4-turbo, claude-3-5-sonnet
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    feedback_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="ai_interactions")
    
    __table_args__ = (
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_type_category', 'interaction_type', 'category'),
    )


class LearningEvent(Base):
    """
    Track learning events when AI updates its understanding.
    
    Audit trail of how the AI's intelligence evolves over time.
    """
    __tablename__ = "learning_events"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Event classification
    event_type: Mapped[str] = mapped_column(String(50), index=True)  # insight_discovered, pattern_validated, knowledge_updated
    intelligence_level: Mapped[str] = mapped_column(String(20), index=True)  # individual, collective, global
    
    # Related entity
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    memory_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_memories.id", ondelete="SET NULL"))
    insight_id: Mapped[Optional[int]] = mapped_column(ForeignKey("collective_insights.id", ondelete="SET NULL"))
    knowledge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("global_knowledge.id", ondelete="SET NULL"))
    
    # Event details
    description: Mapped[str] = mapped_column(Text)
    data_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence_change: Mapped[Optional[float]] = mapped_column(Float)  # how much confidence increased/decreased
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class HealthEmbedding(Base):
    """
    Semantic RAG: stores vector embeddings of each patient's health record sections.

    Each section of the patient context (MEDICATIONS, LAB RESULTS, etc.) is embedded
    using llama3.2 (3072-dim) and stored here.  On each AI query, the query is embedded
    and compared via cosine similarity to retrieve the most semantically relevant sections.
    """
    __tablename__ = "health_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Section identification
    chunk_key: Mapped[str] = mapped_column(String(100), index=True)   # e.g. "MEDICATIONS", "LAB RESULTS"
    chunk_text: Mapped[str] = mapped_column(Text)                      # original text of the section

    # Embedding vector (llama3.2, 3072 dims) stored as JSON float array
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)

    # Freshness tracking — embeddings older than 4 hours are refreshed
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "chunk_key", name="uq_user_chunk"),
        Index("idx_health_emb_user_updated", "user_id", "updated_at"),
    )
