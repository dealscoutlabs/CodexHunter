from __future__ import annotations

from dataclasses import asdict
from typing import Dict

from .agents import ClinicalDiligenceAgent, CommercialDiligenceAgent, DealDiligenceAgent, IPExclusivityAgent, RedFlagAgent, RegulatoryDiligenceAgent
from .models import Asset, DiligenceMemo, Score, now_iso


class MemoGenerator:
    def __init__(self) -> None:
        self.agents = {
            "clinical": ClinicalDiligenceAgent(),
            "regulatory": RegulatoryDiligenceAgent(),
            "ip_exclusivity": IPExclusivityAgent(),
            "commercial": CommercialDiligenceAgent(),
            "deal": DealDiligenceAgent(),
            "red_flags": RedFlagAgent(),
        }

    def generate(self, asset: Asset, score: Score) -> DiligenceMemo:
        sections: Dict[str, dict] = {name: agent.run(asset) for name, agent in self.agents.items()}
        red_flags = sections["red_flags"]["fatal_red_flags"]
        open_questions = (
            sections["regulatory"]["fda_questions"]
            + sections["ip_exclusivity"]["missing"]
            + sections["red_flags"]["diligence_questions"]
        )
        citations = [f"- [{e.title}]({e.url}) ({e.evidence_type}, confidence {e.confidence})" for e in asset.evidence]
        markdown = f"""# Fortress DealScout Diligence Memo: {asset.generic_name}

## Executive Summary
{asset.generic_name} is classified as **{score.rating} / {score.recommendation}** with a transparent score of **{score.total_score}/100**. This memo is generated from MVP seed/public-source style records and is not medical, legal, patent, regulatory, or investment advice.

## Asset Snapshot
- Indication: {asset.indication}
- Therapeutic area: {asset.therapeutic_area}
- Stage/status: {asset.development_stage}; {asset.asset_status}
- Owner: {asset.current_owner}
- Last known activity: {asset.last_known_activity_date}
- License status: {asset.license_status}

## Why This May Be Mispriced
{score.mispricing_score.rationale}

## Evidence Package
{chr(10).join(citations)}

## Clinical Read
{sections["clinical"]["endpoint_quality"]} Safety: {sections["clinical"]["safety_issues"]}

## Regulatory Path
Possible pathways: {", ".join(sections["regulatory"]["possible_pathways"])}. {sections["regulatory"]["uncertainty"]}

## IP / Exclusivity
{sections["ip_exclusivity"]["sufficiency_estimate"]} Needs verification.

## Commercial Opportunity
{sections["commercial"]["unmet_need"]} Buyer types: {", ".join(sections["commercial"]["buyer_universe"])}.

## Competitive Landscape
{sections["commercial"]["crowding"]}

## Buyer Universe
{", ".join(sections["commercial"]["buyer_universe"])}

## Proposed Deal Structure
{", ".join(sections["deal"]["deal_structures"])}

## Red Flags
{chr(10).join(f"- {x}" for x in red_flags) if red_flags else "- No fatal red flag captured in MVP data. Needs verification."}

## Open Questions
{chr(10).join(f"- {x}" for x in open_questions)}

## Recommendation
{score.rationale}

## Source List
{chr(10).join(citations)}
"""
        memo_json = {"asset": asdict(asset), "score": asdict(score), "sections": sections, "source_policy": "Unsupported claims must be marked Needs verification."}
        coverage = min(100, round(len(asset.evidence) * 18 + asset.source_confidence * 40))
        return DiligenceMemo(asset.id, markdown, memo_json, now_iso(), coverage, open_questions, red_flags)
