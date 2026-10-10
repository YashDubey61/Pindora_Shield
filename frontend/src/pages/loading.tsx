import { useEffect, useRef, useState } from "react";
import { getApiUrl } from "../config/api";

type Molecule = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  phase: number;
};

interface LoadingProps {
  currentStep?: number;
  stepLabel?: string;
}

const MILESTONES = [
  { step: 1, title: "Disease Resolution", desc: "Extracting target disease entity" },
  { step: 2, title: "Target Identification", desc: "Querying Open Targets genetics" },
  { step: 3, title: "Reference Inhibitors", desc: "Retrieving ChEMBL bioactivity leads" },
  { step: 4, title: "TenGAN Generative AI", desc: "Generating de novo chemical space" },
  { step: 5, title: "MatriX Predictions", desc: "Predicting IC50 potency & affinity" },
  { step: 6, title: "MPO Scoring & Ranking", desc: "Evaluating QED, PAINS & Ro5 safety" },
];

export default function Loading({ currentStep = 1, stepLabel }: LoadingProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const moleculesRef = useRef<Molecule[]>([]);
  const [status, setStatus] = useState("Initializing cellular discovery pipeline…");
  const [seconds, setSeconds] = useState(0);

  const MOLECULE_COUNT = 20;
  const INTERACTION_DISTANCE = 85;
  const BASE_SPEED = 2.0;

  /* ===============================
     Elapsed Timer
  ================================ */
  useEffect(() => {
    const timer = setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  /* ===============================
     Canvas Physics Animation
  ================================ */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    moleculesRef.current = Array.from({ length: MOLECULE_COUNT }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * BASE_SPEED,
      vy: (Math.random() - 0.5) * BASE_SPEED,
      r: 2.2 + Math.random() * 2.8,
      phase: Math.random() * Math.PI * 2,
    }));

    let animationId: number;

    const drawMolecule = (m: Molecule) => {
      const pulse = Math.sin(Date.now() * 0.003 + m.phase) * 0.5;

      ctx.beginPath();
      ctx.arc(m.x, m.y, m.r + pulse, 0, Math.PI * 2);
      ctx.fillStyle = "#38bdf8";
      ctx.shadowBlur = 10;
      ctx.shadowColor = "#38bdf8";
      ctx.fill();
    };

    const drawInteraction = (a: Molecule, b: Molecule, d: number) => {
      ctx.strokeStyle = `rgba(56, 189, 248, ${1 - d / INTERACTION_DISTANCE})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    };

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      moleculesRef.current.forEach((m, i) => {
        m.vx += (Math.random() - 0.5) * 0.04;
        m.vy += (Math.random() - 0.5) * 0.04;

        m.x += m.vx;
        m.y += m.vy;

        if (m.x < 0 || m.x > canvas.width) m.vx *= -1;
        if (m.y < 0 || m.y > canvas.height) m.vy *= -1;

        for (let j = i + 1; j < moleculesRef.current.length; j++) {
          const o = moleculesRef.current[j];
          const dx = m.x - o.x;
          const dy = m.y - o.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < INTERACTION_DISTANCE) {
            drawInteraction(m, o, dist);
          }
        }

        drawMolecule(m);
      });

      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => cancelAnimationFrame(animationId);
  }, []);

  /* ===============================
     Fallback Periodic Status Check
  ================================ */
  useEffect(() => {
    if (stepLabel) {
      setStatus(stepLabel);
      return;
    }

    const fetchStatus = async () => {
      try {
        const res = await fetch(getApiUrl("/checks/status_checks"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const data = await res.json();
        if (data.message) {
          setStatus(data.message);
        }
      } catch {
        setStatus("Simulating molecular conformations…");
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 4000);
    return () => clearInterval(interval);
  }, [stepLabel]);

  return (
    <div className="loader-root">
      <style>{`
        .loader-root {
          min-height: 100vh;
          width: 100vw;
          background: radial-gradient(circle at top center, #0b1528, #020617);
          display: flex;
          align-items: center;
          justify-content: center;
          font-family: Inter, system-ui, sans-serif;
          color: #d9faff;
          padding: 32px 20px;
          box-sizing: border-box;
        }

        .loader-card {
          width: 100%;
          max-width: 680px;
          background: rgba(15, 23, 42, 0.85);
          border: 1px solid rgba(56, 189, 248, 0.25);
          border-radius: 24px;
          padding: 32px;
          box-shadow: 0 30px 80px rgba(0, 0, 0, 0.6);
          backdrop-filter: blur(16px);
          text-align: center;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 20px;
        }

        .canvas-container {
          position: relative;
          width: 220px;
          height: 220px;
        }

        canvas {
          width: 220px;
          height: 220px;
          border-radius: 50%;
        }

        .timer-badge {
          position: absolute;
          bottom: 6px;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(2, 6, 23, 0.8);
          border: 1px solid rgba(56, 189, 248, 0.3);
          color: #38bdf8;
          font-size: 11.5px;
          font-weight: 600;
          padding: 3px 10px;
          border-radius: 12px;
          white-space: nowrap;
        }

        .active-status {
          font-size: 16px;
          font-weight: 600;
          color: #f8fafc;
          letter-spacing: 0.2px;
        }

        .stepper-container {
          width: 100%;
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 6px;
        }

        .step-row {
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 10px 14px;
          border-radius: 12px;
          background: rgba(2, 6, 23, 0.5);
          border: 1px solid rgba(148, 163, 184, 0.1);
          transition: all 0.25s ease;
          text-align: left;
        }

        .step-row.completed {
          border-color: rgba(34, 197, 94, 0.3);
          background: rgba(34, 197, 94, 0.05);
        }

        .step-row.active {
          border-color: rgba(56, 189, 248, 0.5);
          background: rgba(56, 189, 248, 0.12);
          box-shadow: 0 0 20px rgba(56, 189, 248, 0.15);
        }

        .step-icon-box {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 700;
          flex-shrink: 0;
          border: 1px solid;
        }

        .step-icon-box.completed {
          background: #22c55e;
          border-color: #22c55e;
          color: #020617;
        }

        .step-icon-box.active {
          background: #38bdf8;
          border-color: #38bdf8;
          color: #020617;
          animation: pulse-ring 1.8s infinite;
        }

        .step-icon-box.pending {
          background: transparent;
          border-color: rgba(148, 163, 184, 0.25);
          color: #64748b;
        }

        @keyframes pulse-ring {
          0% { box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.7); }
          70% { box-shadow: 0 0 0 8px rgba(56, 189, 248, 0); }
          100% { box-shadow: 0 0 0 0 rgba(56, 189, 248, 0); }
        }

        .step-content {
          flex: 1;
        }

        .step-title {
          font-size: 13.5px;
          font-weight: 600;
          color: #e2e8f0;
        }

        .step-row.active .step-title {
          color: #38bdf8;
        }

        .step-desc {
          font-size: 11.5px;
          color: #94a3b8;
          margin-top: 1px;
        }
      `}</style>

      <div className="loader-card">
        <div className="canvas-container">
          <canvas ref={canvasRef} width={220} height={220} />
          <div className="timer-badge">Elapsed: {seconds}s</div>
        </div>

        <div className="active-status">
          {stepLabel || status}
        </div>

        {/* Feature 6: Real-time 6-stage Stepper */}
        <div className="stepper-container">
          {MILESTONES.map((item) => {
            const isCompleted = item.step < currentStep;
            const isActive = item.step === currentStep;
            const isPending = item.step > currentStep;

            return (
              <div
                key={item.step}
                className={`step-row ${isCompleted ? "completed" : ""} ${isActive ? "active" : ""}`}
              >
                <div
                  className={`step-icon-box ${
                    isCompleted ? "completed" : isActive ? "active" : "pending"
                  }`}
                >
                  {isCompleted ? "✓" : item.step}
                </div>
                <div className="step-content">
                  <div className="step-title">{item.title}</div>
                  <div className="step-desc">{item.desc}</div>
                </div>
                {isActive && (
                  <div style={{ fontSize: 11, color: "#38bdf8", fontWeight: 600 }}>
                    In progress…
                  </div>
                )}
                {isCompleted && (
                  <div style={{ fontSize: 11, color: "#22c55e", fontWeight: 600 }}>
                    Done
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}