# ALAFIA AI Personalization Engine

## Overview

The ALAFIA AI Personalization Engine is a proprietary LLM-based system that provides intelligent, context-aware health recommendations tailored to each user's unique profile, health history, and goals.

## Features

### 1. Comprehensive User Profiling
- **Demographics**: Age, gender, biological sex, height, weight, BMI
- **Location & Culture**: Locale, timezone, country, language preferences, measurement units
- **Health Profile**: Allergies, food intolerances, dietary restrictions, chronic conditions, family history
- **Fitness Profile**: Activity level, fitness goals, exercise preferences, weekly frequency
- **Lifestyle Factors**: Smoking status, alcohol consumption, sleep schedule, occupation, stress level
- **AI Preferences**: Personality (supportive/motivational/clinical/casual), language complexity

### 2. AI-Powered Recommendations

The engine analyzes 30-90 days of comprehensive health data to provide personalized recommendations in:

#### Nutrition
- Daily calorie and macronutrient targets based on goals and activity level
- Specific food recommendations considering allergies and restrictions
- Meal timing suggestions aligned with sleep schedule and fitness routine
- Micronutrient focus areas based on tracking gaps
- Hydration recommendations

#### Fitness
- Weekly exercise plans (frequency, duration, intensity)
- Workout types aligned with preferences and current fitness level
- Progressive overload strategies for muscle gain goals
- Recovery recommendations based on age, stress, and sleep quality
- Injury prevention tips for chronic conditions

#### Sleep
- Optimal sleep schedule based on chronotype and occupation
- Sleep environment optimization (temperature, noise, light)
- Pre-sleep routine recommendations (caffeine cutoff, screen time)
- Sleep quality improvement strategies
- Specific issue addressing (frequent awakening, etc.)

#### Wellness
- Stress management techniques
- Mood improvement strategies
- Lifestyle modification recommendations
- Social connection suggestions
- Mindfulness and mental health practices

### 3. Symptom Analysis (Non-Diagnostic)

The AI can analyze user-reported symptoms in context of:
- Existing health conditions
- Current medications
- Recent health patterns

**IMPORTANT**: This is NOT a diagnostic tool. The system always recommends professional medical consultation and provides:
- Possible connections to existing conditions
- Urgency assessment (immediate care, schedule appointment, monitor)
- Questions to ask healthcare providers
- Safe self-care measures (when appropriate)
- Red flags to watch for

### 4. Health Score

Automated scoring system (0-100) across five components:
- **Nutrition Adherence** (25%): Tracking consistency and balanced intake
- **Fitness Consistency** (25%): Workout frequency and duration
- **Sleep Quality** (20%): Hours and quality scores
- **Mood Stability** (15%): Mood, energy, and stress levels
- **Vital Signs** (15%): BMI and other metrics

## API Endpoints

### GET `/api/v1/personalization/profile`
Get user's complete personalization profile including all preferences, restrictions, and settings.

**Response**: Full user profile with JSON-parsed arrays for allergies, dietary restrictions, fitness goals, etc.

### PUT `/api/v1/personalization/profile`
Update user's personalization profile.

**Request Body**:
```json
{
  "height_cm": 175.5,
  "current_weight_kg": 70.0,
  "target_weight_kg": 68.0,
  "locale": "en-US",
  "timezone": "America/New_York",
  "allergies": ["peanuts", "shellfish"],
  "dietary_restrictions": ["gluten-free"],
  "dietary_preferences": ["mediterranean"],
  "activity_level": "moderately_active",
  "fitness_goals": ["weight_loss", "endurance"],
  "preferred_activities": ["running", "yoga"],
  "exercise_frequency_per_week": 4,
  "ai_personality_preference": "motivational"
}
```

### POST `/api/v1/personalization/recommendations`
Get AI-generated personalized recommendations.

**Request Body**:
```json
{
  "type": "nutrition|fitness|sleep|wellness",
  "specific_request": "How can I improve my energy levels?",
  "days_context": 30
}
```

**Response**:
```json
{
  "type": "nutrition",
  "recommendations": "Based on your recent data showing average intake of 1800 calories/day with 20% protein, 45% carbs, and 35% fat... [detailed recommendations]",
  "generated_at": "2024-02-14T12:00:00",
  "based_on_days": 30
}
```

### POST `/api/v1/personalization/analyze-symptoms`
Analyze symptoms with user's health context (non-diagnostic).

**Request Body**:
```json
{
  "symptoms_description": "I've been experiencing persistent headaches in the morning for the past 3 days, worse when standing up."
}
```

