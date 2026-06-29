"""Disease surveillance schemas — global map signal + country drill-down."""

from pydantic import BaseModel
from typing import Optional


class DiseaseInfo(BaseModel):
    id: str
    label: str
    icon: str
    category: str
    who_unit: str
    has_cdc: bool


class SourceInfo(BaseModel):
    id: str
    name: str
    full_name: str
    scope: str
    url: Optional[str] = None


class CountrySignal(BaseModel):
    iso2: str
    name: str
    region: Optional[str] = None
    outward: Optional[float] = None        # WHO indicator value
    outward_year: Optional[int] = None
    inward: int = 0                        # ALAFIA patient symptom activity
    level: int = 0                         # 0-4 choropleth bucket (per `view`)
    value_label: Optional[str] = None      # human-readable map tooltip


class GlobalResponse(BaseModel):
    disease: DiseaseInfo
    view: str                              # outward | inward | both
    region: Optional[str] = None
    days: int
    generated_at: str
    countries: list[CountrySignal]
    outward_country_count: int
    inward_total: int
    sources: list[SourceInfo]


class SeriesPoint(BaseModel):
    year: int
    value: float


class SymptomCluster(BaseModel):
    name: str
    count: int


class CountryAlert(BaseModel):
    title: str
    severity: str
    source: str
    disease_name: Optional[str] = None
    issued_date: Optional[str] = None
    source_url: Optional[str] = None


class OutwardDetail(BaseModel):
    value: Optional[float] = None
    year: Optional[int] = None
    unit: str
    source: str
    series: list[SeriesPoint] = []


class CdcUsDetail(BaseModel):
    total: float
    year: Optional[int] = None
    week: Optional[int] = None
    states: dict[str, float] = {}


class InwardDetail(BaseModel):
    report_count: int = 0
    affected: int = 0
    symptom_log_count: int = 0
    clusters: list[SymptomCluster] = []


class CountryDetail(BaseModel):
    iso2: str
    name: str
    region: Optional[str] = None
    disease: DiseaseInfo
    days: int
    outward: OutwardDetail
    cdc_us: Optional[CdcUsDetail] = None
    alerts: list[CountryAlert] = []
    inward: InwardDetail
