# ALAFIA AI Memory & Learning Intelligence

## Overview

ALAFIA's AI possesses a sophisticated three-tier memory and learning system that makes it increasingly intelligent over time. The system learns at three levels:

1. **Individual User Intelligence** - Learns from each user's unique patterns and preferences
2. **Collective User Intelligence** - Discovers patterns across all app users (anonymized)
3. **Global Intelligence** - Integrates evidence-based knowledge from authoritative health sources

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  AI Memory & Learning System                 │
├─────────────────┬──────────────────┬────────────────────────┤
│   Individual    │   Collective     │       Global           │
│   Intelligence  │   Intelligence   │   Intelligence         │
├─────────────────┼──────────────────┼────────────────────────┤
│ User Memories   │ Collective       │ Global Knowledge       │
│ (per person)    │ Insights         │ (WHO, NIH, etc.)       │
│                 │ (all users)      │                        │
│ • Meal timing   │ • Success        │ • Guidelines           │
│ • Workout prefs │   patterns       │ • Research findings    │
│ • Sleep habits  │ • Correlations   │ • Best practices       │
│ • Food prefs    │ • Warnings       │ • Evidence-based       │
│                 │ • Demographics   │   recommendations      │
└─────────────────┴──────────────────┴────────────────────────┘
                           ↓
                  ┌──────────────────┐
                  │  AI Interactions │
                  │   (Learning Log) │
                  └──────────────────┘
                           ↓
              Every interaction teaches the AI
