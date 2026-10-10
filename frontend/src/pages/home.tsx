import { useState, useRef, useCallback } from "react";
import { Search, ChevronRight } from "lucide-react";
import Loading from "./loading";
import ResultPage from "./ResultPage";
import { getApiUrl } from "../config/api";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [results, setResults] = useState<any[] | null>(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [stepLabel, setStepLabel] = useState("Initializing pipeline…");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const runPostFallback = async () => {
    try {
      const apiUrl = getApiUrl("/api/drug_discovery");
      console.log("Running fallback POST request to:", apiUrl);

      const res = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: `(query(${prompt}))` }),
      });

      const text = await res.text();
      let json: any;
      try {
        json = JSON.parse(text);
      } catch {
        throw new Error("Backend returned invalid JSON: " + (text ? text.slice(0, 500) : "(empty response)"));
      }

      if (!res.ok) {
        throw new Error((json && (json.message || json.detail)) || text);
      }

      if (!Array.isArray(json.results)) {
        throw new Error("Unexpected response format: 'results' missing or not an array");
      }

      setResults(json.results);
      if (json.results.length === 0) {
        setStatus(
          json.message ||
            "We need more data for this specific disease. Associated biological targets were identified, but no small-molecule candidates with sufficient bioactivity records were found."
        );
      } else {
        setStatus(json.message || `Generation complete. Found ${json.results.length} molecule series.`);
      }
    } catch (e) {
      setStatus("ERROR: " + (e as Error).message);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleGenerate = () => {
    if (!prompt.trim()) {
      setStatus("Please describe your biological intent.");
      return;
    }

    setIsGenerating(true);
    setCurrentStep(1);
    setStepLabel("Initiating discovery pipeline…");
    setStatus("Processing biological query…");
    setResults(null);

    let eventSource: EventSource | null = null;
    let isCompleted = false;

    try {
      const sseUrl = getApiUrl(`/api/drug_discovery_stream?text=${encodeURIComponent(prompt.trim())}`);
      console.log("Connecting to SSE stream:", sseUrl);

      eventSource = new EventSource(sseUrl);

      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.step) {
            setCurrentStep(payload.step);
          }
          if (payload.label) {
            setStepLabel(payload.label);
          }
          if (payload.step === 6) {
            isCompleted = true;
            eventSource?.close();
            const res = Array.isArray(payload.data) ? payload.data : [];
            setResults(res);
            setIsGenerating(false);
            if (res.length === 0) {
              setStatus("We need more data for this specific disease. Associated biological targets were identified, but no small-molecule candidates were found.");
            } else {
              setStatus(`Generation complete. Found ${res.length} molecule series.`);
            }
          } else if (payload.step === -1) {
            isCompleted = true;
            eventSource?.close();
            setStatus("ERROR: " + (payload.label || "Discovery stream error"));
            setIsGenerating(false);
          }
        } catch (err) {
          console.error("SSE parse error:", err);
        }
      };

      eventSource.onerror = (err) => {
        console.warn("SSE error, falling back to POST:", err);
        if (!isCompleted) {
          eventSource?.close();
          runPostFallback();
        }
      };
    } catch (err) {
      console.warn("Failed to initialize SSE, using POST:", err);
      runPostFallback();
    }
  };

  return (
    <div className="app">
      <style>{`
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }

        body {
          font-family: Inter, system-ui, sans-serif;
          background: radial-gradient(circle at top, #0f172a, #020617);
          color: #fff;
        }

        .app {
          min-height: 100vh;
          width: 100vw;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .hero {
          width: 100%;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 48px;
        }

        .container {
          max-width: 1100px;
          width: 100%;
          text-align: center;
        }

        .hero-title {
          font-size: clamp(40px, 5vw, 64px);
          font-weight: 800;
          line-height: 1.1;
          margin-bottom: 24px;
        }

        .gradient-text {
          background: linear-gradient(135deg, #38bdf8, #22c55e, #a855f7);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .hero-subtitle {
          font-size: 18px;
          color: #cbd5e1;
          max-width: 700px;
          margin: 0 auto 56px;
        }

        .input-section {
          display: flex;
          justify-content: center;
        }

        .input-container {
          background: rgba(15, 23, 42, 0.85);
          border: 1px solid rgba(56, 189, 248, 0.25);
          border-radius: 22px;
          padding: 6px;
          width: 100%;
          max-width: 850px;
          box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
        }

        .input-wrapper {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 18px 22px;
        }

        .input-icon {
          color: #38bdf8;
          flex-shrink: 0;
        }

        .prompt-input {
          flex: 1;
          background: transparent;
          border: none;
          color: white;
          font-size: 16px;
          outline: none;
          resize: none;
          line-height: 1.5;
        }

        .prompt-input::placeholder {
          color: #94a3b8;
        }

        .generate-button {
          display: flex;
          align-items: center;
          gap: 8px;
          background: linear-gradient(135deg, #38bdf8, #6366f1);
          border: none;
          color: white;
          font-size: 16px;
          font-weight: 600;
          padding: 14px 28px;
          border-radius: 16px;
          cursor: pointer;
          transition: all 0.25s ease;
        }

        .generate-button:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 14px 40px rgba(56, 189, 248, 0.5);
        }

        .generate-button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .status {
          margin-top: 20px;
          font-size: 14px;
          color: #38bdf8;
        }
      `}</style>

      {isGenerating ? (
        <Loading currentStep={currentStep} stepLabel={stepLabel} />
      ) : (
        <div className="hero">
          <div className="container">
            <h1 className="hero-title">
              Design <span className="gradient-text">Molecules</span> with
              <br />
              Artificial Intelligence
            </h1>

            <p className="hero-subtitle">
              Describe symptoms, diseases, or biological targets — our AI generates
              and analyzes candidate molecules with unprecedented speed and accuracy.
            </p>

            <div className="input-section">
              <div className="input-container">
                <div className="input-wrapper">
                  <div className="input-icon">
                    <Search size={24} />
                  </div>

                  <textarea
                    rows={3}
                    className="prompt-input"
                    placeholder="Describe a biological target, disease symptoms, or desired molecular properties…"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    disabled={isGenerating}
                  />

                  <button
                    className="generate-button"
                    onClick={handleGenerate}
                    disabled={isGenerating}
                  >
                    Generate Molecules
                    <ChevronRight size={20} />
                  </button>
                </div>
              </div>
            </div>

            {status && results && results.length > 0 && <div className="status">{status}</div>}

            {results && (
              <ResultPage
                results={results}
                message={status}
                onSelectSuggestion={(suggestion: string) => {
                  setPrompt(suggestion);
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}