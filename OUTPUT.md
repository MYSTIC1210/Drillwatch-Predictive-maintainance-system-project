# Sample Output — DrillWatch Predictive Maintenance System

## System Startup (docker compose up)

```
✅ rabbitmq       — ready (amqp://localhost:5672)
✅ postgres        — ready (5432)
✅ api             — listening on :8000
✅ producer        — publishing telemetry at 20 Hz
✅ consumer        — anomaly detector trained, consuming queue
✅ frontend        — served on :3000 (nginx)
```

## Producer Log

```
[Producer] Sensor SIM-001 → depth=1823.4m RPM=118.2 torque=8,912Nm temp=67.1°C vib=0.41g
[Producer] Sensor SIM-001 → depth=1823.5m RPM=117.9 torque=9,102Nm temp=67.4°C vib=0.44g
[Producer] Sensor SIM-001 → depth=1823.6m RPM=103.2 torque=10,841Nm temp=71.2°C vib=2.31g ⚠
```

## Consumer / Anomaly Detector Log

```
[Consumer] Model trained on 500 baseline samples
[Consumer] Consuming from queue: drill.telemetry
[ALERT] SIM-001 | HIGH VIBRATION — possible bearing wear | confidence=1.00
[ALERT] SIM-001 | HIGH TORQUE — possible stick-slip      | confidence=0.67
```

## RUL Model Prediction

```
[RUL] SIM-001 — Remaining Useful Life estimate: 14.2 hours
[RUL] Maintenance recommended within next shift
[RUL] Confidence interval: [11.8h — 17.1h]
```

## API — GET /api/alerts

```json
[
  {
    "sensor_id": "SIM-001",
    "timestamp": "2025-11-12T14:32:11Z",
    "detail": "HIGH VIBRATION — possible bearing wear",
    "rul_hours": 14.2,
    "confidence": 1.0,
    "severity": "critical"
  }
]
```

## Test Suite Results

```
pytest api/tests/ consumer/tests/ producer/tests/ -v

api/tests/test_api.py::test_health_check          PASSED
api/tests/test_api.py::test_ingest_telemetry      PASSED
api/tests/test_api.py::test_get_alerts            PASSED
consumer/tests/test_anomaly_detector.py::test_nominal_data    PASSED
consumer/tests/test_anomaly_detector.py::test_anomaly_spike   PASSED
consumer/tests/test_anomaly_detector.py::test_double_free_safe PASSED
producer/tests/test_producer.py::test_frame_schema            PASSED
producer/tests/test_producer.py::test_drift_injection         PASSED

8 passed in 3.41s
```

## Frontend Dashboard

```
KPIs:  RPM 117.9  |  Torque 10,841 Nm  |  Temp 71.2°C  |  Vib 2.31g 🔴
RUL:   14.2 hrs remaining
Alerts: 2 CRITICAL  |  System Health: 61%
Charts: Real-time telemetry + anomaly markers + RUL trend
```
