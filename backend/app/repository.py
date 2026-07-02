from __future__ import annotations

import csv
import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

from .models import Asset, Evidence, PatentExclusivity, Trial, now_iso
from .seed_data import seed_assets

DB_PATH = Path(os.getenv("CODEXHUNTER_DB_PATH") or os.getenv("DEALSCOUT_DB_PATH") or Path(__file__).resolve().parents[1] / "data" / "codexhunter.sqlite3")


class AssetRepository:
    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self) -> None:
        self.conn.execute(
            """
            create table if not exists assets (
              id text primary key,
              payload text not null,
              created_at text not null,
              updated_at text not null
            )
            """
        )
        self.conn.commit()

    def seed(self, replace: bool = False) -> None:
        if replace:
            self.conn.execute("delete from assets")
        if self.count() == 0:
            self.upsert_many(seed_assets())

    def count(self) -> int:
        return int(self.conn.execute("select count(*) from assets").fetchone()[0])

    def delete_non_real_assets(self) -> int:
        deleted = 0
        for asset in self.list_assets():
            if "real_data" in asset.tags or any("clinicaltrials.gov/study/NCT" in evidence.url for evidence in asset.evidence):
                continue
            self.conn.execute("delete from assets where id = ?", (asset.id,))
            deleted += 1
        self.conn.commit()
        return deleted

    def delete_assets_failing_basic_rules(self) -> int:
        deleted = 0
        for asset in self.list_assets():
            tags = set(asset.tags)
            has_availability = bool(tags & {"availability_signal", "licensable_signal"})
            has_human_efficacy = "human_efficacy_data" in tags
            if has_availability and has_human_efficacy:
                continue
            self.conn.execute("delete from assets where id = ?", (asset.id,))
            deleted += 1
        self.conn.commit()
        return deleted

    def upsert_many(self, assets: Iterable[Asset]) -> None:
        for asset in assets:
            self.upsert(asset)
        self.conn.commit()

    def upsert(self, asset: Asset) -> None:
        payload = json.dumps(asdict(asset))
        self.conn.execute(
            "insert into assets (id, payload, created_at, updated_at) values (?, ?, ?, ?) on conflict(id) do update set payload=excluded.payload, updated_at=excluded.updated_at",
            (asset.id, payload, asset.created_at, asset.updated_at),
        )

    def list_assets(self) -> List[Asset]:
        return [self._hydrate(row["payload"]) for row in self.conn.execute("select payload from assets order by id")]

    def get(self, asset_id: str) -> Optional[Asset]:
        row = self.conn.execute("select payload from assets where id = ?", (asset_id,)).fetchone()
        return self._hydrate(row["payload"]) if row else None

    def import_csv(self, path: Path | str) -> int:
        now = now_iso()
        created = 0
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                asset_id = row.get("id") or row.get("generic_name", "manual").lower().replace(" ", "-")
                asset = Asset(
                    id=asset_id,
                    generic_name=row.get("generic_name", asset_id),
                    brand_names=[x.strip() for x in row.get("brand_names", "").split(";") if x.strip()],
                    aliases=[x.strip() for x in row.get("aliases", "").split(";") if x.strip()],
                    modality=row.get("modality", "unknown"),
                    mechanism_of_action=row.get("mechanism_of_action", "Needs verification"),
                    target=row.get("target", "Needs verification"),
                    indication=row.get("indication", "Needs verification"),
                    therapeutic_area=row.get("therapeutic_area", "Needs verification"),
                    development_stage=row.get("development_stage", "unknown"),
                    regulatory_status=row.get("regulatory_status", "Needs verification"),
                    foreign_approval_status=row.get("foreign_approval_status", "Unknown"),
                    current_owner=row.get("current_owner", "Unknown"),
                    original_inventor_or_institution=row.get("original_inventor_or_institution", "Unknown"),
                    license_status=row.get("license_status", "Unknown"),
                    asset_status=row.get("asset_status", "unknown"),
                    last_known_activity_date=row.get("last_known_activity_date", "1900-01-01"),
                    source_confidence=float(row.get("source_confidence", "0.25") or 0.25),
                    created_at=now,
                    updated_at=now,
                    tags=[x.strip() for x in row.get("tags", "").split(";") if x.strip()],
                    assumptions=["Manual CSV upload; user must verify source-backed facts."],
                )
                asset.evidence = [
                    Evidence(
                        id=f"{asset.id}-manual-1",
                        asset_id=asset.id,
                        evidence_type="other",
                        title=row.get("source_title", "Manual CSV upload"),
                        summary=row.get("source_summary", "Needs verification."),
                        url=row.get("source_url", "Needs verification"),
                        source_name="Manual CSV",
                        date=now[:10],
                        extracted_facts={"needs_verification": True},
                        confidence=asset.source_confidence,
                    )
                ]
                self.upsert(asset)
                created += 1
        self.conn.commit()
        return created

    def _hydrate(self, payload: str) -> Asset:
        data = json.loads(payload)
        return self._hydrate_asset_from_dict(data)

    def _hydrate_asset_from_dict(self, data: dict) -> Asset:
        data["evidence"] = [Evidence(**item) for item in data.get("evidence", [])]
        data["trials"] = [Trial(**item) for item in data.get("trials", [])]
        data["patents"] = [PatentExclusivity(**item) for item in data.get("patents", [])]
        return Asset(**data)
