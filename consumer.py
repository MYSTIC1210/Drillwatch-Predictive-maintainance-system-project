"""
anomaly_detector.py — Moving Average Anomaly Detector
======================================================
Implements a rolling-window 3-sigma (3σ) anomaly detection algorithm
for drilling telemetry streams.

Algorithm:
    Maintains a sliding window of the last N vibration readings.
    A CRITICAL ALERT is raised when the current reading deviates more
    than `sigma_threshold` standard deviations from the rolling mean.

    A per-parameter minimum std floor is applied to prevent false positives
    during near-steady-state operation where window variance collapses.

    This approach mirrors the ISO 13379-1:2012 (Condition Monitoring)
    guidance for process parameter alarm setpoints.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import logging
import math

logger = logging.getLogger("drillwatch.anomaly_detector")


@dataclass
class AnomalyAlert:
    """Structured anomaly alert record."""

    alert_id: str
    timestamp: str
    asset_id: str
    parameter: str
    current_value: float
    rolling_mean: float
    rolling_std: float
    sigma_deviation: float
    severity: str               # "WARNING" | "CRITICAL"
    sequence: int
    message: str
    rul_estimate: Optional[float] = None
    tags: list = field(default_factory=list)


class MovingAverageAnomalyDetector:
    """
    Rolling-window 3σ anomaly detector.

    Parameters
    ----------
    window_size : int
        Number of samples in the rolling window (default: 30).
        At 1 sample/second, this is a 30-second lookback window.
    sigma_threshold : float
        Number of standard deviations to trigger a CRITICAL alert (default: 3.0).
    warning_sigma : float
        Threshold for WARNING-level alerts (default: 2.0).
    min_samples : int
        Minimum samples required before alerting (avoids false alarms on startup).
    """

    # Per-parameter minimum std floor — prevents false positives when the
    # rolling window variance collapses during steady-state operation.
    # Values derived from typical sensor resolution specs (IADC guidelines).
    _MIN_STD: dict = {
        "vibration_g":   0.08,    # 80 mg RMS — accelerometer noise floor
        "bearing_temp_f": 1.5,    # 1.5°F — thermocouple resolution
        "torque_ftlbf":  150.0,   # 150 ft-lbf — torque transducer noise floor
    }

    def __init__(
        self,
        window_size: int = 30,
        sigma_threshold: float = 3.0,
        warning_sigma: float = 2.0,
        min_samples: int = 15,
    ) -> None:
        self.window_size = window_size
        self.sigma_threshold = sigma_threshold
        self.warning_sigma = warning_sigma
        self.min_samples = min_samples

        # Separate windows for key parameters
        self._windows: dict[str, deque] = {
            "vibration_g": deque(maxlen=window_size),
            "bearing_temp_f": deque(maxlen=window_size),
            "torque_ftlbf": deque(maxlen=window_size),
        }

        self._alert_count: int = 0

    def _rolling_stats(self, param: str) -> tuple[float, float]:
        """Return (mean, effective_std) for the current window.

        Applies a minimum std floor per parameter to prevent division
        by near-zero values during steady-state operation.
        """
        window = list(self._windows[param])
        if len(window) < 2:
            return (0.0, self._MIN_STD.get(param, 1.0))

        n = len(window)
        mean = sum(window) / n
        variance = sum((x - mean) ** 2 for x in window) / (n - 1)
        raw_std = math.sqrt(variance) if variance > 0 else 0.0

        # Apply sensor noise floor — ensures we never flag normal measurement
        # variation as anomalous just because the window is unusually quiet.
        floored_std = max(raw_std, self._MIN_STD.get(param, 1e-6))
        return (mean, floored_std)

    def _sigma_deviation(self, value: float, mean: float, std: float) -> float:
        """Compute how many standard deviations the value is from the mean."""
        return abs(value - mean) / max(std, 1e-9)

    def ingest(self, telemetry: dict) -> Optional[AnomalyAlert]:
        """
        Ingest a telemetry record and return an AnomalyAlert if triggered.

        Parameters
        ----------
        telemetry : dict
            Parsed telemetry record (matches DrillingTelemetry dataclass fields).

        Returns
        -------
        AnomalyAlert or None
        """
        # Update all rolling windows
        for param in self._windows:
            if param in telemetry:
                self._windows[param].append(float(telemetry[param]))

        # Require minimum warmup samples
        if len(self._windows["vibration_g"]) < self.min_samples:
            return None

        # --- Primary check: Lateral Vibration (highest diagnostic value) ---
        vib_mean, vib_std = self._rolling_stats("vibration_g")
        vib_value = float(telemetry.get("vibration_g", 0.0))
        vib_sigma = self._sigma_deviation(vib_value, vib_mean, vib_std)

        # --- Secondary check: Bearing Temperature ---
        temp_mean, temp_std = self._rolling_stats("bearing_temp_f")
        temp_value = float(telemetry.get("bearing_temp_f", 0.0))
        temp_sigma = self._sigma_deviation(temp_value, temp_mean, temp_std)

        # Determine worst offender and severity
        worst_sigma = max(vib_sigma, temp_sigma)
        worst_param = "vibration_g" if vib_sigma >= temp_sigma else "bearing_temp_f"
        worst_value = vib_value if worst_param == "vibration_g" else temp_value
        worst_mean = vib_mean if worst_param == "vibration_g" else temp_mean
        worst_std = vib_std if worst_param == "vibration_g" else temp_std

        if worst_sigma >= self.sigma_threshold:
            severity = "CRITICAL"
        elif worst_sigma >= self.warning_sigma:
            severity = "WARNING"
        else:
            return None  # No anomaly

        self._alert_count += 1
        alert = AnomalyAlert(
            alert_id=f"ALT-{self._alert_count:06d}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            asset_id=telemetry.get("asset_id", "UNKNOWN"),
            parameter=worst_param,
            current_value=round(worst_value, 4),
            rolling_mean=round(worst_mean, 4),
            rolling_std=round(worst_std, 6),
            sigma_deviation=round(worst_sigma, 2),
            severity=severity,
            sequence=telemetry.get("sequence", 0),
            rul_estimate=telemetry.get("rul_estimate"),
            message=self._format_message(
                severity, worst_param, worst_value, worst_sigma, telemetry
            ),
            tags=self._build_tags(telemetry, vib_sigma, temp_sigma),
        )

        logger.warning(
            "ANOMALY [%s] %s | σ=%.2f | %s=%.3f (μ=%.3f, σ=%.4f)",
            severity, alert.asset_id, worst_sigma,
            worst_param, worst_value, worst_mean, worst_std,
        )
        return alert

    def _format_message(
        self,
        severity: str,
        param: str,
        value: float,
        sigma: float,
        telemetry: dict,
    ) -> str:
        """Build a human-readable alert message."""
        param_labels = {
            "vibration_g": f"Lateral Vibration {value:.2f}g",
            "bearing_temp_f": f"Bearing Temp {value:.1f}°F",
            "torque_ftlbf": f"Torque {value:.0f} ft-lbf",
        }
        label = param_labels.get(param, f"{param}={value:.3f}")
        rul = telemetry.get("rul_estimate")
        rul_str = f" | RUL: {rul:.1%}" if rul is not None else ""
        return (
            f"[{severity}] Asset {telemetry.get('asset_id', '?')} — "
            f"{label} deviates {sigma:.1f}σ from rolling baseline{rul_str}. "
            f"Seq #{telemetry.get('sequence', '?')}"
        )

    def _build_tags(self, telemetry: dict, vib_sigma: float, temp_sigma: float) -> list:
        """Build context tags for the alert."""
        tags = []
        if telemetry.get("drift_active"):
            tags.append("BEARING_WEAR_DETECTED")
        if vib_sigma >= self.sigma_threshold:
            tags.append("HIGH_VIBRATION")
        if temp_sigma >= self.sigma_threshold:
            tags.append("HIGH_TEMPERATURE")
        rul = telemetry.get("rul_estimate", 1.0) or 1.0
        if rul < 0.2:
            tags.append("IMMINENT_FAILURE")
        elif rul < 0.5:
            tags.append("DEGRADED_HEALTH")
        return tags

    @property
    def alert_count(self) -> int:
        """Total alerts generated since instantiation."""
        return self._alert_count

    def window_summary(self) -> dict:
        """Return current rolling statistics for all monitored parameters."""
        summary = {}
        for param in self._windows:
            mean, std = self._rolling_stats(param)
            summary[param] = {
                "mean": round(mean, 4),
                "std": round(std, 6),
                "samples": len(self._windows[param]),
            }
        return summary