```

## Database Schema

### 1. UserMemory (Individual Intelligence)
Stores personal insights learned from each user's data.

**Key Fields:**
- `category`: nutrition, fitness, sleep, mood, health, preference
- `subcategory`: meal_timing, workout_schedule, chronotype, etc.
- `insight_key`: Unique identifier (e.g., "preferred_breakfast_time")
- `insight_value`: Human-readable insight
- `insight_data`: JSON with supporting data
- `confidence_score`: 0-1, how confident the AI is
- `evidence_count`: Number of data points supporting this insight
- `priority`: 1-10, importance for recommendations

**Example Memory:**
```json
{
  "category": "nutrition",
  "subcategory": "meal_timing",
  "insight_key": "preferred_breakfast_time",
  "insight_value": "User consistently eats breakfast around 7:00",
  "insight_data": {"avg_hour": 7.2, "std_dev": 0.8},
  "confidence_score": 0.92,
  "evidence_count": 45
}
```

### 2. CollectiveInsight (All Users Intelligence)
Patterns discovered across the entire user base (anonymized).

**Key Fields:**
- `pattern_type`: success_pattern, warning_pattern, correlation
- `pattern_name`: Brief pattern description
- `pattern_description`: Detailed explanation
- `sample_size`: Number of users contributing
- `confidence_level`: Statistical confidence (0-1)
- `effect_size`: Magnitude of the effect
- `p_value`: Statistical significance
- `applicable_demographics`: When this applies (age, gender, etc.)
- `times_applied`: Usage count in recommendations

**Example Insight:**
```json
{
  "pattern_type": "success_pattern",
  "pattern_name": "Morning protein boost",
  "pattern_description": "Users who consume 30g+ protein at breakfast report 18% higher sustained energy levels throughout the day",
  "sample_size": 1247,
  "confidence_level": 0.87,
  "effect_size": 0.18,
  "p_value": 0.003,
  "applicable_demographics": {"age_range": [18, 65], "activity_level": ["moderate", "high"]}
}
```

### 3. GlobalKnowledge (World Intelligence)
Curated health knowledge from authoritative sources.

**Key Fields:**
- `knowledge_type`: guideline, research_finding, best_practice, warning
- `domain`: nutrition, fitness, sleep, mental_health, medical
- `topic`: Specific topic (vitamin_d_deficiency, hiit_training, etc.)
- `title`: Knowledge title
- `summary`: Concise AI-friendly summary
- `source_organization`: WHO, NIH, AHA, CDC, etc.
- `evidence_level`: high, moderate, low, expert_opinion
- `source_url`: Reference link
- `publication_date`: When published

**Example Knowledge:**
```json
{
  "knowledge_type": "guideline",
  "domain": "nutrition",
  "topic": "vitamin_d",
  "title": "Vitamin D Deficiency Prevention",
  "summary": "Adults should maintain vitamin D levels of 20-50 ng/mL. Daily intake of 600-800 IU recommended, up to 4000 IU safe upper limit.",
  "source_organization": "National Institutes of Health (NIH)",
  "evidence_level": "high",
  "source_url": "https://ods.od.nih.gov/factsheets/VitaminD-HealthProfessional/",
  "publication_date": "2024-01-15"
}
```

### 4. AIInteraction (Learning Log)
Tracks every AI recommendation with user feedback.

**Key Fields:**
- `interaction_type`: recommendation, symptom_analysis, question
- `category`: nutrition, fitness, sleep, wellness
- `user_request`: What user asked
- `ai_response`: What AI recommended
- `context_used`: Snapshot of data AI considered
- `was_helpful`: User feedback (boolean)
- `user_feedback`: Additional comments
- `was_followed`: Did user act on it?
- `user_sentiment`: positive, neutral, negative
- `llm_provider`: openai, anthropic
- `llm_model`: gpt-4-turbo, claude-3-5-sonnet
- `tokens_used`: Cost tracking
- `response_time_ms`: Performance tracking

**Purpose:** Enables the AI to learn from successes and failures.

### 5. LearningEvent (Audit Trail)
Tracks when AI updates its intelligence.

**Key Fields:**
- `event_type`: insight_discovered, pattern_validated, knowledge_updated
- `intelligence_level`: individual, collective, global
- `description`: What changed
- `confidence_change`: How much confidence shifted

## Learning Mechanisms

### How Individual Intelligence Works

The AI analyzes user data periodically to discover patterns:

**1. Meal Timing Patterns**
```python
# Analyzes when user eats each meal type
# If breakfast consistently at 7am (±1 hour), creates memory:
{
  "insight": "User prefers breakfast around 7:00",
  "confidence": 0.85,  # High consistency
  "evidence": 42  # Days of data
}
```

**2. Workout Preferences**
```python
# Discovers:
# - Preferred days (Monday, Wednesday, Friday)
# - Preferred time (6pm = evening workouts)
# - Favorite activities (running, yoga)
# Creates actionable memories for future recommendations
```

**3. Sleep Patterns**
```python
# Determines chronotype:
# Bedtime < 10pm = early_bird
# Bedtime > 12am = night_owl
# Optimizes recommendations to user's natural rhythm
```

**4. Mood Correlations**
```python
# Tracks mood baseline
# Identifies triggers (both positive and negative)
# Learns what improves user's mental state
```

### How Collective Intelligence Works

Statistical analysis across all users (requires consent):

**Pattern Discovery Process:**
1. Aggregate anonymized data from all users
2. Perform statistical analysis (correlations, A/B comparisons)
3. Validate with p-values and effect sizes
4. Create insights when statistically significant
5. Apply to users matching demographics

**Example Discoveries:**
- "Users who exercise within 3 hours of sleep have 23% worse sleep quality"
- "Mediterranean diet users show 15% better mood stability"
- "Morning workouts correlate with 12% better adherence rates"

### How Global Intelligence Works

**Knowledge Curation:**
1. Health team curates knowledge from trusted sources
2. Summaries are AI-friendly (used in prompts)
3. Ranked by evidence level (high > moderate > low)
4. Updated when new research emerges

**Sources:**
- World Health Organization (WHO)
- National Institutes of Health (NIH)
- American Heart Association (AHA)
- Centers for Disease Control (CDC)
- Peer-reviewed medical journals
- Evidence-based clinical guidelines

## API Endpoints

### POST `/api/v1/personalization/learn-from-data`
Trigger AI to analyze user's data and create memories.

**Request:**
```bash
POST /api/v1/personalization/learn-from-data?days=90
Authorization: Bearer {token}
```

**Response:**
```json
{
  "memories_created": 8,
  "categories": ["nutrition", "fitness", "sleep", "mood"],
  "message": "AI learned 8 new insights from your data"
}
```

### GET `/api/v1/personalization/memories`
View what the AI has learned about you.

**Request:**
```bash
GET /api/v1/personalization/memories?category=nutrition&min_confidence=0.7
Authorization: Bearer {token}
```

**Response:**
```json
{
  "total_memories": 5,
  "memories": [
    {
      "category": "nutrition",
      "subcategory": "meal_timing",
      "insight": "User consistently eats breakfast around 7:00",
      "confidence": 0.92,
      "evidence_count": 45,
      "learned_at": "2024-01-15T10:30:00",
      "last_confirmed": "2024-02-13T09:15:00"
    }
  ]
}
```

### GET `/api/v1/personalization/interaction-history`
See past AI interactions and your feedback.

**Request:**
```bash
GET /api/v1/personalization/interaction-history?limit=10
Authorization: Bearer {token}
```

**Response:**
```json
{
  "total": 10,
  "interactions": [
    {
      "id": 123,
      "type": "recommendation",
      "category": "nutrition",
      "request": "Help me increase my protein intake",
      "response_preview": "Based on your current average of 60g protein/day and your goal...",
      "was_helpful": true,
      "was_followed": true,
      "created_at": "2024-02-10T14:30:00",
      "model_used": "openai/gpt-4-turbo"
    }
  ]
}
```

### POST `/api/v1/personalization/interactions/{id}/feedback`
Teach the AI by providing feedback on recommendations.

**Request:**
```bash
POST /api/v1/personalization/interactions/123/feedback
Authorization: Bearer {token}
Content-Type: application/json

