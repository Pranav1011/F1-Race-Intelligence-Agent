# ============================================
# F1 Race Intelligence Agent - Makefile
# ============================================

.PHONY: help setup up down logs shell ingest ingest-year ingest-race ingest-test test lint format clean

# Default target
help:
	@echo "F1 Race Intelligence Agent - Development Commands"
	@echo ""
	@echo "Setup & Run:"
	@echo "  make setup       - Initial setup (copy .env, pull images, setup Ollama)"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
	@echo "  make restart     - Restart all services"
	@echo "  make logs        - Tail logs from all services"
	@echo ""
	@echo "Development:"
	@echo "  make shell       - Open shell in backend container"
	@echo "  make shell-fe    - Open shell in frontend container"
	@echo "  make test        - Run backend tests"
	@echo "  make lint        - Run linters (backend + frontend)"
	@echo "  make format      - Format code (backend + frontend)"
	@echo ""
	@echo "Data Ingestion:"
	@echo "  make ingest      - Run full data ingestion (2018-2024)"
	@echo "  make ingest-year YEAR=2024  - Ingest specific year"
	@echo "  make ingest-race YEAR=2024 ROUND=1  - Ingest specific race"
	@echo "  make ingest-test - Quick test with 2024 Bahrain GP (no telemetry)"
	@echo ""
	@echo "Database:"
	@echo "  make db-shell    - Open psql shell to TimescaleDB"
	@echo "  make neo4j-shell - Open cypher-shell to Neo4j"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean       - Remove containers and volumes"
	@echo "  make clean-all   - Remove everything including images"

# ============================================
# Setup
# ============================================

setup:
	@echo "Setting up F1 Race Intelligence Agent..."
	@cp -n .env.example .env 2>/dev/null || echo ".env already exists"
	@echo "Please edit .env and add your API keys."
	@echo ""
	@echo "Pulling Docker images..."
	docker compose pull
	@echo ""
	@echo "Setting up Ollama with Llama 3.2..."
	docker compose up -d ollama
	@sleep 5
	docker exec f1_ollama ollama pull llama3.2 || echo "Failed to pull model - you can do this later"
	docker compose down
	@echo ""
	@echo "Setup complete! Run 'make up' to start services."

# ============================================
# Docker Compose
# ============================================

up:
	docker compose up -d
	@echo ""
	@echo "Services starting..."
	@echo ""
	@echo "  Frontend:     http://localhost:3000"
	@echo "  Backend API:  http://localhost:8000"
	@echo "  API Docs:     http://localhost:8000/docs"
	@echo "  Neo4j Browser: http://localhost:7474"
	@echo ""
	@echo "Run 'make logs' to see output"

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend

# ============================================
# Development Shells
# ============================================

shell:
	docker compose exec backend bash

shell-fe:
	docker compose exec frontend sh

db-shell:
	docker compose exec timescaledb psql -U f1 -d f1_telemetry

neo4j-shell:
	docker compose exec neo4j cypher-shell -u neo4j -p f1_password

redis-shell:
	docker compose exec redis redis-cli

# ============================================
# Testing & Linting
# ============================================

test:
	docker compose exec backend pytest -v

test-cov:
	docker compose exec backend pytest -v --cov=. --cov-report=html

lint:
	docker compose exec backend ruff check .
	cd frontend && pnpm lint

format:
	docker compose exec backend ruff format .
	cd frontend && pnpm format

type-check:
	docker compose exec backend mypy .
	cd frontend && pnpm type-check

# ============================================
# Data Ingestion
# ============================================

ingest:
	@echo "Running full data ingestion (2018-2024)..."
	docker compose exec backend python -m ingestion.orchestrator

ingest-year:
ifndef YEAR
	$(error YEAR is required. Usage: make ingest-year YEAR=2024)
endif
	@echo "Ingesting $(YEAR) season..."
	docker compose exec backend python -m ingestion.orchestrator --years $(YEAR)

ingest-race:
ifndef YEAR
	$(error YEAR is required. Usage: make ingest-race YEAR=2024 ROUND=1)
endif
ifndef ROUND
	$(error ROUND is required. Usage: make ingest-race YEAR=2024 ROUND=1)
endif
	@echo "Ingesting $(YEAR) Round $(ROUND)..."
	docker compose exec backend python -m ingestion.orchestrator --race $(YEAR):$(ROUND)

ingest-test:
	@echo "Test ingestion with 2024 Bahrain GP (Round 1)..."
	docker compose exec backend python -m ingestion.orchestrator --race 2024:1 --no-telemetry

# ============================================
# Cleanup
# ============================================

clean:
	docker compose down -v
	@echo "Removed containers and volumes"

clean-all:
	docker compose down -v --rmi all
	@echo "Removed containers, volumes, and images"

# ============================================
# Production Build (for later)
# ============================================

build:
	docker compose build

build-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml build
