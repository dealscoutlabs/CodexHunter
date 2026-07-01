from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:  # Allows domain tests without installed web dependencies.
    FastAPI = None
    File = None
    HTTPException = Exception
    UploadFile = object
    CORSMiddleware = None

from .connectors import ClinicalTrialsConnector, MockClinicalTrialsConnector, connector_status
from .memo import MemoGenerator
from .repository import AssetRepository
from .scoring import ScoringEngine
from .sourcing import SourcingEngine

repo = AssetRepository()
repo.seed()
scorer = ScoringEngine()
memos = MemoGenerator()
sourcing = SourcingEngine(scorer=scorer)


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Run: python3 -m pip install -r backend/requirements.txt")
    app = FastAPI(title="CodexHunter API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health():
        return {"ok": True, "asset_count": repo.count()}

    @app.get("/assets")
    def list_assets(score_min: int = 0, recommendation: str = "", therapeutic_area: str = "", asset_status: str = ""):
        rows = []
        for asset in repo.list_assets():
            score = scorer.score_asset(asset)
            if score.total_score < score_min:
                continue
            if recommendation and score.recommendation != recommendation:
                continue
            if therapeutic_area and therapeutic_area.lower() not in asset.therapeutic_area.lower():
                continue
            if asset_status and asset.asset_status != asset_status:
                continue
            rows.append({"asset": asdict(asset), "score": asdict(score)})
        return rows

    @app.get("/assets/{asset_id}")
    def asset_detail(asset_id: str):
        asset = repo.get(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        score = scorer.score_asset(asset)
        return {"asset": asdict(asset), "score": asdict(score)}

    @app.get("/assets/{asset_id}/score")
    def score(asset_id: str):
        asset = repo.get(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        return asdict(scorer.score_asset(asset))

    @app.get("/assets/{asset_id}/memo")
    def memo(asset_id: str):
        asset = repo.get(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        score = scorer.score_asset(asset)
        return asdict(memos.generate(asset, score))

    @app.post("/upload-csv")
    async def upload_csv(file: UploadFile = File(...)):
        suffix = Path(file.filename or "upload.csv").suffix or ".csv"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as fh:
            fh.write(await file.read())
            tmp_path = fh.name
        imported = repo.import_csv(tmp_path)
        return {"imported": imported, "asset_count": repo.count()}

    @app.post("/connectors/clinicaltrials/mock")
    def ingest_clinicaltrials(query: str):
        connector = MockClinicalTrialsConnector()
        assets = connector.ingest(query)
        repo.upsert_many(assets)
        return {"imported": len(assets), "assets": [asdict(a) for a in assets]}

    @app.post("/connectors/clinicaltrials/ingest")
    def ingest_real_clinicaltrials(query: str = "terminated phase 2 rare disease", page_size: int = 10):
        connector = ClinicalTrialsConnector()
        assets = connector.ingest(query, page_size=page_size)
        repo.upsert_many(assets)
        scored_assets = [{"asset": asdict(asset), "score": asdict(scorer.score_asset(asset))} for asset in assets]
        return {"imported": len(assets), "query": query, "assets": scored_assets, "asset_count": repo.count()}

    @app.get("/sourcing/plays")
    def sourcing_plays():
        return {"plays": sourcing.plays()}

    @app.post("/sourcing/run")
    def run_sourcing_play(play_id: str = "non_safety_terminated", per_query: int = 5):
        try:
            result = sourcing.run_play(play_id, per_query=per_query)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        assets = [repo._hydrate_asset_from_dict(row["asset"]) for row in result["assets"]]
        repo.upsert_many(assets)
        return {**result, "asset_count": repo.count()}

    @app.get("/connectors")
    def connectors():
        return connector_status()

    return app


app = create_app() if FastAPI is not None else None
