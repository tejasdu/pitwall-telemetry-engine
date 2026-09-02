# 🏎️ Pitwall Telemetry Engine MVP 1

A high-performance real-time Formula 1 telemetry ingestion, replay, and strategy inference engine built with **Python 3.12**, **FastAPI**, **Pydantic v2**, **Prometheus**, **Grafana**, **Redis 7 Streams**, and **`uv`**. 

---

## 📌 Project Overview

`pitwall-telemetry-engine` ingests live and historical F1 race telemetry from OpenF1, validates raw sensor streams using strict Pydantic v2 contracts, simulates real-time multi-driver race playback, tracks official FIA track flags (Green, Yellow, Safety Car, Red Flag Suspensions), and derives live strategic insights (such as corner entry deceleration gradients and DRS attack threats).

---

## 🏗️ Architecture & Data Flow

```text
       [ DATA SOURCE LAYER ]
       OpenF1 REST API (Live / Historical)
       ├── /v1/car_data      (Speed, Throttle, Brake, Gear, RPM, DRS)
       ├── /v1/intervals     (Position, Gap to Leader, Rival Intervals)
       ├── /v1/race_control  (Red / Yellow / Green Flags & FIA Stoppages)
       └── /v1/drivers       (Driver Numbers, Acronyms, Teams)
                 │
                 ▼
       [ INGESTION LAYER ] (src/pitwall_telemetry_engine/ingestion/)
       • openf1_client.py: HTTP Client (httpx) with session timeout resilience
       • replay.py: Async Stream Replayer with dynamic inter-tick sleep & pause detection
                 │
                 ▼
       [ DATA CONTRACTS LAYER ] (src/pitwall_telemetry_engine/schemas/)
       • CarData: Vehicle speed, RPM, throttle, brake %, DRS state
       • Driver: Driver numbers, names, acronyms, team colors
       • Intervals: Real-time leader gaps and rival intervals
       • RaceControlMessage: Track flags & FIA race suspension events
       • Sessions: Grand Prix circuit & session metadata
                 │
                 ▼
       [ PROCESSING & INFERENCES ] (src/pitwall_telemetry_engine/metrics/)
       • calculate_deceleration(): Speed delta over time (Δv / Δt)
       • is_heavy_braking(): Cornering deceleration detection
       • is_drs_threat(): Real-time DRS attack proximity alerts (<1.000s)
       • is_full_throttle(): Wide-open throttle zone detector
       • update_race_status(): Track flag status code mapping (Green, Yellow, Red, SC)
                 │
                 ├───────────────────────────────────────────────┐
                 ▼                                               ▼
       [ STORAGE BUFFER LAYER ]                        [ OBSERVABILITY LAYER ]
       • storage/redis_client.py                       • metrics/exporter.py (Prometheus)
       • Redis 7 Stream (`f1:telemetry:raw`)           • Grafana Digital Pit-Wall Dashboard
       • Sliding Buffer (`MAXLEN ~ 5000`)              • Live Speed, RPM, Pedals & Flag Banner
```

---

## 🚀 Completed Features

- [x] **Strict Pydantic v2 Schemas**: Type validation for `car_data`, `drivers`, `intervals`, `race_control`, and `sessions`.
- [x] **OpenF1 Ingestion Client**: Centralized API helper module with session resolution, driver registry lookup, and 60s timeout resilience.
- [x] **Multi-Driver Real-Time Stream Replayer**:
  - Dynamic inter-tick calculation ($\Delta t = t_{i+1} - t_i$).
  - Configurable playback multipliers ($1\times, 2\times, 5\times, 10\times$).
  - Synchronized multi-car wheel-to-wheel replay (e.g. Carlos Sainz `#55` vs. Lando Norris `#1`).
  - Session pause detection with smart 3s fast-forward clamping (`max_pause_seconds`) to handle red flag stoppages.
- [x] **Telemetry Inferences Engine**: Heavy braking deceleration rates ($\text{km/h/s}$), wide-open throttle detection, and live DRS attack threat alerts.
- [x] **FIA Race Control Flag Synchronization**: Real-time track flag detection and status codes (Green, Yellow, Safety Car, Red Flag Race Suspension).
- [x] **Prometheus Metrics Exporter**: Background HTTP server on port `8000` exposing Prometheus Gauges and Counters for speed, throttle, brake, RPM, gear, DRS status, race flag code, and heavy braking totals.
- [x] **Grafana Digital Pit-Wall Dashboard**: Full provisioned dashboard on port `3000` with 1s refresh, speedometers, RPM dials, pedal wave graphs, DRS threat indicators, and a prominent glowing Track Flag Status banner.
- [x] **Redis 7 Stream Message Buffer**: Decoupled asynchronous in-memory buffer publishing to `f1:telemetry:raw` with sliding-window eviction (`MAXLEN ~ 5000`).

---

## 📂 Project Directory Structure

```text
pitwall-telemetry-engine/
├── docker-compose.yml                 # Docker Compose (Prometheus + Grafana)
├── pyproject.toml                     # Build configuration and dependencies (uv)
├── .python-version                    # Python version pin (3.12)
├── README.md                          # Project documentation
├── notes.txt                          # Future architecture blueprint & notes
├── prometheus/
│   └── prometheus.yml                 # Prometheus scrape configuration
├── grafana/
│   ├── provisioning/                  # Auto-provisioned datasources & dashboards
│   │   ├── datasources/
│   │   └── dashboards/
│   └── dashboards/
│       └── pitwall_dashboard.json     # Declarative F1 Pit-Wall Dashboard JSON
└── src/
    └── pitwall_telemetry_engine/
        ├── __init__.py                # Package initialization
        ├── main.py                    # Synchronized battle stream & flag engine
        ├── schemas/                   # Pydantic v2 data models
        │   ├── __init__.py
        │   ├── car_data.py            # CarData model
        │   ├── driver.py              # Driver metadata model
        │   ├── intervals.py           # Timing intervals model
        │   ├── race_control.py        # FIA Race Control track flag model
        │   └── sessions.py            # Session metadata model
        ├── ingestion/                 # Data fetchers & streaming simulator
        │   ├── __init__.py
        │   ├── openf1_client.py       # OpenF1 HTTP API client
        │   └── replay.py              # Async telemetry stream replayer
        ├── metrics/                   # Strategy calculations & observability
        │   ├── __init__.py
        │   ├── inferences.py          # Deceleration & DRS inference logic
        │   └── exporter.py            # Prometheus metrics HTTP exporter
        └── storage/                   # High-throughput message queuing
            ├── __init__.py
            └── redis_client.py        # Redis 7 Stream buffer publisher
```

---

## 🛠️ Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) installed on your system.
- Docker Desktop installed and running.

### Installation & Running

1. **Start the Prometheus and Grafana Docker Stack**:
   ```bash
   docker compose up -d
   ```

2. **Sync dependencies and virtual environment**:
   ```bash
   uv sync
   ```

3. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

4. **Run the telemetry engine**:
   ```bash
   pitwall-telemetry-engine
   ```

5. **View the live F1 Digital Pit-Wall Dashboard**:
   Open **[http://localhost:3000/d/f1-pitwall-live](http://localhost:3000/d/f1-pitwall-live)** in your browser!