**Response**:
```json
{
  "analysis": "Based on your health profile... [detailed analysis with urgency assessment, possible connections, and recommendations]",
  "disclaimer": "This analysis is for informational purposes only and is not a medical diagnosis. Please consult a healthcare professional for proper evaluation.",
  "generated_at": "2024-02-14T12:00:00"
}
```

### GET `/api/v1/personalization/health-score`
Calculate overall health score based on recent tracking data.

**Response**:
```json
{
  "overall_score": 82.5,
  "component_scores": {
    "nutrition": 85.0,
    "fitness": 90.0,
    "sleep": 75.0,
    "mood": 80.0,
    "vitals": 85.0
  },
  "grade": "B",
  "calculated_at": "2024-02-14T12:00:00"
}
```

## LLM Provider Configuration

The engine supports two LLM providers:

### OpenAI (Default)
Set environment variables:
```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo-preview  # optional, defaults to this
```

### Anthropic Claude
Set environment variables:
```bash
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022  # optional, defaults to this
```

In code, specify provider:
```python
ai_engine = AIPersonalizationEngine(provider="anthropic")
```

## Safety & Privacy

### Medical Disclaimer
The AI engine is designed to provide health information and suggestions, NOT medical diagnosis or treatment. Key safety features:
- Always recommends professional consultation for concerning patterns
- Flags symptoms requiring immediate medical attention
- Considers contraindications and medication interactions
- Emphasizes individual variation in health responses

### Data Privacy
- **AI Coaching Enabled**: Users must explicitly enable AI features (default: true)
- **Data Sharing Consent**: Controls whether data can be shared with partners (default: false)
- **AI Training Consent**: Controls whether data can be used for model training (default: false)

All AI recommendations consider user's consent settings and respect data boundaries.

## Context Building

The engine builds comprehensive context from:
- **User Profile**: All personalization fields
- **Health Tracking**: Last 30-90 days of:
  - Nutrition logs (50+ nutrient fields)
  - Fitness activities
  - Sleep patterns
  - Mood entries
  - Vital signs and body composition
  - Symptoms and conditions
  - Current medications
  
This rich context enables highly personalized, relevant recommendations.

## Implementation Details

### Architecture
```
User Request
    ↓
Personalization API Endpoint
    ↓
AIPersonalizationEngine
    ↓
Context Builder (aggregates health data)
    ↓
LLM API (OpenAI/Anthropic)
    ↓
Response Processing
    ↓
Formatted Recommendations
```

### Key Classes

**AIPersonalizationEngine** (`app/services/ai_engine.py`):
- `_build_user_context()`: Aggregates all user data
- `generate_personalized_recommendations()`: Main recommendation engine
- `analyze_symptoms()`: Symptom analysis with context
- `_call_llm()`: Unified LLM API interface

**Personalization Router** (`app/api/personalization.py`):
- Profile management endpoints
- Recommendation request handling
- Health score calculation

## Usage Examples

### Enable AI Coaching for User
```python
# Update user profile
PUT /api/v1/personalization/profile
{
  "ai_coaching_enabled": true,
  "ai_personality_preference": "supportive",
  "ai_language_complexity": "moderate"
}
```

### Get Nutrition Recommendations
```python
# Request nutrition guidance
POST /api/v1/personalization/recommendations
{
  "type": "nutrition",
  "specific_request": "I want to lose 5kg in 3 months while maintaining muscle mass",
  "days_context": 30
}
```

### Analyze Recent Symptoms
```python
# Get context-aware symptom analysis
POST /api/v1/personalization/analyze-symptoms
{
  "symptoms_description": "Feeling very fatigued after workouts, even after 8 hours of sleep. This started last week."
}
```

### Check Health Score
```python
# Get current health score
GET /api/v1/personalization/health-score
```

## Future Enhancements

Planned features for future releases:
1. **Predictive Analytics**: Forecast health trends based on current patterns
2. **Intervention Timing**: Smart notifications for optimal behavior change moments
3. **Social Support**: Connect users with similar goals and conditions
4. **Integration with Wearables**: Real-time data from Apple Health, Google Fit, etc.
5. **Multi-language Support**: Recommendations in user's preferred language
6. **Voice Interface**: Conversational AI health coaching
7. **Meal Planning**: AI-generated meal plans with recipes
8. **Workout Planning**: Detailed exercise routines with form videos

## Testing

To test the AI engine without API keys (development only):
```python
# Mock mode for testing (returns sample recommendations)
os.environ["AI_MOCK_MODE"] = "true"
```

## Support

For questions about the AI Personalization Engine, contact the development team or consult the API documentation at `/api/docs`.
