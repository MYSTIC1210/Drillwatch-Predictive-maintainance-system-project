# DrillWatch — Industrial Predictive Maintenance System

> High-availability, real-time predictive maintenance platform for drilling assets.
> Architected to NOV/Baker Hughes-grade standards: decoupled microservices, resilient
> messaging, anomaly detection, and a live operations dashboard.

---

## Project Structure

```
drillwatch/
├── README.md                          ← You are here
│
├── docker-compose.yml                 ← Spins up ALL services + RabbitMQ broker
│
├── .github/
│   └── workflows/
│       └── ci.yml                     ← GitHub Actions: pytest + flake8 CI pipeline
│
├── infra/
│   └── rabbitmq/
│       └── definitions.json           ← RabbitMQ queue/exchange bootstrap config
│
├── producer/
│   ├── Dockerfile                     ← Container for the telemetry producer
│   ├── requirements.txt
│   ├── producer.py                    ← MAIN: Generates synthetic drilling telemetry
│   │                                     Simulates sensor drift (bearing wear model)
│   │                                     Publishes JSON messages to RabbitMQ
│   └── tests/
│       └── test_producer.py           ← Unit tests for telemetry generation
│
├── consumer/
│   ├── Dockerfile                     ← Container for the predictor/consumer service
│   ├── requirements.txt
│   ├── consumer.py                    ← MAIN: Subscribes to RabbitMQ
│   │                                     Moving Average Anomaly Detector
│   │                                     3-sigma Critical Alert flagging
│   │                                     RandomForest RUL placeholder
│   ├── anomaly_detector.py            ← Modular: rolling stats + alert logic
│   ├── rul_model.py                   ← Modular: RUL prediction (RF placeholder)
│   └── tests/
│       └── test_anomaly_detector.py   ← Unit tests for anomaly detection logic
│
├── api/
│   ├── Dockerfile                     ← Container for the FastAPI backend
│   ├── requirements.txt
│   ├── main.py                        ← MAIN: FastAPI app
│   │                                     In-memory cache (deque, last 100 points)
│   │                                     GET /telemetry  — last N readings
│   │                                     GET /alerts     — active critical alerts
│   │                                     GET /health     — system health status
│   └── tests/
│       └── test_api.py                ← Unit tests for API endpoints
│
└── frontend/
    ├── Dockerfile                     ← Container for the React dashboard
    ├── package.json
    ├── tailwind.config.js
    ├── vite.config.js
    └── src/
        ├── main.jsx                   ← React entry point
        ├── App.jsx                    ← Root layout + polling logic
        ├── index.css                  ← Tailwind base + custom industrial CSS vars
        └── components/
            ├── SystemHealthBar.jsx    ← High-visibility operational status banner
            ├── TelemetryChart.jsx     ← Recharts real-time line chart component
            ├── AlertFeed.jsx          ← Scrolling critical alert log
            └── MetricsPanel.jsx       ← Live KPI gauges (RPM, Torque, Temp, Vib)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PRODUCER (Python)         BROKER (RabbitMQ)                │
│  ─────────────────         ─────────────────                │
│  Simulates drilling   ──►  Queue: drill.telemetry           │
│  telemetry w/ drift        Exchange: drill.exchange         │
└─────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────┐
│  CONSUMER (Python)                                          │
│  ──────────────────                                         │
│  Anomaly Detector (3σ rolling window)                       │
│  RUL Model (RandomForest placeholder)                       │
│  Pushes alerts + processed data → FastAPI via HTTP          │
└─────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────┐
│  FASTAPI BACKEND                                            │
│  ───────────────                                            │
│  In-memory cache (deque[100])                               │
│  GET /telemetry  GET /alerts  GET /health                   │
└─────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────┐
│  REACT DASHBOARD (Vite + Tailwind + Recharts)               │
│  Polls /telemetry & /alerts every 2s                        │
│  System Health Bar │ Live Charts │ Alert Feed │ KPI Panel   │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Docker 24+ and Docker Compose v2
- Node 18+ (only needed for local frontend dev outside Docker)

### Launch the full stack
```bash
git clone <repo>
cd drillwatch
docker compose up --build
```

### Access Points
| Service         | URL                          |
|----------------|------------------------------|
| Dashboard       | http://localhost:5173        |
| FastAPI docs    | http://localhost:8000/docs   |
| RabbitMQ UI     | http://localhost:15672       |

RabbitMQ default credentials: `guest` / `guest`

---

## Environment Variables

All configs are injected via environment variables (see `docker-compose.yml`):

| Variable              | Default              | Description                        |
|----------------------|----------------------|------------------------------------|
| `RABBITMQ_HOST`       | `rabbitmq`           | Broker hostname                    |
| `RABBITMQ_PORT`       | `5672`               | AMQP port                          |
| `RABBITMQ_USER`       | `guest`              | Broker username                    |
| `RABBITMQ_PASS`       | `guest`              | Broker password                    |
| `RABBITMQ_QUEUE`      | `drill.telemetry`    | Queue name                         |
| `API_HOST`            | `api`                | FastAPI host (consumer → API)      |
| `API_PORT`            | `8000`               | FastAPI port                       |
| `TELEMETRY_INTERVAL`  | `1.0`                | Seconds between telemetry publishes|
| `DRIFT_START_STEP`    | `200`                | Step at which sensor drift begins  |
| `ANOMALY_WINDOW`      | `30`                 | Rolling window size for 3σ detector|

---

## Sensor Drift Model

The producer simulates **bearing wear** using a physics-inspired drift model:

- **Vibration drift**: Exponential growth starting at `DRIFT_START_STEP`
- **Temperature drift**: Coupled linear rise (friction → heat)
- **RPM / Torque**: Slight degradation as wear progresses (load compensation)

This mimics real IADC-documented failure progression curves for rotary steerable systems.

---

## Running Tests Locally

```bash
# Producer tests
cd producer && pip install -r requirements.txt && pytest tests/ -v

# Consumer tests
cd consumer && pip install -r requirements.txt && pytest tests/ -v

# API tests
cd api && pip install -r requirements.txt && pytest tests/ -v
```

---

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`) runs on every push/PR:
1. `flake8` linting across all Python services
2. `pytest` for producer, consumer, and API test suites
3. Docker build validation for all three service images
