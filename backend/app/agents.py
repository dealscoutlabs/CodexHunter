from __future__ import annotations

from .models import Asset
from .scoring import months_since


class ClinicalDiligenceAgent:
    def run(self, asset: Asset) -> dict:
        return {
            "trial_history": [f"{t.nct_id}: {t.phase} / {t.status} / enrollment {t.enrollment}" for t in asset.trials],
            "human_proof_of_concept": "human_data" in asset.tags or bool(asset.trials),
            "endpoint_quality": "Exploratory endpoints present; confirm validated endpoints and statistical plan.",
            "safety_issues": "Potential safety signal requires verification." if "safety_signal" in asset.tags else "No severe safety signal captured in MVP data. Needs verification.",
            "trial_inactivity_months": months_since(asset.last_known_activity_date),
        }


class RegulatoryDiligenceAgent:
    def run(self, asset: Asset) -> dict:
        pathways = []
        if "505b2_hypothesis" in asset.tags or "foreign_approved" in asset.tags:
            pathways.extend(["505(b)(2)", "foreign-data bridge"])
        if "rare" in asset.tags or "orphan_potential" in asset.tags:
            pathways.extend(["orphan", "accelerated approval hypothesis", "rare pediatric disease PRV hypothesis"])
        if not pathways:
            pathways.append("standard NDA/BLA")
        return {
            "possible_pathways": sorted(set(pathways)),
            "uncertainty": "All regulatory pathways are hypotheses until counsel/FDA confirmation.",
            "fda_questions": ["Adequacy of human data", "Safety database size", "Endpoint acceptability", "CMC comparability"],
        }


class IPExclusivityAgent:
    def run(self, asset: Asset) -> dict:
        return {
            "known_records": [p.notes for p in asset.patents],
            "sufficiency_estimate": "Potentially sufficient only if patent/regulatory exclusivity can be verified." if any(tag in asset.tags for tag in ["rare", "505b2_hypothesis"]) else "Weak or unknown in MVP data.",
            "missing": ["Patent family search", "Orange Book or Purple Book check", "Orphan/data/pediatric exclusivity"],
        }


class CommercialDiligenceAgent:
    def run(self, asset: Asset) -> dict:
        buyer_types = ["specialty pharma", "rare-disease company"] if "rare" in asset.tags else ["strategic pharma", "focused biotech", "search fund / NewCo"]
        return {
            "indication": asset.indication,
            "unmet_need": "Plausible but not verified; quantify epidemiology and treatment gaps.",
            "buyer_universe": buyer_types,
            "crowding": "Crowded and weak differentiation risk." if "crowded" in asset.tags else "Competitive intensity needs source-backed mapping.",
        }


class DealDiligenceAgent:
    def run(self, asset: Asset) -> dict:
        return {
            "current_owner": asset.current_owner,
            "non_core_signal": asset.asset_status in ["dormant", "discontinued"] or "large_pharma_noncore" in asset.tags,
            "outreach_targets": ["business development", "tech transfer office", "portfolio strategy lead", "asset owner CEO/CBO"],
            "deal_structures": ["low upfront + milestones + royalty", "option-to-license", "asset acquisition", "subsidiary formation", "co-development"],
        }


class RedFlagAgent:
    def run(self, asset: Asset) -> dict:
        fatal = []
        questions = []
        if "safety_signal" in asset.tags:
            fatal.append("Possible severe safety signal.")
        if "failed" in asset.tags:
            fatal.append("Failed clinical program without verified credible explanation.")
        if "crowded" in asset.tags:
            questions.append("Crowded indication with uncertain differentiation.")
        if not asset.patents:
            questions.append("No IP/exclusivity records.")
        questions.extend(asset.assumptions)
        return {"fatal_red_flags": fatal, "diligence_questions": questions}
