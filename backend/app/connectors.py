from __future__ import annotations

import json
from datetime import date
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from .models import Asset, Evidence, Trial, now_iso, parse_date


class Connector(Protocol):
    name: str

    def ingest(self, query: str) -> list[Asset]:
        ...


class MockClinicalTrialsConnector:
    name = "clinicaltrials.gov"

    def ingest(self, query: str) -> list[Asset]:
        now = now_iso()
        asset = Asset(
            id=f"ctgov-{query.lower().replace(' ', '-')}",
            generic_name=query,
            brand_names=[],
            aliases=[],
            modality="unknown",
            mechanism_of_action="Needs verification",
            target="Needs verification",
            indication="Needs verification",
            therapeutic_area="Needs verification",
            development_stage="Needs verification",
            regulatory_status="Investigational or unknown",
            foreign_approval_status="Unknown",
            current_owner="Needs verification",
            original_inventor_or_institution="Needs verification",
            license_status="Unknown",
            asset_status="unknown",
            last_known_activity_date=now[:10],
            source_confidence=0.25,
            created_at=now,
            updated_at=now,
            tags=["mock_connector"],
            assumptions=["Mock connector result. Replace with ClinicalTrials.gov API parser."],
        )
        asset.evidence = [Evidence(f"{asset.id}-ctgov", asset.id, "clinical_trial", "ClinicalTrials.gov mock ingestion", "Mock connector placeholder; needs verification.", f"https://clinicaltrials.gov/search?term={query}", "ClinicalTrials.gov", now[:10], {"needs_verification": True}, 0.25)]
        return [asset]


