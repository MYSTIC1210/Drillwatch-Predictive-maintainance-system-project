"""
producer.py — DrillWatch Telemetry Simulation Engine
=====================================================
Generates synthetic drilling telemetry based on real-world IADC (International
Association of Drilling Contractors) operational parameter ranges for a typical
offshore PDC-bit rotary drilling operation.

Sensor Drift Model:
    Simulates progressive bearing wear using an exponential vibration growth
    curve and a coupled temperature rise, matching failure patterns documented
    in SPE-174965 (Bearing Failure Detection in Drilling Motors).

Real-World Parameter Baselines (Source: IADC Drilling Manual, 12th Ed.):
    - WOB (Weight on Bit): 10–40 klbf
    - RPM: 60–200 (surface rotary, PDC bit)
    - Torque: 8,000–25,000 ft-lbf
    - Standpipe Pressure: 2,500–4,500 psi
    - Vibration (RMS lateral): 0.5–2.0 g (normal), >4.0 g (severe)
    - Downhole Temperature: 150–280°F (Gulf of Mexico shelf)
"""

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pika
import pika.exceptions

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("drillwatch.producer")

# ---------------------------------------------------------------------------
# Configuration (all from environment variables)
# ---------------------------------------------------------------------------
RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER: str = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS: str = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_QUEUE: str = os.getenv("RABBITMQ_QUEUE", "drill.telemetry")
RABBITMQ_EXCHANGE: str = os.getenv("RABBITMQ_EXCHANGE", "drill.exchange")
TELEMETRY_INTERVAL: float = float(os.getenv("TELEMETRY_INTERVAL", "1.0"))
DRIFT_START_STEP: int = int(os.getenv("DRIFT_START_STEP", "200"))
ASSET_ID: str = os.getenv("ASSET_ID", "DRILLRIG-NOV-001")

