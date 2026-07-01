import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, ClipboardList, Database, DownloadCloud, FileText, Filter, RefreshCcw, Search, Settings, Star, Upload } from "lucide-react";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

type SubScore = { score: number; rationale: string; supporting_sources: string[]; missing_information: string[]; confidence: number };
type Score = Record<string, unknown> & { total_score: number; recommendation: string; rating: string; rationale: string };
type Asset = {
  id: string;
  generic_name: string;
  brand_names: string[];
  aliases: string[];
  modality: string;
  mechanism_of_action: string;
  target: string;
  indication: string;
  therapeutic_area: string;
  development_stage: string;
  regulatory_status: string;
  foreign_approval_status: string;
  current_owner: string;
  asset_status: string;
  last_known_activity_date: string;
  evidence: { title: string; url: string; evidence_type: string; confidence: number; summary: string }[];
  trials: { nct_id: string; phase: string; status: string; enrollment: number; url: string }[];
  tags: string[];
};
type Row = { asset: Asset; score: Score };
type SourcingPlay = { id: string; name: string; description: string; queries: string[] };

function App() {
  const [rows, setRows] = useState<Row[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [tab, setTab] = useState("overview");
  const [query, setQuery] = useState("");
  const [rec, setRec] = useState("");
  const [scoreMin, setScoreMin] = useState(0);
  const [memo, setMemo] = useState<string>("");
  const [status, setStatus] = useState("Loading assets...");
  const [discoveryQuery, setDiscoveryQuery] = useState("terminated phase 2 rare disease not safety");
  const [discoveryLimit, setDiscoveryLimit] = useState(10);
  const [importedRows, setImportedRows] = useState<Row[]>([]);
  const [plays, setPlays] = useState<SourcingPlay[]>([]);
  const [selectedPlay, setSelectedPlay] = useState("non_safety_terminated");

  async function load() {
    setStatus("Loading assets...");
    const params = new URLSearchParams();
    if (rec) params.set("recommendation", rec);
    if (scoreMin) params.set("score_min", String(scoreMin));
    const res = await fetch(`${API}/assets?${params.toString()}`);
    const data = await res.json();
    setRows(data);
    setSelectedId((id) => id || data[0]?.asset.id || "");
    setStatus(`${data.length} assets loaded`);
  }

  useEffect(() => {
    load().catch((err) => setStatus(`API unavailable: ${err.message}`));
  }, [rec, scoreMin]);

  useEffect(() => {
    fetch(`${API}/sourcing/plays`).then((res) => res.json()).then((data) => setPlays(data.plays || [])).catch(() => setPlays([]));
  }, []);

  const filtered = useMemo(() => {
    const term = query.toLowerCase();
    return rows.filter(({ asset }) => [asset.generic_name, asset.indication, asset.therapeutic_area, asset.current_owner, asset.tags.join(" ")].join(" ").toLowerCase().includes(term));
  }, [rows, query]);
  const selected = rows.find((row) => row.asset.id === selectedId) || filtered[0];

  async function generateMemo(id: string) {
    setTab("memo");
    const res = await fetch(`${API}/assets/${id}/memo`);
    const data = await res.json();
    setMemo(data.memo_markdown);
  }

  async function uploadCsv(file: File) {
    const body = new FormData();
    body.append("file", file);
    const res = await fetch(`${API}/upload-csv`, { method: "POST", body });
    const data = await res.json();
    setStatus(`Imported ${data.imported} CSV assets`);
    await load();
  }

  async function ingestClinicalTrials() {
    setStatus("Importing real ClinicalTrials.gov data...");
    const params = new URLSearchParams({ query: discoveryQuery, page_size: String(discoveryLimit) });
    const res = await fetch(`${API}/connectors/clinicaltrials/ingest?${params.toString()}`, { method: "POST" });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "ClinicalTrials.gov ingestion failed");
    }
    const data = await res.json();
    setImportedRows(data.assets);
    setScoreMin(0);
    setSelectedId(data.assets[0]?.asset.id || "");
    setStatus(`Imported ${data.imported} real ClinicalTrials.gov records`);
    await load();
    setTab("discovery");
  }

  async function runSourcingPlay(playId: string) {
    setStatus("Running sourcing play...");
    setSelectedPlay(playId);
    const params = new URLSearchParams({ play_id: playId, per_query: String(Math.max(1, Math.min(discoveryLimit, 20))) });
    const res = await fetch(`${API}/sourcing/run?${params.toString()}`, { method: "POST" });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "Sourcing play failed");
    }
    const data = await res.json();
    setImportedRows(data.assets);
    setScoreMin(0);
    setSelectedId(data.assets[0]?.asset.id || "");
    setStatus(`Sourcing play imported ${data.imported} candidates`);
    await load();
    setTab("discovery");
  }

  async function replaceDemoData() {
    setStatus("Removing demo assets and sourcing real candidates...");
    const params = new URLSearchParams({ per_query: String(Math.max(1, Math.min(discoveryLimit, 20))) });
    const res = await fetch(`${API}/sourcing/replace-demo-data?${params.toString()}`, { method: "POST" });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "Real-only sourcing failed");
    }
    const data = await res.json();
    setImportedRows(data.assets);
    setScoreMin(0);
    setSelectedId(data.assets[0]?.asset.id || "");
    setStatus(`Removed ${data.deleted_demo_assets} demo assets; imported ${data.imported_real_assets} real candidates`);
    await load();
    setTab("discovery");
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><Activity size={22} /> CodexHunter</div>
        {["overview", "discovery", "assets", "score", "evidence", "memo", "upload", "watchlist", "settings"].map((name) => (
          <button key={name} className={tab === name ? "nav active" : "nav"} onClick={() => setTab(name)}>
            {iconFor(name)}<span>{name}</span>
          </button>
        ))}
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>{selected?.asset.generic_name || "Asset finder"}</h1>
            <p>{selected ? `${selected.asset.indication} · ${selected.asset.current_owner}` : status}</p>
          </div>
          <button className="primary" onClick={() => selected && generateMemo(selected.asset.id)}><FileText size={16} /> Memo</button>
        </header>

        <div className="filters">
          <label><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search assets, owners, indications" /></label>
          <label><Filter size={16} /><select value={rec} onChange={(e) => setRec(e.target.value)}><option value="">All recommendations</option><option value="pursue">Pursue</option><option value="monitor">Monitor</option><option value="needs_review">Needs review</option><option value="pass">Pass</option></select></label>
          <label>Min score <input type="range" min="0" max="100" value={scoreMin} onChange={(e) => setScoreMin(Number(e.target.value))} /><strong>{scoreMin}</strong></label>
          <button onClick={load}><RefreshCcw size={16} /></button>
        </div>

        {tab === "overview" && <Overview rows={rows} status={status} />}
        {tab === "discovery" && <Discovery query={discoveryQuery} setQuery={setDiscoveryQuery} limit={discoveryLimit} setLimit={setDiscoveryLimit} ingest={ingestClinicalTrials} runPlay={runSourcingPlay} replaceDemoData={replaceDemoData} plays={plays} selectedPlay={selectedPlay} importedRows={importedRows} selectedId={selectedId} onSelect={setSelectedId} status={status} />}
        {tab === "assets" && <AssetList rows={filtered} selectedId={selectedId} onSelect={setSelectedId} />}
        {tab === "score" && selected && <ScoreBreakdown row={selected} />}
        {tab === "evidence" && selected && <Evidence row={selected} />}
        {tab === "memo" && <Memo memo={memo} selected={selected} generateMemo={generateMemo} />}
        {tab === "upload" && <UploadCsv uploadCsv={uploadCsv} />}
        {tab === "watchlist" && <AssetList rows={filtered.filter((r) => r.asset.tags.includes("watchlist") || r.score.recommendation === "monitor")} selectedId={selectedId} onSelect={setSelectedId} />}
        {tab === "settings" && <SettingsPanel />}
      </section>
    </main>
  );
}

