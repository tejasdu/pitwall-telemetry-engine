# 🏎️ Pitwall Telemetry Engine

A high-performance real-time Formula 1 telemetry ingestion, replay, and strategy inference engine built with **Python 3.12**, **FastAPI**, **Pydantic v2**, and **`uv`**.

---

## 📌 Project Overview

`pitwall-telemetry-engine` ingests live and historical F1 race telemetry from OpenF1, validates raw sensor streams using strict Pydantic v2 contracts, simulates real-time race playback, and derives live strategic insights (such as corner entry deceleration gradients and DRS attack threats).

---

## 🏗️ Architecture & Data Flow

```text
       [ DATA SOURCE LAYER ]
       OpenF1 REST API (Live / Historical)
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
       • Sessions: Grand Prix circuit & session metadata
                 │
                 ▼
       [ PROCESSING & INFERENCES ] (src/pitwall_telemetry_engine/metrics/)
       • calculate_deceleration(): Speed delta over time (Δv / Δt)
       • is_heavy_braking(): Threshold detection for cornering deceleration events
                 │
                 ▼
       [ OUTPUT / OBSERVABILITY ]
       • Real-time Terminal Ticker (CLI)
       • [Upcoming] Redis 7 Stream Buffer (`f1:telemetry:raw`)
       • [Upcoming] Prometheus Exporter (`/metrics`) & Grafana Dashboard
```

---

## 🚀 Current Progress & Features (WIP)

- [x] **Strict Pydantic v2 Schemas**: Type validation for `car_data`, `drivers`, `intervals`, and `sessions`, handling real-world edge cases like `drs: int | None` and lapped driver strings (`"+1 LAP"`).
- [x] **OpenF1 Ingestion Client**: Centralized API helper module with session resolution, driver registry lookup, and configurable timeouts.
- [x] **Real-Time Historical Stream Replayer**:
  - Dynamic inter-tick calculation ($\Delta t = t_{i+1} - t_i$).
  - Configurable playback multipliers ($1\times, 2\times, 5\times, 10\times$).
  - Session pause detection with smart fast-forward clamping (`max_pause_seconds`) to handle overnight or red flag delays without freezing.
- [ ] **Telemetry Inferences (In Progress)**: Heavy braking deceleration rates and DRS threat alerts.
- [ ] **Redis Message Buffer**: Decoupled producer-consumer stream buffer.
- [ ] **Prometheus & Grafana**: Time-series metrics export and Digital Pit-Wall dashboard.

---

## 📂 Project Directory Structure

```text
pitwall-telemetry-engine/
├── pyproject.toml                     # Build configuration and dependencies (uv)
├── .python-version                    # Python version pin (3.12)
├── README.md                          # Project documentation
├── car_data.json                      # Sample historical telemetry payload
├── driver_data.json                   # Sample full-session dataset
└── src/
    └── pitwall_telemetry_engine/
        ├── __init__.py                # Package initialization
        ├── main.py                    # Main runner & CLI entrypoint
        ├── schemas/                   # Pydantic v2 data models
        │   ├── __init__.py
        │   ├── car_data.py            # CarData model
        │   ├── driver.py              # Driver metadata model
        │   ├── intervals.py           # Timing intervals model
        │   └── sessions.py            # Session metadata model
        ├── ingestion/                 # Data fetchers & streaming simulator
        │   ├── __init__.py
        │   ├── openf1_client.py       # OpenF1 HTTP API client
        │   └── replay.py              # Async telemetry stream replayer
        └── metrics/                   # Strategy calculations & inferences
            ├── __init__.py
            └── inferences.py          # Deceleration & braking inference logic
```

---

## 🛠️ Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) installed on your system.

### Installation & Environment Setup

1. **Sync dependencies and create virtual environment**:
   ```bash
   uv sync
   ```

2. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

3. **Run the telemetry engine**:
   ```bash
   pitwall-telemetry-engine
   ```
   *or directly via `uv`:*
   ```bash
   uv run python src/pitwall_telemetry_engine/main.py
   ```

---

## 🧭 Roadmap

| Sprint / Phase | Focus | Status |
| :--- | :--- | :--- |
| **Phase 1** | Data Contracts & Pydantic v2 Schemas | ✅ Complete |
| **Phase 2** | Ingestion Client & Real-Time Stream Replayer | ✅ Complete |
| **Phase 3** | Strategy Inferences (Braking deltas, DRS threat detector) | 🟡 In Progress |
| **Phase 4** | Redis 7 Stream Buffer (`XADD` / `XREADGROUP`) | ⏳ Upcoming |
| **Phase 5** | Prometheus Exporter & Grafana Pit-Wall Dashboard | ⏳ Upcoming |