class ClinicalTrialsConnector:
    name = "clinicaltrials.gov"
    base_url = "https://clinicaltrials.gov/api/v2/studies"

    def ingest(self, query: str, page_size: int = 10) -> list[Asset]:
        params = {
            "query.term": query,
            "pageSize": max(1, min(page_size, 50)),
            "format": "json",
        }
        url = f"{self.base_url}?{urlencode(params)}"
        with urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [self._study_to_asset(study) for study in payload.get("studies", [])]

    def _study_to_asset(self, study: dict) -> Asset:
        protocol = study.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        design = protocol.get("designModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        arms = protocol.get("armsInterventionsModule", {})
        outcomes = protocol.get("outcomesModule", {})
        description = protocol.get("descriptionModule", {})
        results = study.get("resultsSection", {})
        derived = study.get("derivedSection", {})

        nct_id = ident.get("nctId", "unknown-nct")
        interventions = arms.get("interventions", [])
        drug_interventions = [item for item in interventions if item.get("type", "").upper() in {"DRUG", "BIOLOGICAL", "GENETIC"}]
        primary_intervention = (drug_interventions or interventions or [{}])[0]
        generic_name = primary_intervention.get("name") or ident.get("briefTitle") or nct_id
        aliases = sorted({name for item in interventions for name in item.get("otherNames", []) if name})
        phases = design.get("phases", []) or ["Not applicable"]
        conditions = conditions_module.get("conditions", [])
        sponsor = sponsor_module.get("leadSponsor", {})
        collaborators = [item.get("name", "") for item in sponsor_module.get("collaborators", []) if item.get("name")]
        last_update = self._date_value(status.get("lastUpdatePostDateStruct") or status.get("lastUpdateSubmitDate"))
        completion = self._date_value(status.get("completionDateStruct"))
        primary_completion = self._date_value(status.get("primaryCompletionDateStruct"))
        start = self._date_value(status.get("startDateStruct"))
        overall_status = status.get("overallStatus", "UNKNOWN")
        why_stopped = status.get("whyStopped", "")
        evidence_url = f"https://clinicaltrials.gov/study/{nct_id}"
        source_date = now_iso()[:10]
        tags = ["real_data", "clinicaltrials"]

        dormant_months = self._months_since(last_update)
        if dormant_months >= 18:
            tags.append("dormant")
        if overall_status in {"TERMINATED", "WITHDRAWN", "SUSPENDED"}:
            tags.append("terminated")
        if why_stopped and "safety" not in why_stopped.lower():
            tags.append("non_safety_stop_reason")
        if any("PHASE2" in phase.replace(" ", "").upper() for phase in phases):
            tags.append("human_data")
        if self._is_rare_record(conditions, description.get("briefSummary", "")):
            tags.extend(["rare", "orphan_potential"])

        outcome_lines = [item.get("measure", "") for item in outcomes.get("primaryOutcomes", []) if item.get("measure")]
        serious_terms = self._serious_event_terms(results)
        asset_status = "discontinued" if overall_status in {"TERMINATED", "WITHDRAWN"} else "dormant" if "dormant" in tags else "active"
        stage = ", ".join(phases)
        summary = self._summary(ident.get("briefTitle", ""), overall_status, why_stopped, completion)
        therapeutic_area = self._therapeutic_area(conditions, derived)
        now = now_iso()

        asset = Asset(
            id=f"ctgov-{nct_id.lower()}",
            generic_name=generic_name,
            brand_names=[],
            aliases=aliases,
            modality=self._modality(primary_intervention.get("type", "")),
            mechanism_of_action="Needs verification",
            target="Needs verification",
            indication=", ".join(conditions) or "Needs verification",
            therapeutic_area=therapeutic_area,
            development_stage=stage,
            regulatory_status=f"ClinicalTrials.gov status: {overall_status}",
            foreign_approval_status="Needs verification",
            current_owner=sponsor.get("name", "Needs verification"),
            original_inventor_or_institution=ident.get("organization", {}).get("fullName", sponsor.get("name", "Needs verification")),
            license_status="Needs verification",
            asset_status=asset_status,
            last_known_activity_date=last_update or completion or primary_completion or start or now[:10],
            source_confidence=0.78,
            created_at=now,
            updated_at=now,
            tags=sorted(set(tags)),
            assumptions=[
                "ClinicalTrials.gov record is real public data, but asset licensability, ownership rights, IP, regulatory pathway, and commercial conclusions need verification.",
                "Drug identity is inferred from trial intervention names and may include combination, comparator, or dosing text.",
            ],
        )
        asset.evidence = [
            Evidence(
                id=f"{asset.id}-trial-record",
                asset_id=asset.id,
                evidence_type="clinical_trial",
                title=ident.get("briefTitle", f"ClinicalTrials.gov record {nct_id}"),
                summary=summary,
                url=evidence_url,
                source_name="ClinicalTrials.gov",
                date=last_update or source_date,
                extracted_facts={
                    "nct_id": nct_id,
                    "overall_status": overall_status,
                    "why_stopped": why_stopped or "Needs verification",
                    "conditions": conditions,
                    "interventions": [item.get("name") for item in interventions if item.get("name")],
                    "source_title": ident.get("briefTitle", f"ClinicalTrials.gov record {nct_id}"),
                    "source_url": evidence_url,
                    "date_accessed": source_date,
                    "source_type": "clinical_trial",
                    "quote_or_paraphrase": summary,
                    "confidence": 0.78,
                },
                confidence=0.78,
            )
        ]
        asset.trials = [
            Trial(
                asset_id=asset.id,
                nct_id=nct_id,
                phase=stage,
                status=overall_status,
                sponsor=sponsor.get("name", "Needs verification"),
                collaborators=collaborators,
                enrollment=(design.get("enrollmentInfo") or {}).get("count"),
                start_date=start or "Needs verification",
                completion_date=completion or "Needs verification",
                primary_completion_date=primary_completion or "Needs verification",
                indication=", ".join(conditions) or "Needs verification",
                endpoints=outcome_lines or ["Needs verification"],
                outcome_summary=self._outcome_summary(outcomes, results),
                adverse_events_summary=", ".join(serious_terms[:8]) if serious_terms else "No adverse event summary parsed from the public record. Needs verification.",
                url=evidence_url,
            )
        ]
        return asset

    @staticmethod
    def _date_value(value: object) -> str:
        if isinstance(value, dict):
            return value.get("date", "")
        if isinstance(value, str):
            return value[:10]
        return ""

    @staticmethod
    def _months_since(value: str) -> int:
        parsed = parse_date(value)
        if not parsed:
            return 999
        today = date.today()
        return max(0, (today.year - parsed.year) * 12 + today.month - parsed.month)

    @staticmethod
    def _is_rare_record(conditions: list[str], summary: str) -> bool:
        text = " ".join(conditions + [summary]).lower()
        rare_terms = ["rare", "orphan", "pediatric", "pulmonary arterial hypertension", "cystic fibrosis", "duchenne", "lysosomal"]
        return any(term in text for term in rare_terms)

    @staticmethod
    def _modality(intervention_type: str) -> str:
        value = intervention_type.upper()
        if value == "BIOLOGICAL":
            return "biologic"
        if value == "GENETIC":
            return "gene therapy"
        if value == "DRUG":
            return "drug"
        return "unknown"

    @staticmethod
    def _therapeutic_area(conditions: list[str], derived: dict) -> str:
        meshes = ((derived.get("conditionBrowseModule") or {}).get("meshes") or [])
        if meshes:
            return meshes[0].get("term", "Needs verification")
        return conditions[0] if conditions else "Needs verification"

    @staticmethod
    def _summary(title: str, status: str, why_stopped: str, completion: str) -> str:
        parts = [f"{title or 'Trial'} is listed as {status} on ClinicalTrials.gov."]
        if completion:
            parts.append(f"Completion date: {completion}.")
        if why_stopped:
            parts.append(f"Why stopped: {why_stopped}")
        return " ".join(parts)

    @staticmethod
    def _outcome_summary(outcomes: dict, results: dict) -> str:
        primary = [item.get("measure", "") for item in outcomes.get("primaryOutcomes", []) if item.get("measure")]
        if primary:
            return "Primary outcomes listed: " + "; ".join(primary[:4])
        if results:
            return "Results section exists; detailed efficacy extraction needs verification."
        return "Outcome results not parsed from public record. Needs verification."

    @staticmethod
    def _serious_event_terms(results: dict) -> list[str]:
        events = (((results.get("adverseEventsModule") or {}).get("seriousEvents")) or [])
        return [event.get("term", "") for event in events if event.get("term")]


CONNECTOR_STUBS = {
    "clinicaltrials": "Implemented real ClinicalTrials.gov API v2 ingestion plus a mock fallback endpoint.",
    "pubmed": "Stub for NCBI E-utilities integration via NCBI_API_KEY optional env var.",
    "openfda": "Stub for labels and approvals via openFDA public endpoints.",
    "sec_edgar": "Stub for EDGAR company filings and pipeline discontinuation extraction.",
    "press_releases": "Stub for generic URL ingestion with allowlisted domains.",
    "university_tech_transfer": "Stub for configured URL list crawl.",
    "manual_csv": "Implemented through /upload-csv.",
}


def connector_status() -> dict:
    return {"connectors": CONNECTOR_STUBS, "source_claim_policy": "Every connector emits source URLs or Needs verification."}
