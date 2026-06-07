"""ICD-10 Reference Data — comprehensive code catalog.

Contains the 22 ICD-10 chapters with commonly-encountered codes.
This is a lightweight in-memory catalog; for production, consider
loading from the full WHO/CMS ICD-10-CM flat files.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ICD10Code:
    """A single ICD-10 code."""
    code: str
    title: str
    chapter: str
    category: str
    is_billable: bool = True
    includes: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    body_system: str = ""
    common_symptoms: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)


# ── ICD-10 Chapters ──────────────────────────────────────────────────

ICD10_CHAPTERS = {
    "I":    {"range": "A00-B99",  "title": "Certain infectious and parasitic diseases"},
    "II":   {"range": "C00-D49",  "title": "Neoplasms"},
    "III":  {"range": "D50-D89",  "title": "Diseases of the blood and blood-forming organs"},
    "IV":   {"range": "E00-E89",  "title": "Endocrine, nutritional and metabolic diseases"},
    "V":    {"range": "F01-F99",  "title": "Mental, behavioural and neurodevelopmental disorders"},
    "VI":   {"range": "G00-G99",  "title": "Diseases of the nervous system"},
    "VII":  {"range": "H00-H59",  "title": "Diseases of the eye and adnexa"},
    "VIII": {"range": "H60-H95",  "title": "Diseases of the ear and mastoid process"},
    "IX":   {"range": "I00-I99",  "title": "Diseases of the circulatory system"},
    "X":    {"range": "J00-J99",  "title": "Diseases of the respiratory system"},
    "XI":   {"range": "K00-K95",  "title": "Diseases of the digestive system"},
    "XII":  {"range": "L00-L99",  "title": "Diseases of the skin and subcutaneous tissue"},
    "XIII": {"range": "M00-M99", "title": "Diseases of the musculoskeletal system and connective tissue"},
    "XIV":  {"range": "N00-N99", "title": "Diseases of the genitourinary system"},
    "XV":   {"range": "O00-O9A", "title": "Pregnancy, childbirth and the puerperium"},
    "XVI":  {"range": "P00-P96", "title": "Certain conditions originating in the perinatal period"},
    "XVII": {"range": "Q00-Q99", "title": "Congenital malformations, deformations and chromosomal abnormalities"},
    "XVIII":{"range": "R00-R99", "title": "Symptoms, signs and abnormal clinical and laboratory findings"},
    "XIX":  {"range": "S00-T88", "title": "Injury, poisoning and certain other consequences of external causes"},
    "XX":   {"range": "V00-Y99", "title": "External causes of morbidity"},
    "XXI":  {"range": "Z00-Z99", "title": "Factors influencing health status and contact with health services"},
}


def _build_catalog() -> Dict[str, ICD10Code]:
    """Build the ICD-10 code catalog."""
    codes: Dict[str, ICD10Code] = {}

    def _add(code: str, title: str, chapter: str, category: str, **kw):
        codes[code] = ICD10Code(code=code, title=title, chapter=chapter, category=category, **kw)

    # ═══════════════════════════════════════════════════════════════
    # Chapter I — Infectious & Parasitic Diseases (A00-B99)
    # ═══════════════════════════════════════════════════════════════
    _add("A09",   "Infectious gastroenteritis and colitis", "I", "Intestinal infectious diseases",
         body_system="gastrointestinal", common_symptoms=["diarrhea", "vomiting", "abdominal pain", "fever"])
    _add("A15.0", "Tuberculosis of lung", "I", "Tuberculosis",
         body_system="respiratory", common_symptoms=["chronic cough", "hemoptysis", "night sweats", "weight loss"])
    _add("A41.9", "Sepsis, unspecified organism", "I", "Sepsis",
         body_system="systemic", common_symptoms=["fever", "tachycardia", "hypotension", "confusion"])
    _add("A49.9", "Bacterial infection, unspecified", "I", "Other bacterial diseases",
         body_system="systemic", common_symptoms=["fever", "malaise", "localized pain"])
    _add("B20",   "HIV disease", "I", "HIV disease",
         body_system="immune", common_symptoms=["weight loss", "fatigue", "recurrent infections"])
    _add("B34.9", "Viral infection, unspecified", "I", "Viral infections",
         body_system="systemic", common_symptoms=["fever", "fatigue", "body aches"])
    _add("B35.1", "Tinea unguium (nail fungus)", "I", "Mycoses",
         body_system="skin", common_symptoms=["nail discoloration", "thickened nails"])
    _add("B37.0", "Candidal stomatitis (oral thrush)", "I", "Mycoses",
         body_system="oral", common_symptoms=["white patches in mouth", "pain", "difficulty swallowing"])
    _add("A15.9", "Respiratory tuberculosis, unspecified", "I", "Tuberculosis",
         body_system="respiratory", common_symptoms=["cough", "hemoptysis", "night sweats", "weight loss", "fever"])
    _add("A90",   "Dengue fever", "I", "Arthropod-borne viral fevers",
         body_system="systemic", common_symptoms=["high fever", "severe headache", "joint pain", "rash", "bleeding"],
         risk_factors=["tropical climate", "mosquito exposure"])
    _add("A06.0", "Acute amebic dysentery", "I", "Protozoal intestinal diseases",
         body_system="gastrointestinal", common_symptoms=["bloody diarrhea", "abdominal pain", "fever"])
    _add("B50.9", "Plasmodium falciparum malaria, unspecified", "I", "Protozoal diseases",
         body_system="systemic", common_symptoms=["cyclical fever", "chills", "sweating", "headache", "anemia"],
         risk_factors=["tropical region", "mosquito exposure", "no prophylaxis"])
    _add("B53.8", "Other malaria, not elsewhere classified", "I", "Protozoal diseases",
         body_system="systemic", common_symptoms=["fever", "chills", "splenomegaly"])
    _add("B86",   "Scabies", "I", "Pediculosis, acariasis and other infestations",
         body_system="skin", common_symptoms=["intense itching", "rash", "burrow tracks"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter II — Neoplasms (C00-D49)
    # ═══════════════════════════════════════════════════════════════
    _add("C18.9", "Malignant neoplasm of colon, unspecified", "II", "Malignant neoplasms of digestive organs",
         body_system="gastrointestinal", common_symptoms=["change in bowel habits", "rectal bleeding", "weight loss"],
         risk_factors=["family history", "age >50", "high-fat diet", "inflammatory bowel disease"])
    _add("C34.90","Malignant neoplasm of unspecified part of bronchus or lung", "II", "Malignant neoplasms of respiratory organs",
         body_system="respiratory", common_symptoms=["persistent cough", "hemoptysis", "chest pain", "weight loss"],
         risk_factors=["smoking", "asbestos exposure", "family history"])
    _add("C50.919","Malignant neoplasm of unspecified site of unspecified female breast", "II", "Malignant neoplasms of breast",
         body_system="breast", common_symptoms=["breast lump", "nipple discharge", "skin changes"],
         risk_factors=["family history", "BRCA mutation", "age >50", "hormone therapy"])
    _add("C61",   "Malignant neoplasm of prostate", "II", "Malignant neoplasms of male genital organs",
         body_system="genitourinary", common_symptoms=["difficulty urinating", "blood in urine", "bone pain"],
         risk_factors=["age >50", "family history", "African descent"])
    _add("C73",   "Malignant neoplasm of thyroid gland", "II", "Malignant neoplasms of thyroid",
         body_system="endocrine", common_symptoms=["neck lump", "hoarseness", "difficulty swallowing"])
    _add("D50.9", "Iron deficiency anemia, unspecified", "III", "Nutritional anemias",
         body_system="hematologic", common_symptoms=["fatigue", "pallor", "shortness of breath", "dizziness"],
         risk_factors=["menstruation", "poor diet", "GI bleeding"])
    _add("C56.9", "Malignant neoplasm of unspecified ovary", "II", "Malignant neoplasms of female genital organs",
         body_system="reproductive", common_symptoms=["abdominal bloating", "pelvic pain", "urinary urgency"],
         risk_factors=["family history", "BRCA mutation", "age >50"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter III — Blood & Blood-forming Organs (D50-D89)
    # ═══════════════════════════════════════════════════════════════
    _add("D56.0", "Alpha thalassemia", "III", "Hemolytic anemias",
         body_system="hematologic", common_symptoms=["fatigue", "weakness", "pale skin", "jaundice"])
    _add("D56.1", "Beta thalassemia", "III", "Hemolytic anemias",
         body_system="hematologic", common_symptoms=["fatigue", "weakness", "bone deformities", "splenomegaly"],
         risk_factors=["Mediterranean descent", "African descent", "Southeast Asian descent"])
    _add("D57.1", "Sickle-cell disease without crisis", "III", "Hemolytic anemias",
         body_system="hematologic", common_symptoms=["pain episodes", "fatigue", "swelling hands/feet", "jaundice"],
         risk_factors=["African descent", "family history", "sickle cell trait"])
    _add("D57.0", "Sickle-cell disease with crisis", "III", "Hemolytic anemias",
         body_system="hematologic", common_symptoms=["severe pain", "fever", "swelling", "acute chest syndrome"])
    _add("D55.0", "G6PD deficiency anemia", "III", "Hemolytic anemias",
         body_system="hematologic", common_symptoms=["fatigue", "jaundice", "dark urine", "pallor"],
         risk_factors=["African descent", "Mediterranean descent", "fava beans", "certain medications"])
    _add("D64.9", "Anemia, unspecified", "III", "Other anemias",
         body_system="hematologic", common_symptoms=["fatigue", "weakness", "pallor", "shortness of breath"])
    _add("D68.9", "Coagulation defect, unspecified", "III", "Coagulation defects",
         body_system="hematologic", common_symptoms=["easy bruising", "prolonged bleeding"])
    _add("D69.6", "Thrombocytopenia, unspecified", "III", "Purpura and other hemorrhagic conditions",
         body_system="hematologic", common_symptoms=["petechiae", "easy bruising", "bleeding gums"])
    _add("D80.1", "Nonfamilial hypogammaglobulinemia", "III", "Immunodeficiency disorders",
         body_system="immune", common_symptoms=["recurrent infections", "chronic sinusitis"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter IV — Endocrine, Nutritional & Metabolic (E00-E89)
    # ═══════════════════════════════════════════════════════════════
    _add("E03.9", "Hypothyroidism, unspecified", "IV", "Thyroid disorders",
         body_system="endocrine", common_symptoms=["fatigue", "weight gain", "cold intolerance", "constipation", "dry skin"],
         risk_factors=["female sex", "age >60", "family history", "autoimmune disease"])
    _add("E05.90","Thyrotoxicosis, unspecified", "IV", "Thyroid disorders",
         body_system="endocrine", common_symptoms=["weight loss", "tachycardia", "tremor", "heat intolerance", "anxiety"])
    _add("E10.9", "Type 1 diabetes mellitus without complications", "IV", "Diabetes mellitus",
         body_system="endocrine", common_symptoms=["polyuria", "polydipsia", "weight loss", "fatigue"],
         risk_factors=["family history", "autoimmune conditions"])
    _add("E11.9", "Type 2 diabetes mellitus without complications", "IV", "Diabetes mellitus",
         body_system="endocrine", common_symptoms=["polyuria", "polydipsia", "fatigue", "blurred vision"],
         risk_factors=["obesity", "sedentary lifestyle", "family history", "age >45"])
    _add("E11.65","Type 2 diabetes mellitus with hyperglycemia", "IV", "Diabetes mellitus",
         body_system="endocrine", common_symptoms=["extreme thirst", "frequent urination", "blurred vision"])
    _add("E11.40","Type 2 diabetes with diabetic neuropathy, unspecified", "IV", "Diabetes mellitus",
         body_system="endocrine", common_symptoms=["numbness", "tingling", "burning pain in extremities"])
    _add("E11.22","Type 2 diabetes with diabetic chronic kidney disease", "IV", "Diabetes mellitus",
         body_system="endocrine", common_symptoms=["edema", "fatigue", "decreased urine output"])
    _add("E13.9", "Other specified diabetes mellitus without complications", "IV", "Diabetes mellitus",
         body_system="endocrine", common_symptoms=["polyuria", "polydipsia", "weight changes"])
    _add("E66.01","Morbid (severe) obesity due to excess calories", "IV", "Obesity and other hyperalimentation",
         body_system="metabolic", common_symptoms=["BMI ≥40", "joint pain", "shortness of breath"],
         risk_factors=["sedentary lifestyle", "caloric excess", "genetics"])
    _add("E66.9", "Obesity, unspecified", "IV", "Obesity",
         body_system="metabolic", common_symptoms=["elevated BMI", "weight gain"],
         risk_factors=["sedentary lifestyle", "poor diet", "genetics"])
    _add("E78.0", "Pure hypercholesterolemia", "IV", "Disorders of lipoprotein metabolism",
         body_system="metabolic", common_symptoms=["asymptomatic", "xanthomas"],
         risk_factors=["family history", "high-fat diet", "sedentary lifestyle"])
    _add("E78.5", "Hyperlipidemia, unspecified", "IV", "Disorders of lipoprotein metabolism",
         body_system="metabolic", common_symptoms=["asymptomatic"],
         risk_factors=["obesity", "diabetes", "family history", "high-fat diet"])
    _add("E55.9", "Vitamin D deficiency, unspecified", "IV", "Other nutritional deficiencies",
         body_system="metabolic", common_symptoms=["fatigue", "bone pain", "muscle weakness"],
         risk_factors=["limited sun exposure", "dark skin", "obesity"])
    _add("E61.1", "Iron deficiency", "IV", "Other nutritional deficiencies",
         body_system="metabolic", common_symptoms=["fatigue", "weakness", "pale skin"])
    _add("E87.6", "Hypokalemia", "IV", "Disorders of fluid, electrolyte and acid-base balance",
         body_system="metabolic", common_symptoms=["muscle weakness", "cramps", "palpitations", "fatigue"])
    _add("E87.1", "Hypo-osmolality and hyponatremia", "IV", "Electrolyte disorders",
         body_system="metabolic", common_symptoms=["confusion", "nausea", "headache", "seizures"])
    _add("E27.1", "Primary adrenocortical insufficiency (Addison disease)", "IV", "Adrenal disorders",
         body_system="endocrine", common_symptoms=["fatigue", "weight loss", "hyperpigmentation", "hypotension"])
    _add("E24.9", "Cushing syndrome, unspecified", "IV", "Adrenal disorders",
         body_system="endocrine", common_symptoms=["weight gain", "moon face", "buffalo hump", "striae"])
    _add("E21.0", "Primary hyperparathyroidism", "IV", "Parathyroid disorders",
         body_system="endocrine", common_symptoms=["kidney stones", "bone pain", "fatigue", "depression"])
    _add("E83.52","Hypercalcemia", "IV", "Disorders of mineral metabolism",
         body_system="metabolic", common_symptoms=["fatigue", "nausea", "constipation", "confusion"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter V — Mental & Behavioural Disorders (F01-F99)
    # ═══════════════════════════════════════════════════════════════
    _add("F32.1", "Major depressive disorder, single episode, moderate", "V", "Mood disorders",
         body_system="psychiatric", common_symptoms=["depressed mood", "loss of interest", "fatigue", "sleep changes"])
    _add("F32.9", "Major depressive disorder, single episode, unspecified", "V", "Mood disorders",
         body_system="psychiatric", common_symptoms=["persistent sadness", "hopelessness", "appetite changes"])
    _add("F33.0", "Major depressive disorder, recurrent, mild", "V", "Mood disorders",
         body_system="psychiatric", common_symptoms=["recurrent depressed mood", "low energy"])
    _add("F41.1", "Generalized anxiety disorder", "V", "Anxiety disorders",
         body_system="psychiatric", common_symptoms=["excessive worry", "restlessness", "muscle tension", "insomnia"])
    _add("F41.0", "Panic disorder", "V", "Anxiety disorders",
         body_system="psychiatric", common_symptoms=["panic attacks", "chest pain", "palpitations", "fear of dying"])
    _add("F43.10","Post-traumatic stress disorder, unspecified", "V", "Trauma and stressor-related disorders",
         body_system="psychiatric", common_symptoms=["flashbacks", "nightmares", "hypervigilance", "avoidance"])
    _add("F50.00","Anorexia nervosa, unspecified", "V", "Eating disorders",
         body_system="psychiatric", common_symptoms=["severe weight loss", "fear of weight gain", "distorted body image"])
    _add("F50.2", "Bulimia nervosa", "V", "Eating disorders",
         body_system="psychiatric", common_symptoms=["binge eating", "purging", "guilt after eating"])
    _add("F10.20","Alcohol dependence, uncomplicated", "V", "Substance use disorders",
         body_system="psychiatric", common_symptoms=["craving", "tolerance", "withdrawal symptoms"])
    _add("F17.210","Nicotine dependence, cigarettes, uncomplicated", "V", "Substance use disorders",
         body_system="psychiatric", common_symptoms=["craving", "irritability", "difficulty quitting"])
    _add("F90.0", "ADHD, predominantly inattentive type", "V", "Neurodevelopmental disorders",
         body_system="psychiatric", common_symptoms=["inattention", "disorganization", "forgetfulness"])
    _add("F84.0", "Autistic disorder", "V", "Pervasive developmental disorders",
         body_system="psychiatric", common_symptoms=["social communication difficulties", "restricted interests"])
    _add("F51.01","Primary insomnia", "V", "Sleep disorders",
         body_system="psychiatric", common_symptoms=["difficulty falling asleep", "difficulty staying asleep", "daytime fatigue"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter VI — Diseases of the Nervous System (G00-G99)
    # ═══════════════════════════════════════════════════════════════
    _add("G20",   "Parkinson disease", "VI", "Extrapyramidal and movement disorders",
         body_system="neurological", common_symptoms=["tremor", "rigidity", "bradykinesia", "postural instability"])
    _add("G30.9", "Alzheimer disease, unspecified", "VI", "Other degenerative diseases of the nervous system",
         body_system="neurological", common_symptoms=["memory loss", "confusion", "personality changes"])
    _add("G35",   "Multiple sclerosis", "VI", "Demyelinating diseases of the CNS",
         body_system="neurological", common_symptoms=["vision problems", "numbness", "fatigue", "difficulty walking"])
    _add("G40.909","Epilepsy, unspecified, not intractable", "VI", "Episodic and paroxysmal disorders",
         body_system="neurological", common_symptoms=["seizures", "loss of consciousness", "confusion"])
    _add("G43.909","Migraine, unspecified, not intractable", "VI", "Episodic and paroxysmal disorders",
         body_system="neurological", common_symptoms=["severe headache", "nausea", "light sensitivity", "aura"])
    _add("G47.33","Obstructive sleep apnea", "VI", "Sleep disorders",
         body_system="neurological", common_symptoms=["snoring", "daytime sleepiness", "witnessed apneas"],
         risk_factors=["obesity", "male sex", "age >50", "large neck circumference"])
    _add("G62.9", "Polyneuropathy, unspecified", "VI", "Polyneuropathies",
         body_system="neurological", common_symptoms=["numbness", "tingling", "weakness in extremities"])
    _add("G89.29","Other chronic pain", "VI", "Pain, not elsewhere classified",
         body_system="neurological", common_symptoms=["persistent pain", "reduced function"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter IX — Diseases of the Circulatory System (I00-I99)
    # ═══════════════════════════════════════════════════════════════
    _add("I10",   "Essential (primary) hypertension", "IX", "Hypertensive diseases",
         body_system="cardiovascular", common_symptoms=["usually asymptomatic", "headache", "dizziness"],
         risk_factors=["obesity", "high sodium diet", "sedentary lifestyle", "family history", "age", "African descent"])
    _add("I11.9", "Hypertensive heart disease without heart failure", "IX", "Hypertensive diseases",
         body_system="cardiovascular", common_symptoms=["chest pain", "shortness of breath"])
    _add("I20.9", "Angina pectoris, unspecified", "IX", "Ischemic heart diseases",
         body_system="cardiovascular", common_symptoms=["chest pain", "chest pressure", "pain with exertion"])
    _add("I21.9", "Acute myocardial infarction, unspecified", "IX", "Ischemic heart diseases",
         body_system="cardiovascular", common_symptoms=["chest pain", "radiating arm pain", "shortness of breath", "diaphoresis"])
    _add("I25.10","Atherosclerotic heart disease of native coronary artery", "IX", "Ischemic heart diseases",
         body_system="cardiovascular", common_symptoms=["chest pain", "shortness of breath with exertion"],
         risk_factors=["smoking", "diabetes", "hypertension", "hyperlipidemia"])
    _add("I48.91","Unspecified atrial fibrillation", "IX", "Other cardiac arrhythmias",
         body_system="cardiovascular", common_symptoms=["palpitations", "irregular heartbeat", "fatigue", "dizziness"])
    _add("I50.9", "Heart failure, unspecified", "IX", "Heart failure",
         body_system="cardiovascular", common_symptoms=["dyspnea", "edema", "fatigue", "orthopnea"],
         risk_factors=["hypertension", "coronary artery disease", "diabetes", "obesity"])
    _add("I63.9", "Cerebral infarction, unspecified (stroke)", "IX", "Cerebrovascular diseases",
         body_system="cardiovascular", common_symptoms=["sudden weakness", "speech difficulty", "facial droop", "confusion"])
    _add("I73.9", "Peripheral vascular disease, unspecified", "IX", "Diseases of arteries",
         body_system="cardiovascular", common_symptoms=["leg pain with walking", "cold extremities", "poor wound healing"])
    _add("I83.90","Asymptomatic varicose veins of unspecified lower extremity", "IX", "Diseases of veins",
         body_system="cardiovascular", common_symptoms=["visible varicose veins", "leg heaviness", "aching"])
    _add("I26.99","Other pulmonary embolism without acute cor pulmonale", "IX", "Pulmonary heart disease",
         body_system="cardiovascular", common_symptoms=["sudden dyspnea", "chest pain", "tachycardia"],
         risk_factors=["immobility", "surgery", "DVT", "oral contraceptives"])
    _add("I42.9", "Cardiomyopathy, unspecified", "IX", "Cardiomyopathy",
         body_system="cardiovascular", common_symptoms=["dyspnea", "fatigue", "edema", "arrhythmia"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter X — Diseases of the Respiratory System (J00-J99)
    # ═══════════════════════════════════════════════════════════════
    _add("J00",   "Acute nasopharyngitis (common cold)", "X", "Acute upper respiratory infections",
         body_system="respiratory", common_symptoms=["rhinorrhea", "sore throat", "cough", "sneezing"])
    _add("J06.9", "Acute upper respiratory infection, unspecified", "X", "Acute upper respiratory infections",
         body_system="respiratory", common_symptoms=["sore throat", "nasal congestion", "cough", "fever"])
    _add("J18.9", "Pneumonia, unspecified organism", "X", "Pneumonia",
         body_system="respiratory", common_symptoms=["cough", "fever", "dyspnea", "chest pain"],
         risk_factors=["age >65", "immunocompromised", "chronic lung disease"])
    _add("J20.9", "Acute bronchitis, unspecified", "X", "Other acute lower respiratory infections",
         body_system="respiratory", common_symptoms=["cough", "sputum production", "chest discomfort"])
    _add("J44.1", "COPD with acute exacerbation", "X", "Chronic lower respiratory diseases",
         body_system="respiratory", common_symptoms=["worsening dyspnea", "increased cough", "sputum changes"],
         risk_factors=["smoking", "occupational exposure"])
    _add("J45.20","Mild intermittent asthma, uncomplicated", "X", "Chronic lower respiratory diseases",
         body_system="respiratory", common_symptoms=["wheezing", "cough", "chest tightness", "shortness of breath"])
    _add("J45.50","Severe persistent asthma, uncomplicated", "X", "Chronic lower respiratory diseases",
         body_system="respiratory", common_symptoms=["daily symptoms", "frequent exacerbations", "limited activity"])
    _add("J84.10","Pulmonary fibrosis, unspecified", "X", "Other interstitial pulmonary diseases",
         body_system="respiratory", common_symptoms=["progressive dyspnea", "dry cough", "fatigue"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter XI — Diseases of the Digestive System (K00-K95)
    # ═══════════════════════════════════════════════════════════════
    _add("K21.0", "GERD with esophagitis", "XI", "Diseases of esophagus, stomach and duodenum",
         body_system="gastrointestinal", common_symptoms=["heartburn", "regurgitation", "dysphagia"])
    _add("K25.9", "Gastric ulcer, unspecified", "XI", "Diseases of esophagus, stomach and duodenum",
         body_system="gastrointestinal", common_symptoms=["epigastric pain", "nausea", "bloating"])
    _add("K29.70","Gastritis, unspecified, without bleeding", "XI", "Diseases of esophagus, stomach and duodenum",
         body_system="gastrointestinal", common_symptoms=["epigastric pain", "nausea", "loss of appetite"])
    _add("K35.80","Unspecified acute appendicitis", "XI", "Diseases of appendix",
         body_system="gastrointestinal", common_symptoms=["right lower quadrant pain", "nausea", "fever", "anorexia"])
    _add("K50.90","Crohn disease, unspecified, without complications", "XI", "Noninfective enteritis and colitis",
         body_system="gastrointestinal", common_symptoms=["diarrhea", "abdominal pain", "weight loss", "fatigue"])
    _add("K51.90","Ulcerative colitis, unspecified, without complications", "XI", "Noninfective enteritis and colitis",
         body_system="gastrointestinal", common_symptoms=["bloody diarrhea", "abdominal cramps", "urgency"])
    _add("K58.9", "Irritable bowel syndrome without diarrhea", "XI", "Other disorders of intestine",
         body_system="gastrointestinal", common_symptoms=["abdominal pain", "bloating", "altered bowel habits"])
    _add("K70.30","Alcoholic cirrhosis of liver without ascites", "XI", "Diseases of liver",
         body_system="gastrointestinal", common_symptoms=["fatigue", "jaundice", "abdominal swelling"])
    _add("K76.0", "Fatty (change of) liver, not elsewhere classified (NAFLD)", "XI", "Other diseases of liver",
         body_system="gastrointestinal", common_symptoms=["usually asymptomatic", "fatigue", "right upper quadrant discomfort"],
         risk_factors=["obesity", "diabetes", "metabolic syndrome"])
    _add("K80.20","Calculus of gallbladder without obstruction", "XI", "Disorders of gallbladder",
         body_system="gastrointestinal", common_symptoms=["right upper quadrant pain", "nausea", "pain after fatty meals"])
    _add("K85.90","Acute pancreatitis without necrosis or infection, unspecified", "XI", "Diseases of pancreas",
         body_system="gastrointestinal", common_symptoms=["severe epigastric pain", "nausea", "vomiting"])
    _add("K92.0", "Hematemesis (vomiting blood)", "XI", "Other GI diseases",
         body_system="gastrointestinal", common_symptoms=["vomiting blood", "dark stools", "dizziness"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter XII — Diseases of the Skin (L00-L99)
    # ═══════════════════════════════════════════════════════════════
    _add("L20.9", "Atopic dermatitis, unspecified (eczema)", "XII", "Dermatitis and eczema",
         body_system="skin", common_symptoms=["itching", "dry skin", "red patches", "scaling"])
    _add("L40.0", "Psoriasis vulgaris", "XII", "Papulosquamous disorders",
         body_system="skin", common_symptoms=["red scaly patches", "itching", "nail changes"])
    _add("L70.0", "Acne vulgaris", "XII", "Disorders of skin appendages",
         body_system="skin", common_symptoms=["comedones", "papules", "pustules", "cysts"])
    _add("L50.9", "Urticaria, unspecified (hives)", "XII", "Urticaria and erythema",
         body_system="skin", common_symptoms=["wheals", "itching", "angioedema"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter XIII — Musculoskeletal (M00-M99)
    # ═══════════════════════════════════════════════════════════════
    _add("M06.9", "Rheumatoid arthritis, unspecified", "XIII", "Inflammatory polyarthropathies",
         body_system="musculoskeletal", common_symptoms=["joint pain", "swelling", "morning stiffness", "fatigue"])
    _add("M10.9", "Gout, unspecified", "XIII", "Crystal arthropathies",
         body_system="musculoskeletal", common_symptoms=["sudden joint pain", "swelling", "redness", "warmth"],
         risk_factors=["high-purine diet", "obesity", "male sex", "alcohol"])
    _add("M17.9", "Osteoarthritis of knee, unspecified", "XIII", "Arthrosis",
         body_system="musculoskeletal", common_symptoms=["knee pain", "stiffness", "crepitus", "reduced range of motion"])
    _add("M54.5", "Low back pain", "XIII", "Dorsopathies",
         body_system="musculoskeletal", common_symptoms=["back pain", "muscle spasm", "limited mobility"])
    _add("M79.3", "Panniculitis, unspecified", "XIII", "Other soft tissue disorders",
         body_system="musculoskeletal", common_symptoms=["subcutaneous nodules", "pain"])
    _add("M81.0", "Age-related osteoporosis without pathological fracture", "XIII", "Osteopathies",
         body_system="musculoskeletal", common_symptoms=["usually asymptomatic", "fractures with minimal trauma"],
         risk_factors=["postmenopausal", "low calcium", "vitamin D deficiency", "sedentary"])
    _add("M79.1", "Myalgia", "XIII", "Other soft tissue disorders",
         body_system="musculoskeletal", common_symptoms=["muscle pain", "tenderness", "stiffness"])
    _add("M54.2", "Cervicalgia (neck pain)", "XIII", "Dorsopathies",
         body_system="musculoskeletal", common_symptoms=["neck pain", "stiffness", "limited range of motion"])
    _add("M75.10","Rotator cuff tear, unspecified shoulder", "XIII", "Shoulder lesions",
         body_system="musculoskeletal", common_symptoms=["shoulder pain", "weakness", "limited overhead reach"])
    _add("M32.9", "Systemic lupus erythematosus, unspecified", "XIII", "Systemic connective tissue disorders",
         body_system="musculoskeletal", common_symptoms=["fatigue", "joint pain", "butterfly rash", "photosensitivity"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter XIV — Genitourinary (N00-N99)
    # ═══════════════════════════════════════════════════════════════
    _add("N18.3", "Chronic kidney disease, stage 3", "XIV", "Renal tubulo-interstitial diseases",
         body_system="renal", common_symptoms=["fatigue", "edema", "nocturia"],
         risk_factors=["diabetes", "hypertension", "age >60"])
    _add("N18.4", "Chronic kidney disease, stage 4", "XIV", "Renal tubulo-interstitial diseases",
         body_system="renal", common_symptoms=["fatigue", "edema", "nausea", "decreased appetite"])
    _add("N18.5", "Chronic kidney disease, stage 5 (ESRD)", "XIV", "Renal tubulo-interstitial diseases",
         body_system="renal", common_symptoms=["severe fatigue", "edema", "nausea", "pruritus", "anemia"])
    _add("N18.9", "Chronic kidney disease, unspecified", "XIV", "Renal tubulo-interstitial diseases",
         body_system="renal", common_symptoms=["fatigue", "edema", "changes in urination"])
    _add("N39.0", "Urinary tract infection, site not specified", "XIV", "Other diseases of urinary system",
         body_system="renal", common_symptoms=["dysuria", "frequency", "urgency", "suprapubic pain"])
    _add("N20.0", "Calculus of kidney (kidney stone)", "XIV", "Urolithiasis",
         body_system="renal", common_symptoms=["flank pain", "hematuria", "nausea", "radiating groin pain"])
    _add("N40.0", "Benign prostatic hyperplasia without LUTS", "XIV", "Diseases of male genital organs",
         body_system="genitourinary", common_symptoms=["urinary hesitancy", "weak stream", "nocturia"])
    _add("N80.9", "Endometriosis, unspecified", "XIV", "Noninflammatory disorders of female genital tract",
         body_system="reproductive", common_symptoms=["pelvic pain", "dysmenorrhea", "dyspareunia", "infertility"])
    _add("N92.0", "Excessive menstruation with regular cycle (menorrhagia)", "XIV", "Noninflammatory disorders",
         body_system="reproductive", common_symptoms=["heavy menstrual bleeding", "clots", "fatigue"])
    _add("N95.1", "Menopausal and female climacteric states", "XIV", "Menopausal disorders",
         body_system="reproductive", common_symptoms=["hot flashes", "night sweats", "mood changes", "vaginal dryness"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter XV — Pregnancy (O00-O9A)
    # ═══════════════════════════════════════════════════════════════
    _add("O13.9", "Gestational hypertension, unspecified trimester", "XV", "Edema, proteinuria and hypertensive disorders",
         body_system="obstetric", common_symptoms=["elevated blood pressure", "headache", "visual changes"])
    _add("O24.419","Gestational diabetes mellitus in pregnancy, unspecified", "XV", "Diabetes mellitus in pregnancy",
         body_system="obstetric", common_symptoms=["polyuria", "polydipsia", "fatigue"],
         risk_factors=["obesity", "family history of diabetes", "advanced maternal age"])
    _add("O14.90","Unspecified pre-eclampsia, unspecified trimester", "XV", "Pre-eclampsia",
         body_system="obstetric", common_symptoms=["hypertension", "proteinuria", "headache", "visual changes", "edema"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter XVIII — Symptoms & Signs (R00-R99)
    # ═══════════════════════════════════════════════════════════════
    _add("R00.0", "Tachycardia, unspecified", "XVIII", "Symptoms involving the circulatory system",
         body_system="cardiovascular", common_symptoms=["rapid heartbeat", "palpitations"])
    _add("R05.9", "Cough, unspecified", "XVIII", "Symptoms involving the respiratory system",
         body_system="respiratory", common_symptoms=["cough"])
    _add("R06.00","Dyspnea, unspecified", "XVIII", "Symptoms involving the respiratory system",
         body_system="respiratory", common_symptoms=["shortness of breath", "difficulty breathing"])
    _add("R07.9", "Chest pain, unspecified", "XVIII", "Symptoms involving the circulatory system",
         body_system="cardiovascular", common_symptoms=["chest pain", "chest discomfort"])
    _add("R10.9", "Unspecified abdominal pain", "XVIII", "Symptoms involving the digestive system",
         body_system="gastrointestinal", common_symptoms=["abdominal pain"])
    _add("R11.2", "Nausea with vomiting, unspecified", "XVIII", "Symptoms involving the digestive system",
         body_system="gastrointestinal", common_symptoms=["nausea", "vomiting"])
    _add("R42",   "Dizziness and giddiness", "XVIII", "Symptoms involving the nervous system",
         body_system="neurological", common_symptoms=["dizziness", "vertigo", "lightheadedness"])
    _add("R50.9", "Fever, unspecified", "XVIII", "General symptoms and signs",
         body_system="systemic", common_symptoms=["elevated temperature", "chills", "malaise"])
    _add("R51.9", "Headache, unspecified", "XVIII", "Symptoms involving the nervous system",
         body_system="neurological", common_symptoms=["headache"])
    _add("R53.1", "Weakness", "XVIII", "General symptoms and signs",
         body_system="systemic", common_symptoms=["weakness", "fatigue"])
    _add("R53.83","Other fatigue", "XVIII", "General symptoms and signs",
         body_system="systemic", common_symptoms=["fatigue", "tiredness", "lethargy"])
    _add("R63.4", "Abnormal weight loss", "XVIII", "Symptoms involving food and fluid intake",
         body_system="systemic", common_symptoms=["unintentional weight loss"])
    _add("R73.03","Prediabetes", "XVIII", "Abnormal findings on examination of blood",
         body_system="endocrine", common_symptoms=["usually asymptomatic"],
         risk_factors=["obesity", "sedentary lifestyle", "family history", "age >45"])
    _add("R19.7", "Diarrhea, unspecified", "XVIII", "Symptoms involving the digestive system",
         body_system="gastrointestinal", common_symptoms=["loose stools", "increased frequency"])
    _add("R60.0", "Localized edema", "XVIII", "General symptoms and signs",
         body_system="systemic", common_symptoms=["swelling", "pitting edema"])
    _add("R23.1", "Pallor", "XVIII", "Symptoms involving the skin",
         body_system="skin", common_symptoms=["pale skin", "pale mucous membranes"])
    _add("R79.89","Other specified abnormal findings of blood chemistry", "XVIII", "Abnormal lab findings",
         body_system="systemic", common_symptoms=["abnormal lab values"])

    # ═══════════════════════════════════════════════════════════════
    # Chapter XXI — Factors Influencing Health Status (Z00-Z99)
    # ═══════════════════════════════════════════════════════════════
    _add("Z00.00","General adult medical exam without abnormal findings", "XXI", "Persons encountering health services for examination",
         body_system="general", common_symptoms=[])
    _add("Z23",   "Encounter for immunization", "XXI", "Persons encountering health services for specific procedures",
         body_system="general", common_symptoms=[])
    _add("Z71.3", "Dietary counseling and surveillance", "XXI", "Persons encountering health services in other circumstances",
         body_system="general", common_symptoms=[])
    _add("Z72.0", "Tobacco use", "XXI", "Persons with potential health hazards related to lifestyle",
         body_system="general", common_symptoms=[], risk_factors=["smoking"])
    _add("Z87.891","Personal history of nicotine dependence", "XXI", "Personal history of other diseases",
         body_system="general", common_symptoms=[])
    _add("Z96.1", "Presence of intraocular lens", "XXI", "Persons with artificial devices",
         body_system="general", common_symptoms=[])

    # ═══════════════════════════════════════════════════════════════
    # Additional high-prevalence conditions
    # ═══════════════════════════════════════════════════════════════
    _add("H10.9", "Unspecified conjunctivitis", "VII", "Disorders of conjunctiva",
         body_system="ophthalmologic", common_symptoms=["red eye", "discharge", "itching", "tearing"])
    _add("H66.90","Otitis media, unspecified, unspecified ear", "VIII", "Diseases of middle ear",
         body_system="ENT", common_symptoms=["ear pain", "hearing loss", "fever", "ear drainage"])
    _add("J02.9", "Acute pharyngitis, unspecified (sore throat)", "X", "Acute upper respiratory infections",
         body_system="ENT", common_symptoms=["sore throat", "pain swallowing", "fever"])
    _add("J30.9", "Allergic rhinitis, unspecified", "X", "Other diseases of upper respiratory tract",
         body_system="respiratory", common_symptoms=["sneezing", "rhinorrhea", "nasal congestion", "itchy eyes"])
    _add("J32.9", "Chronic sinusitis, unspecified", "X", "Other diseases of upper respiratory tract",
         body_system="respiratory", common_symptoms=["nasal congestion", "facial pain", "postnasal drip", "headache"])

    return codes


# ── Module-level singleton ────────────────────────────────────────────
ICD10_CATALOG: Dict[str, ICD10Code] = _build_catalog()


# ── Lookup helpers ────────────────────────────────────────────────────

def search_icd10(
    query: str,
    body_system: Optional[str] = None,
    chapter: Optional[str] = None,
    limit: int = 20,
) -> List[ICD10Code]:
    """Search ICD-10 codes by keyword, body system, or chapter.

    The *query* is matched case-insensitively against code, title,
    category, synonyms, and common_symptoms.
    """
    query_lower = query.lower()
    results: List[ICD10Code] = []

    for code_obj in ICD10_CATALOG.values():
        if body_system and code_obj.body_system != body_system:
            continue
        if chapter and code_obj.chapter != chapter:
            continue

        searchable = " ".join([
            code_obj.code.lower(),
            code_obj.title.lower(),
            code_obj.category.lower(),
            " ".join(code_obj.synonyms),
            " ".join(code_obj.common_symptoms),
            code_obj.body_system,
        ])
        if query_lower in searchable:
            results.append(code_obj)

        if len(results) >= limit:
            break

    return results


def get_icd10_by_code(code: str) -> Optional[ICD10Code]:
    """Get a specific ICD-10 code."""
    return ICD10_CATALOG.get(code)


def get_codes_by_body_system(body_system: str) -> List[ICD10Code]:
    """Get all ICD-10 codes for a body system."""
    return [c for c in ICD10_CATALOG.values() if c.body_system == body_system]


def get_codes_by_symptoms(symptoms: List[str], min_match: int = 1) -> List[tuple]:
    """Find ICD-10 codes whose common_symptoms overlap with given symptoms.

    Returns list of (ICD10Code, match_count) sorted by match_count desc.
    """
    symptom_set = {s.lower() for s in symptoms}
    matches: List[tuple] = []

    for code_obj in ICD10_CATALOG.values():
        code_symptoms = {s.lower() for s in code_obj.common_symptoms}
        overlap = symptom_set & code_symptoms
        if len(overlap) >= min_match:
            matches.append((code_obj, len(overlap)))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


def get_all_body_systems() -> List[str]:
    """Return distinct body systems in the catalog."""
    return sorted({c.body_system for c in ICD10_CATALOG.values()})
