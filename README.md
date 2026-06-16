# wan-provider-emulator

**Purpose:** Simulate Megaport and Equinix Fabric v4 APIs for demo and integration development  
**Stack:** Python 3.12, Flask, Gunicorn  
**Container:** Single Docker image, all routes on one port

---

## What This Is

A self-contained Flask server that simulates the Megaport and Equinix Fabric v4 APIs. Point your workflows and automation agents at this server instead of live provider endpoints during development or demos.

Response schemas match the real APIs exactly (sourced from the official Megaport Postman collection and Equinix Fabric v4 OpenAPI spec v4.15). Async behavior is simulated: Equinix returns 202 + PROVISIONING, transitions to PROVISIONED after a configurable number of polls.

Both providers' utilization endpoints are mocked — Equinix stats return a `BandwidthUtilization` JSON object, Megaport returns genuine Prometheus OpenMetrics text with per-VXC labeled counters.

---

## Files

```
README.md                   this file
mock_server.py              Flask application
requirements.txt            Python dependencies
Dockerfile                  container build
docker-compose.yml          compose file for host-network deployment
openapi-megaport-mock.yaml  OpenAPI 3.0 spec for Megaport routes
openapi-equinix-mock.yaml   OpenAPI 3.0 spec for Equinix routes
seed-data.json              initial circuit state loaded on startup
```

---

## Quick Start

```bash
# Build
docker build --network=host -t wan-provider-emulator .

# Run with defaults
docker run -p 5000:5000 wan-provider-emulator

# Or with compose (uses host networking — required on some Docker setups)
docker compose up -d
```

Base URL: `http://localhost:5000`

Two integration definitions are needed — one per provider spec (see openapi-*.yaml files).
Both point to the same server; the base paths `/megaport` and `/equinix` differentiate them.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEGAPORT_DELAY_SECONDS` | `3` | Simulated propagation delay before 200 on VXC update |
| `EQUINIX_POLL_ROUNDS` | `3` | GET polls before connection transitions to PROVISIONED |
| `PORT` | `5000` | Listen port |

---

## Demo Cheat Sheet

```bash
BASE=http://localhost:5000

# Seed high utilization on a Megaport circuit
curl -X POST $BASE/mock/seed/utilization/a49cf3f1-20a1-4390-93aa-5005bdafe3d7 \
  -H 'Content-Type: application/json' -d '{"utilization_pct": 94}'

# Check Megaport OpenMetrics (Prometheus byte counters)
curl $BASE/megaport/v1/openmetrics

# Check Equinix connection stats (Mbps utilization)
curl "$BASE/equinix/fabric/v4/connections/3a58dd05-f46d-4b1d-a154-2e85c396ea62/stats?startDateTime=2026-06-16T00:00:00Z&endDateTime=2026-06-16T12:00:00Z&viewPoint=aSide"

# Drop utilization for revert demo
curl -X POST $BASE/mock/seed/utilization/a49cf3f1-20a1-4390-93aa-5005bdafe3d7 \
  -H 'Content-Type: application/json' -d '{"utilization_pct": 35}'

# Full state dump
curl $BASE/mock/state

# Reset between demo runs
curl -X POST $BASE/mock/reset
```

---

## Pre-Seeded Circuits

| circuit_id | provider | name | bandwidth | max | utilization |
|------------|----------|------|-----------|-----|-------------|
| `a49cf3f1-20a1-4390-93aa-5005bdafe3d7` | megaport | corp-ord-nyc-01    | 1000 Mbps | 10000 | 40% |
| `b72ef8c2-31b2-5501-a4bb-6116cebf4e48` | megaport | corp-dfw-lax-01    | 1000 Mbps | 10000 | 40% |
| `c14a2b3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d` | megaport | corp-sea-chi-01    | 500 Mbps  | 5000  | 62% |
| `d25b3c4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e` | megaport | corp-mia-nyc-01    | 2000 Mbps | 10000 | 28% |
| `3a58dd05-f46d-4b1d-a154-2e85c396ea62` | equinix  | corp-eqx-chi-ny-01 | 1000 Mbps | 10000 | 40% |
| `e36c4d5f-6a7b-8c9d-0e1f-2a3b4c5d6e7f` | equinix  | corp-eqx-sv-la-01  | 500 Mbps  | 5000  | 55% |
| `f47d5e6a-7b8c-9d0e-1f2a-3b4c5d6e7f8a` | equinix  | corp-eqx-dc-ny-01  | 2000 Mbps | 10000 | 33% |

All circuits reset to these values on `POST /mock/reset`.