{
  "was_helpful": true,
  "user_feedback": "This really helped! Energy levels improved significantly",
  "was_followed": true
}
```

**Response:**
```json
{
  "message": "Thank you for your feedback!",
  "interaction_id": 123,
  "sentiment": "positive"
}
```

### GET `/api/v1/personalization/collective-insights`
View patterns learned from all users (requires data_sharing_consent).

**Request:**
```bash
GET /api/v1/personalization/collective-insights?category=fitness&limit=5
Authorization: Bearer {token}
```

**Response:**
```json
{
  "total": 5,
  "insights": [
    {
      "pattern_name": "Morning workout adherence boost",
      "description": "Users who schedule workouts before 9am show 27% better long-term adherence",
      "category": "fitness",
      "confidence_level": 0.89,
      "based_on_users": 3420,
      "effect_size": 0.27,
      "positive_feedback": 1247,
      "negative_feedback": 83
    }
  ]
}
```

### GET `/api/v1/personalization/global-knowledge`
Access evidence-based health knowledge.

**Request:**
```bash
GET /api/v1/personalization/global-knowledge?domain=nutrition&topics=protein,vitamins
Authorization: Bearer {token}
```

**Response:**
```json
{
  "total": 3,
  "knowledge_items": [
    {
      "title": "Protein Intake Guidelines for Active Adults",
      "summary": "Active adults should consume 1.2-2.0g protein per kg bodyweight daily...",
      "domain": "nutrition",
      "topic": "protein",
      "source": "International Society of Sports Nutrition",
      "evidence_level": "high",
      "source_url": "https://...",
      "publication_date": "2023-09-15",
      "times_referenced": 3420
    }
  ]
}
```

## How Memory Enhances Recommendations

### Before Memory (Generic AI):
```
User: "What should I eat for breakfast?"

