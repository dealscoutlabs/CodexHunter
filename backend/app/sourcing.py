from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .connectors import ClinicalTrialsConnector
from .models import Asset
from .scoring import ScoringEngine


SOURCING_PLAYS = [
    {
        "id": "dormant_phase2",
        "name": "Dormant Phase 2",
        "description": "Find old human-stage programs with long update gaps and plausible next-inflection studies.",
        "queries": [
            "phase 2 completed rare disease drug",
            "phase 2 completed orphan drug",
            "phase 2 completed investigator drug",
        ],
    },
    {
        "id": "non_safety_terminated",
        "name": "Non-Safety Terminations",
        "description": "Find terminated or withdrawn trials where the public stop reason is not obviously a safety failure.",
        "queries": [
            "terminated phase 2 not safety drug",
            "terminated phase 2 business decision drug",
            "terminated phase 2 insufficient funding drug",
        ],
    },
    {
        "id": "academic_poc",
        "name": "Academic Human PoC",
        "description": "Find investigator-sponsored or university/hospital programs that may be licensable.",
        "queries": [
            "investigator sponsored phase 2 drug rare disease",
            "university phase 2 drug proof of concept",
            "hospital phase 2 drug completed",
        ],
    },
    {
        "id": "rare_orphan",
        "name": "Rare / Orphan",
        "description": "Find rare-disease programs with potential orphan, PRV, or specialty-pharma fit.",
        "queries": [
            "rare disease phase 2 drug completed",
            "orphan phase 2 drug terminated",
            "pediatric rare disease phase 2 drug",
        ],
    },
    {
        "id": "repositioning_505b2",
        "name": "Repositioning / 505(b)(2)",
        "description": "Find known drugs being tested in new indications where bridging or reformulation may matter.",
        "queries": [
            "phase 2 repurposed drug completed",
            "phase 2 reformulation drug completed",
            "approved drug new indication phase 2",
        ],
    },
    {
        "id": "large_owner_noncore",
        "name": "Large-Owner Non-Core",
        "description": "Find programs sponsored by larger pharma or acquired portfolios that may have become non-core.",
        "queries": [
            "phase 2 drug terminated industry",
            "phase 3 terminated business decision drug",
            "completed phase 2 drug industry rare disease",
        ],
    },
]


class SourcingEngine:
    def __init__(self, connector: ClinicalTrialsConnector | None = None, scorer: ScoringEngine | None = None) -> None:
        self.connector = connector or ClinicalTrialsConnector()
        self.scorer = scorer or ScoringEngine()

    def plays(self) -> list[dict]:
        return SOURCING_PLAYS

    def run_play(self, play_id: str, per_query: int = 5) -> dict:
        play = self._find_play(play_id)
        imported = self.run_queries(play["queries"], per_query=per_query)
        return {"play": play, **imported}

    def run_queries(self, queries: Iterable[str], per_query: int = 5) -> dict:
        seen: set[str] = set()
        assets: list[Asset] = []
        failures: list[dict] = []
        for query in queries:
            try:
                for asset in self.connector.ingest(query, page_size=per_query):
                    if asset.id in seen:
                        continue
                    asset.tags = sorted(set(asset.tags + ["sourcing_candidate"]))
                    seen.add(asset.id)
                    assets.append(asset)
            except Exception as exc:
                failures.append({"query": query, "error": str(exc)})
        scored = [{"asset": asdict(asset), "score": asdict(self.scorer.score_asset(asset))} for asset in assets]
        scored.sort(key=lambda row: row["score"]["total_score"], reverse=True)
        return {"imported": len(assets), "assets": scored, "failures": failures}

    @staticmethod
    def _find_play(play_id: str) -> dict:
        for play in SOURCING_PLAYS:
            if play["id"] == play_id:
                return play
        raise ValueError(f"Unknown sourcing play: {play_id}")
