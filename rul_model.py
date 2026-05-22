"""
consumer.py — DrillWatch Predictor & Anomaly Detection Service
==============================================================
Subscribes to the RabbitMQ drill.telemetry queue, runs the moving-average
anomaly detector and RUL predictor, then forwards processed data to the
FastAPI backend via HTTP POST.

Concurrency model: Single-threaded RabbitMQ consumer with synchronous HTTP
forwarding. For high-throughput production use, replace with aio-pika +
asyncio HTTP client (httpx) or a multi-threaded worker pool.
"""

import json
import logging
import os
import time
from dataclasses import asdict
from typing import Optional

import pika
import pika.exceptions
import requests
import requests.exceptions

from anomaly_detector import MovingAverageAnomalyDetector, AnomalyAlert
from rul_model import RULPredictor

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("drillwatch.consumer")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER: str = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS: str = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_QUEUE: str = os.getenv("RABBITMQ_QUEUE", "drill.telemetry")

API_HOST: str = os.getenv("API_HOST", "localhost")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
API_BASE_URL: str = f"http://{API_HOST}:{API_PORT}"

ANOMALY_WINDOW: int = int(os.getenv("ANOMALY_WINDOW", "30"))
ALERT_SIGMA_THRESHOLD: float = float(os.getenv("ALERT_SIGMA_THRESHOLD", "3.0"))

MAX_RETRIES: int = 15
RETRY_BACKOFF_BASE: float = 2.0


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------
class DrillWatchAPIClient:
    """Simple HTTP client for posting processed telemetry to the FastAPI backend."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def post_telemetry(self, telemetry: dict) -> bool:
        """Forward a telemetry record to the API cache."""
        try:
            resp = self._session.post(
                f"{self.base_url}/ingest/telemetry",
                json=telemetry,
                timeout=3.0,
            )
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException as exc:
            logger.error("Failed to POST telemetry to API: %s", exc)
            return False

    def post_alert(self, alert: AnomalyAlert) -> bool:
        """Forward an anomaly alert to the API."""
        try:
            resp = self._session.post(
                f"{self.base_url}/ingest/alert",
                json=asdict(alert),
                timeout=3.0,
            )
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException as exc:
            logger.error("Failed to POST alert to API: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Consumer Service
# ---------------------------------------------------------------------------
class DrillWatchConsumer:
    """
    RabbitMQ consumer that processes drilling telemetry in real time.

    Pipeline per message:
        1. Deserialize JSON payload
        2. Feed to MovingAverageAnomalyDetector (3σ check)
        3. Feed to RULPredictor
        4. Annotate telemetry record with predictions
        5. POST processed data + any alerts to FastAPI
        6. ACK message to RabbitMQ
    """

    def __init__(self) -> None:
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel = None
        self._anomaly_detector = MovingAverageAnomalyDetector(
            window_size=ANOMALY_WINDOW,
            sigma_threshold=ALERT_SIGMA_THRESHOLD,
            warning_sigma=ALERT_SIGMA_THRESHOLD * 0.67,
        )
        self._rul_predictor = RULPredictor()
        self._api_client = DrillWatchAPIClient(API_BASE_URL)
        self._msg_count = 0

    def _make_connection_params(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS),
            heartbeat=600,
            blocked_connection_timeout=300,
        )

    def connect(self) -> None:
        """Establish RabbitMQ connection with exponential backoff."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    "Connecting to RabbitMQ (attempt %d/%d)…", attempt, MAX_RETRIES
                )
                self._connection = pika.BlockingConnection(self._make_connection_params())
                self._channel = self._connection.channel()

                self._channel.queue_declare(
                    queue=RABBITMQ_QUEUE,
                    durable=True,
                    arguments={"x-message-ttl": 60_000, "x-max-length": 10_000},
                )
                # Fair dispatch — process one message at a time
                self._channel.basic_qos(prefetch_count=1)

                logger.info("✓ Consumer connected — watching queue: %s", RABBITMQ_QUEUE)
                return

            except pika.exceptions.AMQPConnectionError as exc:
                wait = min(RETRY_BACKOFF_BASE ** attempt, 30.0)
                logger.warning("Broker unavailable: %s. Retry in %.1fs…", exc, wait)
                time.sleep(wait)

        raise RuntimeError(
            f"Could not connect to RabbitMQ after {MAX_RETRIES} attempts."
        )

    def _process_message(
        self,
        channel,
        method,
        properties,
        body: bytes,
    ) -> None:
        """
        Callback executed for each incoming RabbitMQ message.

        Implements: deserialize → anomaly check → RUL predict → API forward → ACK
        """
        self._msg_count += 1
        try:
            telemetry: dict = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON payload (seq unknown): %s", exc)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        seq = telemetry.get("sequence", "?")

        try:
            # --- Step 1: Anomaly Detection ---
            alert: Optional[AnomalyAlert] = self._anomaly_detector.ingest(telemetry)

            # --- Step 2: RUL Prediction ---
            rul_pred = self._rul_predictor.predict(telemetry)
            telemetry["rul_predicted"] = rul_pred.rul_score
            telemetry["rul_health_state"] = rul_pred.health_state
            telemetry["rul_confidence"] = rul_pred.confidence
            telemetry["rul_model_version"] = rul_pred.model_version

            # Annotate anomaly flag for the dashboard
            telemetry["is_anomaly"] = alert is not None
            telemetry["alert_severity"] = alert.severity if alert else None

            # --- Step 3: Forward to FastAPI ---
            self._api_client.post_telemetry(telemetry)

            if alert:
                self._api_client.post_alert(alert)
                logger.warning(
                    "[%s] Alert #%s | σ=%.2f | %s",
                    alert.severity, alert.alert_id,
                    alert.sigma_deviation, alert.message[:80],
                )

            # --- Step 4: Periodic stats log ---
            if self._msg_count % 50 == 0:
                window_stats = self._anomaly_detector.window_summary()
                logger.info(
                    "Stats | processed=%d | alerts=%d | vib_mean=%.3f | bear_temp_mean=%.1f",
                    self._msg_count,
                    self._anomaly_detector.alert_count,
                    window_stats.get("vibration_g", {}).get("mean", 0.0),
                    window_stats.get("bearing_temp_f", {}).get("mean", 0.0),
                )

            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as exc:
            logger.exception("Error processing message seq=%s: %s", seq, exc)
            # NACK with requeue=False to avoid poison-message loops
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start_consuming(self) -> None:
        """Start the blocking consume loop with automatic reconnection."""
        while True:
            try:
                self.connect()
                self._channel.basic_consume(
                    queue=RABBITMQ_QUEUE,
                    on_message_callback=self._process_message,
                )
                logger.info("Consumer ready — waiting for messages…")
                self._channel.start_consuming()

            except pika.exceptions.AMQPConnectionError as exc:
                logger.error("Connection lost: %s. Reconnecting…", exc)
                time.sleep(5.0)

            except KeyboardInterrupt:
                logger.info("Shutdown signal — stopping consumer.")
                if self._channel:
                    self._channel.stop_consuming()
                if self._connection and not self._connection.is_closed:
                    self._connection.close()
                break


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info(
        "DrillWatch Consumer starting | API: %s | Queue: %s | Window: %d | σ threshold: %.1f",
        API_BASE_URL, RABBITMQ_QUEUE, ANOMALY_WINDOW, ALERT_SIGMA_THRESHOLD,
    )
    consumer = DrillWatchConsumer()
    consumer.start_consuming()


if __name__ == "__main__":
    main()