AI: "A balanced breakfast typically includes:
- Whole grains (oatmeal, whole wheat toast)
- Protein (eggs, Greek yogurt)  
- Fruit (berries, banana)
- Healthy fats (avocado, nuts)"
```

### After Learning (Intelligent AI):
```
User: "What should I eat for breakfast?"

AI: "Based on your patterns, I know you:
✓ Prefer eating breakfast around 7:00am
✓ Like Mediterranean flavors (learned from past logs)
✓ Need 30g+ protein (your morning workouts at 8:30am)
✓ Are lactose intolerant (from your profile)
✓ Users like you report 18% better energy with high-protein breakfasts

Recommendation for YOU:
- 7:00am: Greek-style omelet (3 eggs)
  • With spinach, tomatoes, olives (your preferences!)
  • Whole grain pita on the side
  • 35g protein, ready in 10 minutes
  • Matches your Mediterranean preferences
  • Fuels your 8:30am workout optimally

This is personalized for YOUR schedule, preferences, and goals."
```

## Privacy & Ethics

### Data Usage Levels

**Level 1: Individual Learning (Always Active)**
- AI learns from YOUR data only
- Improves YOUR recommendations
- Never shared with anyone
- Can be disabled in settings

**Level 2: Collective Learning (Opt-in: data_sharing_consent)**
- Your anonymized data helps discover patterns
- Personal identity completely removed
- Sample sizes always 10+ users minimum
- Helps all ALAFIA users improve
- Can be revoked anytime

**Level 3: AI Training (Opt-in: ai_training_consent)**
- Your interactions help improve the AI model
- Fully anonymized
- Used to make AI smarter for everyone
- Can be revoked anytime

### User Controls

**Disable AI Coaching:**
```json
PUT /api/v1/personalization/profile
{
  "ai_coaching_enabled": false  // Stops all AI learning
}
```

**Opt-out of Collective Intelligence:**
```json
PUT /api/v1/personalization/profile
{
  "data_sharing_consent": false  // Your data not used for insights
}
```

**Opt-out of AI Training:**
```json
PUT /api/v1/personalization/profile
{
  "ai_training_consent": false  // Interactions not used for training
}
```

## Performance & Scalability

**Memory Creation:**
- Automatic learning runs nightly for active users
- Triggered manually via `/learn-from-data` endpoint
- Confidence scores increase with more evidence
- Old memories fade if not confirmed

**Query Optimization:**
- Composite indexes on user_id + category + insight_key
- Memories cached per user session
- Collective insights cached globally (1 hour TTL)
- Paginated results for large datasets

**Storage Efficiency:**
- JSON columns for flexible data schemas
- Aggregated insights (not raw data)
- Automatic archival of old interactions (90+ days)

## Future Enhancements

**Planned Features:**
1. **Predictive Intelligence** - Forecast health trends before they happen
2. **Causal Inference** - Understand cause-effect relationships
3. **Federated Learning** - Learn across devices without centralizing data
4. **Active Learning** - AI asks questions to fill knowledge gaps
5. **Explainable AI** - Show WHY AI made each recommendation
6. **Real-time Learning** - Update insights immediately from new data
7. **Multi-modal Learning** - Learn from images, voice, wearables

## Best Practices

**For Users:**
1. Enable AI coaching for best experience
2. Track data consistently (more data = better insights)
3. Provide feedback on recommendations
4. Review your memories periodically
5. Consider opting into collective learning (help everyone!)

**For Developers:**
1. Run learning jobs during low-traffic hours
2. Monitor confidence scores (retrain if dropping)
3. Validate collective insights with statisticians
4. Update global knowledge quarterly
5. Respect user privacy controls strictly

## Support & Documentation

- **API Documentation**: `/api/docs` (Swagger UI)
- **Memory Dashboard**: Mobile apps (Settings > AI Intelligence)
- **Privacy Settings**: Profile > AI & Privacy

---

**The more you use ALAFIA, the smarter it becomes for YOU.** 🧠✨
