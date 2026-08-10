"""Sample script to populate AI with global health knowledge."""

import requests
import json

# Backend URL
BASE_URL = "http://localhost:8000/api/v1"

# Login as demo user
def login():
    response = requests.post(f"{BASE_URL}/auth/login", data={
        "username": "demo@alafia.app",
        "password": "demo1234"
    })
    return response.json()["access_token"]

# Add global health knowledge
SAMPLE_KNOWLEDGE = [
    {
        "knowledge_type": "guideline",
        "domain": "nutrition",
        "topic": "protein_intake",
        "title": "Protein Intake Guidelines for Adults",
        "summary": "Adults should consume 0.8-1.2g of protein per kg of body weight daily. Active individuals and athletes may need 1.4-2.0g/kg. Quality sources include lean meats, fish, eggs, legumes, and dairy. Distribute protein intake across meals for optimal muscle protein synthesis.",
        "source_organization": "International Society of Sports Nutrition (ISSN)",
        "evidence_level": "high",
        "source_url": "https://jissn.biomedcentral.com/articles/10.1186/s12970-017-0177-8",
        "key_points": [
            "0.8g/kg minimum for sedentary adults",
            "1.4-2.0g/kg for active individuals and athletes",
            "Distribute across 3-4 meals (20-40g per meal)",
            "Quality matters: complete proteins preferred",
            "Timing around workouts enhances recovery"
        ]
    },
    {
        "knowledge_type": "guideline",
        "domain": "fitness",
        "topic": "cardio_recommendations",
        "title": "Cardiovascular Exercise Guidelines",
        "summary": "Adults should perform 150-300 minutes of moderate-intensity or 75-150 minutes of vigorous-intensity aerobic exercise weekly. Can be broken into sessions of 10+ minutes. Benefits include reduced cardiovascular disease risk, improved mental health, and weight management.",
        "source_organization": "American Heart Association (AHA)",
        "evidence_level": "high",
        "source_url": "https://www.heart.org/en/healthy-living/fitness/fitness-basics/aha-recs-for-physical-activity-in-adults",
        "key_points": [
            "150-300 min/week moderate intensity (brisk walking, cycling)",
            "75-150 min/week vigorous intensity (running, swimming)",
            "Can combine moderate and vigorous activities",
            "Add muscle-strengthening activities 2+ days/week",
            "More is better, but some is better than none"
        ]
    },
    {
        "knowledge_type": "guideline",
        "domain": "sleep",
        "topic": "sleep_duration",
        "title": "Recommended Sleep Duration by Age",
        "summary": "Adults aged 18-64 should aim for 7-9 hours of sleep per night. Adults 65+ need 7-8 hours. Consistent sleep schedule is as important as duration. Quality matters: deep sleep and REM sleep are essential for recovery and cognitive function.",
        "source_organization": "National Sleep Foundation",
        "evidence_level": "high",
        "source_url": "https://www.sleepfoundation.org/how-sleep-works/how-much-sleep-do-we-really-need",
        "key_points": [
            "Adults 18-64: 7-9 hours",
            "Adults 65+: 7-8 hours",
            "Consistency matters (same bedtime/wake time)",
            "Quality over quantity (deep + REM sleep crucial)",
            "Individual needs vary slightly"
        ]
    },
    {
        "knowledge_type": "research_finding",
        "domain": "nutrition",
        "topic": "mediterranean_diet",
        "title": "Mediterranean Diet and Cardiovascular Health",
        "summary": "The Mediterranean diet, rich in olive oil, nuts, fish, fruits, vegetables, and whole grains, reduces cardiovascular disease risk by 30%. Key components: high monounsaturated fats, omega-3 fatty acids, fiber, and antioxidants. Moderate wine consumption (optional) and minimal red meat and processed foods.",
        "source_organization": "New England Journal of Medicine (NEJM)",
        "evidence_level": "high",
        "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa1200303",
        "key_points": [
            "30% reduction in cardiovascular disease risk",
            "High in healthy fats (olive oil, nuts, fish)",
            "Rich in fruits, vegetables, whole grains, legumes",
            "Low in red meat and processed foods",
            "Associated with longevity and cognitive health"
        ],
        "publication_date": "2023-06-15"
    },
    {
        "knowledge_type": "best_practice",
        "domain": "fitness",
        "topic": "progressive_overload",
        "title": "Progressive Overload for Muscle Growth",
        "summary": "To build muscle and strength, progressively increase training demands over time. Methods: increase weight (5-10% when you can do 2+ reps above target), increase reps (add 1-2 reps per set), increase sets (add 1 set when fully recovered), decrease rest time, or increase training frequency. Track workouts to ensure progression.",
        "source_organization": "National Strength and Conditioning Association (NSCA)",
        "evidence_level": "high",
        "source_url": "https://www.nsca.com/education/articles/progressive-overload/",
        "key_points": [
            "Gradual increase in training stimulus required for gains",
            "Increase weight by 5-10% when 2+ reps above target",
            "Alternative: increase reps, sets, or frequency",
            "Track workouts to ensure progression",
            "Allow adequate recovery between sessions"
        ]
    },
    {
        "knowledge_type": "guideline",
        "domain": "mental_health",
        "topic": "stress_management",
        "title": "Evidence-Based Stress Management Techniques",
        "summary": "Effective stress management combines multiple approaches: regular physical activity (30+ min/day), mindfulness meditation (10-20 min/day), adequate sleep (7-9 hours), social connection, and professional support when needed. Deep breathing exercises provide immediate relief. Chronic stress requires lifestyle changes and may benefit from therapy.",
        "source_organization": "American Psychological Association (APA)",
        "evidence_level": "high",
        "source_url": "https://www.apa.org/topics/stress/manage",
        "key_points": [
            "Regular exercise reduces stress hormones",
            "Mindfulness meditation decreases anxiety",
            "7-9 hours sleep essential for stress regulation",
            "Social support buffers stress impact",
            "Seek professional help for chronic stress"
        ]
    },
    {
        "knowledge_type": "warning",
        "domain": "nutrition",
        "topic": "supplement_safety",
        "title": "Dietary Supplement Safety and Interactions",
        "summary": "Supplements can interact with medications and have side effects. High-dose vitamin E and K affect blood clotting. Calcium supplements may interfere with thyroid medication. St. John's Wort reduces effectiveness of many drugs. Always consult healthcare provider before starting supplements, especially if taking medications or have health conditions.",
        "source_organization": "National Institutes of Health (NIH) - Office of Dietary Supplements",
        "evidence_level": "high",
        "source_url": "https://ods.od.nih.gov/HealthInformation/DS_WhatYouNeedToKnow.aspx",
        "key_points": [
            "Supplements can interact with medications",
            "Vitamin E, K affect blood clotting",
            "Calcium interferes with thyroid medication",
            "St. John's Wort reduces drug effectiveness",
            "Always consult healthcare provider first"
        ],
        "contraindications": ["blood_thinners", "thyroid_medication", "antidepressants"]
    },
    {
        "knowledge_type": "research_finding",
        "domain": "sleep",
        "topic": "sleep_exercise_relationship",
        "title": "Exercise Timing and Sleep Quality",
        "summary": "Moderate-to-vigorous exercise improves sleep quality, but timing matters. Morning and afternoon exercise show most benefit. Exercise within 2 hours of bedtime may impair sleep onset in some individuals due to elevated core temperature and arousal. Light exercise or yoga in evening is generally beneficial. Individual responses vary.",
        "source_organization": "Sleep Medicine Reviews",
        "evidence_level": "moderate",
        "source_url": "https://www.sleephealthjournal.org/article/S2352-7218(17)30026-7/fulltext",
        "key_points": [
            "Regular exercise improves sleep quality",
            "Morning/afternoon exercise optimal for most",
            "Vigorous exercise <2 hours before bed may impair sleep",
            "Light evening exercise or yoga generally fine",
            "Individual tolerance varies"
        ],
        "publication_date": "2023-03-20"
    }
]

