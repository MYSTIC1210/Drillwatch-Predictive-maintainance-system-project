@tailwind base;
@tailwind components;
@tailwind utilities;

/* ============================================================
   DrillWatch — Industrial Operations Dashboard
   Design system: Military HUD / Offshore Control Room
   ============================================================ */

:root {
  --bg-void:      #050810;
  --bg-deep:      #080d1a;
  --bg-panel:     #0d1528;
  --bg-raised:    #111d35;
  --border-dim:   rgba(6, 182, 212, 0.12);
  --border-glow:  rgba(6, 182, 212, 0.35);
  --text-primary: #e2e8f0;
  --text-dim:     #64748b;
  --text-mono:    #94a3b8;
  --cyan:         #06b6d4;
  --cyan-glow:    rgba(6, 182, 212, 0.25);
  --amber:        #f59e0b;
  --crimson:      #ef4444;
  --emerald:      #10b981;
  --font-display: 'Barlow Condensed', sans-serif;
  --font-body:    'Barlow', sans-serif;
  --font-mono:    'Share Tech Mono', monospace;
}

* { box-sizing: border-box; }

body {
  font-family: var(--font-body);
  background: var(--bg-void);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
}

/* ── Scrollbars ─────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: rgba(6, 182, 212, 0.3); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(6, 182, 212, 0.55); }

/* ── Panel chrome ───────────────────────────────────── */
.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-dim);
  border-radius: 4px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.03);
  position: relative;
  overflow: hidden;
}

.panel::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--cyan) 40%, var(--cyan) 60%, transparent);
  opacity: 0.25;
}

/* ── Typography ─────────────────────────────────────── */
.label-mono {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  letter-spacing: 0.12em;
  color: var(--text-dim);
  text-transform: uppercase;
}

.label-display {
  font-family: var(--font-display);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.value-readout {
  font-family: var(--font-mono);
  font-size: 1.6rem;
  letter-spacing: -0.02em;
  line-height: 1;
}

/* ── Status pills ───────────────────────────────────── */
.status-healthy  { color: var(--emerald); border-color: var(--emerald); }
.status-degraded { color: var(--amber);   border-color: var(--amber);   }
.status-critical { color: var(--crimson); border-color: var(--crimson); }
.status-unknown  { color: var(--text-dim); border-color: var(--text-dim); }

/* ── Blinking critical indicator ────────────────────── */
@keyframes blink-critical {
  0%, 49%  { opacity: 1; }
  50%, 100% { opacity: 0.2; }
}
.blink-critical { animation: blink-critical 0.8s step-end infinite; }

/* ── Scan line overlay (CRT effect) ─────────────────── */
@keyframes scan {
  0%   { transform: translateY(-5%); }
  100% { transform: translateY(105%); }
}
.scanline-container { position: relative; overflow: hidden; }
.scanline-container::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 40px;
  background: linear-gradient(transparent, rgba(6, 182, 212, 0.03), transparent);
  animation: scan 6s linear infinite;
  pointer-events: none;
}

/* ── Grid dot background ────────────────────────────── */
.grid-bg {
  background-image:
    radial-gradient(circle, rgba(6, 182, 212, 0.06) 1px, transparent 1px);
  background-size: 28px 28px;
}

/* ── Recharts overrides ─────────────────────────────── */
.recharts-cartesian-grid-horizontal line,
.recharts-cartesian-grid-vertical line {
  stroke: rgba(6, 182, 212, 0.07) !important;
}
.recharts-text { fill: #475569 !important; font-family: var(--font-mono) !important; font-size: 10px !important; }
.recharts-tooltip-wrapper { outline: none; }

/* ── Fade-in animation ──────────────────────────────── */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.fade-up { animation: fadeUp 0.35s ease-out both; }
