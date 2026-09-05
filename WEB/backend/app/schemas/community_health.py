"""Community Health schemas — alerts, recalls, reports, guidelines, subscriptions."""

from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


# ─── Alert / Recall / Advisory ────────────────────────────────────────

class AlertCreate(BaseModel):
    title: str
    summary: str
    description: Optional[str] = None
    category: str  # pandemic, recall_drug, recall_food, advisory, poison, etc.
    severity: str = "moderate"  # info, low, moderate, high, critical
    source: str  # who, cdc, fda, ema, health_canada, poison_control, etc.
    source_url: Optional[str] = None
    source_reference_id: Optional[str] = None

    affected_countries: Optional[list[str]] = None
    affected_regions: Optional[list[str]] = None
    is_global: bool = False

    issued_date: date
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None

    # Recall fields
    product_name: Optional[str] = None
    product_type: Optional[str] = None
    manufacturer: Optional[str] = None
    lot_numbers: Optional[list[str]] = None
    reason_for_recall: Optional[str] = None
    recall_class: Optional[str] = None

    # Outbreak fields
    disease_name: Optional[str] = None
    pathogen: Optional[str] = None
    confirmed_cases: Optional[int] = None
    deaths: Optional[int] = None

    # Advisory fields
    recommended_actions: Optional[list[str]] = None
    target_population: Optional[list[str]] = None

    tags: Optional[list[str]] = None


class AlertUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    severity: Optional[str] = None
    confirmed_cases: Optional[int] = None
    deaths: Optional[int] = None
    is_active: Optional[bool] = None
    is_resolved: Optional[bool] = None
    resolution_date: Optional[date] = None
    resolution_notes: Optional[str] = None


class AlertResponse(BaseModel):
    id: int
    title: str
    summary: str
    description: Optional[str] = None
    category: str
    severity: str
    source: str
    source_url: Optional[str] = None
    source_reference_id: Optional[str] = None

    affected_countries: Optional[list[str]] = None
    affected_regions: Optional[list[str]] = None
    is_global: bool

    issued_date: date
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None

    product_name: Optional[str] = None
    product_type: Optional[str] = None
    manufacturer: Optional[str] = None
    lot_numbers: Optional[list[str]] = None
    reason_for_recall: Optional[str] = None
    recall_class: Optional[str] = None

    disease_name: Optional[str] = None
    pathogen: Optional[str] = None
    confirmed_cases: Optional[int] = None
    deaths: Optional[int] = None

    recommended_actions: Optional[list[str]] = None
    target_population: Optional[list[str]] = None

    is_active: bool
    is_resolved: bool
    resolution_date: Optional[date] = None
    resolution_notes: Optional[str] = None

    tags: Optional[list[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Community Health Report ──────────────────────────────────────────

class ReportCreate(BaseModel):
    report_type: str  # symptom_cluster, foodborne_illness, poisoning, etc.
    title: str
    description: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    symptoms_reported: Optional[list[str]] = None
    number_affected: Optional[int] = None
    onset_date: Optional[date] = None
    product_involved: Optional[str] = None
    severity: str = "moderate"


class ReportResponse(BaseModel):
    id: int
    user_id: int
    report_type: str
    title: str
    description: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    symptoms_reported: Optional[list[str]] = None
    number_affected: Optional[int] = None
    onset_date: Optional[date] = None
    product_involved: Optional[str] = None
    severity: str
    is_verified: bool
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Health Guidelines ────────────────────────────────────────────────

class GuidelineCreate(BaseModel):
    title: str
    summary: str
    full_text: Optional[str] = None
    category: str  # infection_prevention, vaccination, chronic_disease, etc.
    source: str
    source_url: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[date] = None
    target_population: Optional[list[str]] = None
    applicable_countries: Optional[list[str]] = None
    applicable_conditions: Optional[list[str]] = None
    recommendations: Optional[list[str]] = None
    tags: Optional[list[str]] = None


class GuidelineResponse(BaseModel):
    id: int
    title: str
    summary: str
    full_text: Optional[str] = None
    category: str
    source: str
    source_url: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[date] = None
    superseded_date: Optional[date] = None
    is_current: bool
    target_population: Optional[list[str]] = None
    applicable_countries: Optional[list[str]] = None
    applicable_conditions: Optional[list[str]] = None
    recommendations: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── User Subscription ───────────────────────────────────────────────

class SubscriptionCreate(BaseModel):
    categories: Optional[list[str]] = None
    sources: Optional[list[str]] = None
    countries: Optional[list[str]] = None
    severities: Optional[list[str]] = None
    push_enabled: bool = True
    email_enabled: bool = False
    sms_enabled: bool = False


class SubscriptionResponse(BaseModel):
    id: int
    user_id: int
    categories: Optional[list[str]] = None
    sources: Optional[list[str]] = None
    countries: Optional[list[str]] = None
    severities: Optional[list[str]] = None
    push_enabled: bool
    email_enabled: bool
    sms_enabled: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Dashboard Stats ─────────────────────────────────────────────────

class CommunityDashboardStats(BaseModel):
    """Aggregate stats for the community health dashboard."""
    total_active_alerts: int = 0
    critical_alerts: int = 0
    active_recalls: int = 0
    active_outbreaks: int = 0
    active_advisories: int = 0
    active_poison_alerts: int = 0
    total_guidelines: int = 0
    user_reports_30d: int = 0
    unread_alerts: int = 0
    bookmarked_alerts: int = 0

    # Latest outbreak summary
    latest_outbreaks: list[AlertResponse] = []
    # Latest recalls
    latest_recalls: list[AlertResponse] = []
    # Latest advisories
    latest_advisories: list[AlertResponse] = []

    model_config = {"from_attributes": True}


# ─── Reference Data ──────────────────────────────────────────────────

class AlertCategoryInfo(BaseModel):
    id: str
    name: str
    description: str
    icon: str


class AlertSourceInfo(BaseModel):
    id: str
    name: str
    full_name: str
    url: str
    country: Optional[str] = None
