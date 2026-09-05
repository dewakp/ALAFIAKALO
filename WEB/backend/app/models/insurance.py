"""Multi-insurance models — locale-structured insurance for patients."""

from datetime import datetime, timezone, date
from enum import Enum as PyEnum

from sqlalchemy import String, DateTime, Date, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ──────────────────────────────────────────────
# Regional insurance-system enums
# ──────────────────────────────────────────────

class InsuranceRegion(str, PyEnum):
    NORTH_AMERICA = "north_america"
    EUROPE = "europe"
    AFRICA = "africa"
    MIDDLE_EAST = "middle_east"
    SOUTH_ASIA = "south_asia"
    OTHER = "other"


# Comprehensive country → providers mapping (used by frontend dropdowns)
INSURANCE_PROVIDERS_BY_COUNTRY: dict[str, list[dict[str, str]]] = {
    # ── North America ──────────────────────────
    "US": [
        {"code": "medicare", "name": "Medicare"},
        {"code": "medicaid", "name": "Medicaid"},
        {"code": "tricare", "name": "TRICARE"},
        {"code": "va", "name": "Veterans Affairs (VA)"},
        {"code": "bcbs", "name": "Blue Cross Blue Shield"},
        {"code": "united_health", "name": "UnitedHealthcare"},
        {"code": "aetna", "name": "Aetna"},
        {"code": "cigna", "name": "Cigna"},
        {"code": "humana", "name": "Humana"},
        {"code": "kaiser", "name": "Kaiser Permanente"},
        {"code": "anthem", "name": "Anthem"},
        {"code": "centene", "name": "Centene / Wellcare"},
        {"code": "molina", "name": "Molina Healthcare"},
        {"code": "oscar", "name": "Oscar Health"},
        {"code": "marketplace", "name": "ACA Marketplace Plan"},
        {"code": "other_us", "name": "Other (US)"},
    ],
    "CA": [
        {"code": "ohip", "name": "OHIP (Ontario)"},
        {"code": "ramq", "name": "RAMQ (Quebec)"},
        {"code": "msp_bc", "name": "MSP (British Columbia)"},
        {"code": "ahcip", "name": "AHCIP (Alberta)"},
        {"code": "shp_sk", "name": "Saskatchewan Health"},
        {"code": "mhsal_nb", "name": "Medicare (New Brunswick)"},
        {"code": "sun_life", "name": "Sun Life"},
        {"code": "manulife", "name": "Manulife"},
        {"code": "great_west", "name": "Great-West Life / Canada Life"},
        {"code": "other_ca", "name": "Other (Canada)"},
    ],
    "MX": [
        {"code": "imss", "name": "IMSS"},
        {"code": "issste", "name": "ISSSTE"},
        {"code": "insabi", "name": "INSABI / IMSS-Bienestar"},
        {"code": "seguro_popular", "name": "Seguro Popular"},
        {"code": "metlife_mx", "name": "MetLife México"},
        {"code": "gnp", "name": "GNP Seguros"},
        {"code": "axa_mx", "name": "AXA Seguros"},
        {"code": "other_mx", "name": "Other (Mexico)"},
    ],

    # ── Europe ─────────────────────────────────
    "GB": [
        {"code": "nhs", "name": "NHS (National Health Service)"},
        {"code": "bupa", "name": "BUPA"},
        {"code": "axa_ppp", "name": "AXA PPP"},
        {"code": "aviva", "name": "Aviva"},
        {"code": "vitality", "name": "Vitality Health"},
        {"code": "other_gb", "name": "Other (UK)"},
    ],
    "DE": [
        {"code": "gkv", "name": "GKV (Statutory Health Insurance)"},
        {"code": "tk", "name": "Techniker Krankenkasse (TK)"},
        {"code": "barmer", "name": "BARMER"},
        {"code": "dak", "name": "DAK-Gesundheit"},
        {"code": "aok", "name": "AOK"},
        {"code": "pkv", "name": "PKV (Private Health Insurance)"},
        {"code": "allianz_de", "name": "Allianz Private"},
        {"code": "other_de", "name": "Other (Germany)"},
    ],
    "FR": [
        {"code": "securite_sociale", "name": "Sécurité Sociale (Assurance Maladie)"},
        {"code": "cmu", "name": "CMU-C / Complémentaire Santé Solidaire"},
        {"code": "axa_fr", "name": "AXA France"},
        {"code": "harmonie", "name": "Harmonie Mutuelle"},
        {"code": "mgen", "name": "MGEN"},
        {"code": "other_fr", "name": "Other (France)"},
    ],
    "IT": [
        {"code": "ssn", "name": "SSN (Servizio Sanitario Nazionale)"},
        {"code": "unisalute", "name": "UniSalute"},
        {"code": "generali_it", "name": "Generali Italia"},
        {"code": "other_it", "name": "Other (Italy)"},
    ],
    "ES": [
        {"code": "sns", "name": "SNS (Sistema Nacional de Salud)"},
        {"code": "mapfre", "name": "MAPFRE"},
        {"code": "sanitas", "name": "Sanitas"},
        {"code": "adeslas", "name": "Adeslas"},
        {"code": "dkv_es", "name": "DKV"},
        {"code": "other_es", "name": "Other (Spain)"},
    ],
    "NL": [
        {"code": "zvw", "name": "Basisverzekering (Mandatory)"},
        {"code": "cz", "name": "CZ"},
        {"code": "vgz", "name": "VGZ"},
        {"code": "menzis", "name": "Menzis"},
        {"code": "zilveren_kruis", "name": "Zilveren Kruis"},
        {"code": "other_nl", "name": "Other (Netherlands)"},
    ],
    "SE": [
        {"code": "forsakringskassan", "name": "Försäkringskassan (Public)"},
        {"code": "skandia", "name": "Skandia"},
        {"code": "folksam", "name": "Folksam"},
        {"code": "other_se", "name": "Other (Sweden)"},
    ],
    "PT": [
        {"code": "sns_pt", "name": "SNS (Serviço Nacional de Saúde)"},
        {"code": "multicare", "name": "Multicare"},
        {"code": "medis", "name": "Médis"},
        {"code": "other_pt", "name": "Other (Portugal)"},
    ],
    "BE": [
        {"code": "mutualite", "name": "Mutualité / Ziekenfonds"},
        {"code": "cm", "name": "CM / MC"},
        {"code": "other_be", "name": "Other (Belgium)"},
    ],
    "AT": [
        {"code": "oegk", "name": "ÖGK (Austrian Health Insurance)"},
        {"code": "svs", "name": "SVS"},
        {"code": "other_at", "name": "Other (Austria)"},
    ],
    "CH": [
        {"code": "lamal", "name": "LAMal (Mandatory Basic)"},
        {"code": "css", "name": "CSS"},
        {"code": "helsana", "name": "Helsana"},
        {"code": "swica", "name": "SWICA"},
        {"code": "other_ch", "name": "Other (Switzerland)"},
    ],
    "IE": [
        {"code": "hse", "name": "HSE (Public Health)"},
        {"code": "vhi", "name": "VHI Healthcare"},
        {"code": "laya", "name": "Laya Healthcare"},
        {"code": "irish_life", "name": "Irish Life Health"},
        {"code": "other_ie", "name": "Other (Ireland)"},
    ],
    "PL": [
        {"code": "nfz", "name": "NFZ (National Health Fund)"},
        {"code": "luxmed", "name": "LuxMed"},
        {"code": "medicover_pl", "name": "Medicover"},
        {"code": "other_pl", "name": "Other (Poland)"},
    ],
    "GR": [
        {"code": "eopyy", "name": "EOPYY (National Health System)"},
        {"code": "other_gr", "name": "Other (Greece)"},
    ],

    # ── India ──────────────────────────────────
    "IN": [
        {"code": "ab_pmjay", "name": "Ayushman Bharat (PM-JAY)"},
        {"code": "cghs", "name": "CGHS"},
        {"code": "esis", "name": "ESIS (Employee State Insurance)"},
        {"code": "star_health", "name": "Star Health Insurance"},
        {"code": "niva_bupa", "name": "Niva Bupa (Max Bupa)"},
        {"code": "hdfc_ergo", "name": "HDFC ERGO"},
        {"code": "icici_lombard", "name": "ICICI Lombard"},
        {"code": "bajaj_allianz", "name": "Bajaj Allianz"},
        {"code": "new_india", "name": "New India Assurance"},
        {"code": "lic_health", "name": "LIC Health"},
        {"code": "other_in", "name": "Other (India)"},
    ],

    # ── Africa ─────────────────────────────────
    "NG": [
        {"code": "nhis_ng", "name": "NHIS (National Health Insurance)"},
        {"code": "hmo_ng", "name": "HMO Provider"},
        {"code": "leadway", "name": "Leadway Health"},
        {"code": "hygeia", "name": "Hygeia HMO"},
        {"code": "other_ng", "name": "Other (Nigeria)"},
    ],
    "ZA": [
        {"code": "discovery", "name": "Discovery Health"},
        {"code": "bonitas", "name": "Bonitas"},
        {"code": "medshield", "name": "Medshield"},
        {"code": "gems", "name": "GEMS (Government Employees)"},
        {"code": "momentum", "name": "Momentum Health"},
        {"code": "other_za", "name": "Other (South Africa)"},
    ],
    "GH": [
        {"code": "nhis_gh", "name": "NHIS (National Health Insurance)"},
        {"code": "acacia", "name": "Acacia Health"},
        {"code": "other_gh", "name": "Other (Ghana)"},
    ],
    "KE": [
        {"code": "nhif_ke", "name": "NHIF (National Hospital Insurance Fund)"},
        {"code": "sha_ke", "name": "SHA (Social Health Authority)"},
        {"code": "jubilee_ke", "name": "Jubilee Health Insurance"},
        {"code": "aar_ke", "name": "AAR Insurance"},
        {"code": "other_ke", "name": "Other (Kenya)"},
    ],
    "ET": [
        {"code": "cbhi_et", "name": "CBHI (Community-Based Health Insurance)"},
        {"code": "other_et", "name": "Other (Ethiopia)"},
    ],
    "TZ": [
        {"code": "nhif_tz", "name": "NHIF Tanzania"},
        {"code": "other_tz", "name": "Other (Tanzania)"},
    ],
    "EG": [
        {"code": "uhi_eg", "name": "UHI (Universal Health Insurance)"},
        {"code": "other_eg", "name": "Other (Egypt)"},
    ],
    "RW": [
        {"code": "mutuelle", "name": "Mutuelle de Santé"},
        {"code": "rssb_rw", "name": "RSSB"},
        {"code": "other_rw", "name": "Other (Rwanda)"},
    ],
    "SN": [
        {"code": "cmu_sn", "name": "CMU (Couverture Maladie Universelle)"},
        {"code": "other_sn", "name": "Other (Senegal)"},
    ],
    "CI": [
        {"code": "cmu_ci", "name": "CMU (Côte d'Ivoire)"},
        {"code": "other_ci", "name": "Other (Côte d'Ivoire)"},
    ],
    "ML": [
        {"code": "amo_ml", "name": "AMO (Assurance Maladie Obligatoire)"},
        {"code": "ramed_ml", "name": "RAMED"},
        {"code": "other_ml", "name": "Other (Mali)"},
    ],

    # ── Middle East ────────────────────────────
    "AE": [
        {"code": "dha", "name": "DHA (Dubai Health Authority)"},
        {"code": "haad", "name": "HAAD / DoH Abu Dhabi"},
        {"code": "daman", "name": "Daman (National Health Insurance)"},
        {"code": "oman_ins_ae", "name": "Oman Insurance"},
        {"code": "adnic", "name": "ADNIC"},
        {"code": "other_ae", "name": "Other (UAE)"},
    ],
    "SA": [
        {"code": "cchi", "name": "CCHI (Council for Cooperative Health Insurance)"},
        {"code": "bupa_sa", "name": "Bupa Arabia"},
        {"code": "medgulf", "name": "MedGulf"},
        {"code": "tawuniya", "name": "Tawuniya"},
        {"code": "other_sa", "name": "Other (Saudi Arabia)"},
    ],
    "QA": [
        {"code": "nhis_qa", "name": "NHIS (Qatar)"},
        {"code": "ql_health", "name": "QLM Life & Medical Insurance"},
        {"code": "other_qa", "name": "Other (Qatar)"},
    ],
    "KW": [
        {"code": "moh_kw", "name": "MOH (Ministry of Health Kuwait)"},
        {"code": "other_kw", "name": "Other (Kuwait)"},
    ],
    "BH": [
        {"code": "nhra_bh", "name": "NHRA (National Health Regulatory Authority)"},
        {"code": "other_bh", "name": "Other (Bahrain)"},
    ],
    "JO": [
        {"code": "rms_jo", "name": "Royal Medical Services"},
        {"code": "moh_jo", "name": "MOH Insurance (Jordan)"},
        {"code": "other_jo", "name": "Other (Jordan)"},
    ],
    "LB": [
        {"code": "nssf_lb", "name": "NSSF (National Social Security Fund)"},
        {"code": "other_lb", "name": "Other (Lebanon)"},
    ],
    "IL": [
        {"code": "clalit", "name": "Clalit Health Services"},
        {"code": "maccabi", "name": "Maccabi Healthcare Services"},
        {"code": "meuhedet", "name": "Meuhedet"},
        {"code": "leumit", "name": "Leumit Health Services"},
        {"code": "other_il", "name": "Other (Israel)"},
    ],
    "TR": [
        {"code": "sgk", "name": "SGK (Social Security Institution)"},
        {"code": "other_tr", "name": "Other (Turkey)"},
    ],
}