function iconFor(name: string) {
  const props = { size: 17 };
  return name === "discovery" ? <DownloadCloud {...props} /> : name === "assets" ? <Database {...props} /> : name === "score" ? <ClipboardList {...props} /> : name === "evidence" ? <Search {...props} /> : name === "memo" ? <FileText {...props} /> : name === "upload" ? <Upload {...props} /> : name === "watchlist" ? <Star {...props} /> : name === "settings" ? <Settings {...props} /> : <Activity {...props} />;
}

function Overview({ rows, status }: { rows: Row[]; status: string }) {
  const avg = rows.length ? Math.round(rows.reduce((sum, row) => sum + row.score.total_score, 0) / rows.length) : 0;
  return <div className="grid"><Metric label="Assets" value={rows.length} /><Metric label="Average score" value={avg} /><Metric label="Pursue / monitor" value={rows.filter((r) => ["pursue", "monitor"].includes(r.score.recommendation)).length} /><Metric label="Status" value={status} wide /></div>;
}

function Metric({ label, value, wide }: { label: string; value: string | number; wide?: boolean }) {
  return <div className={wide ? "metric wide" : "metric"}><span>{label}</span><strong>{value}</strong></div>;
}

function AssetList({ rows, selectedId, onSelect }: { rows: Row[]; selectedId: string; onSelect: (id: string) => void }) {
  return <div className="table">{rows.map(({ asset, score }) => <button className={selectedId === asset.id ? "row active-row" : "row"} key={asset.id} onClick={() => onSelect(asset.id)}><strong>{asset.generic_name}</strong><span>{asset.indication}</span><span>{asset.development_stage}</span><b>{score.total_score} · {score.rating}</b><em>{score.recommendation}</em></button>)}</div>;
}