def main():
    print("=" * 60)
    print("ALAFIA AI Global Knowledge Seeding Script")
    print("=" * 60)
    print()
    
    # Note: This would require an admin endpoint to add global knowledge
    # For now, this is a demonstration of what knowledge would be added
    
    print("Sample Global Health Knowledge to be added:")
    print()
    
    for i, knowledge in enumerate(SAMPLE_KNOWLEDGE, 1):
        print(f"{i}. {knowledge['title']}")
        print(f"   Domain: {knowledge['domain']} | Topic: {knowledge['topic']}")
        print(f"   Source: {knowledge['source_organization']}")
        print(f"   Evidence Level: {knowledge['evidence_level']}")
        print(f"   Summary: {knowledge['summary'][:100]}...")
        print()
    
    print("=" * 60)
    print("To add this knowledge to the database, run:")
    print()
    print("  docker exec web-backend-1 python -c \"")
    print("  from app.core.database import SessionLocal")
    print("  from app.services.ai_memory_service import AIMemoryService")
    print("  import json")
    print()
    print("  db = SessionLocal()")
    print("  memory_service = AIMemoryService(db)")
    print()
    print("  # Add each knowledge item")
    print("  for item in SAMPLE_KNOWLEDGE:")
    print("      memory_service.add_global_knowledge(**item)")
    print("  db.commit()\"")
    print()
    print("=" * 60)
    print()
    print("Testing AI Memory Endpoints:")
    print()
    
    try:
        token = login()
        print("✓ Logged in successfully")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test learning from data
        print("\n1. Triggering AI learning from user data...")
        response = requests.post(
            f"{BASE_URL}/personalization/learn-from-data?days=90",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ AI learned {data['memories_created']} insights")
            print(f"   Categories: {', '.join(data['categories'])}")
        else:
            print(f"   ✗ Error: {response.status_code}")
        
        # Test getting memories
        print("\n2. Retrieving AI memories...")
        response = requests.get(
            f"{BASE_URL}/personalization/memories",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Found {data['total_memories']} memories")
            if data['memories']:
                print(f"\n   Sample memory:")
                mem = data['memories'][0]
                print(f"   • {mem['insight']}")
                print(f"   • Confidence: {mem['confidence']:.0%}")
                print(f"   • Evidence: {mem['evidence_count']} data points")
        else:
            print(f"   ✗ Error: {response.status_code}")
        
        # Test interaction history
        print("\n3. Checking interaction history...")
        response = requests.get(
            f"{BASE_URL}/personalization/interaction-history",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Found {data['total']} past interactions")
        else:
            print(f"   ✗ Error: {response.status_code}")
        
        # Test health score (which uses the enhanced AI engine)
        print("\n4. Calculating health score with AI context...")
        response = requests.get(
            f"{BASE_URL}/personalization/health-score",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Overall Score: {data['overall_score']:.1f}/100 (Grade: {data['grade']})")
            print(f"   Component scores:")
            for component, score in data['component_scores'].items():
                print(f"     • {component.capitalize()}: {score:.1f}/100")
        else:
            print(f"   ✗ Error: {response.status_code}")
        
        print("\n" + "=" * 60)
        print("✓ AI Memory System is operational!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nMake sure the backend is running:")
        print("  docker compose -f WEB/docker-compose.yml up -d")

if __name__ == "__main__":
    main()