COUNTRIES_BY_REGION: dict[str, list[dict[str, str]]] = {
    "north_america": [
        {"code": "US", "name": "United States"},
        {"code": "CA", "name": "Canada"},
        {"code": "MX", "name": "Mexico"},
    ],
    "europe": [
        {"code": "GB", "name": "United Kingdom"},
        {"code": "DE", "name": "Germany"},
        {"code": "FR", "name": "France"},
        {"code": "IT", "name": "Italy"},
        {"code": "ES", "name": "Spain"},
        {"code": "NL", "name": "Netherlands"},
        {"code": "SE", "name": "Sweden"},
        {"code": "PT", "name": "Portugal"},
        {"code": "BE", "name": "Belgium"},
        {"code": "AT", "name": "Austria"},
        {"code": "CH", "name": "Switzerland"},
        {"code": "IE", "name": "Ireland"},
        {"code": "PL", "name": "Poland"},
        {"code": "GR", "name": "Greece"},
    ],
    "south_asia": [
        {"code": "IN", "name": "India"},
    ],
    "africa": [
        {"code": "NG", "name": "Nigeria"},
        {"code": "ZA", "name": "South Africa"},
        {"code": "GH", "name": "Ghana"},
        {"code": "KE", "name": "Kenya"},
        {"code": "ET", "name": "Ethiopia"},
        {"code": "TZ", "name": "Tanzania"},
        {"code": "EG", "name": "Egypt"},
        {"code": "RW", "name": "Rwanda"},
        {"code": "SN", "name": "Senegal"},
        {"code": "CI", "name": "Côte d'Ivoire"},
        {"code": "ML", "name": "Mali"},
    ],
    "middle_east": [
        {"code": "AE", "name": "United Arab Emirates"},
        {"code": "SA", "name": "Saudi Arabia"},
        {"code": "QA", "name": "Qatar"},
        {"code": "KW", "name": "Kuwait"},
        {"code": "BH", "name": "Bahrain"},
        {"code": "JO", "name": "Jordan"},
        {"code": "LB", "name": "Lebanon"},
        {"code": "IL", "name": "Israel"},
        {"code": "TR", "name": "Turkey"},
    ],
}


# ──────────────────────────────────────────────
# SQLAlchemy ORM model
# ──────────────────────────────────────────────

class Insurance(Base):
    """A single insurance plan belonging to a user.  Users may have multiple."""
    __tablename__ = "insurances"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Location / locale
    region: Mapped[str] = mapped_column(String(50), nullable=False)          # InsuranceRegion value
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)    # ISO 3166-1 alpha-2
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Provider details
    provider_code: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "medicare", "nhs"
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)  # human-readable

    # Policy details
    policy_number: Mapped[str | None] = mapped_column(String(100))
    group_number: Mapped[str | None] = mapped_column(String(100))
    member_id: Mapped[str | None] = mapped_column(String(100))
    plan_name: Mapped[str | None] = mapped_column(String(255))
    plan_type: Mapped[str | None] = mapped_column(String(100))  # e.g. HMO, PPO, EPO, POS

    # Coverage
    coverage_start: Mapped[date | None] = mapped_column(Date)
    coverage_end: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Contact
    subscriber_name: Mapped[str | None] = mapped_column(String(255))
    subscriber_relationship: Mapped[str | None] = mapped_column(String(50))  # self, spouse, child, other
    insurance_phone: Mapped[str | None] = mapped_column(String(50))

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="insurances")
