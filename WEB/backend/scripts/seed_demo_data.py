#!/usr/bin/env python3
"""
ALAFIA Demo Data Seed Script
================================
Populates the database with realistic, compelling demo data for video demos,
investor presentations, and accelerator applications.

Creates a demo user profile inspired by a chronic kidney disease patient managing
their health holistically — nutrition, fitness, mental health, medications, labs,
dialysis therapy sessions, vitals, mood, calendar events, and community health alerts.

Usage:
    python scripts/seed_demo_data.py

Requires the backend to be running at http://localhost:8000
"""

import requests
import json
import sys
from datetime import date, datetime, timedelta
import random

BASE_URL = "http://localhost:8000/api/v1"
DEMO_EMAIL = "demo@alafia.app"
DEMO_PASSWORD = "demo1234"
DEMO_NAME = "Wole Akpose"

# ─────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────

def api(method, path, data=None, token=None):
    """Make an API call and return the response."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE_URL}{path}"
    try:
        if method == "POST":
            r = requests.post(url, json=data, headers=headers)
        elif method == "PATCH":
            r = requests.patch(url, json=data, headers=headers)
        elif method == "PUT":
            r = requests.put(url, json=data, headers=headers)
        elif method == "GET":
            r = requests.get(url, headers=headers)
        else:
            r = requests.request(method, url, json=data, headers=headers)
        
        if r.status_code >= 400:
            print(f"  ⚠ {method} {path} → {r.status_code}: {r.text[:200]}")
            return None
        return r.json() if r.text else None
    except Exception as e:
        print(f"  ✗ {method} {path} → {e}")
        return None


def register_and_login():
    """Register demo user (if needed) and return JWT token."""
    # Try to register  
    reg = api("POST", "/auth/register", {
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "full_name": DEMO_NAME,
        "date_of_birth": "1970-06-15",
        "gender": "male",
        "gender_at_birth": "male",
        "blood_type": "O+",
    })
    if reg:
        print(f"  ✓ Registered user: {DEMO_EMAIL}")
    else:
        print(f"  ℹ User may already exist, attempting login...")

    # Login
    r = requests.post(f"{BASE_URL}/auth/login", data={
        "username": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
    })
    if r.status_code != 200:
        print(f"  ✗ Login failed: {r.text}")
        sys.exit(1)
    
    token = r.json()["access_token"]
    print(f"  ✓ Logged in as {DEMO_EMAIL}")
    return token


def d(days_ago):
    """Return a date string N days ago."""
    return (date.today() - timedelta(days=days_ago)).isoformat()


def dt(days_ago, hour=9, minute=0):
    """Return a datetime string N days ago."""
    return (datetime.now() - timedelta(days=days_ago)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ).isoformat()


# ─────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────

def seed_profile(token):
    """Update user profile with comprehensive health data."""
    print("\n📋 Updating profile...")
    profile = {
        "height_cm": 180.0,
        "current_weight_kg": 82.5,
        "target_weight_kg": 78.0,
        "locale": "en-US",
        "timezone": "America/New_York",
        "country": "United States",
        "preferred_units": "imperial",
        "preferred_language": "en",
        "allergies": "Sulfonamides, Ibuprofen (NSAID)",
        "food_intolerances": "Fava beans (G6PD), High-potassium foods (renal)",
        "dietary_restrictions": "Renal diet: low potassium, low phosphorus, controlled protein, fluid restricted",
        "dietary_preferences": "Mediterranean-adapted renal diet",
        "family_history": "Hypertension (mother), Type 2 Diabetes (father), Sickle cell trait carrier (both parents)",
        "activity_level": "moderate",
        "fitness_goals": "Maintain cardiovascular health, manage fluid retention, gentle strength preservation",
        "preferred_activities": "Walking, Stationary cycling, Light resistance training, Stretching",
        "exercise_frequency_per_week": 4,
        "smoking_status": "never",
        "alcohol_consumption": "none",
        "sleep_schedule": "10:30pm - 6:30am",
        "occupation": "Technology Executive / Health Entrepreneur",
        "stress_level": "moderate",
        "ai_coaching_enabled": True,
        "ai_persona": "babalawo",
        "ai_personality_preference": "analytical",
        "ai_language_complexity": "detailed",
        "data_sharing_consent": True,
        "ai_training_consent": True,
    }
    result = api("PATCH", "/users/me", profile, token)
    if result:
        print(f"  ✓ Profile updated with comprehensive health data")


# ─────────────────────────────────────────────────────
# Medications
# ─────────────────────────────────────────────────────

def seed_medications(token):
    """Add realistic ESRD medications."""
    print("\n💊 Adding medications...")
    meds = [
        {
            "name": "Epoetin Alfa (Epogen)",
            "dosage": "4000",
            "dosage_unit": "units",
            "frequency": "3x/week during dialysis",
            "route": "injection",
            "start_date": "2016-12-01",
            "prescribing_doctor": "Dr. Amara Okafor",
            "reason": "Anemia secondary to ESRD — stimulates red blood cell production",
            "is_active": True,
            "notes": "Administered IV during hemodialysis sessions. Target Hgb 10-11.5 g/dL."
        },
        {
            "name": "Sevelamer Carbonate (Renvela)",
            "dosage": "800",
            "dosage_unit": "mg",
            "frequency": "3x daily with meals",
            "route": "oral",
            "start_date": "2017-01-15",
            "prescribing_doctor": "Dr. Amara Okafor",
            "reason": "Phosphorus binder — prevents hyperphosphatemia in ESRD",
            "is_active": True,
            "notes": "Take with each meal. Binds dietary phosphorus in GI tract."
        },
        {
            "name": "Calcitriol (Rocaltrol)",
            "dosage": "0.25",
            "dosage_unit": "mcg",
            "frequency": "Daily",
            "route": "oral",
            "start_date": "2017-02-01",
            "prescribing_doctor": "Dr. Amara Okafor",
            "reason": "Active vitamin D — kidneys cannot convert vitamin D; prevents secondary hyperparathyroidism",
            "is_active": True,
            "notes": "Monitor calcium and PTH levels monthly."
        },
        {
            "name": "Lisinopril",
            "dosage": "10",
            "dosage_unit": "mg",
            "frequency": "Daily",
            "route": "oral",
            "start_date": "2016-10-01",
            "prescribing_doctor": "Dr. Chen Wei",
            "reason": "ACE inhibitor for blood pressure management and renal protection",
            "is_active": True,
            "notes": "Monitor potassium — risk of hyperkalemia with ESRD."
        },
        {
            "name": "Ferrous Sulfate",
            "dosage": "325",
            "dosage_unit": "mg",
            "frequency": "Daily",
            "route": "oral",
            "start_date": "2017-03-01",
            "prescribing_doctor": "Dr. Amara Okafor",
            "reason": "Iron supplementation for anemia management alongside EPO",
            "is_active": True,
            "notes": "Take on empty stomach. Avoid calcium-rich foods within 2 hours."
        },
        {
            "name": "Amlodipine",
            "dosage": "5",
            "dosage_unit": "mg",
            "frequency": "Daily",
            "route": "oral",
            "start_date": "2018-06-01",
            "prescribing_doctor": "Dr. Chen Wei",
            "reason": "Calcium channel blocker — additional blood pressure control",
            "is_active": True,
            "notes": "Added when BP consistently above target on Lisinopril alone."
        },
        {
            "name": "Eculizumab (Soliris)",
            "dosage": "900",
            "dosage_unit": "mg",
            "frequency": "Biweekly IV infusion",
            "route": "injection",
            "start_date": "2016-11-01",
            "end_date": "2017-08-31",
            "prescribing_doctor": "Dr. Sarah Mitchell",
            "reason": "Originally prescribed for suspected aHUS — discontinued after G6PD deficiency confirmed as underlying cause",
            "is_active": False,
            "side_effects": "Headaches, fatigue, increased infection risk",
            "notes": "DISCONTINUED. Cost $500K+/year. Self-directed data analysis revealed G6PD deficiency, not aHUS."
        },
    ]
    for med in meds:
        result = api("POST", "/medications", med, token)
        if result:
            status = "ACTIVE" if med["is_active"] else "DISCONTINUED"
            print(f"  ✓ [{status}] {med['name']}")


# ─────────────────────────────────────────────────────
# Lab Results (90 days of data)
# ─────────────────────────────────────────────────────

def seed_labs(token):
    """Add realistic ESRD lab results over 90 days — showing trends."""
    print("\n🔬 Adding lab results...")
    
    # Monthly comprehensive metabolic panels + CBC + specialized ESRD labs
    lab_sets = [
        # 90 days ago — slightly worse values
        {
            "date": d(90),
            "labs": [
                {"test_name": "BUN (Blood Urea Nitrogen)", "category": "chemistry", "value": 58.0, "unit": "mg/dL", "reference_range_low": 7.0, "reference_range_high": 20.0, "is_abnormal": True, "notes": "Elevated — consistent with ESRD pre-dialysis"},
                {"test_name": "Creatinine", "category": "chemistry", "value": 9.8, "unit": "mg/dL", "reference_range_low": 0.7, "reference_range_high": 1.3, "is_abnormal": True, "notes": "Severely elevated — ESRD baseline"},
                {"test_name": "eGFR (Estimated Glomerular Filtration Rate)", "category": "chemistry", "value": 6.0, "unit": "mL/min/1.73m²", "reference_range_low": 90.0, "reference_range_high": 120.0, "is_abnormal": True, "notes": "Stage 5 CKD"},
                {"test_name": "Potassium", "category": "chemistry", "value": 5.6, "unit": "mEq/L", "reference_range_low": 3.5, "reference_range_high": 5.0, "is_abnormal": True, "notes": "Mildly elevated — dietary adjustment needed"},
                {"test_name": "Phosphorus", "category": "chemistry", "value": 6.2, "unit": "mg/dL", "reference_range_low": 2.5, "reference_range_high": 4.5, "is_abnormal": True, "notes": "Elevated — increase Renvela compliance"},
                {"test_name": "Calcium", "category": "chemistry", "value": 8.8, "unit": "mg/dL", "reference_range_low": 8.5, "reference_range_high": 10.5, "is_abnormal": False},
                {"test_name": "Hemoglobin", "category": "hematology", "value": 9.8, "unit": "g/dL", "reference_range_low": 13.5, "reference_range_high": 17.5, "is_abnormal": True, "notes": "Anemia of CKD — EPO dose stable"},
                {"test_name": "Hematocrit", "category": "hematology", "value": 29.4, "unit": "%", "reference_range_low": 38.0, "reference_range_high": 50.0, "is_abnormal": True},
                {"test_name": "PTH (Parathyroid Hormone)", "category": "endocrine", "value": 380.0, "unit": "pg/mL", "reference_range_low": 15.0, "reference_range_high": 65.0, "is_abnormal": True, "notes": "Secondary hyperparathyroidism — monitoring"},
                {"test_name": "Albumin", "category": "chemistry", "value": 3.6, "unit": "g/dL", "reference_range_low": 3.5, "reference_range_high": 5.0, "is_abnormal": False, "notes": "Nutritional status adequate"},
                {"test_name": "G6PD Enzyme Activity", "category": "hematology", "value": 2.1, "unit": "U/g Hb", "reference_range_low": 4.6, "reference_range_high": 13.5, "is_abnormal": True, "notes": "CONFIRMED DEFICIENT — underlying cause identified through self-directed data analysis"},
                {"test_name": "Reticulocyte Count", "category": "hematology", "value": 2.8, "unit": "%", "reference_range_low": 0.5, "reference_range_high": 2.5, "is_abnormal": True, "notes": "Slightly elevated — compensatory response"},
                {"test_name": "LDH (Lactate Dehydrogenase)", "category": "chemistry", "value": 310.0, "unit": "U/L", "reference_range_low": 140.0, "reference_range_high": 280.0, "is_abnormal": True, "notes": "Mildly elevated — marker of ongoing low-grade hemolysis"},
                {"test_name": "Haptoglobin", "category": "chemistry", "value": 18.0, "unit": "mg/dL", "reference_range_low": 30.0, "reference_range_high": 200.0, "is_abnormal": True, "notes": "Low — consistent with hemolytic component"},
                {"test_name": "Iron (Serum)", "category": "chemistry", "value": 55.0, "unit": "mcg/dL", "reference_range_low": 60.0, "reference_range_high": 170.0, "is_abnormal": True},
                {"test_name": "Ferritin", "category": "chemistry", "value": 180.0, "unit": "ng/mL", "reference_range_low": 200.0, "reference_range_high": 500.0, "is_abnormal": True, "notes": "Below target for dialysis patients"},
                {"test_name": "TSAT (Transferrin Saturation)", "category": "chemistry", "value": 18.0, "unit": "%", "reference_range_low": 20.0, "reference_range_high": 50.0, "is_abnormal": True},
            ]
        },
        # 60 days ago — improving 
        {
            "date": d(60),
            "labs": [
                {"test_name": "BUN (Blood Urea Nitrogen)", "category": "chemistry", "value": 52.0, "unit": "mg/dL", "reference_range_low": 7.0, "reference_range_high": 20.0, "is_abnormal": True, "notes": "Trending down with dietary management"},
                {"test_name": "Creatinine", "category": "chemistry", "value": 9.5, "unit": "mg/dL", "reference_range_low": 0.7, "reference_range_high": 1.3, "is_abnormal": True},
                {"test_name": "eGFR", "category": "chemistry", "value": 6.0, "unit": "mL/min/1.73m²", "reference_range_low": 90.0, "reference_range_high": 120.0, "is_abnormal": True},
                {"test_name": "Potassium", "category": "chemistry", "value": 5.1, "unit": "mEq/L", "reference_range_low": 3.5, "reference_range_high": 5.0, "is_abnormal": True, "notes": "Improved with dietary potassium restriction"},
                {"test_name": "Phosphorus", "category": "chemistry", "value": 5.4, "unit": "mg/dL", "reference_range_low": 2.5, "reference_range_high": 4.5, "is_abnormal": True, "notes": "Improving — better Renvela compliance"},
                {"test_name": "Hemoglobin", "category": "hematology", "value": 10.2, "unit": "g/dL", "reference_range_low": 13.5, "reference_range_high": 17.5, "is_abnormal": True, "notes": "Improving — EPO effective"},
                {"test_name": "Albumin", "category": "chemistry", "value": 3.8, "unit": "g/dL", "reference_range_low": 3.5, "reference_range_high": 5.0, "is_abnormal": False, "notes": "Good nutritional status"},
                {"test_name": "Ferritin", "category": "chemistry", "value": 220.0, "unit": "ng/mL", "reference_range_low": 200.0, "reference_range_high": 500.0, "is_abnormal": False, "notes": "Now in target range"},
                {"test_name": "TSAT", "category": "chemistry", "value": 22.0, "unit": "%", "reference_range_low": 20.0, "reference_range_high": 50.0, "is_abnormal": False, "notes": "Reached target"},
            ]
        },
        # 30 days ago — best yet (showing the system working)
        {
            "date": d(30),
            "labs": [
                {"test_name": "BUN (Blood Urea Nitrogen)", "category": "chemistry", "value": 48.0, "unit": "mg/dL", "reference_range_low": 7.0, "reference_range_high": 20.0, "is_abnormal": True, "notes": "Continued improvement — optimal for dialysis patient"},
                {"test_name": "Creatinine", "category": "chemistry", "value": 9.2, "unit": "mg/dL", "reference_range_low": 0.7, "reference_range_high": 1.3, "is_abnormal": True},
                {"test_name": "eGFR", "category": "chemistry", "value": 6.0, "unit": "mL/min/1.73m²", "reference_range_low": 90.0, "reference_range_high": 120.0, "is_abnormal": True},
                {"test_name": "Potassium", "category": "chemistry", "value": 4.8, "unit": "mEq/L", "reference_range_low": 3.5, "reference_range_high": 5.0, "is_abnormal": False, "notes": "Now in normal range — dietary management working"},
                {"test_name": "Phosphorus", "category": "chemistry", "value": 4.8, "unit": "mg/dL", "reference_range_low": 2.5, "reference_range_high": 4.5, "is_abnormal": True, "notes": "Near target — continued improvement"},
                {"test_name": "Calcium", "category": "chemistry", "value": 9.2, "unit": "mg/dL", "reference_range_low": 8.5, "reference_range_high": 10.5, "is_abnormal": False},
                {"test_name": "Hemoglobin", "category": "hematology", "value": 10.8, "unit": "g/dL", "reference_range_low": 13.5, "reference_range_high": 17.5, "is_abnormal": True, "notes": "Best in 6 months — target 10-11.5 for ESRD"},
                {"test_name": "Hematocrit", "category": "hematology", "value": 32.4, "unit": "%", "reference_range_low": 38.0, "reference_range_high": 50.0, "is_abnormal": True},
                {"test_name": "PTH", "category": "endocrine", "value": 320.0, "unit": "pg/mL", "reference_range_low": 15.0, "reference_range_high": 65.0, "is_abnormal": True, "notes": "Improving — Calcitriol working"},
                {"test_name": "Albumin", "category": "chemistry", "value": 4.0, "unit": "g/dL", "reference_range_low": 3.5, "reference_range_high": 5.0, "is_abnormal": False, "notes": "Excellent nutritional marker"},
                {"test_name": "LDH", "category": "chemistry", "value": 265.0, "unit": "U/L", "reference_range_low": 140.0, "reference_range_high": 280.0, "is_abnormal": False, "notes": "Now in normal range — hemolysis controlled by avoiding G6PD triggers"},
                {"test_name": "Haptoglobin", "category": "chemistry", "value": 35.0, "unit": "mg/dL", "reference_range_low": 30.0, "reference_range_high": 200.0, "is_abnormal": False, "notes": "Normalized — hemolysis resolved"},
                {"test_name": "HbA1c", "category": "chemistry", "value": 5.4, "unit": "%", "reference_range_low": 4.0, "reference_range_high": 5.6, "is_abnormal": False, "notes": "No diabetes"},
                {"test_name": "Vitamin D (25-OH)", "category": "chemistry", "value": 32.0, "unit": "ng/mL", "reference_range_low": 30.0, "reference_range_high": 100.0, "is_abnormal": False, "notes": "Adequate with supplementation"},
                {"test_name": "CRP (C-Reactive Protein)", "category": "chemistry", "value": 2.8, "unit": "mg/L", "reference_range_low": 0.0, "reference_range_high": 3.0, "is_abnormal": False, "notes": "Low inflammation — good sign"},
            ]
        },
    ]

    count = 0
    for lab_set in lab_sets:
        for lab in lab_set["labs"]:
            lab["test_date"] = lab_set["date"]
            lab["status"] = "final"
            lab["performing_lab"] = "Quest Diagnostics"
            result = api("POST", "/labs", lab, token)
            if result:
                count += 1
    print(f"  ✓ Added {count} lab results across 3 months (showing improvement trends)")


# ─────────────────────────────────────────────────────
# Nutrition (14 days of meals)
# ─────────────────────────────────────────────────────

def seed_nutrition(token):
    """Add 14 days of renal-diet-compliant nutrition data."""
    print("\n🥗 Adding nutrition logs (14 days)...")
    
    # Realistic renal diet meals
    meal_templates = [
        # Breakfasts
        {"meal_type": "breakfast", "food_name": "Scrambled Eggs (2 large)", "calories": 182, "protein_g": 12.6, "carbs_g": 1.6, "fat_g": 13.6, "sodium_mg": 294, "potassium_mg": 138, "phosphorus_mg": 198, "cholesterol_mg": 372},
        {"meal_type": "breakfast", "food_name": "White Rice Porridge with Cinnamon", "calories": 205, "protein_g": 4.3, "carbs_g": 44.5, "fat_g": 0.4, "sodium_mg": 5, "potassium_mg": 55, "phosphorus_mg": 68, "fiber_g": 0.6},
        {"meal_type": "breakfast", "food_name": "Sourdough Toast with Olive Oil", "calories": 180, "protein_g": 5.0, "carbs_g": 28.0, "fat_g": 6.0, "sodium_mg": 310, "potassium_mg": 50, "phosphorus_mg": 40},
        {"meal_type": "breakfast", "food_name": "Blueberry Pancakes (low-phosphorus flour)", "calories": 260, "protein_g": 6.0, "carbs_g": 38.0, "fat_g": 9.0, "sodium_mg": 380, "potassium_mg": 110, "phosphorus_mg": 85, "vitamin_c_mg": 4.0},
        
        # Lunches
        {"meal_type": "lunch", "food_name": "Grilled Chicken Breast (4oz) with White Rice", "calories": 380, "protein_g": 32.0, "carbs_g": 42.0, "fat_g": 5.5, "sodium_mg": 310, "potassium_mg": 260, "phosphorus_mg": 220, "iron_mg": 1.2, "vitamin_b3_niacin_mg": 14.0},
        {"meal_type": "lunch", "food_name": "Tuna Salad on White Bread (low-potassium veggies)", "calories": 340, "protein_g": 24.0, "carbs_g": 30.0, "fat_g": 13.0, "sodium_mg": 520, "potassium_mg": 280, "phosphorus_mg": 240, "omega3_g": 1.2},
        {"meal_type": "lunch", "food_name": "Egg Salad Sandwich with Cucumber", "calories": 310, "protein_g": 15.0, "carbs_g": 28.0, "fat_g": 16.0, "sodium_mg": 480, "potassium_mg": 170, "phosphorus_mg": 180},
        {"meal_type": "lunch", "food_name": "Turkey Wrap (low-sodium turkey, lettuce, cranberry)", "calories": 290, "protein_g": 22.0, "carbs_g": 32.0, "fat_g": 8.0, "sodium_mg": 410, "potassium_mg": 240, "phosphorus_mg": 195},
        
        # Dinners
        {"meal_type": "dinner", "food_name": "Baked Salmon (4oz) with Steamed Green Beans", "calories": 350, "protein_g": 30.0, "carbs_g": 12.0, "fat_g": 20.0, "sodium_mg": 180, "potassium_mg": 380, "phosphorus_mg": 290, "omega3_g": 2.3, "vitamin_d_iu": 570, "vitamin_b12_mcg": 4.8},
        {"meal_type": "dinner", "food_name": "Jollof Rice with Grilled Tilapia", "calories": 420, "protein_g": 28.0, "carbs_g": 48.0, "fat_g": 12.0, "sodium_mg": 350, "potassium_mg": 310, "phosphorus_mg": 260, "vitamin_a_iu": 850, "iron_mg": 2.5},
        {"meal_type": "dinner", "food_name": "Herb-Roasted Chicken Thigh with Couscous", "calories": 390, "protein_g": 26.0, "carbs_g": 38.0, "fat_g": 14.0, "sodium_mg": 290, "potassium_mg": 300, "phosphorus_mg": 230},
        {"meal_type": "dinner", "food_name": "Stir-Fried Shrimp with Bell Peppers and White Rice", "calories": 360, "protein_g": 24.0, "carbs_g": 44.0, "fat_g": 8.0, "sodium_mg": 420, "potassium_mg": 270, "phosphorus_mg": 210, "vitamin_c_mg": 65.0},
        
        # Snacks
        {"meal_type": "snack", "food_name": "Apple Slices with Almond Butter (1 tbsp)", "calories": 160, "protein_g": 3.5, "carbs_g": 22.0, "fat_g": 8.0, "sodium_mg": 35, "potassium_mg": 180, "phosphorus_mg": 48, "fiber_g": 3.5, "vitamin_c_mg": 6.0},
        {"meal_type": "snack", "food_name": "Rice Cakes with Cream Cheese", "calories": 120, "protein_g": 3.0, "carbs_g": 18.0, "fat_g": 4.0, "sodium_mg": 160, "potassium_mg": 30, "phosphorus_mg": 25},
        {"meal_type": "snack", "food_name": "Cranberry Juice (unsweetened, 8oz)", "calories": 116, "protein_g": 0.0, "carbs_g": 30.5, "fat_g": 0.0, "sodium_mg": 5, "potassium_mg": 95, "phosphorus_mg": 13, "vitamin_c_mg": 24.0},
    ]
    
    count = 0
    for days_ago in range(14, 0, -1):
        log_date = d(days_ago)
        # Pick random meals for each type
        breakfast = random.choice([m for m in meal_templates if m["meal_type"] == "breakfast"]).copy()
        lunch = random.choice([m for m in meal_templates if m["meal_type"] == "lunch"]).copy()
        dinner = random.choice([m for m in meal_templates if m["meal_type"] == "dinner"]).copy()
        snack = random.choice([m for m in meal_templates if m["meal_type"] == "snack"]).copy()
        
        for meal in [breakfast, lunch, dinner, snack]:
            meal["log_date"] = log_date
            meal["serving_size"] = "1 serving"
            result = api("POST", "/nutrition", meal, token)
            if result:
                count += 1
    
    print(f"  ✓ Added {count} nutrition logs across 14 days")


# ─────────────────────────────────────────────────────
# Fitness (14 days)
# ─────────────────────────────────────────────────────

def seed_fitness(token):
    """Add 14 days of exercise data — careful ESRD-appropriate exercise."""
    print("\n🏃 Adding fitness logs (14 days)...")
    
    workouts = [
        {"activity_type": "Walking", "duration_minutes": 35, "distance_km": 2.8, "calories_burned": 150, "heart_rate_avg": 95, "steps": 3800, "intensity": "moderate", "notes": "Morning walk — felt good. No dizziness."},
        {"activity_type": "Stationary Cycling", "duration_minutes": 25, "calories_burned": 130, "heart_rate_avg": 105, "heart_rate_max": 120, "intensity": "moderate", "notes": "Non-dialysis day. Energy level 7/10."},
        {"activity_type": "Light Resistance Training", "duration_minutes": 30, "calories_burned": 110, "heart_rate_avg": 90, "sets": 3, "reps": 12, "weight_kg": 8.0, "intensity": "low", "notes": "Upper body — resistance bands + light dumbbells. Careful with fistula arm."},
        {"activity_type": "Stretching & Yoga", "duration_minutes": 40, "calories_burned": 80, "heart_rate_avg": 75, "intensity": "low", "notes": "Gentle yoga flow. Focus on flexibility and stress reduction."},
        {"activity_type": "Walking", "duration_minutes": 45, "distance_km": 3.5, "calories_burned": 190, "heart_rate_avg": 100, "steps": 4800, "intensity": "moderate", "notes": "Evening neighborhood walk. Good energy post-dialysis recovery."},
        {"activity_type": "Stationary Cycling", "duration_minutes": 20, "calories_burned": 100, "heart_rate_avg": 100, "heart_rate_max": 115, "intensity": "low", "notes": "Light recovery day. Kept it easy."},
        {"activity_type": "Walking", "duration_minutes": 30, "distance_km": 2.4, "calories_burned": 130, "heart_rate_avg": 92, "steps": 3200, "intensity": "low", "notes": "Dialysis day — short walk before session only."},
    ]
    
    count = 0
    for days_ago in range(14, 0, -1):
        # Exercise 4-5 days per week, skip some days (dialysis recovery)
        if days_ago % 7 in [0, 3]:  # Rest days
            continue
        log_date = d(days_ago)
        workout = random.choice(workouts).copy()
        workout["log_date"] = log_date
        result = api("POST", "/fitness", workout, token)
        if result:
            count += 1
    
    print(f"  ✓ Added {count} fitness logs")


# ─────────────────────────────────────────────────────
# Mood (14 days)
# ─────────────────────────────────────────────────────

def seed_mood(token):
    """Add 14 days of mood tracking — realistic chronic illness emotional journey."""
    print("\n😊 Adding mood entries (14 days)...")
    
    mood_data = [
        {"mood_score": 7, "energy_level": 6, "stress_level": 4, "anxiety_level": 3, "sleep_quality": 7, "sleep_hours": 7.5, "gratitude": "Felt strong during walk. Grateful for another good dialysis session.", "journal_entry": "Good day overall. Labs trending in right direction. The data-driven approach is working."},
        {"mood_score": 5, "energy_level": 4, "stress_level": 6, "anxiety_level": 5, "sleep_quality": 5, "sleep_hours": 5.5, "triggers": "Post-dialysis fatigue", "journal_entry": "Rough day. Cramped during dialysis. Low energy. Drinking fluids within limits.", "coping_strategies": "Rest, light stretching, called a friend"},
        {"mood_score": 8, "energy_level": 7, "stress_level": 3, "anxiety_level": 2, "sleep_quality": 8, "sleep_hours": 8.0, "gratitude": "10 years on dialysis and still building. Grateful for clarity and purpose.", "journal_entry": "Productive day on ALAFIA. New feature working. The platform saved my life — now it helps others."},
        {"mood_score": 6, "energy_level": 5, "stress_level": 5, "anxiety_level": 4, "sleep_quality": 6, "sleep_hours": 6.5, "triggers": "Insurance paperwork, funding stress", "journal_entry": "Spent 2 hours on insurance forms. System is broken. More motivation to build ALAFIA.", "coping_strategies": "Breathing exercise, went for walk"},
        {"mood_score": 7, "energy_level": 7, "stress_level": 3, "anxiety_level": 3, "sleep_quality": 8, "sleep_hours": 7.5, "gratitude": "Great conversation with potential pilot clinic. Feeling hopeful.", "journal_entry": "Non-dialysis day. Full energy. Worked on chronic conditions tracking feature. This is going to help so many people."},
        {"mood_score": 4, "energy_level": 3, "stress_level": 7, "anxiety_level": 6, "sleep_quality": 4, "sleep_hours": 5.0, "triggers": "Dialysis complications — needle infiltration", "journal_entry": "Fistula needle infiltrated during session. Pain and swelling. Had to switch to other access. Reminded why continuous health monitoring matters.", "coping_strategies": "Ice, elevation, breathing exercises, journaling"},
        {"mood_score": 8, "energy_level": 8, "stress_level": 2, "anxiety_level": 2, "sleep_quality": 9, "sleep_hours": 8.5, "gratitude": "My daughter visited. Cooked renal-friendly meal together. Life is good.", "journal_entry": "Beautiful day. Family time. No health worries today. These days remind me why I fight."},
        {"mood_score": 6, "energy_level": 5, "stress_level": 5, "anxiety_level": 4, "sleep_quality": 6, "sleep_hours": 6.0, "journal_entry": "Moderate day. Blood pressure was high this morning. Adjusted fluid intake. Tracked everything in the app."},
        {"mood_score": 7, "energy_level": 6, "stress_level": 4, "anxiety_level": 3, "sleep_quality": 7, "sleep_hours": 7.0, "gratitude": "Phosphorus levels improving. Diet changes and Renvela compliance working.", "journal_entry": "The pattern is clear in the data — strict meal tracking correlates with better lab numbers. This is exactly what ALAFIA proves."},
        {"mood_score": 9, "energy_level": 8, "stress_level": 2, "anxiety_level": 1, "sleep_quality": 9, "sleep_hours": 8.0, "gratitude": "10 years. I was given 6 months. Data saved my life.", "journal_entry": "Anniversary of my diagnosis. Reflected on the journey. From being told I had 6 months to live to building a platform that can save others. Emotional but empowered."},
    ]
    
    count = 0
    for days_ago in range(14, 0, -1):
        entry = mood_data[days_ago % len(mood_data)].copy()
        entry["entry_date"] = d(days_ago)
        result = api("POST", "/mood", entry, token)
        if result:
            count += 1
    
    print(f"  ✓ Added {count} mood entries")


# ─────────────────────────────────────────────────────
# Lifestyle / Vitals (14 days)
# ─────────────────────────────────────────────────────

def seed_lifestyle(token):
    """Add 14 days of vitals — BP, HR, SpO₂, weight, temperature."""
    print("\n❤️ Adding lifestyle/vitals entries (14 days)...")
    
    count = 0
    for days_ago in range(14, 0, -1):
        # Simulate realistic ESRD vitals with slight variation
        is_dialysis_day = days_ago % 3 == 0  # MWF roughly
        
        # Weight fluctuates — higher before dialysis, lower after
        base_weight = 82.5
        weight_variation = random.uniform(0.5, 2.0) if is_dialysis_day else random.uniform(-0.5, 0.5)
        
        entry = {
            "entry_date": d(days_ago),
            "weight_kg": round(base_weight + weight_variation, 1),
            "blood_pressure_systolic": random.randint(128, 148) if is_dialysis_day else random.randint(122, 138),
            "blood_pressure_diastolic": random.randint(78, 90) if is_dialysis_day else random.randint(75, 85),
            "resting_heart_rate": random.randint(72, 88),
            "body_temperature_c": round(random.uniform(36.4, 36.8), 1),
            "blood_oxygen_pct": round(random.uniform(95.0, 98.5), 1),
            "caffeine_mg": random.choice([0, 0, 80, 80, 160]),  # Occasional coffee
            "screen_time_minutes": random.randint(180, 420),
            "outdoor_time_minutes": random.randint(20, 90),
            "social_interactions": random.randint(1, 5),
            "notes": "Pre-dialysis vitals" if is_dialysis_day else "Non-dialysis day",
        }
        result = api("POST", "/lifestyle", entry, token)
        if result:
            count += 1
    
    print(f"  ✓ Added {count} lifestyle/vitals entries")


# ─────────────────────────────────────────────────────
# Chronic Conditions & Therapy Sessions
# ─────────────────────────────────────────────────────

def seed_chronic_conditions(token):
    """Add ESRD condition with dialysis therapy sessions."""
    print("\n🏥 Adding chronic conditions & therapy sessions...")
    
    # Primary condition: ESRD
    esrd = api("POST", "/chronic/conditions", {
        "condition_name": "End-Stage Renal Disease (ESRD)",
        "category": "renal",
        "icd10_code": "N18.6",
        "severity": "severe",
        "diagnosis_date": "2016-09-15T00:00:00",
        "diagnosed_by": "Dr. Sarah Mitchell",
        "diagnosing_facility": "University of Washington Medical Center",
        "is_active": True,
        "stage": "Stage 5 CKD (ESRD)",
        "current_treatment_plan": "In-center hemodialysis 3x/week (MWF), EPO for anemia, phosphorus binders, ACE inhibitor + CCB for BP, iron supplementation, calcitriol for vitamin D. Strict renal diet with potassium, phosphorus, sodium, and fluid restrictions.",
        "primary_physician": "Dr. Amara Okafor (Nephrologist)",
        "specialist_physician": "Dr. Chen Wei (Cardiologist), Dr. Lisa Park (Hematologist)",
        "monitoring_frequency": "Monthly labs, weekly weight/vitals, continuous nutrition tracking",
        "symptoms": "Fatigue, fluid retention, occasional cramping during dialysis, mild neuropathy",
        "complications": "Anemia of CKD, secondary hyperparathyroidism, occasional fistula issues",
        "notes": "ESRD caused by G6PD deficiency-triggered hemolysis from untreated flu infections. Originally misdiagnosed as aHUS by 20+ physicians across Johns Hopkins, UW Medicine, and others. Correct diagnosis identified through self-directed data analysis in 2017."
    }, token)
    
    esrd_id = esrd["id"] if esrd else None
    if esrd:
        print(f"  ✓ Added ESRD condition (ID: {esrd_id})")
    
    # Secondary: G6PD Deficiency
    g6pd = api("POST", "/chronic/conditions", {
        "condition_name": "Glucose-6-Phosphate Dehydrogenase (G6PD) Deficiency",
        "category": "other",
        "icd10_code": "D55.0",
        "severity": "moderate",
        "diagnosis_date": "2017-06-01T00:00:00",
        "diagnosed_by": "Self-identified via data analytics, confirmed by Dr. Lisa Park",
        "diagnosing_facility": "Johns Hopkins Hospital (confirmation)",
        "is_active": True,
        "current_treatment_plan": "Avoidance of oxidative triggers: fava beans, certain medications (sulfonamides, aspirin, NSAIDs), naphthalene. Prompt treatment of infections to prevent hemolytic episodes.",
        "primary_physician": "Dr. Lisa Park (Hematologist)",
        "monitoring_frequency": "Quarterly hematology panel, G6PD enzyme level annually",
        "symptoms": "Susceptibility to hemolytic episodes when exposed to triggers",
        "notes": "KEY FINDING: G6PD deficiency was the root cause of the hemolytic crisis that led to ESRD. Untreated flu infections triggered extended hemolysis, causing organ failure. This was missed by 20+ physicians over 3 years. Pattern identified through personal database tracking of labs, medications, symptoms, and illness history — connecting decades of data that no single provider had analyzed holistically."
    }, token)
    
    if g6pd:
        print(f"  ✓ Added G6PD Deficiency condition")
    
    # Hypertension
    htn = api("POST", "/chronic/conditions", {
        "condition_name": "Hypertension",
        "category": "other",
        "icd10_code": "I10",
        "severity": "moderate",
        "diagnosis_date": "2016-10-01T00:00:00",
        "diagnosed_by": "Dr. Chen Wei",
        "diagnosing_facility": "Johns Hopkins Hospital",
        "is_active": True,
        "current_treatment_plan": "Lisinopril 10mg + Amlodipine 5mg daily. Target BP <140/90. Fluid and sodium restriction.",
        "primary_physician": "Dr. Chen Wei (Cardiologist)",
        "monitoring_frequency": "Daily home monitoring, weekly provider review",
        "notes": "Secondary to ESRD. Managed with dual antihypertensive therapy and fluid management."
    }, token)
    
    if htn:
        print(f"  ✓ Added Hypertension condition")
    
    # Dialysis sessions (last 14 days — 3x/week)
    if esrd_id:
        session_count = 0
        for days_ago in [14, 12, 10, 7, 5, 3, 1]:  # Rough MWF schedule
            pre_weight = round(random.uniform(83.5, 85.0), 1)
            fluid_removed = random.randint(2000, 3500)
            post_weight = round(pre_weight - (fluid_removed / 1000), 1)
            
            session = {
                "condition_id": esrd_id,
                "therapy_type": "dialysis",
                "therapy_name": "In-Center Hemodialysis",
                "session_number": 1560 + (14 - days_ago),  # ~10 years of sessions
                "scheduled_date": dt(days_ago, 6, 30),
                "actual_start_time": dt(days_ago, 6, 45),
                "actual_end_time": dt(days_ago, 10, 45),
                "duration_minutes": 240,
                "status": "completed",
                "facility_name": "DaVita Kidney Care - Columbia Center",
                "attending_physician": "Dr. Amara Okafor",
                "attending_nurse": "RN Sarah Johnson",
                "dialysis_access_type": "AV Fistula (left forearm)",
                "pre_dialysis_weight_kg": pre_weight,
                "post_dialysis_weight_kg": post_weight,
                "fluid_removed_ml": fluid_removed,
                "blood_flow_rate": 400,
                "dialysate_flow_rate": 800,
                "pre_systolic_bp": random.randint(138, 155),
                "pre_diastolic_bp": random.randint(82, 95),
                "post_systolic_bp": random.randint(118, 132),
                "post_diastolic_bp": random.randint(72, 82),
                "pre_heart_rate": random.randint(78, 92),
                "post_heart_rate": random.randint(70, 85),
                "pre_temperature": round(random.uniform(36.5, 36.9), 1),
                "post_temperature": round(random.uniform(36.3, 36.7), 1),
                "oxygen_saturation": random.randint(96, 99),
                "patient_tolerance": "good" if days_ago != 5 else "fair",
                "side_effects": "Mild cramping in last 30 minutes" if days_ago == 5 else None,
                "clinical_notes": f"Routine HD session. UF goal met. Patient tolerated well." if days_ago != 5 else "Mild intradialytic hypotension at 3hr mark. UF rate reduced. Patient recovered.",
                "patient_notes": "Felt good throughout" if days_ago != 5 else "Cramped near the end. Needed saline bolus. Drank too much fluid yesterday — logged in ALAFIA, will adjust."
            }
            result = api("POST", "/chronic/therapy-sessions", session, token)
            if result:
                session_count += 1
        
        print(f"  ✓ Added {session_count} dialysis therapy sessions")


# ─────────────────────────────────────────────────────
# Mental Health Assessments
# ─────────────────────────────────────────────────────

def seed_mental_health(token):
    """Add mental health assessments, breathing sessions, gratitude entries."""
    print("\n🧠 Adding mental health data...")
    
    # PHQ-9 assessment (mild depression — realistic for chronic illness)
    phq9 = api("POST", "/mental-health/assessments", {
        "assessment_date": d(7),
        "assessment_type": "phq9",
        "phq_interest": 1,           # Little interest/pleasure — some days
        "phq_feeling_down": 1,       # Feeling down — some days
        "phq_sleep": 1,              # Sleep issues — some days (dialysis nights)
        "phq_energy": 2,             # Fatigue — more than half the days (ESRD)
        "phq_appetite": 0,           # Appetite OK
        "phq_self_esteem": 0,        # Self-esteem good
        "phq_concentration": 0,      # Concentration OK
        "phq_psychomotor": 0,        # No psychomotor issues
        "phq_suicidal_ideation": 0,  # None
        "notes": "Fatigue score reflects ESRD-related exhaustion, not depression. Overall mood is positive — the mission gives purpose."
    }, token)
    if phq9:
        print(f"  ✓ PHQ-9 assessment (score: {phq9.get('total_score', 'N/A')})")
    
    # GAD-7 assessment (minimal anxiety)
    gad7 = api("POST", "/mental-health/assessments", {
        "assessment_date": d(7),
        "assessment_type": "gad7",
        "gad_nervous": 1,
        "gad_uncontrollable_worry": 0,
        "gad_excessive_worry": 1,
        "gad_trouble_relaxing": 1,
        "gad_restless": 0,
        "gad_irritable": 0,
        "gad_afraid": 0,
        "notes": "Mild anxiety around funding/sustainability. Manageable with exercise and breathing exercises."
    }, token)
    if gad7:
        print(f"  ✓ GAD-7 assessment (score: {gad7.get('total_score', 'N/A')})")
    
    # WHO-5 Wellbeing (above average despite chronic illness)
    who5 = api("POST", "/mental-health/assessments", {
        "assessment_date": d(7),
        "assessment_type": "who5",
        "who5_cheerful": 4,
        "who5_calm": 3,
        "who5_active": 3,
        "who5_rested": 3,
        "who5_interesting": 5,
        "notes": "High engagement score — building ALAFIA gives strong sense of purpose. Physical energy limited by ESRD but mental engagement very high."
    }, token)
    if who5:
        print(f"  ✓ WHO-5 assessment (score: {who5.get('total_score', 'N/A')})")
    
    # Breathing sessions (last 7 days)
    breathing_exercises = [
        {"exercise_type": "box_breathing", "duration_seconds": 300, "mood_before": 5, "mood_after": 7, "notes": "Pre-dialysis calming routine"},
        {"exercise_type": "4_7_8", "duration_seconds": 240, "mood_before": 4, "mood_after": 7, "notes": "After difficult insurance call"},
        {"exercise_type": "deep_breathing", "duration_seconds": 180, "mood_before": 6, "mood_after": 8, "notes": "Morning practice"},
        {"exercise_type": "body_scan", "duration_seconds": 600, "mood_before": 5, "mood_after": 8, "notes": "Evening relaxation — full body scan"},
        {"exercise_type": "grounding_5_4_3_2_1", "duration_seconds": 300, "mood_before": 3, "mood_after": 6, "notes": "Used during unexpected lab anxiety"},
    ]
    
    breathing_count = 0
    for i, days_ago in enumerate([7, 6, 5, 3, 1]):
        exercise = breathing_exercises[i].copy()
        exercise["session_date"] = d(days_ago)
        result = api("POST", "/mental-health/breathing/sessions", exercise, token)
        if result:
            breathing_count += 1
    print(f"  ✓ Added {breathing_count} breathing sessions")
    
    # Gratitude entries (last 7 days)
    gratitude_entries = [
        {"item_1": "Completed another week of dialysis without complications", "item_2": "ALAFIA nutrition tracking caught a potassium spike before it showed in labs", "item_3": "Had energy for a 45-minute walk", "reflection": "The consistency of tracking is paying off. My body responds when I listen to the data."},
        {"item_1": "My daughter called to check on me", "item_2": "Blood pressure stayed under 140 all day", "item_3": "Made progress on the AI personalization engine", "reflection": "Family and purpose — the two things that keep me going."},
        {"item_1": "Phosphorus labs came back improved", "item_2": "Connected with another ESRD patient online who wants to try the app", "item_3": "Slept a full 8 hours", "reflection": "When the data shows improvement, it validates everything about this approach."},
        {"item_1": "10 years since diagnosis — still here, still building", "item_2": "Clear mind, productive code day", "item_3": "Sunset walk was beautiful", "reflection": "They gave me 6 months. I gave myself a mission. The mission sustains me."},
        {"item_1": "Good dialysis session — no cramping", "item_2": "Cooked a new renal-friendly recipe that actually tasted great", "item_3": "Received encouraging feedback on the platform", "reflection": "Small wins compound. In health, in code, in life."},
    ]
    
    gratitude_count = 0
    for i, days_ago in enumerate([7, 5, 4, 2, 1]):
        entry = gratitude_entries[i].copy()
        entry["entry_date"] = d(days_ago)
        result = api("POST", "/mental-health/gratitude", entry, token)
        if result:
            gratitude_count += 1
    print(f"  ✓ Added {gratitude_count} gratitude entries")


# ─────────────────────────────────────────────────────
# Calendar Events
# ─────────────────────────────────────────────────────

def seed_calendar(token):
    """Add upcoming and recent calendar events."""
    print("\n📅 Adding calendar events...")
    
    events = [
        # Recurring dialysis
        {"title": "Hemodialysis Session", "category": "therapy", "event_date": d(-1), "start_time": "06:30:00", "end_time": "10:30:00", "location": "DaVita Kidney Care - Columbia Center", "recurrence": "custom", "recurrence_days": "mon,wed,fri", "priority": "high", "color": "#EF4444", "notes": "4-hour session. Bring snack, water bottle (limited). Check pre-dialysis weight."},
        
        # Medications
        {"title": "Morning Medications", "category": "medication", "event_date": d(0), "start_time": "07:00:00", "recurrence": "daily", "priority": "high", "color": "#8B5CF6", "notes": "Lisinopril 10mg, Amlodipine 5mg, Calcitriol 0.25mcg, Ferrous Sulfate 325mg (empty stomach)"},
        {"title": "Renvela with Lunch", "category": "medication", "event_date": d(0), "start_time": "12:00:00", "recurrence": "daily", "priority": "high", "color": "#8B5CF6"},
        {"title": "Renvela with Dinner", "category": "medication", "event_date": d(0), "start_time": "18:30:00", "recurrence": "daily", "priority": "high", "color": "#8B5CF6"},
        
        # Upcoming appointments
        {"title": "Nephrology Follow-up — Dr. Okafor", "category": "appointment", "event_date": d(-5), "start_time": "14:00:00", "end_time": "14:45:00", "location": "Johns Hopkins Nephrology Clinic", "priority": "high", "color": "#3B82F6", "notes": "Review latest labs. Discuss EPO dose adjustment. Bring 30-day vitals report from ALAFIA."},
        {"title": "Monthly Lab Draw", "category": "lab", "event_date": d(-3), "start_time": "07:30:00", "end_time": "08:00:00", "location": "Quest Diagnostics", "priority": "high", "color": "#F59E0B", "notes": "CMP, CBC, Iron panel, PTH, Phosphorus. Fasting required."},
        {"title": "Cardiology Check-up — Dr. Wei", "category": "appointment", "event_date": d(-14), "start_time": "10:00:00", "end_time": "10:30:00", "location": "Johns Hopkins Cardiology", "priority": "medium", "color": "#3B82F6", "notes": "BP management review. Bring home BP log."},
        
        # Wellness
        {"title": "Morning Walk", "category": "exercise", "event_date": d(0), "start_time": "06:00:00", "end_time": "06:40:00", "recurrence": "daily", "priority": "medium", "color": "#10B981", "notes": "Skip on dialysis days or if feeling dizzy."},
        {"title": "Evening Meditation", "category": "meditation", "event_date": d(0), "start_time": "21:00:00", "end_time": "21:20:00", "recurrence": "daily", "priority": "medium", "color": "#6366F1"},
        
        # Meals
        {"title": "Meal Prep Sunday", "category": "meal", "event_date": d(-2), "start_time": "10:00:00", "end_time": "12:00:00", "priority": "medium", "color": "#F97316", "notes": "Prep renal-friendly meals for the week. Focus on low-K, low-P options."},
    ]
    
    count = 0
    for event in events:
        result = api("POST", "/calendar", event, token)
        if result:
            count += 1
    print(f"  ✓ Added {count} calendar events")


# ─────────────────────────────────────────────────────
# Community Health Alerts
# ─────────────────────────────────────────────────────

def seed_community_health(token):
    """Add realistic community health alerts."""
    print("\n🌍 Adding community health alerts & guidelines...")
    
    alerts = [
        {
            "title": "FDA Safety Alert: NSAID Use in Chronic Kidney Disease",
            "summary": "FDA reinforces warning that NSAIDs (ibuprofen, naproxen) can cause further kidney damage in CKD/ESRD patients and should be avoided.",
            "description": "The FDA has issued an updated safety communication regarding non-steroidal anti-inflammatory drugs (NSAIDs) in patients with chronic kidney disease. NSAIDs reduce blood flow to the kidneys, can worsen kidney function, and may cause dangerous hyperkalemia when combined with ACE inhibitors.",
            "category": "drug_safety",
            "severity": "high",
            "source": "fda",
            "source_url": "https://www.fda.gov/drugs/drug-safety-and-availability",
            "affected_countries": ["US", "CA", "GB"],
            "is_global": True,
            "issued_date": d(10),
            "recommended_actions": ["Avoid all NSAID medications", "Use acetaminophen for pain relief (with renal dosing)", "Consult nephrologist before any new medication", "Report adverse reactions to FDA MedWatch"],
            "target_population": ["CKD patients", "ESRD/dialysis patients", "Kidney transplant recipients"],
            "tags": ["kidney", "NSAID", "drug-safety", "CKD"]
        },
        {
            "title": "WHO: Meningitis Outbreak Alert — West Africa Region",
            "summary": "WHO reports increased meningitis cases across the meningitis belt in West Africa. Vaccination recommended for travelers and residents.",
            "description": "The World Health Organization has reported a significant increase in meningococcal meningitis cases across the Sahel region of West Africa, particularly affecting Nigeria, Niger, and Chad. The outbreak is primarily caused by Neisseria meningitidis serogroup C.",
            "category": "outbreak",
            "severity": "critical",
            "source": "who",
            "source_url": "https://www.who.int/emergencies/disease-outbreak-news",
            "affected_countries": ["NG", "NE", "TD", "ML", "BF"],
            "affected_regions": ["West Africa", "Sahel"],
            "is_global": False,
            "issued_date": d(5),
            "disease_name": "Meningococcal Meningitis",
            "pathogen": "Neisseria meningitidis serogroup C",
            "confirmed_cases": 3420,
            "deaths": 198,
            "recommended_actions": ["Vaccination with MenACWY vaccine", "Seek immediate medical attention for fever + stiff neck + headache", "Practice good hygiene", "Avoid overcrowded spaces during outbreak"],
            "target_population": ["Residents of affected countries", "Travelers to West Africa", "Healthcare workers"],
            "tags": ["meningitis", "outbreak", "west-africa", "vaccination"]
        },
        {
            "title": "CDC: Updated Flu Vaccination Guidance for Immunocompromised Patients",
            "summary": "CDC recommends high-dose or adjuvanted influenza vaccination for dialysis patients and other immunocompromised individuals for the 2025-2026 season.",
            "category": "advisory",
            "severity": "moderate",
            "source": "cdc",
            "source_url": "https://www.cdc.gov/flu/professionals/acip",
            "affected_countries": ["US"],
            "is_global": False,
            "issued_date": d(20),
            "recommended_actions": ["Get high-dose flu vaccine (Fluzone HD or Flublok)", "Vaccinate early in season (September-October)", "Report any adverse reactions", "Dialysis patients: vaccinate on non-dialysis days"],
            "target_population": ["Dialysis patients", "Immunocompromised individuals", "Adults 65+"],
            "tags": ["influenza", "vaccination", "dialysis", "immunocompromised"]
        },
        {
            "title": "FDA Drug Recall: Losartan Potassium Tablets — NDMA Contamination",
            "summary": "Voluntary recall of specific lots of Losartan Potassium tablets due to potential contamination with N-Nitrosodimethylamine (NDMA), a probable carcinogen.",
            "category": "drug_recall",
            "severity": "high",
            "source": "fda",
            "source_url": "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts",
            "affected_countries": ["US"],
            "issued_date": d(15),
            "product_name": "Losartan Potassium Tablets, USP",
            "product_type": "Prescription medication",
            "manufacturer": "Torrent Pharmaceuticals Ltd",
            "lot_numbers": ["LOT2024-A1", "LOT2024-A2", "LOT2024-B1"],
            "reason_for_recall": "Potential NDMA contamination above acceptable daily intake limit",
            "recall_class": "Class II",
            "recommended_actions": ["Check medication lot numbers", "Do NOT stop taking medication without consulting doctor", "Contact pharmacy for replacement", "Report adverse effects to FDA MedWatch"],
            "tags": ["recall", "losartan", "NDMA", "contamination"]
        },
    ]
    
    alert_count = 0
    for alert in alerts:
        result = api("POST", "/community/alerts", alert, token)
        if result:
            alert_count += 1
    print(f"  ✓ Added {alert_count} community health alerts")
    
    # Guidelines
    guidelines = [
        {
            "title": "KDOQI Clinical Practice Guidelines for Nutrition in Chronic Kidney Disease",
            "summary": "Comprehensive guidelines for dietary management of CKD and ESRD patients, including protein, phosphorus, potassium, sodium, and fluid recommendations.",
            "category": "clinical_guideline",
            "source": "National Kidney Foundation (NKF)",
            "source_url": "https://www.kidney.org/professionals/guidelines/guidelines_commentaries/nutrition-ckd",
            "effective_date": d(90),
            "target_population": ["CKD patients (all stages)", "ESRD/dialysis patients", "Nephrologists", "Renal dietitians"],
            "applicable_conditions": ["Chronic Kidney Disease", "ESRD", "Hemodialysis", "Peritoneal Dialysis"],
            "recommendations": [
                "Protein: 1.0-1.2 g/kg/day for hemodialysis patients",
                "Phosphorus: 800-1000 mg/day, use phosphorus binders with meals",
                "Potassium: Individualized, typically 2000-3000 mg/day",
                "Sodium: <2300 mg/day, preferably <2000 mg/day",
                "Fluid: Limit to 1000 mL/day + urine output",
                "Calories: 25-35 kcal/kg/day to maintain nutritional status",
                "Monitor serum albumin as nutritional marker (target >4.0 g/dL)"
            ],
            "tags": ["kidney", "nutrition", "CKD", "dialysis", "KDOQI"]
        },
        {
            "title": "G6PD Deficiency: Medications and Substances to Avoid",
            "summary": "Comprehensive list of medications, foods, and chemicals that can trigger hemolytic episodes in G6PD-deficient patients.",
            "category": "clinical_guideline",
            "source": "American Society of Hematology (ASH)",
            "source_url": "https://www.hematology.org/education/patients/anemia/g6pd-deficiency",
            "target_population": ["G6PD-deficient patients", "Physicians treating G6PD patients", "Pharmacists"],
            "applicable_conditions": ["G6PD Deficiency", "Hemolytic Anemia"],
            "recommendations": [
                "AVOID: Sulfonamide antibiotics (sulfamethoxazole, dapsone)",
                "AVOID: Antimalarials (primaquine, chloroquine)",
                "AVOID: NSAIDs (aspirin in high doses, ibuprofen)",
                "AVOID: Nitrofurantoin, methylene blue, rasburicase",
                "AVOID: Fava beans (Vicia faba) — can trigger severe hemolysis",
                "AVOID: Naphthalene (mothballs)",
                "CAUTION: Diabetic ketoacidosis and infections can trigger hemolysis",
                "CRITICAL: Treat all infections promptly — untreated infections are a major hemolysis trigger"
            ],
            "tags": ["G6PD", "hemolysis", "drug-avoidance", "genetic"]
        },
    ]
    
    guideline_count = 0
    for guideline in guidelines:
        result = api("POST", "/community/guidelines", guideline, token)
        if result:
            guideline_count += 1
    print(f"  ✓ Added {guideline_count} health guidelines")


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  ALAFIA Demo Data Seed Script")
    print("  Populating realistic ESRD patient health data")
    print("=" * 60)
    
    # Check backend is running
    try:
        r = requests.get("http://localhost:8000/api/health")
        if r.status_code != 200:
            print("✗ Backend not responding. Start it with: docker compose up")
            sys.exit(1)
    except requests.ConnectionError:
        print("✗ Cannot connect to backend at http://localhost:8000")
        print("  Start it with: cd WEB && docker compose up")
        sys.exit(1)
    
    print("✓ Backend is running\n")
    
    # Register/login
    token = register_and_login()
    
    # Seed all data
    seed_profile(token)
    seed_medications(token)
    seed_labs(token)
    seed_nutrition(token)
    seed_fitness(token)
    seed_mood(token)
    seed_lifestyle(token)
    seed_chronic_conditions(token)
    seed_mental_health(token)
    seed_calendar(token)
    seed_community_health(token)
    
    print("\n" + "=" * 60)
    print("  ✅ Demo data seeding complete!")
    print("=" * 60)
    print(f"\n  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"  Web:   http://localhost:5173")
    print(f"  API:   http://localhost:8000/docs")
    print()


if __name__ == "__main__":
    main()
