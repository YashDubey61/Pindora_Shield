import { useEffect, useRef, useState, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import ReportModal from "./Report";
import { getApiUrl } from "../config/api";

type Molecule = {
  smiles: string;
  similarity: number;
  scaffold_preserved?: boolean | null;
  properties: {
    molecular_weight: number;
    logp: number;
    hbd: number;
    hba: number;
    rotatable_bonds: number;
    aromatic_rings: number;
    qed?: number;
    sascore?: number;
    lipinski_violations?: number;
    pains_alert?: boolean;
  };
};

type ResultItem = {
  disease_name: string;
  target_symbol: string;
  drug_name: string;
  input_smile?: string;
  generated_molecules: Molecule[][];
  predictions?: {
    IC50?: number;
    Association_Score?: number;
    Max_Clinical_Phase?: number;
    Predicted_Target?: string;
  } | null;
};

interface ResultPageProps {
  results: ResultItem[];
  message?: string | null;
  onSelectSuggestion?: (suggestion: string) => void;
}

// ── Feature 3: Druggability Score (O(1) arithmetic) ──────────────────────
function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function computeDruggabilityScore(
  predictions: ResultItem["predictions"],
  mol: Molecule
): number | null {
  if (!predictions) return null;

  const ic50 = predictions.IC50;
  const assoc = predictions.Association_Score;
  const qed = mol.properties?.qed;
  const sascore = mol.properties?.sascore;
  const lipinski = mol.properties?.lipinski_violations ?? 0;
  const pains = mol.properties?.pains_alert ? 1 : 0;

  if (ic50 == null || assoc == null || qed == null || sascore == null) return null;

  const sPotency = clamp(1.0 - Math.log10(Math.max(ic50, 0.001)) / 4.0, 0, 1);
  const sAssoc = clamp(assoc, 0, 1);
  const sSynth = clamp(1.0 - (sascore - 1.0) / 9.0, 0, 1);
  const sPenalty = 0.25 * lipinski + 0.5 * pains;

  const raw = 0.35 * sPotency + 0.25 * sAssoc + 0.25 * qed + 0.15 * sSynth - 0.10 * sPenalty;
  return Math.round(clamp(raw * 100, 0, 100));
}

// ── Feature 5: Client-side CSV export ────────────────────────────────────
function exportCSV(results: ResultItem[]) {
  const header = "Disease,Target,Seed Drug,Candidate SMILES,Similarity,Scaffold Status,MW,LogP,QED,SAScore,Lipinski Violations,PAINS,IC50,Association Score,Max Phase\n";
  const rows: string[] = [];

  for (const item of results) {
    for (const molGroup of item.generated_molecules) {
      for (const mol of molGroup) {
        const p = mol.properties;
        const pred = item.predictions;
        const scaffStatus = mol.scaffold_preserved === true ? "Preserved" : mol.scaffold_preserved === false ? "Hopping" : "N/A";
        rows.push([
          `"${item.disease_name}"`,
          `"${item.target_symbol}"`,
          `"${item.drug_name}"`,
          `"${mol.smiles}"`,
          mol.similarity?.toFixed(3) ?? "",
          `"${scaffStatus}"`,
          p?.molecular_weight?.toFixed(1) ?? "",
          p?.logp?.toFixed(2) ?? "",
          p?.qed?.toFixed(3) ?? "",
          p?.sascore?.toFixed(1) ?? "",
          p?.lipinski_violations ?? "",
          p?.pains_alert ? "Yes" : "No",
          pred?.IC50?.toFixed(2) ?? "",
          pred?.Association_Score?.toFixed(3) ?? "",
          pred?.Max_Clinical_Phase ?? "",
        ].join(","));
      }
    }
  }

  const blob = new Blob([header + rows.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `pindora_candidates_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Feature 1: Badge color helpers ───────────────────────────────────────
function qedColor(v: number): string {
  if (v >= 0.67) return "#22c55e";
  if (v >= 0.50) return "#eab308";
  return "#ef4444";
}
function saColor(v: number): string {
  if (v <= 4.0) return "#22c55e";
  if (v <= 6.0) return "#eab308";
  return "#ef4444";
}
function scoreColor(v: number): string {
  if (v >= 70) return "#22c55e";
  if (v >= 45) return "#eab308";
  return "#ef4444";
}

type SortOption = "score" | "potency" | "synth" | "similarity";
type ViewerStyle = "ball_and_stick" | "stick" | "sphere";

export default function ResultPage({ results, message, onSelectSuggestion }: ResultPageProps) {
  const topRef = useRef<HTMLDivElement | null>(null);

  const [metrics, setMetrics] = useState<any | null>(null);
  const [activeSmile, setActiveSmile] = useState<string | null>(null);
  const [isMetricsLoading, setIsMetricsLoading] = useState(false);
  const [reportSmile, setReportSmile] = useState<string | null>(null);

  // Track which result cards are expanded to show all molecules
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());

  // Feature 2: 3D Viewer state
  const [viewer3dSmile, setViewer3dSmile] = useState<string | null>(null);
  const [viewer3dData, setViewer3dData] = useState<any | null>(null);
  const [viewer3dLoading, setViewer3dLoading] = useState(false);
  const [viewerStyle, setViewerStyle] = useState<ViewerStyle>("ball_and_stick");
  const [isSpinning, setIsSpinning] = useState(true);
  const [showSdfCode, setShowSdfCode] = useState(false);
  const viewer3dCanvasRef = useRef<HTMLDivElement | null>(null);
  const gl3dmolRef = useRef<any>(null);

  // Feature 3: Sort & Filter state
  const [sortBy, setSortBy] = useState<SortOption>("score");
  const [hidePains, setHidePains] = useState(false);
  const [lipinskiOnly, setLipinskiOnly] = useState(false);

  const toggleExpand = (index: number) => {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const fetchMetrics = async (smile: string) => {
    try {
      setActiveSmile(smile);
      setMetrics(null);
      setIsMetricsLoading(true);

      const res = await fetch(getApiUrl("/metrics/metrics_data"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_smile: smile }),
      });

      const data = await res.json();
      setMetrics(data);
    } catch (err) {
      console.error("Metrics API error:", err);
    } finally {
      setIsMetricsLoading(false);
    }
  };

  // Feature 2: On-demand 3D generation
  const fetch3DModel = async (smile: string) => {
    try {
      setViewer3dSmile(smile);
      setViewer3dData(null);
      setViewer3dLoading(true);
      setShowSdfCode(false);

      const res = await fetch(getApiUrl("/api/generate-3d"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_smile: smile }),
      });

      const data = await res.json();
      if (!res.ok) {
        setViewer3dData({ detail: data.detail || data.message || "Failed to generate 3D conformer" });
      } else {
        setViewer3dData(data);
      }
    } catch (err) {
      console.error("3D generation error:", err);
      setViewer3dData({ detail: "Network error generating 3D conformer" });
    } finally {
      setViewer3dLoading(false);
    }
  };

  // Feature 2: Render 3D conformer with 3Dmol.js
  useEffect(() => {
    if (!viewer3dData?.sdf_block || !viewer3dCanvasRef.current) return;

    const win = window as any;
    if (typeof win.$3Dmol !== "undefined") {
      viewer3dCanvasRef.current.innerHTML = "";
      const viewer = win.$3Dmol.createViewer(viewer3dCanvasRef.current, {
        backgroundColor: "#030712",
      });
      gl3dmolRef.current = viewer;
      viewer.addModel(viewer3dData.sdf_block, "sdf");

      if (viewerStyle === "ball_and_stick") {
        viewer.setStyle({}, { stick: { radius: 0.14 }, sphere: { scale: 0.28 } });
      } else if (viewerStyle === "stick") {
        viewer.setStyle({}, { stick: { radius: 0.22 } });
      } else if (viewerStyle === "sphere") {
        viewer.setStyle({}, { sphere: {} });
      }

      viewer.zoomTo();
      viewer.render();
      if (isSpinning) {
        viewer.spin(true);
      }
    }
  }, [viewer3dData, viewerStyle, isSpinning, showSdfCode]);

  useEffect(() => {
    if (topRef.current) {
      topRef.current.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  }, [results]);

  // Feature 3: Sorted & filtered results
  const processedResults = useMemo(() => {
    let filtered = [...results];

    // Apply PAINS / Lipinski filters across all molecules in each result
    if (hidePains || lipinskiOnly) {
      filtered = filtered.filter((item) =>
        item.generated_molecules.some((group) =>
          group.some((mol) => {
            if (hidePains && mol.properties?.pains_alert) return false;
            if (lipinskiOnly && (mol.properties?.lipinski_violations ?? 0) > 0) return false;
            return true;
          })
        )
      );
    }

    // Sort
    filtered.sort((a, b) => {
      const scoreA = getRepresentativeScore(a, sortBy);
      const scoreB = getRepresentativeScore(b, sortBy);
      return scoreB - scoreA; // Descending
    });

    return filtered;
  }, [results, sortBy, hidePains, lipinskiOnly]);

  function getRepresentativeScore(item: ResultItem, sort: SortOption): number {
    const firstMol = item.generated_molecules?.[0]?.[0];
    if (!firstMol) return 0;
    switch (sort) {
      case "score":
        return computeDruggabilityScore(item.predictions, firstMol) ?? 0;
      case "potency":
        return item.predictions?.IC50 != null ? 1 / item.predictions.IC50 : 0;
      case "synth":
        return firstMol.properties?.sascore != null ? 10 - firstMol.properties.sascore : 0;
      case "similarity":
        return firstMol.similarity ?? 0;
      default:
        return 0;
    }
  }

  const renderMoleculeCard = (
    mol: Molecule,
    molGroupIndex: number,
    componentIndex: number,
    isFirst: boolean,
    predictions?: ResultItem["predictions"] | null
  ) => {
    const dscore = computeDruggabilityScore(predictions ?? null, mol);

    return (
      <div
        key={`${molGroupIndex}-${componentIndex}`}
        className={`mol-card ${isFirst ? "mol-card-primary" : ""}`}
      >
        {mol.properties?.valid !== false && (
          <div className="props">
            <div>MW: {mol.properties.molecular_weight?.toFixed(1)}</div>
            <div>LogP: {mol.properties.logp?.toFixed(2)}</div>
            <div>HBD: {mol.properties.hbd}</div>
            <div>HBA: {mol.properties.hba}</div>
            <div>Rot. Bonds: {mol.properties.rotatable_bonds}</div>
            <div>Arom. Rings: {mol.properties.aromatic_rings}</div>
            {mol.similarity > 0 && (
              <div>Similarity: {(mol.similarity * 100).toFixed(1)}%</div>
            )}
          </div>
        )}

        {/* Feature 1 & 4: Drug-likeness & Scaffold badges */}
        {mol.properties?.valid !== false && (
          <div className="badge-row">
            {mol.properties.qed != null && (
              <span className="badge" style={{ borderColor: qedColor(mol.properties.qed) + "66", color: qedColor(mol.properties.qed) }}>
                QED: {mol.properties.qed.toFixed(2)}
              </span>
            )}
            {mol.properties.sascore != null && (
              <span className="badge" style={{ borderColor: saColor(mol.properties.sascore) + "66", color: saColor(mol.properties.sascore) }}>
                Synth: {mol.properties.sascore <= 4 ? "Easy" : mol.properties.sascore <= 6 ? "Moderate" : "Hard"} ({mol.properties.sascore})
              </span>
            )}
            {mol.properties.pains_alert != null && (
              <span className="badge" style={{
                borderColor: mol.properties.pains_alert ? "#ef444466" : "#22c55e66",
                color: mol.properties.pains_alert ? "#ef4444" : "#22c55e"
              }}>
                {mol.properties.pains_alert ? "⚠ PAINS" : "✓ Clean"}
              </span>
            )}
            {mol.properties.lipinski_violations != null && (
              <span className="badge" style={{
                borderColor: mol.properties.lipinski_violations === 0 ? "#22c55e66" : "#eab30866",
                color: mol.properties.lipinski_violations === 0 ? "#22c55e" : "#eab308"
              }}>
                Ro5: {mol.properties.lipinski_violations === 0 ? "Pass" : `${mol.properties.lipinski_violations} violation${mol.properties.lipinski_violations > 1 ? "s" : ""}`}
              </span>
            )}
            {/* Feature 4: High-speed Scaffold Alignment badge */}
            {mol.scaffold_preserved != null && (
              <span
                className="badge"
                style={{
                  borderColor: mol.scaffold_preserved ? "#38bdf888" : "#c084fc88",
                  color: mol.scaffold_preserved ? "#38bdf8" : "#c084fc",
                  background: mol.scaffold_preserved ? "rgba(56, 189, 248, 0.08)" : "rgba(192, 132, 252, 0.08)",
                }}
              >
                {mol.scaffold_preserved ? "⚗ Core Scaffold Preserved" : "✨ Scaffold Hopping (Novel Ring)"}
              </span>
            )}
            {/* Feature 3: Druggability composite score badge */}
            {dscore != null && (
              <span className="badge score-badge" style={{ borderColor: scoreColor(dscore) + "66", color: scoreColor(dscore) }}>
                Score: {dscore}/100
              </span>
            )}
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
          <div
            className="smiles"
            style={{ cursor: "pointer" }}
            onClick={() => fetchMetrics(mol.smiles)}
            title="Click to analyze this molecule"
          >
            SMILES: {mol.smiles}
          </div>

          <button
            className="report-button"
            onClick={() => setReportSmile(mol.smiles)}
          >
            Report
          </button>

          {/* Feature 2: 3D View button */}
          <button
            className="view3d-button"
            disabled={mol.properties?.valid === false}
            onClick={() => fetch3DModel(mol.smiles)}
            title={mol.properties?.valid === false ? "Cannot generate 3D model for invalid SMILES" : "View 3D Conformer"}
            style={mol.properties?.valid === false ? { opacity: 0.4, cursor: "not-allowed" } : undefined}
          >
            3D View
          </button>
        </div>

        {activeSmile === mol.smiles && (
          <div className="props" style={{ marginTop: "16px" }}>
            {isMetricsLoading ? (
              <div>Analyzing selected molecule…</div>
            ) : metrics ? (
              <div className="prose prose-invert max-w-none text-sm">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {metrics?.report}
                </ReactMarkdown>
              </div>
            ) : null}
          </div>
        )}
      </div>
    );
  };

  return (
    <div ref={topRef} className="results-page">
      <style>{`
        .results-page {
          margin-top: 72px;
          display: grid;
          gap: 32px;
          max-width: 1100px;
          width: 100%;
          margin-left: auto;
          margin-right: auto;
        }
        .controls-bar {
          display: flex;
          align-items: center;
          gap: 12px;
          flex-wrap: wrap;
          padding: 14px 18px;
          background: rgba(15, 23, 42, 0.9);
          border: 1px solid rgba(148, 163, 184, 0.15);
          border-radius: 16px;
        }
        .controls-bar label {
          font-size: 13px;
          color: #94a3b8;
          display: flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
        }
        .controls-bar select {
          background: rgba(2, 6, 23, 0.7);
          border: 1px solid rgba(148, 163, 184, 0.2);
          color: #e5e7eb;
          padding: 6px 10px;
          border-radius: 8px;
          font-size: 13px;
          cursor: pointer;
        }
        .controls-bar input[type="checkbox"] {
          accent-color: #38bdf8;
        }
        .export-btn {
          margin-left: auto;
          background: linear-gradient(90deg, #22c55e, #16a34a);
          border: none;
          color: white;
          padding: 8px 16px;
          border-radius: 10px;
          cursor: pointer;
          font-weight: 600;
          font-size: 13px;
          transition: all 0.2s ease;
        }
        .export-btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .result-card {
          background: rgba(15, 23, 42, 0.9);
          border: 1px solid rgba(148, 163, 184, 0.15);
          border-radius: 22px;
          padding: 28px;
          text-align: left;
        }
        .result-header h3 {
          font-size: 22px;
          margin-bottom: 6px;
          font-weight: 700;
        }
        .result-meta {
          font-size: 14px;
          color: #94a3b8;
          margin-bottom: 18px;
          line-height: 1.6;
        }
        .predictions-bar {
          display: flex;
          gap: 16px;
          flex-wrap: wrap;
          margin-bottom: 18px;
          font-size: 13px;
        }
        .pred-chip {
          background: rgba(56, 189, 248, 0.12);
          border: 1px solid rgba(56, 189, 248, 0.25);
          border-radius: 8px;
          padding: 4px 10px;
          color: #38bdf8;
        }
        .mol-card {
          margin-top: 12px;
          padding: 16px;
          background: rgba(2, 6, 23, 0.5);
          border: 1px solid rgba(148, 163, 184, 0.1);
          border-radius: 14px;
        }
        .mol-card-primary {
          border-color: rgba(56, 189, 248, 0.25);
        }
        .mol-label {
          font-size: 12px;
          color: #64748b;
          margin-bottom: 8px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .props {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 8px;
          font-size: 14px;
          color: #e5e7eb;
          background: rgba(2, 6, 23, 0.6);
          border: 1px solid rgba(148, 163, 184, 0.12);
          padding: 14px;
          border-radius: 12px;
        }
        .badge-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 10px;
        }
        .badge {
          font-size: 12px;
          font-weight: 600;
          padding: 3px 10px;
          border-radius: 8px;
          border: 1px solid;
          background: rgba(2, 6, 23, 0.5);
        }
        .score-badge {
          font-size: 13px;
          font-weight: 700;
        }
        .smiles {
          margin-top: 8px;
          font-family: monospace;
          font-size: 13px;
          color: #38bdf8;
          word-break: break-all;
        }
        .report-button {
          background: linear-gradient(90deg, #06b6d4, #3b82f6);
          border: none;
          color: white;
          padding: 8px 12px;
          border-radius: 10px;
          cursor: pointer;
          font-weight: 600;
          font-size: 13px;
          white-space: nowrap;
        }
        .report-button:hover { opacity: 0.95; }
        .view3d-button {
          background: linear-gradient(90deg, #a855f7, #6366f1);
          border: none;
          color: white;
          padding: 8px 12px;
          border-radius: 10px;
          cursor: pointer;
          font-weight: 600;
          font-size: 13px;
          white-space: nowrap;
          transition: all 0.2s ease;
        }
        .view3d-button:hover { opacity: 0.9; transform: translateY(-1px); }
        .expand-btn {
          background: rgba(148, 163, 184, 0.12);
          border: 1px solid rgba(148, 163, 184, 0.2);
          color: #94a3b8;
          padding: 8px 16px;
          border-radius: 10px;
          cursor: pointer;
          font-size: 13px;
          margin-top: 12px;
          transition: all 0.2s ease;
        }
        .expand-btn:hover {
          background: rgba(56, 189, 248, 0.12);
          color: #38bdf8;
          border-color: rgba(56, 189, 248, 0.3);
        }
        .empty-state {
          margin-top: 36px;
          padding: 44px 32px;
          background: rgba(15, 23, 42, 0.85);
          border: 1px solid rgba(56, 189, 248, 0.25);
          border-radius: 20px;
          text-align: center;
          max-width: 760px;
          margin-left: auto;
          margin-right: auto;
          box-shadow: 0 25px 60px rgba(0, 0, 0, 0.45);
          backdrop-filter: blur(14px);
        }
        .empty-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 56px;
          height: 56px;
          border-radius: 16px;
          background: rgba(56, 189, 248, 0.12);
          border: 1px solid rgba(56, 189, 248, 0.3);
          color: #38bdf8;
          margin-bottom: 18px;
        }
        .empty-title {
          font-size: 22px;
          font-weight: 700;
          color: #f8fafc;
          margin-bottom: 12px;
        }
        .empty-desc {
          font-size: 15px;
          color: #94a3b8;
          line-height: 1.6;
          margin-bottom: 24px;
        }
        .empty-suggestions {
          text-align: left;
          background: rgba(2, 6, 23, 0.6);
          border: 1px solid rgba(148, 163, 184, 0.15);
          border-radius: 14px;
          padding: 20px 24px;
          font-size: 13.5px;
          color: #cbd5e1;
        }
        .empty-suggestions-title {
          font-weight: 600;
          color: #38bdf8;
          margin-bottom: 10px;
          font-size: 14px;
        }
        .empty-list {
          padding-left: 20px;
          margin-bottom: 16px;
          line-height: 1.6;
          color: #94a3b8;
        }
        .empty-list li {
          margin-bottom: 6px;
        }
        .empty-pill-list {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 10px;
        }
        .empty-pill-btn {
          background: rgba(56, 189, 248, 0.1);
          border: 1px solid rgba(56, 189, 248, 0.25);
          color: #7dd3fc;
          padding: 6px 14px;
          border-radius: 10px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .empty-pill-btn:hover {
          background: rgba(56, 189, 248, 0.2);
          border-color: rgba(56, 189, 248, 0.45);
          transform: translateY(-1px);
          color: #fff;
        }
        .viewer3d-overlay {
          position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
          background: rgba(0,0,0,0.75); display: flex;
          justify-content: center; align-items: center; z-index: 3000;
          backdrop-filter: blur(8px);
        }
        .viewer3d-modal {
          width: 760px; max-height: 90vh; background: rgba(15,23,42,0.98);
          color: #e2e8f0; border-radius: 24px; padding: 26px;
          overflow-y: auto; box-shadow: 0 25px 70px rgba(0,0,0,0.7);
          border: 1px solid rgba(56,189,248,0.25);
          display: flex; flex-direction: column; gap: 14px;
        }
        .viewer3d-header {
          display: flex; align-items: center; justify-content: space-between;
        }
        .viewer3d-close {
          background: rgba(148,163,184,0.12); border: 1px solid rgba(148,163,184,0.2);
          color: #94a3b8; font-size: 20px; cursor: pointer; padding: 4px 10px;
          border-radius: 10px; transition: all 0.2s ease;
        }
        .viewer3d-close:hover { color: #fff; background: rgba(239,68,68,0.2); border-color: #ef4444; }
        .viewer3d-canvas-wrap {
          width: 100%; height: 380px; position: relative;
          background: #030712; border-radius: 16px;
          overflow: hidden; border: 1px solid rgba(148,163,184,0.15);
        }
        .viewer3d-canvas {
          width: 100%; height: 100%; position: relative;
        }
        .viewer3d-controls-bar {
          display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
          padding: 8px 12px; background: rgba(2,6,23,0.7);
          border: 1px solid rgba(148,163,184,0.15); border-radius: 12px;
        }
        .viewer-btn {
          background: rgba(148,163,184,0.12); border: 1px solid rgba(148,163,184,0.2);
          color: #cbd5e1; padding: 6px 12px; border-radius: 8px; font-size: 12px;
          font-weight: 500; cursor: pointer; transition: all 0.2s ease;
        }
        .viewer-btn:hover { background: rgba(56,189,248,0.18); color: #fff; }
        .viewer-btn.active {
          background: linear-gradient(135deg, #38bdf8, #6366f1);
          border-color: transparent; color: #fff; font-weight: 600;
        }
        .viewer3d-sdf {
          background: rgba(2,6,23,0.85); border: 1px solid rgba(148,163,184,0.15);
          border-radius: 12px; padding: 14px; font-family: monospace;
          font-size: 11px; color: #94a3b8; max-height: 260px;
          overflow-y: auto; white-space: pre; line-height: 1.4;
        }
        .viewer3d-info {
          display: flex; gap: 20px; font-size: 13px; color: #94a3b8;
          padding: 8px 12px; background: rgba(2,6,23,0.5); border-radius: 10px;
        }
        .viewer3d-info span { display: flex; align-items: center; gap: 6px; }
        .viewer3d-legend {
          display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
          padding: 8px 14px; background: rgba(2,6,23,0.65);
          border: 1px solid rgba(148,163,184,0.14); border-radius: 12px;
          font-size: 12px; color: #cbd5e1;
        }
        .legend-item { display: flex; align-items: center; gap: 6px; font-weight: 500; }
        .legend-dot { width: 11px; height: 11px; border-radius: 50%; display: inline-block; box-shadow: 0 0 6px rgba(0,0,0,0.4); }
      `}</style>

      {results.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h2 className="empty-title">We need more data for this specific disease</h2>
          <p className="empty-desc">
            {message ||
              "The biological disease entity was recognized and associated targets were identified in Open Targets, but current biomedical databases lack sufficient small-molecule lead compounds or ChEMBL bioactivity records (IC50) required for de novo molecule generation."}
          </p>
          <div className="empty-suggestions">
            <div className="empty-suggestions-title">💡 Why did this happen & what can you try?</div>
            <ul className="empty-list">
              <li>
                Many conditions (such as Dengue or acute viral infections) primarily have protein biologics, vaccines, or antibodies rather than characterized small-molecule chemical leads in public databases.
              </li>
              <li>
                Our AI molecular generation model requires small-molecule chemical scaffolds to explore analog chemical space.
              </li>
              <li>
                Try querying diseases with extensive small-molecule chemical coverage in ChEMBL and Open Targets:
              </li>
            </ul>
            <div className="empty-pill-list">
              {["HIV", "Breast Cancer", "Type 2 Diabetes", "Hypertension", "Alzheimer Disease", "Leukemia"].map(
                (item) => (
                  <button
                    key={item}
                    className="empty-pill-btn"
                    onClick={() => onSelectSuggestion?.(item)}
                    title={`Try ${item}`}
                  >
                    + {item}
                  </button>
                )
              )}
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* Feature 3 & 5: Controls bar */}
          <div className="controls-bar">
            <label>
              Sort:
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortOption)}>
                <option value="score">Druggability Score</option>
                <option value="potency">Highest Potency</option>
                <option value="synth">Best Synthesizability</option>
                <option value="similarity">Highest Similarity</option>
              </select>
            </label>

            <label>
              <input type="checkbox" checked={hidePains} onChange={(e) => setHidePains(e.target.checked)} />
              Hide PAINS
            </label>

            <label>
              <input type="checkbox" checked={lipinskiOnly} onChange={(e) => setLipinskiOnly(e.target.checked)} />
              Lipinski Only
            </label>

            <button className="export-btn" onClick={() => exportCSV(results)}>
              ⬇ Export CSV
            </button>
          </div>

          {processedResults.map((item, index) => {
            const allMolecules = item.generated_molecules || [];
            const isExpanded = expandedCards.has(index);
            const displayMols = isExpanded ? allMolecules : allMolecules.slice(0, 1);
            const hasMore = allMolecules.length > 1;

            return (
              <div key={index} className="result-card">
                <div className="result-header">
                  <h3>{index + 1}. {item.drug_name}</h3>
                </div>

                <div className="result-meta">
                  Disease: {item.disease_name}<br />
                  Target: {item.target_symbol}
                </div>

                {/* Show inline MatriX predictions if available */}
                {item.predictions && (
                  <div className="predictions-bar">
                    {item.predictions.IC50 != null && (
                      <span className="pred-chip">IC50: {item.predictions.IC50.toFixed(2)} nM</span>
                    )}
                    {item.predictions.Association_Score != null && (
                      <span className="pred-chip">Assoc: {item.predictions.Association_Score.toFixed(3)}</span>
                    )}
                    {item.predictions.Max_Clinical_Phase != null && (
                      <span className="pred-chip">Phase: {item.predictions.Max_Clinical_Phase}</span>
                    )}
                    {item.predictions.Predicted_Target && (
                      <span className="pred-chip">Target: {item.predictions.Predicted_Target}</span>
                    )}
                  </div>
                )}

                {displayMols.map((molGroup, groupIdx) => (
                  <div key={groupIdx}>
                    {allMolecules.length > 1 && (
                      <div className="mol-label">
                        Variant {groupIdx + 1} of {allMolecules.length}
                      </div>
                    )}
                    {molGroup.map((mol, compIdx) =>
                      renderMoleculeCard(mol, groupIdx, compIdx, groupIdx === 0 && compIdx === 0, item.predictions)
                    )}
                  </div>
                ))}

                {hasMore && (
                  <button className="expand-btn" onClick={() => toggleExpand(index)}>
                    {isExpanded
                      ? "Show less"
                      : `Show all ${allMolecules.length} generated variants`}
                  </button>
                )}
              </div>
            );
          })}
        </>
      )}

      {reportSmile && (
        <ReportModal smiles={reportSmile} onClose={() => setReportSmile(null)} />
      )}

      {/* Feature 2: Interactive 3D Conformer Viewer Modal */}
      {viewer3dSmile && (
        <div className="viewer3d-overlay" onClick={() => { setViewer3dSmile(null); setViewer3dData(null); }}>
          <div className="viewer3d-modal" onClick={(e) => e.stopPropagation()}>
            <div className="viewer3d-header">
              <div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "#f8fafc" }}>3D Molecular Conformer</div>
                <div style={{ fontSize: 13, color: "#94a3b8", marginTop: 2 }}>Interactive UFF-minimized 3D structural model</div>
              </div>
              <button className="viewer3d-close" onClick={() => { setViewer3dSmile(null); setViewer3dData(null); }}>×</button>
            </div>

            <div style={{ fontSize: 13, color: "#38bdf8", fontFamily: "monospace", wordBreak: "break-all" }}>
              {viewer3dSmile}
            </div>

            {viewer3dLoading && (
              <div style={{ padding: 40, textAlign: "center", color: "#38bdf8" }}>
                Generating 3D conformer & running UFF force-field minimization…
              </div>
            )}

            {viewer3dData && viewer3dData.sdf_block && (
              <>
                <div className="viewer3d-controls-bar">
                  <span style={{ fontSize: 12, color: "#94a3b8", marginRight: 4 }}>Style:</span>
                  <button
                    className={`viewer-btn ${viewerStyle === "ball_and_stick" ? "active" : ""}`}
                    onClick={() => setViewerStyle("ball_and_stick")}
                  >
                    Ball & Stick
                  </button>
                  <button
                    className={`viewer-btn ${viewerStyle === "stick" ? "active" : ""}`}
                    onClick={() => setViewerStyle("stick")}
                  >
                    Stick
                  </button>
                  <button
                    className={`viewer-btn ${viewerStyle === "sphere" ? "active" : ""}`}
                    onClick={() => setViewerStyle("sphere")}
                  >
                    Space-Filling (CPK)
                  </button>

                  <div style={{ width: 1, height: 18, background: "rgba(148,163,184,0.2)", margin: "0 4px" }} />

                  <button
                    className={`viewer-btn ${isSpinning ? "active" : ""}`}
                    onClick={() => {
                      const next = !isSpinning;
                      setIsSpinning(next);
                      if (gl3dmolRef.current) {
                        gl3dmolRef.current.spin(next);
                      }
                    }}
                  >
                    {isSpinning ? "⏸ Pause Spin" : "▶ Auto-Rotate"}
                  </button>

                  <button
                    className="viewer-btn"
                    onClick={() => {
                      if (gl3dmolRef.current) {
                        gl3dmolRef.current.zoomTo();
                        gl3dmolRef.current.render();
                      }
                    }}
                  >
                    ↺ Reset View
                  </button>

                  <button
                    className={`viewer-btn ${showSdfCode ? "active" : ""}`}
                    style={{ marginLeft: "auto" }}
                    onClick={() => setShowSdfCode(!showSdfCode)}
                  >
                    {showSdfCode ? "👁 View 3D" : "{ } Raw SDF"}
                  </button>
                </div>

                {!showSdfCode ? (
                  <div className="viewer3d-canvas-wrap">
                    <div ref={viewer3dCanvasRef} className="viewer3d-canvas" />
                  </div>
                ) : (
                  <div className="viewer3d-sdf">
                    {viewer3dData.sdf_block}
                  </div>
                )}

                <div className="viewer3d-legend">
                  <span style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px", marginRight: 2 }}>Atom Legend:</span>
                  <span className="legend-item"><span className="legend-dot" style={{ background: "#909090" }} /> Carbon (C)</span>
                  <span className="legend-item"><span className="legend-dot" style={{ background: "#ffffff", border: "1px solid #94a3b8" }} /> Hydrogen (H)</span>
                  <span className="legend-item"><span className="legend-dot" style={{ background: "#ef4444" }} /> Oxygen (O)</span>
                  <span className="legend-item"><span className="legend-dot" style={{ background: "#60a5fa" }} /> Nitrogen (N)</span>
                  <span className="legend-item"><span className="legend-dot" style={{ background: "#eab308" }} /> Sulfur (S)</span>
                  <span className="legend-item"><span className="legend-dot" style={{ background: "#22c55e" }} /> Halogen (F/Cl)</span>
                </div>

                <div className="viewer3d-info">
                  <span>⚛ Atoms: <strong>{viewer3dData.num_atoms ?? "—"}</strong></span>
                  <span>🔗 Bonds: <strong>{viewer3dData.num_bonds ?? "—"}</strong></span>
                  <span>⚡ Force Field: <strong>UFF Minimized</strong></span>
                  <span style={{ marginLeft: "auto", color: "#22c55e" }}>● {viewer3dData.status || "Ready"}</span>
                </div>
              </>
            )}

            {viewer3dData && !viewer3dData.sdf_block && (
              <div style={{ padding: 24, color: "#f87171", background: "rgba(239,68,68,0.1)", borderRadius: 12 }}>
                Error: {viewer3dData.detail || "Failed to generate 3D model conformer"}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
