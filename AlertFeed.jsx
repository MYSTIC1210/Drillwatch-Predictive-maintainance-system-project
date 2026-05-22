/**
 * TelemetryChart.jsx
 * Real-time line chart for a single telemetry parameter.
 * Uses Recharts ResponsiveContainer with industrial dark theme.
 */

import React, { useMemo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";

// ── Custom Tooltip ─────────────────────────────────────────────────────────
function DrillTooltip({ active, payload, label, unit, color }) {
  if (!active || !payload?.length) return null;
  const val = payload[0]?.value;
  return (
    <div
      className="border border-cyan-900/50 bg-slate-950/95 backdrop-blur-sm px-3 py-2 rounded-sm shadow-xl"
      style={{ fontFamily: "'Share Tech Mono', monospace" }}
    >
      <div className="text-slate-500 text-[0.6rem] tracking-widest mb-1">{label}</div>
      <div className="text-sm" style={{ color }}>
        {typeof val === "number" ? val.toFixed(3) : val}
        <span className="text-slate-500 ml-1 text-xs">{unit}</span>
      </div>
    </div>
  );
}

// ── Anomaly dot renderer ───────────────────────────────────────────────────
function AnomalyDot(props) {
  const { cx, cy, payload } = props;
  if (!payload?.is_anomaly) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill="rgba(239,68,68,0.85)"
      stroke="#f87171"
      strokeWidth={1.5}
      style={{ filter: "drop-shadow(0 0 6px rgba(239,68,68,0.8))" }}
    />
  );
}

// ── Main Component ─────────────────────────────────────────────────────────
export default function TelemetryChart({
  data = [],
  dataKey,
  label,
  unit = "",
  color = "#06b6d4",
  warnLine,
  critLine,
  domain,
  showAnomaly = false,
}) {
  // Downsample to last 60 points for chart performance
  const chartData = useMemo(() => {
    const pts = data.slice(-60);
    return pts.map((d, i) => ({
      ...d,
      _idx: i,
      _label: d.sequence ? `#${d.sequence}` : `${i}`,
    }));
  }, [data]);

  const hasData = chartData.length > 0;
  const latest = hasData ? chartData[chartData.length - 1][dataKey] : null;
  const isAnomalous = hasData && chartData[chartData.length - 1]?.is_anomaly;

  // Compute value color based on thresholds
  const valueColor =
    critLine && latest >= critLine
      ? "#ef4444"
      : warnLine && latest >= warnLine
      ? "#f59e0b"
      : color;

  return (
    <div className="panel flex flex-col h-full scanline-container">
      {/* Header */}
      <div className="flex items-start justify-between px-4 pt-3 pb-2 shrink-0">
        <div>
          <div className="label-mono text-[0.6rem] text-slate-500 mb-0.5">{label}</div>
          <div
            className="value-readout transition-colors duration-300"
            style={{ color: valueColor, fontFamily: "'Share Tech Mono', monospace" }}
          >
            {latest != null ? latest.toFixed(2) : "—"}
            <span className="text-slate-500 text-sm ml-1.5 font-normal">{unit}</span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {isAnomalous && (
            <span className="label-mono text-[0.6rem] text-red-400 border border-red-500/40 px-2 py-0.5 rounded-sm blink-critical bg-red-950/30">
              ANOMALY
            </span>
          )}
          {warnLine && (
            <span className="label-mono text-[0.55rem] text-slate-600">
              WARN {warnLine} {unit}
            </span>
          )}
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 min-h-0 pb-2 pr-2">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
              <CartesianGrid
                strokeDasharray="2 6"
                stroke="rgba(6,182,212,0.07)"
                vertical={false}
              />
              <XAxis
                dataKey="_label"
                tick={{ fontSize: 9, fill: "#475569", fontFamily: "'Share Tech Mono'" }}
                tickLine={false}
                axisLine={{ stroke: "rgba(6,182,212,0.1)" }}
                interval={Math.floor(chartData.length / 6)}
              />
              <YAxis
                domain={domain || ["auto", "auto"]}
                tick={{ fontSize: 9, fill: "#475569", fontFamily: "'Share Tech Mono'" }}
                tickLine={false}
                axisLine={false}
                width={40}
                tickFormatter={(v) => v.toFixed(1)}
              />
              <Tooltip
                content={<DrillTooltip unit={unit} color={color} />}
                isAnimationActive={false}
              />
              {warnLine && (
                <ReferenceLine
                  y={warnLine}
                  stroke="rgba(245,158,11,0.45)"
                  strokeDasharray="4 4"
                  strokeWidth={1}
                />
              )}
              {critLine && (
                <ReferenceLine
                  y={critLine}
                  stroke="rgba(239,68,68,0.5)"
                  strokeDasharray="3 3"
                  strokeWidth={1}
                />
              )}
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={1.5}
                dot={showAnomaly ? <AnomalyDot /> : false}
                activeDot={{ r: 4, fill: color, stroke: "transparent" }}
                isAnimationActive={false}
                style={{ filter: `drop-shadow(0 0 4px ${color}50)` }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center">
            <span className="label-mono text-slate-700 text-xs">AWAITING TELEMETRY…</span>
          </div>
        )}
      </div>
    </div>
  );
}
