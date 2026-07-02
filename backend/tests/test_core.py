import tempfile
import unittest
from pathlib import Path

from app.memo import MemoGenerator
from app.connectors import ClinicalTrialsConnector
from app.repository import AssetRepository
from app.scoring import ScoringEngine
from app.seed_data import seed_assets
from app.sourcing import SourcingEngine


class DealScoutCoreTests(unittest.TestCase):
    def test_seed_data_has_required_assets_and_sources(self):
        assets = seed_assets()
        self.assertGreaterEqual(len(assets), 10)
        for asset in assets:
            self.assertGreaterEqual(len(asset.evidence), 1)
            for evidence in asset.evidence:
                self.assertTrue(evidence.url)

    def test_scoring_is_transparent_and_classifies(self):
        asset = seed_assets()[0]
        score = ScoringEngine().score_asset(asset)
        self.assertGreaterEqual(score.total_score, 0)
        self.assertLessEqual(score.total_score, 100)
        self.assertTrue(score.human_evidence_score.rationale)
        self.assertTrue(score.human_evidence_score.supporting_sources)
        self.assertIn(score.recommendation, {"pursue", "monitor", "needs_review", "pass"})

    def test_memo_contains_needs_verification_and_sources(self):
        asset = seed_assets()[0]
        score = ScoringEngine().score_asset(asset)
        memo = MemoGenerator().generate(asset, score)
        self.assertIn("Needs verification", memo.memo_markdown)
        self.assertIn(asset.evidence[0].url, memo.memo_markdown)

    def test_repository_seed_and_csv_import(self):
        with tempfile.TemporaryDirectory() as td:
            repo = AssetRepository(Path(td) / "test.sqlite3")
            repo.seed()
            self.assertGreaterEqual(repo.count(), 10)
            csv_path = Path(td) / "assets.csv"
            csv_path.write_text("id,generic_name,indication,therapeutic_area,development_stage,current_owner,asset_status,source_url\nmanual-1,Manual Asset,Rare fever,Rare disease,Phase 1,ManualCo,dormant,https://example.com/manual\n", encoding="utf-8")
            imported = repo.import_csv(csv_path)
            self.assertEqual(imported, 1)
            self.assertIsNotNone(repo.get("manual-1"))

    def test_repository_can_delete_non_real_assets(self):
        with tempfile.TemporaryDirectory() as td:
            repo = AssetRepository(Path(td) / "test.sqlite3")
            repo.seed()
            self.assertGreaterEqual(repo.count(), 10)
            deleted = repo.delete_non_real_assets()
            self.assertGreaterEqual(deleted, 10)
            self.assertEqual(repo.count(), 0)

    def test_clinicaltrials_parser_creates_source_backed_asset(self):
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT12345678", "briefTitle": "A Phase 2 Test of RealDrug"},
                "statusModule": {
                    "overallStatus": "TERMINATED",
                    "whyStopped": "Business decision unrelated to safety",
                    "lastUpdatePostDateStruct": {"date": "2022-01-15"},
                    "completionDateStruct": {"date": "2021-12-01"},
                },
                "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Sponsor", "class": "INDUSTRY"}},
                "conditionsModule": {"conditions": ["Rare Disease"]},
                "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 42}},
                "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "RealDrug", "otherNames": ["RD-1"]}]},
                "outcomesModule": {"primaryOutcomes": [{"measure": "Change in functional score"}]},
                "descriptionModule": {"briefSummary": "A rare disease study."},
            },
            "hasResults": True,
            "resultsSection": {
                "outcomeMeasuresModule": {
                    "outcomeMeasures": [
                        {"type": "PRIMARY", "title": "Change in functional score", "description": "Human efficacy outcome posted."}
                    ]
                }
            },
        }
        asset = ClinicalTrialsConnector()._study_to_asset(study)
        self.assertEqual(asset.id, "ctgov-nct12345678")
        self.assertEqual(asset.generic_name, "RealDrug")
        self.assertIn("real_data", asset.tags)
        self.assertIn("clinicaltrials", asset.tags)
        self.assertIn("availability_signal", asset.tags)
        self.assertIn("human_efficacy_data", asset.tags)
        self.assertEqual(asset.evidence[0].url, "https://clinicaltrials.gov/study/NCT12345678")
        self.assertEqual(asset.trials[0].nct_id, "NCT12345678")

    def test_clinicaltrials_basic_rules_reject_records_without_efficacy_results(self):
        study = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Safety Only Study"},
                "statusModule": {
                    "overallStatus": "TERMINATED",
                    "lastUpdatePostDateStruct": {"date": "2022-01-15"},
                },
                "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Sponsor", "class": "INDUSTRY"}},
                "conditionsModule": {"conditions": ["Rare Disease"]},
                "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 20}},
                "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "SafetyDrug"}]},
                "outcomesModule": {"primaryOutcomes": [{"measure": "Dose limiting toxicity"}]},
                "descriptionModule": {"briefSummary": "A rare disease study."},
            },
            "hasResults": True,
            "resultsSection": {
                "outcomeMeasuresModule": {
                    "outcomeMeasures": [
                        {"type": "PRIMARY", "title": "Dose Limiting Toxicity", "description": "Safety endpoint."}
                    ]
                }
            },
        }
        asset = ClinicalTrialsConnector()._study_to_asset(study)
        self.assertIn("availability_signal", asset.tags)
        self.assertNotIn("human_efficacy_data", asset.tags)
        self.assertFalse(ClinicalTrialsConnector.passes_basic_rules(asset))

    def test_clinicaltrials_basic_rules_reject_placebo_assets(self):
        asset = seed_assets()[0]
        asset.generic_name = "Placebo"
        asset.tags = ["real_data", "clinicaltrials", "availability_signal", "human_efficacy_data"]
        self.assertFalse(ClinicalTrialsConnector.passes_basic_rules(asset))

    def test_sourcing_engine_dedupes_and_scores_candidates(self):
        class FakeConnector:
            def ingest(self, query, page_size=5):
                asset = seed_assets()[0]
                asset.id = "same-real-asset"
                asset.tags = ["real_data", "clinicaltrials", "availability_signal", "human_efficacy_data"]
                return [asset]

        result = SourcingEngine(connector=FakeConnector()).run_queries(["one", "two"], per_query=1)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["assets"][0]["asset"]["id"], "same-real-asset")
        self.assertIn("sourcing_candidate", result["assets"][0]["asset"]["tags"])
        self.assertIn("total_score", result["assets"][0]["score"])


if __name__ == "__main__":
    unittest.main()