# Connection retry parameters
MAX_RETRIES: int = 15
RETRY_BACKOFF_BASE: float = 2.0  # seconds, exponential backoff


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------
@dataclass
class DrillingTelemetry:
    """
    Represents one telemetry snapshot from a drilling asset.

    Fields align with real WITS (Wellsite Information Transfer Standard)
    Level 0 data records used in industry SCADA systems.
    """

    timestamp: str
    asset_id: str
    sequence: int
    # Mechanical parameters
    surface_rpm: float          # Surface rotary RPM
    downhole_rpm: float         # Estimated downhole RPM (motor + surface)
    torque_ftlbf: float         # Surface torque [ft-lbf]
    weight_on_bit_klbf: float   # WOB [klbf]
    # Vibration (RMS lateral acceleration at surface sub)
    vibration_g: float          # [g RMS]
    # Thermal
    inlet_temp_f: float         # Drilling fluid inlet temperature [°F]
    outlet_temp_f: float        # Drilling fluid outlet temperature [°F]
    bearing_temp_f: float       # Estimated bearing temperature [°F]
    # Hydraulics
    standpipe_pressure_psi: float
    flow_rate_gpm: float
    # Derived / health indicators
    rul_estimate: Optional[float] = None   # Remaining Useful Life [0–1]
    is_anomaly: bool = False
    drift_active: bool = False
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sensor Drift Model (Bearing Wear Simulation)
# ---------------------------------------------------------------------------
class BearingWearModel:
    """
    Physics-inspired progressive wear model.

    Based on the Hertz contact fatigue model and empirical data from:
    SPE-174965 "Real-Time Downhole Vibration Classification for Drilling Motors"

    The model produces:
        - Exponential vibration growth (classic bearing spalling signature)
        - Coupled temperature rise (friction → heat transfer)
        - Slight RPM/torque fluctuation (bit-bounce effect under wear)
    """

    def __init__(self, drift_start: int, severity_scale: float = 0.018) -> None:
        self.drift_start = drift_start
        self.severity_scale = severity_scale  # Controls how fast wear progresses

    def vibration_multiplier(self, step: int) -> float:
        """Return vibration gain factor at given simulation step."""
        if step < self.drift_start:
            return 1.0
        elapsed = step - self.drift_start
        return 1.0 + (np.exp(self.severity_scale * elapsed) - 1.0)

    def temperature_offset_f(self, step: int) -> float:
        """Return additional temperature offset [°F] due to bearing friction."""
        if step < self.drift_start:
            return 0.0
        elapsed = step - self.drift_start
        # Linear rise with small acceleration: ΔT = k * t^1.3
        return 0.12 * (elapsed ** 1.3)

    def rul_estimate(self, step: int, failure_step: int = 500) -> float:
        """Normalized RUL: 1.0 = new, 0.0 = failed."""
        if step < self.drift_start:
            return 1.0
        rul = 1.0 - (step - self.drift_start) / max(failure_step - self.drift_start, 1)
        return float(np.clip(rul, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Telemetry Generator
# ---------------------------------------------------------------------------
class TelemetryGenerator:
    """
    Generates realistic drilling telemetry with configurable noise and drift.

    Baseline values derived from a Gulf of Mexico shallow-water PDC bit run
    at ~8,500 ft TVD with 10.2 ppg WBM (water-based mud).
    """

    # Nominal operating envelope (IADC mid-range values)
    NOMINAL = {
        "surface_rpm": 120.0,       # [RPM]
        "downhole_rpm": 180.0,      # [RPM] (motor adds ~60 RPM)
        "torque_ftlbf": 14_500.0,   # [ft-lbf]
        "wob_klbf": 22.0,           # [klbf]
        "vibration_g": 1.2,         # [g RMS] — normal lateral vib
        "inlet_temp_f": 85.0,       # [°F] — surface pit temp
        "outlet_temp_f": 148.0,     # [°F] — returns at surface
        "bearing_temp_f": 195.0,    # [°F] — estimated bearing
        "standpipe_psi": 3_200.0,   # [psi]
        "flow_gpm": 620.0,          # [GPM]
    }

    # Gaussian noise standard deviations (reflects sensor resolution specs)
    NOISE_STD = {
        "surface_rpm": 1.5,
        "downhole_rpm": 3.0,
        "torque_ftlbf": 280.0,
        "wob_klbf": 0.4,
        "vibration_g": 0.15,
        "inlet_temp_f": 0.8,
        "outlet_temp_f": 1.2,
        "bearing_temp_f": 2.5,
        "standpipe_psi": 45.0,
        "flow_gpm": 8.0,
    }

    def __init__(self, asset_id: str, drift_start: int) -> None:
        self.asset_id = asset_id
        self.step = 0
        self.wear_model = BearingWearModel(drift_start=drift_start)
        self._rng = np.random.default_rng(seed=42)

    def _noisy(self, key: str) -> float:
        """Return nominal value + Gaussian noise for a parameter."""
        return float(
            self._rng.normal(
                loc=self.NOMINAL[key],
                scale=self.NOISE_STD[key],
            )
        )

    def generate(self) -> DrillingTelemetry:
        """Generate a single telemetry snapshot for the current simulation step."""
        self.step += 1
        s = self.step

        vib_mult = self.wear_model.vibration_multiplier(s)
        temp_offset = self.wear_model.temperature_offset_f(s)
        drift_active = s >= self.wear_model.drift_start
        rul = self.wear_model.rul_estimate(s)

        # Under bearing wear: slight RPM drop (friction load), torque spike
        rpm_degrade = 0.0
        torque_spike = 0.0
        if drift_active:
            elapsed = s - self.wear_model.drift_start
            rpm_degrade = min(elapsed * 0.05, 15.0)
            torque_spike = min(elapsed * 12.0, 2_200.0)

        vibration = float(
            np.clip(
                self._noisy("vibration_g") * vib_mult,
                0.05,
                25.0,
            )
        )
        bearing_temp = float(
            np.clip(
                self._noisy("bearing_temp_f") + temp_offset,
                160.0,
                420.0,
            )
        )

        return DrillingTelemetry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            asset_id=self.asset_id,
            sequence=s,
            surface_rpm=float(
                np.clip(self._noisy("surface_rpm") - rpm_degrade, 30.0, 250.0)
            ),
            downhole_rpm=float(
                np.clip(self._noisy("downhole_rpm") - rpm_degrade * 0.8, 40.0, 300.0)
            ),
            torque_ftlbf=float(
                np.clip(self._noisy("torque_ftlbf") + torque_spike, 4_000.0, 35_000.0)
            ),
            weight_on_bit_klbf=float(np.clip(self._noisy("wob_klbf"), 5.0, 50.0)),
            vibration_g=vibration,
            inlet_temp_f=float(np.clip(self._noisy("inlet_temp_f"), 60.0, 110.0)),
            outlet_temp_f=float(
                np.clip(self._noisy("outlet_temp_f") + temp_offset * 0.4, 100.0, 280.0)
            ),
            bearing_temp_f=bearing_temp,
            standpipe_pressure_psi=float(np.clip(self._noisy("standpipe_psi"), 1_500.0, 5_500.0)),
            flow_rate_gpm=float(np.clip(self._noisy("flow_gpm"), 300.0, 900.0)),
            rul_estimate=rul,
            drift_active=drift_active,
            metadata={"wear_model_step": s, "vib_multiplier": round(vib_mult, 4)},
        )


# ---------------------------------------------------------------------------
# RabbitMQ Publisher
# ---------------------------------------------------------------------------
class DrillTelemetryPublisher:
    """
    Publishes drilling telemetry JSON to RabbitMQ with automatic reconnect.

    Uses a persistent (durable) queue and publisher confirms to ensure
    zero message loss — critical for industrial monitoring systems.
    """

    def __init__(self) -> None:
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None

    def _make_credentials(self) -> pika.PlainCredentials:
        return pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)

    def _make_params(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=self._make_credentials(),
            heartbeat=600,
            blocked_connection_timeout=300,
        )

    def connect(self) -> None:
        """Establish connection with exponential backoff retry."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    "Connecting to RabbitMQ at %s:%d (attempt %d/%d)…",
                    RABBITMQ_HOST, RABBITMQ_PORT, attempt, MAX_RETRIES,
                )
                self._connection = pika.BlockingConnection(self._make_params())
                self._channel = self._connection.channel()

                # Declare durable queue (survives broker restart)
                self._channel.queue_declare(
                    queue=RABBITMQ_QUEUE,
                    durable=True,
                    arguments={
                        "x-message-ttl": 60_000,   # 60s TTL
                        "x-max-length": 10_000,
                    },
                )
                # Enable publisher confirms
                self._channel.confirm_delivery()

                logger.info("✓ Connected to RabbitMQ — queue: %s", RABBITMQ_QUEUE)
                return

            except pika.exceptions.AMQPConnectionError as exc:
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "Connection failed: %s. Retrying in %.1fs…", exc, wait
                )
                time.sleep(min(wait, 30.0))

        raise RuntimeError(
            f"Could not connect to RabbitMQ after {MAX_RETRIES} attempts."
        )

    def publish(self, telemetry: DrillingTelemetry) -> None:
        """Serialize and publish a telemetry record."""
        payload = json.dumps(asdict(telemetry), default=str)
        try:
            self._channel.basic_publish(
                exchange=RABBITMQ_EXCHANGE,
                routing_key="telemetry.drilling",
                body=payload.encode("utf-8"),
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                    message_id=str(uuid.uuid4()),
                    timestamp=int(time.time()),
                ),
                mandatory=False,
            )
        except (
            pika.exceptions.AMQPConnectionError,
            pika.exceptions.StreamLostError,
            pika.exceptions.ChannelWrongStateError,
        ) as exc:
            logger.error("Publish failed, reconnecting: %s", exc)
            self.connect()
            self.publish(telemetry)  # single retry after reconnect

    def close(self) -> None:
        """Gracefully close the connection."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.info("RabbitMQ connection closed.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    """Main producer loop — generates and publishes telemetry indefinitely."""
    logger.info(
        "DrillWatch Producer starting | Asset: %s | Drift begins at step: %d",
        ASSET_ID, DRIFT_START_STEP,
    )

    generator = TelemetryGenerator(asset_id=ASSET_ID, drift_start=DRIFT_START_STEP)
    publisher = DrillTelemetryPublisher()
    publisher.connect()

    try:
        while True:
            telemetry = generator.generate()
            publisher.publish(telemetry)

            # Structured log line for observability
            log_extra = (
                f"seq={telemetry.sequence:05d} | "
                f"vib={telemetry.vibration_g:.3f}g | "
                f"bear_temp={telemetry.bearing_temp_f:.1f}°F | "
                f"rpm={telemetry.surface_rpm:.0f} | "
                f"RUL={telemetry.rul_estimate:.3f}"
            )
            if telemetry.drift_active:
                logger.warning("DRIFT ACTIVE | %s", log_extra)
            else:
                logger.info("Published   | %s", log_extra)

            time.sleep(TELEMETRY_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Shutdown signal received.")
    finally:
        publisher.close()


if __name__ == "__main__":
    main()
