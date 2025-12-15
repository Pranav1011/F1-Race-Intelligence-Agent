# F1 Race Intelligence Agent

An AI-powered Race Engineer Co-Pilot that provides conversational analysis of Formula 1 races, strategies, and telemetry data.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![Node](https://img.shields.io/badge/node-20+-green.svg)

## Overview

Ask natural language questions about F1 and get intelligent analysis with dynamic visualizations:

- *"Compare Verstappen and Norris's tire degradation in the 2024 Singapore GP"*
- *"What would've happened if Max pitted on lap 33 instead of lap 38?"*
- *"Show me Hamilton's speed trace through Sector 3 at Monaco"*
- *"Why did Ferrari's strategy fail at Silverstone 2024?"*

## Features

- **Conversational Interface** - Natural language queries about F1 data
- **Adaptive UI** - Interface transforms based on query type (telemetry traces, strategy timelines, comparisons)
- **Historical Analysis** - 7 years of data (2018-2024), 168 races, full telemetry
- **What-If Scenarios** - Explore alternative strategies using historical analogies
- **Long-Term Memory** - Remembers your preferences across sessions
- **Production-Grade** - Observability, error handling, graceful degradation

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                 │
│              Next.js 14 + Tailwind + Recharts                   │
│              Context-Aware Adaptive UI                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        API LAYER                                 │
│                  FastAPI + WebSocket                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT (LangGraph)                           │
│         Groq (Llama 3.3) → Gemini → Ollama fallback            │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ TimescaleDB  │    │    Neo4j     │    │   Qdrant     │
│  Telemetry   │    │   Knowledge  │    │    RAG       │
│              │    │    Graph     │    │   Vectors    │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Agent Framework | LangGraph |
| Primary LLM | Groq (Llama 3.3 70B) - Free tier |
| Backup LLM | Google Gemini, Ollama (local) |
| Time-Series DB | TimescaleDB |
| Knowledge Graph | Neo4j |
| Vector Store | Qdrant |
| Cache | Redis |
| Memory | Mem0 |
| Backend | FastAPI |
| Frontend | Next.js 14, TailwindCSS, Recharts |
| Observability | Langfuse, Sentry |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- API keys (at least one):
  - [Groq](https://console.groq.com/) (recommended, free tier)
  - [Google AI Studio](https://makersuite.google.com/app/apikey) (free tier)

### Setup

```bash
# Clone the repository
git clone https://github.com/Pranav1011/F1-Race-Intelligence-Agent.git
cd F1-Race-Intelligence-Agent

# Initial setup (creates .env, pulls images)
make setup

# Add your API keys to .env
nano .env  # or your preferred editor

# Start all services
make up
```

### Access

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474

### Data Ingestion

```bash
# Ingest all F1 data (2018-2024) - takes several hours
make ingest

# Or ingest a single year
make ingest-year YEAR=2024

# Or a single race
make ingest-race YEAR=2024 ROUND=1
```

## Development

```bash
# View logs
make logs

# Run tests
make test

# Lint code
make lint

# Format code
make format

# Open backend shell
make shell

# Open database shell
make db-shell
```

## Project Structure

```
├── backend/
│   ├── api/              # FastAPI routes
│   ├── agent/            # LangGraph agent + tools
│   ├── ingestion/        # Data pipeline (FastF1)
│   ├── rag/              # Retrieval system
│   ├── memory/           # Mem0 + Redis
│   ├── observability/    # Langfuse + Sentry
│   └── db/               # Database clients
├── frontend/
│   ├── app/              # Next.js app router
│   ├── components/       # React components
│   │   ├── chat/         # Chat interface
│   │   ├── visualizations/ # Charts
│   │   └── layout/       # Adaptive layout
│   ├── hooks/            # Custom hooks
│   └── stores/           # Zustand state
├── docs/
│   └── plans/            # Design documents
├── scripts/              # Utility scripts
└── docker-compose.yml
```

## Documentation

- [Architecture Design](docs/plans/2025-12-14-f1-race-intelligence-agent-design.md)

## Roadmap

### Completed
- [x] **Phase 1**: Project scaffolding, Docker setup, database initialization
- [x] **Phase 2**: Data ingestion pipeline (FastF1 → TimescaleDB + Neo4j)
- [x] **Phase 3**: LangGraph Agent Core
  - [x] LLM Router with fallback chain (Groq → Gemini → Ollama)
  - [x] Agent state management and graph structure
  - [x] Core tools (telemetry queries, lap times, knowledge graph)
  - [x] Chat API endpoints (HTTP + WebSocket)
  - [x] Session history management

### Upcoming
- [ ] **Phase 4**: Frontend UI enhancement
- [ ] **Phase 5**: RAG system (Qdrant + hybrid retrieval)
- [ ] **Phase 6**: Memory system (Mem0)
- [ ] **Phase 7**: Observability (Langfuse + Sentry)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [FastF1](https://github.com/theOehrly/Fast-F1) for F1 data access
- Formula 1 for the sport we love
