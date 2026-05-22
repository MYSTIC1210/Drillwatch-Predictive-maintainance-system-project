/**
 * MetricsPanel.jsx
 * Live KPI gauges panel — shows latest values for key drilling parameters.
 * Uses inline mini-bar indicators and threshold colouring.
 */

import React from "react";
import { Gauge, Thermometer, Zap, Layers, Droplets, ArrowDown } from "lucide-react";

function clamp(val, min, max) {
  return Math.min(Math.max(val ?? 0, min), max);
}

function getColor(val, warn, crit) {
  if (crit != null && val >= crit) return { text: "text-red-400", bar: "bg-red-500" };
  if (warn != null && val >= warn) return { text: "text-amber-400", bar: "bg-amber-500" };
  return { text: "text-cyan-400", bar: "bg-cyan-500" };
}

function MiniBar({ pct, color }) {
  return (
    <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden mt-1">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${clamp(pct, 0, 100)}%` }}
      />
    </div>
  );
}

function KPICard({ icon: Icon, label, value, unit, warn, crit, min, max, suffix }) {
  const numeric = typeof value === "number" ? value : parseFloat(value);
  const pct = ((numeric - min) / (max - min)) * 100;
  const { text, bar } = getColor(numeric, warn, crit);
  const displayVal = isNaN(numeric) ? "—" : numeric.toFixed(suffix ?? 1);

  return (
    <div className="panel px-3 py-3 flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Icon size={11} className="text-slate-500 shrink-0" />
          <span className="label-mono text-[0.58rem] text-slate-500">{label}</span>
        </div>
        {warn != null && numeric >= warn && (
          <span
            className={`label-mono text-[0.55rem] px-1 rounded-sm ${
              numeric >= (crit ?? Infinity)
                ? "text-red-400 bg-red-950/50 border border-red-500/30"
                : "text-amber-400 bg-amber-950/50 border border-amber-500/30"
            }`}
          >
            {numeric >= (crit ?? Infinity) ? "CRIT" : "WARN"}
          </span>
        )}
      </div>
      <div className={`font-mono font-bold text-xl leading-none ${text}`}>
        {displayVal}
        <span className="text-slate-600 text-xs font-normal ml-1">{unit}</span>
      </div>
      <MiniBar pct={pct} color={bar} />
      <div className="flex justify-between mt-0.5">
        <span className="label-mono text-[0.5rem] text-slate-700">{min}{unit}</span>
        <span className="label-mono text-[0.5rem] text-slate-700">{max}{unit}</span>
      </div>
    </div>
  );
}

function RULGauge({ rul, healthState }) {
  const pct = clamp((rul ?? 0) * 100, 0, 100);
  const color =
    pct > 60
      ? { ring: "stroke-emerald-500", text: "text-emerald-400", label: "HEALTHY" }
      : pct > 30
      ? { ring: "stroke-amber-500", text: "text-amber-400", label: "DEGRADED" }
      : { ring: "stroke-red-500", text: "text-red-400", label: "CRITICAL" };

  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const strokeDash = (pct / 100) * circumference;

  return (
    <div className="panel px-3 py-3 flex flex-col items-center justify-center gap-1">
      <span className="label-mono text-[0.58rem] text-slate-500 mb-1">REMAINING USEFUL LIFE</span>
      <div className="relative w-24 h-24">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 96 96">
          <circle
            cx="48" cy="48" r={radius}
            fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="6"
          />
          <circle
            cx="48" cy="48" r={radius}
            fill="none"
            className={color.ring}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={`${strokeDash} ${circumference}`}
            style={{ transition: "stroke-dasharray 0.7s ease", filter: "drop-shadow(0 0 4px currentColor)" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`font-mono font-bold text-xl leading-none ${color.text}`}>
            {pct.toFixed(0)}%
          </span>
          <span className={`label-mono text-[0.55rem] ${color.text} mt-0.5`}>
            {healthState ?? color.label}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function MetricsPanel({ latest }) {
  const d = latest ?? {};

  return (
    <div className="panel flex flex-col h-full">
      {/* Header */}
      <div className="px-4 pt-3 pb-2 border-b border-slate-800/60 shrink-0">
        <span className="label-display font-semibold text-sm text-slate-300 tracking-wider">
          LIVE PARAMETERS
        </span>
      </div>

      {/* Grid of KPIs */}
      <div className="flex-1 overflow-y-auto p-3 grid grid-cols-2 gap-2 content-start">
        <KPICard
          icon={Gauge}
          label="SURFACE RPM"
          value={d.surface_rpm}
          unit="rpm"
          min={30} max={250}
          warn={190} crit={230}
          suffix={0}
        />
        <KPICard
          icon={Zap}
          label="TORQUE"
          value={d.torque_ftlbf != null ? d.torque_ftlbf / 1000 : null}
          unit="k ft·lbf"
          min={4} max={35}
          warn={28} crit={32}
          suffix={1}
        />
        <KPICard
          icon={Layers}
          label="VIBRATION RMS"
          value={d.vibration_g}
          unit="g"
          min={0} max={12}
          warn={3.5} crit={6.0}
          suffix={3}
        />
        <KPICard
          icon={Thermometer}
          label="BEARING TEMP"
          value={d.bearing_temp_f}
          unit="°F"
          min={160} max={400}
          warn={300} crit={360}
          suffix={1}
        />
        <KPICard
          icon={ArrowDown}
          label="WEIGHT ON BIT"
          value={d.weight_on_bit_klbf}
          unit="klbf"
          min={5} max={50}
          warn={40} crit={47}
          suffix={1}
        />
        <KPICard
          icon={Droplets}
          label="FLOW RATE"
          value={d.flow_rate_gpm}
          unit="gpm"
          min={300} max={900}
          warn={820} crit={875}
          suffix={0}
        />

        {/* Full-width RUL gauge */}
        <div className="col-span-2">
          <RULGauge
            rul={d.rul_predicted ?? d.rul_estimate}
            healthState={d.rul_health_state}
          />
        </div>

        {/* Standpipe pressure */}
        <div className="col-span-2">
          <KPICard
            icon={Gauge}
            label="STANDPIPE PRESSURE"
            value={d.standpipe_pressure_psi}
            unit="psi"
            min={1500} max={5500}
            warn={4800} crit={5200}
            suffix={0}
          />
        </div>

        {/* Sequence counter */}
        <div className="col-span-2 panel px-3 py-2 flex items-center justify-between">
          <span className="label-mono text-[0.58rem] text-slate-600">SEQUENCE #</span>
          <span className="font-mono text-sm text-slate-400">
            {d.sequence != null ? String(d.sequence).padStart(6, "0") : "——————"}
          </span>
        </div>
      </div>
    </div>
  );
}
