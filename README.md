# Algo Trading Platform

A private multi-user algorithmic trading platform with server-side strategy execution.

## Quick Start (Local Dev)

```bash
cp .env.example .env
# Fill in .env values
docker compose up -d
```

Backend API docs: http://localhost/api/docs  
Grafana: http://localhost:3001

## Architecture

```
nginx (443/80)
  ├── /api/* → FastAPI backend (port 8000)
  │               ├── PostgreSQL (data)
  │               ├── Redis (cache + pub/sub)
  │               └── Strategy Worker (Celery)
  └── /* → React frontend (port 80)
```

## Adding a Strategy

1. Create `backend/app/strategy/engines/your_strategy.py` extending `BaseStrategy`
2. Register it in `backend/app/strategy/registry.py`
3. Insert a row in the `strategies` table with the `engine_class` name

Strategies are **never** exposed via API. Users only see names and parameters.

## VPS Deployment

```bash
scp deployment/setup_vps.sh root@your-vps-ip:/root/
ssh root@your-vps-ip "bash setup_vps.sh"
```

## Project Structure

```
algo-platform/
├── backend/          FastAPI app, broker adapters, strategies, risk
├── frontend/         React + Tailwind dashboard
├── docker/           Dockerfiles
├── nginx/            Reverse proxy config
├── strategy/         Strategy engine files (mounted into containers)
├── monitoring/       Prometheus + Grafana configs
└── deployment/       VPS setup scripts
```
