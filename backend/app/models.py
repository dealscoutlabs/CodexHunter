from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class SourceRef:
    title: str
    url: str
    source_type: str
    date_accessed: str
    quote_or_paraphrase: str
    confidence: float = 0.5


@dataclass
class Evidence:
    id: str
    asset_id: str
    evidence_type: str
    title: str
    summary: str
    url: str
    source_name: str
    date: str
    extracted_facts: Dict[str, Any]
    confidence: float


@dataclass
class Trial:
    asset_id: str
    nct_id: str
    phase: str
    status: str
    sponsor: str
    collaborators: List[str]
    enrollment: Optional[int]
    start_date: str
    completion_date: str
    primary_completion_date: str
    indication: str
    endpoints: List[str]
    outcome_summary: str
    adverse_events_summary: str
    url: str


@dataclass
class Company:
    id: str
    name: str
    ticker: str
    market_cap: Optional[float]
    cash: Optional[float]
    enterprise_value: Optional[float]
    pipeline_assets: List[str]
    source_urls: List[str]


@dataclass
class PatentExclusivity:
    asset_id: str
    patent_number: str
    title: str
    owner: str
    expiration_date: str
    claim_type: str
    orange_book_listed: bool
    orphan_exclusivity: bool
    data_exclusivity: bool
    pediatric_exclusivity: bool
    notes: str
    confidence: float


@dataclass
class Asset:
    id: str
    generic_name: str
    brand_names: List[str]
    aliases: List[str]
    modality: str
    mechanism_of_action: str
    target: str
    indication: str
    therapeutic_area: str
    development_stage: str
    regulatory_status: str
    foreign_approval_status: str
    current_owner: str
    original_inventor_or_institution: str
    license_status: str
    asset_status: str
    last_known_activity_date: str
    source_confidence: float
    created_at: str
    updated_at: str
    evidence: List[Evidence] = field(default_factory=list)
    trials: List[Trial] = field(default_factory=list)
    patents: List[PatentExclusivity] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)


@dataclass
class SubScore:
    score: int
    rationale: str
    supporting_sources: List[str]
    missing_information: List[str]
    confidence: float


@dataclass
class Score:
    asset_id: str
    total_score: int
    human_evidence_score: SubScore
    regulatory_path_score: SubScore
    cost_to_inflection_score: SubScore
    dealability_score: SubScore
    exclusivity_score: SubScore
    buyer_universe_score: SubScore
    competition_score: SubScore
    safety_risk_score: SubScore
    cmc_risk_score: SubScore
    commercial_score: SubScore
    mispricing_score: SubScore
    red_flag_score: SubScore
    recommendation: str
    rating: str
    rationale: str


@dataclass
class DiligenceMemo:
    asset_id: str
    memo_markdown: str
    memo_json: Dict[str, Any]
    generated_at: str
    source_coverage_score: int
    open_questions: List[str]
    red_flags: List[str]


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
