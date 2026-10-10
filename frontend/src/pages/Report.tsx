import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { getApiUrl } from "../config/api";

interface ReportProps {
  smiles: string;
  onClose: () => void;
}

function normalizeReport(raw: string): string {
  if (!raw) return "";
  let s = raw.trim();
  // Clean up any accidentally doubled leading hashes (e.g. # ###)
  s = s.replace(/^#+\s*(#+\s*)/, "$1");
  return s;
}

export default function ReportModal({ smiles, onClose }: ReportProps) {
  const [report, setReport] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const fetchReport = async () => {
    try {
      setLoading(true);
      setError(null);

      const res = await fetch(getApiUrl("/metrics/metrics_data"), {
        method: "POST",
        headers: {
          "accept": "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ input_smile: smiles }),
      });

      const text = await res.text();
      let parsed: any = null;
      try { parsed = JSON.parse(text); } catch {}

      const raw = parsed?.report || parsed?.data?.report || parsed?.report_text || text;

      if (!res.ok) throw new Error(parsed?.detail || parsed?.message || text || `HTTP ${res.status}`);

      const normalized = normalizeReport(raw);
      setReport(normalized);
      setStatus(parsed?.status || "success");
    } catch (err: any) {
      setError(err.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchReport(); }, [smiles]);

  const handlePrint = () => {
    window.print();
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <style>{`
          .report-modal-content {
            text-align: left !important;
            font-family: Inter, system-ui, sans-serif;
            color: #cbd5e1;
            line-height: 1.65;
          }
          .report-modal-content h1 {
            font-size: 24px;
            font-weight: 800;
            color: #f8fafc;
            margin-top: 4px;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.2);
            text-align: left;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
          }
          .report-modal-content h2 {
            font-size: 17px;
            font-weight: 700;
            color: #38bdf8;
            margin-top: 26px;
            margin-bottom: 12px;
            text-align: left;
            display: flex;
            align-items: center;
            gap: 8px;
          }
          .report-modal-content h3 {
            font-size: 15px;
            font-weight: 600;
            color: #e2e8f0;
            margin-top: 18px;
            margin-bottom: 8px;
            text-align: left;
          }
          .report-modal-content p {
            margin-bottom: 12px;
            text-align: left;
            font-size: 14px;
            color: #cbd5e1;
          }
          .report-modal-content strong {
            color: #f8fafc;
            font-weight: 600;
          }
          .report-modal-content table {
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
            background: rgba(2, 6, 23, 0.65);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px;
            overflow: hidden;
            text-align: left;
          }
          .report-modal-content th {
            background: rgba(56, 189, 248, 0.12);
            color: #7dd3fc;
            padding: 10px 14px;
            font-size: 13px;
            font-weight: 600;
            text-align: left;
            border-bottom: 1px solid rgba(148, 163, 184, 0.2);
          }
          .report-modal-content td {
            padding: 9px 14px;
            font-size: 13px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.1);
            color: #cbd5e1;
            text-align: left;
          }
          .report-modal-content tr:last-child td {
            border-bottom: none;
          }
          .report-modal-content ul {
            padding-left: 24px;
            margin: 12px 0;
            text-align: left;
            list-style-type: disc;
          }
          .report-modal-content ol {
            padding-left: 24px;
            margin: 12px 0;
            text-align: left;
            list-style-type: decimal;
          }
          .report-modal-content li {
            margin-bottom: 7px;
            text-align: left;
            font-size: 14px;
            color: #cbd5e1;
            line-height: 1.6;
          }
          .report-modal-content code {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            background: rgba(2, 6, 23, 0.75);
            border: 1px solid rgba(148, 163, 184, 0.2);
            padding: 2px 7px;
            border-radius: 6px;
            color: #38bdf8;
            font-size: 12.5px;
            word-break: break-all;
          }
          @media print {
            body * { visibility: hidden; }
            .report-modal-content, .report-modal-content * {
              visibility: visible;
              color: #000 !important;
              background: transparent !important;
            }
            .report-modal-content {
              position: absolute;
              left: 0;
              top: 0;
              width: 100%;
            }
          }
        `}</style>
        
        <div style={headerRow}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "#f8fafc" }}>Clinical Pharmacology & Assessment Dossier</div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>Medicinal chemistry profile & MPO developability evaluation</div>
          </div>
          <button style={closeBtn} onClick={onClose} title="Close">×</button>
        </div>

        <div style={subHeader}>
          <span style={{ color: "#38bdf8", fontFamily: "monospace", wordBreak: "break-all" }}>{smiles}</span>
          {status && <span style={{ marginLeft: 10, color: "#22c55e", fontWeight: 600 }}>• {status}</span>}
        </div>

        {loading && (
          <div style={{ padding: 40, textAlign: "center", color: "#38bdf8" }}>
            Synthesizing clinical assessment dossier…
          </div>
        )}
        {error && (
          <div style={{ padding: 24, color: "#f87171", background: "rgba(239,68,68,0.1)", borderRadius: 12, textAlign: "left" }}>
            Error generating report: {error}
          </div>
        )}

        {!loading && !error && report && (
          <div className="report-modal-content">
            <ReactMarkdown
              remarkPlugins={[remarkMath, remarkGfm]}
              rehypePlugins={[rehypeKatex]}
            >
              {report}
            </ReactMarkdown>
          </div>
        )}

        <div style={footerRow}>
          <button style={printBtn} onClick={handlePrint} title="Print or save as PDF">
            🖨 Print / Export PDF
          </button>
          <button style={footerCloseBtn} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/* 🔹 Themed Styles */

const overlay = {
  position: "fixed",
  top: 0,
  left: 0,
  width: "100vw",
  height: "100vh",
  background: "rgba(0, 0, 0, 0.7)",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  zIndex: 2500,
  backdropFilter: "blur(8px)",
} as const;

const modal = {
  width: "820px",
  maxHeight: "88vh",
  background: "rgba(15, 23, 42, 0.98)",
  color: "#e2e8f0",
  borderRadius: "24px",
  padding: "26px 32px",
  overflowY: "auto",
  boxShadow: "0 25px 70px rgba(0, 0, 0, 0.7)",
  border: "1px solid rgba(56, 189, 248, 0.25)",
  textAlign: "left",
  display: "flex",
  flexDirection: "column",
  gap: "14px",
} as const;

const headerRow = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
} as const;

const closeBtn = {
  background: "rgba(148, 163, 184, 0.12)",
  border: "1px solid rgba(148, 163, 184, 0.2)",
  color: "#94a3b8",
  fontSize: "20px",
  cursor: "pointer",
  padding: "4px 10px",
  borderRadius: "10px",
} as const;

const subHeader = {
  fontSize: 13,
  color: "#94a3b8",
  background: "rgba(2, 6, 23, 0.5)",
  padding: "8px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(148, 163, 184, 0.12)",
  textAlign: "left",
} as const;

const footerRow = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "12px",
  marginTop: 18,
  paddingTop: 16,
  borderTop: "1px solid rgba(148, 163, 184, 0.15)",
} as const;

const printBtn = {
  borderRadius: "10px",
  background: "rgba(56, 189, 248, 0.15)",
  border: "1px solid rgba(56, 189, 248, 0.35)",
  color: "#38bdf8",
  padding: "8px 16px",
  cursor: "pointer",
  fontWeight: 600,
  fontSize: "13px",
  display: "flex",
  alignItems: "center",
  gap: "6px",
  transition: "all 0.2s ease",
} as const;

const footerCloseBtn = {
  borderRadius: "10px",
  background: "rgba(148, 163, 184, 0.15)",
  border: "1px solid rgba(148, 163, 184, 0.25)",
  color: "#cbd5e1",
  padding: "8px 18px",
  cursor: "pointer",
  fontWeight: 600,
  fontSize: "13px",
  transition: "all 0.2s ease",
} as const;