function Discovery({ query, setQuery, limit, setLimit, ingest, runPlay, replaceDemoData, plays, selectedPlay, importedRows, selectedId, onSelect, status }: { query: string; setQuery: (value: string) => void; limit: number; setLimit: (value: number) => void; ingest: () => Promise<void>; runPlay: (playId: string) => Promise<void>; replaceDemoData: () => Promise<void>; plays: SourcingPlay[]; selectedPlay: string; importedRows: Row[]; selectedId: string; onSelect: (id: string) => void; status: string }) {
  const [error, setError] = useState("");
  async function run(action: () => Promise<void>) {
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    }
  }
  return (
    <div className="panel discovery">
      <h2>Sourcing Plays</h2>
      <div className="real-only">
        <div>
          <strong>Real-data mode</strong>
          <span>Remove demo records and refill the database from public ClinicalTrials.gov sourcing plays.</span>
        </div>
        <button className="primary" onClick={() => run(replaceDemoData)}><DownloadCloud size={16} /> Replace demo data</button>
      </div>
      <div className="play-grid">
        {plays.map((play) => (
          <button key={play.id} className={selectedPlay === play.id ? "play active-play" : "play"} onClick={() => run(() => runPlay(play.id))}>
            <strong>{play.name}</strong>
            <span>{play.description}</span>
            <small>{play.queries.length} queries</small>
          </button>
        ))}
      </div>
      <h2>Custom ClinicalTrials.gov Search</h2>
      <div className="discovery-controls">
        <label><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} /></label>
        <label>Records <input type="number" min="1" max="50" value={limit} onChange={(e) => setLimit(Number(e.target.value))} /></label>
        <button className="primary" onClick={() => run(ingest)}><DownloadCloud size={16} /> Import</button>
      </div>
      <p>{status}</p>
      {error && <p className="error">{error}</p>}
      {importedRows.length > 0 && <AssetList rows={importedRows} selectedId={selectedId} onSelect={onSelect} />}
    </div>
  );
}

function ScoreBreakdown({ row }: { row: Row }) {
  const entries = Object.entries(row.score).filter(([key, value]) => key.endsWith("_score") && typeof value === "object") as [string, SubScore][];
  return <div className="score-grid">{entries.map(([key, sub]) => <div className="score" key={key}><div><strong>{key.replaceAll("_", " ")}</strong><b>{sub.score}</b></div><p>{sub.rationale}</p><small>Missing: {sub.missing_information.join(", ") || "none captured"}</small></div>)}</div>;
}

function Evidence({ row }: { row: Row }) {
  return <div className="panel"><h2>Evidence and Sources</h2>{row.asset.evidence.map((e) => <a className="source" href={e.url} target="_blank" key={e.title}><strong>{e.title}</strong><span>{e.summary}</span><small>{e.evidence_type} · confidence {e.confidence}</small></a>)}<h2>Trials</h2>{row.asset.trials.map((t) => <a className="source" href={t.url} target="_blank" key={t.nct_id}><strong>{t.nct_id}</strong><span>{t.phase} · {t.status} · enrollment {t.enrollment}</span></a>)}</div>;
}

function Memo({ memo, selected, generateMemo }: { memo: string; selected?: Row; generateMemo: (id: string) => void }) {
  return <div className="panel">{selected && <button className="primary" onClick={() => generateMemo(selected.asset.id)}><FileText size={16} /> Generate memo</button>}<pre className="memo">{memo || "Generate a memo for the selected asset."}</pre></div>;
}

function UploadCsv({ uploadCsv }: { uploadCsv: (file: File) => void }) {
  return <div className="panel upload"><Upload size={26} /><h2>Upload CSV</h2><input type="file" accept=".csv" onChange={(e) => e.target.files?.[0] && uploadCsv(e.target.files[0])} /><p>Columns can include id, generic_name, indication, therapeutic_area, development_stage, current_owner, asset_status, tags, source_url, and source_summary.</p></div>;
}

function SettingsPanel() {
  return <div className="panel"><h2>Connector Settings</h2><p>OPENAI_API_KEY, NCBI_API_KEY, SEC_USER_AGENT, and source URL allowlists can be added in .env. The default MVP uses deterministic source-backed behavior.</p><ul><li>ClinicalTrials.gov: real API v2 ingestion implemented</li><li>Manual CSV: implemented</li><li>PubMed, openFDA, SEC EDGAR, press releases, university tech transfer: stubs documented for next integration</li></ul></div>;
}

createRoot(document.getElementById("root")!).render(<App />);
