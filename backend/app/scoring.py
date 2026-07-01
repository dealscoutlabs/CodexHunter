from __future__ import annotations

from datetime import date
from typing import Callable, Dict, List

from .models import Asset, Score, SubScore, parse_date

WEIGHTS = {
    "human_evidence_score": 0.20,
    "regulatory_path_score": 0.15,
    "cost_to_inflection_score": 0.12,
    "dealability_score": 0.12,
    "exclusivity_score": 0.12,
    "buyer_universe_score": 0.10,
    "commercial_score": 0.08,
    "competition_score": 0.05,
    "cmc_risk_score": 0.03,
    "mispricing_score": 0.03,
}


def sources(asset: Asset) -> List[str]:
    return [e.url for e in asset.evidence if e.url] or ["Needs verification"]


def sub(score: int, rationale: str, asset: Asset, missing: List[str] | None = None, confidence: float | None = None) -> SubScore:
    return SubScore(
        score=max(0, min(100, int(score))),
        rationale=rationale,
        supporting_sources=sources(asset),
        missing_information=missing or [],
        confidence=asset.source_confidence if confidence is None else confidence,
    )


def months_since(value: str, today: date | None = None) -> int:
    parsed = parse_date(value)
    if not parsed:
        return 999
    today = today or date.today()
    return max(0, (today.year - parsed.year) * 12 + today.month - parsed.month)


class ScoringEngine:
    def score_asset(self, asset: Asset) -> Score:
        dormant_months = months_since(asset.last_known_activity_date)
        stage_upper = asset.development_stage.upper().replace(" ", "")
        has_human = any(tag in asset.tags for tag in ["human_data", "foreign_approved", "commercial"]) or "PHASE" in stage_upper
        rare = "rare" in asset.tags or "orphan" in " ".join(asset.tags)
        failed = any(tag in asset.tags for tag in ["failed", "safety_signal"])
        crowded = "crowded" in asset.tags or asset.therapeutic_area.lower() == "oncology"
        cmc_complex = "gene_therapy" in asset.tags or "CMC" in asset.regulatory_status

        subs: Dict[str, SubScore] = {
            "human_evidence_score": sub(82 if has_human else 45, "Human exposure or commercial/foreign-use signal is present." if has_human else "No verified human proof-of-concept in the seed record.", asset, ["Verify trial outcomes and adverse-event tables."]),
            "regulatory_path_score": sub(78 if rare or "505b2" in asset.tags else 55, "Rare-disease, PRV, foreign-data bridge, or 505(b)(2) hypotheses may exist." if rare or "505b2" in asset.tags else "Standard path likely; regulatory leverage is unclear.", asset, ["Confirm pathway with regulatory counsel/FDA interaction history."]),
            "cost_to_inflection_score": sub(74 if "PHASE2" in stage_upper or "commercial" in asset.tags else 48 if "gene_therapy" in asset.tags else 60, "Existing human stage suggests a bounded next inflection study." if "PHASE2" in stage_upper else "Cost to next inflection needs modeling.", asset, ["Estimate trial size, CMC spend, and runway."]),
            "dealability_score": sub(85 if asset.asset_status in ["dormant", "discontinued"] or "large_pharma_noncore" in asset.tags else 55, "Dormant, discontinued, or non-core ownership increases outreach plausibility." if asset.asset_status in ["dormant", "discontinued"] else "Owner willingness to license is not established.", asset, ["Identify decision maker and encumbrances."]),
            "exclusivity_score": sub(55 if rare or "505b2" in asset.tags else 28, "Potential regulatory exclusivity may help, but IP is not yet verified." if rare or "505b2" in asset.tags else "Protectable exclusivity is weak or missing in current data.", asset, ["Patent family, Orange Book, orphan, data, and pediatric exclusivity search."]),
            "buyer_universe_score": sub(72 if rare or "commercial" in asset.tags else 52, "Likely specialty pharma or rare-disease buyer universe exists." if rare else "Buyer universe requires mapping.", asset, ["Comparable acquirers/partners."]),
            "competition_score": sub(25 if crowded else 68, "Crowded market with weak differentiation risk." if crowded else "Competition appears manageable in seed record.", asset, ["Current standard of care and pipeline competitors."]),
            "safety_risk_score": sub(15 if "safety_signal" in asset.tags else 72, "Potential severe safety signal; try to kill the deal first." if "safety_signal" in asset.tags else "No severe safety signal captured in seed data.", asset, ["Verify adverse event tables and discontinuation reasons."]),
            "cmc_risk_score": sub(38 if cmc_complex else 76, "Complex manufacturing or modality-specific CMC risk." if cmc_complex else "CMC complexity appears manageable for MVP scoring.", asset, ["Manufacturing process, comparability, stability."]),
            "commercial_score": sub(70 if rare or "commercial" in asset.tags else 48 if crowded else 60, "Unmet need or specialty commercial fit appears plausible." if rare or "commercial" in asset.tags else "Commercial opportunity is not yet compelling.", asset, ["Prevalence, pricing, payer friction."]),
            "mispricing_score": sub(88 if dormant_months >= 18 or asset.asset_status in ["dormant", "discontinued"] else 48, "Dormancy/non-core status suggests possible neglect and mispricing." if dormant_months >= 18 else "Recent activity reduces neglect signal.", asset, ["Confirm last meaningful owner activity."]),
            "red_flag_score": sub(20 if failed else 72, "Failed/safety/crowding red flags may be fatal." if failed else "No fatal red flag captured; still needs diligence.", asset, ["Termination reason and full safety package."]),
        }

        total = round(sum(subs[key].score * weight for key, weight in WEIGHTS.items()))
        if failed:
            total -= 20
        if subs["exclusivity_score"].score < 35:
            total -= 7
        total = max(0, min(100, total))
        rating, recommendation = self.classify(total)
        rationale = f"{rating} classification: {recommendation}. Score is driven by human evidence, regulatory leverage, dealability, exclusivity, and neglect signals; unsupported claims remain flagged."
        return Score(asset_id=asset.id, total_score=total, recommendation=recommendation, rating=rating, rationale=rationale, **subs)

    @staticmethod
    def classify(score: int) -> tuple[str, str]:
        if score >= 85:
            return "A", "pursue"
        if score >= 70:
            return "B", "monitor"
        if score >= 55:
            return "C", "needs_review"
        if score >= 40:
            return "D", "pass"
        return "F", "pass"
