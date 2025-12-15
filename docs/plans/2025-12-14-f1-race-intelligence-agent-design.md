# F1 Race Intelligence Agent - Architecture Design

**Date**: 2025-12-14
**Status**: Approved
**Author**: Collaborative Design Session

---

## Executive Summary

The F1 Race Intelligence Agent is a conversational AI system that acts as an AI-powered Race Engineer Co-Pilot. Users can ask natural language questions about Formula 1 races, drivers, strategies, and telemetry. The agent analyzes data, provides insights, and generates dynamic visualizations.

### Example Interactions

- "Compare Verstappen and Norris's tire degradation in the 2024 Singapore GP"
- "What would've happened if Max pitted on lap 33 instead of lap 38?"
- "Show me Hamilton's speed trace through Sector 3 at Monaco"
- "Why did Ferrari's strategy fail at Silverstone 2024?"

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                  FRONTEND                                        │
│                         Next.js 14 + React + TailwindCSS                        │
│              Context-Aware Adaptive UI with F1 Visual Language                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                API GATEWAY                                       │
│                        FastAPI + WebSocket Support                              │
│                    Streaming responses, session management                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AGENT ORCHESTRATION                                 │
│                                  LangGraph                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   Router    │→ │    Data     │→ │  Analysis   │→ │Visualization│            │
│  │   Agent     │  │  Retrieval  │  │   Agent     │  │   Agent     │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│    MEMORY LAYER     │  │     DATA LAYER      │  │   EXTERNAL APIS     │
│  ┌───────────────┐  │  │  ┌───────────────┐  │  │  ┌───────────────┐  │
│  │ Mem0 (Long)   │  │  │  │ TimescaleDB   │  │  │  │ Groq API      │  │
│  │ Redis (Short) │  │  │  │ Neo4j         │  │  │  │ Gemini API    │  │
│  │ Qdrant (RAG)  │  │  │  │ Qdrant        │  │  │  │ Ollama        │  │
│  └───────────────┘  │  │  └───────────────┘  │  │  └───────────────┘  │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

### Core Principles

- **Separation of concerns**: Each layer has a single responsibility
- **Stateless API**: All state lives in databases, enables horizontal scaling
- **Streaming-first**: All LLM responses stream to frontend in real-time
- **Graceful degradation**: If Groq fails, fallback to Gemini, then Ollama

---

## Technology Decisions

| Category | Choice | Rationale |
|----------|--------|-----------|
| **Agent Framework** | LangGraph | Stateful cycles, production checkpointing, multi-agent ready |
| **Primary LLM** | Groq (Llama 3.3 70B) | Free tier, fastest inference, strong reasoning |
| **Backup LLM** | Google Gemini | Free tier, vision capabilities, 1M context |
| **Local LLM** | Ollama | Offline development, no API costs |
| **Time-Series DB** | TimescaleDB | PostgreSQL compatibility, continuous aggregates, compression |
| **Knowledge Graph** | Neo4j | Industry standard, rich relationship queries |
| **Vector Store** | Qdrant | Best filtering, hybrid search support |
| **Cache** | Redis | Fast, reliable, session management |
| **Long-term Memory** | Mem0 | Purpose-built for agent memory |
| **Frontend** | Next.js 14 | Production quality, app router |
| **Styling** | Tailwind + shadcn/ui | Fast development, consistent design |
| **Charts** | Recharts + D3 | Balance of ease and customization |
| **API** | FastAPI | Async, WebSocket support, auto docs |
| **Observability** | Langfuse + Sentry | LLM tracing + error tracking, both free tier |
| **Package Manager** | uv (Python), pnpm (JS) | Fast, modern |

---

## Data Layer

### TimescaleDB (Time-Series Telemetry)

Stores all telemetry, lap times, and sensor data.

**Hypertables:**
- `telemetry` - Car sensor data (speed, throttle, brake, gear, DRS, position)
- `lap_times` - Lap and sector times per driver
- `weather` - Track and air conditions throughout sessions

**Data Scope:**
- Years: 2018-2024
- Races: ~168 race weekends
- Storage: ~17GB
- Sessions: FP1, FP2, FP3, Qualifying, Sprint, Race

### Neo4j (Knowledge Graph)

Models F1 domain relationships for complex queries.

**Node Types (35):**
- Competition: Season, Race, Session, Circuit, Corner, Sector, Championship
- Participants: Driver, Team, TeamPrincipal, RaceEngineer, Manufacturer
- Race Events: Stint, PitStop, Overtake, Incident, Penalty, SafetyCar, RedFlag, VSC, StrategyDecision
- Technical: TireCompound, TireSet, CarSetup, WeatherCondition
- Results: RaceResult, QualifyingResult, ChampionshipStanding, FastestLap, PolePosition

**Key Relationships (80+):**
- `(Driver)-[:DROVE_FOR {year}]->(Team)`
- `(Driver)-[:FINISHED {position}]->(Race)`
- `(Stint)-[:USED_COMPOUND]->(TireCompound)`
- `(Driver)-[:OVERTOOK {lap, corner}]->(Driver)`
- `(Driver)-[:UNDERCUT]->(Driver)`
- `(PitStop)-[:DURING]->(SafetyCar)`

### Qdrant (Vector Store)

Semantic search over unstructured content.

**Collections:**
- `race_reports` - Journalist articles, post-race analysis
- `reddit_discussions` - Filtered high-quality community posts
- `regulations` - FIA sporting/technical rules
- `past_analyses` - Previous agent responses

### Redis (Caching)

Fast caching, session state, rate limiting.

---

## Agent Architecture

### LangGraph State Machine

Single ReAct agent with tools, architected for future multi-agent split.

**State Schema:**
```python
class F1AgentState(MessagesState):
    query_type: Optional[str]        # telemetry, strategy, comparison, etc.
    entities: dict                   # extracted: drivers, races, teams
    ui_mode: UIMode                  # chat, comparison, timeline, telemetry
    visualizations: list[dict]       # chart specs to render
    retrieved_docs: list[str]        # RAG results
    telemetry_data: Optional[dict]   # queried sensor data
    graph_results: Optional[dict]    # Neo4j query results
    user_preferences: dict           # from Mem0
    session_context: list[str]       # key facts from this session
```

### Agent Tools

1. **Data Retrieval**
   - `query_telemetry` - Raw sensor data
   - `query_lap_times` - Lap and sector times
   - `query_knowledge_graph` - Cypher queries

2. **Analysis**
   - `compare_drivers` - Head-to-head comparison
   - `analyze_tire_degradation` - Tire deg curves
   - `analyze_strategy` - Pit stops, stints, undercuts

3. **Simulation**
   - `find_similar_scenarios` - Historical analogies for what-if

4. **RAG**
   - `search_race_context` - Articles and discussions
   - `search_regulations` - FIA rules

5. **Visualization**
   - `generate_chart` - Chart specifications

6. **Memory**
   - `recall_user_preferences` - Get from Mem0
   - `store_user_fact` - Save to Mem0

### LLM Routing

```
Primary:  Groq (Llama 3.3 70B) - Fast, free tier
Backup:   Google Gemini - Vision tasks, fallback
Local:    Ollama (Llama 3.2) - Development, offline
```

---

## Memory System

### Multi-Tier Architecture

1. **Working Memory (Redis)**
   - Current conversation messages
   - Extracted entities from session
   - Intermediate tool results
   - TTL: Session duration

2. **Short-Term Memory (LangGraph + Redis)**
   - Last N conversation turns
   - Query cache (semantic deduplication)
   - Recently accessed telemetry
   - TTL: 24 hours

3. **Long-Term Memory (Mem0)**
   - User preferences
   - Cross-session facts
   - Favorite drivers/teams
   - TTL: Persistent

4. **Semantic Memory (Qdrant)**
   - Past analysis results
   - Similar historical queries
   - TTL: Persistent, versioned

---

## RAG Architecture

### Retrieval Pipeline

1. **Hybrid Retrieval**: BM25 (keyword) + Dense embeddings (semantic)
2. **Cross-encoder Reranking**: Cohere or local model
3. **CRAG Pattern**: Fallback to alternative sources on low confidence
4. **HyDE**: Generate hypothetical answer for vague queries

### Content Sources

- Curated journalism (The Race, Autosport, Motorsport.com)
- Reddit r/formula1 high-quality posts (score > 50, quality filtered)
- FIA regulations and technical documents

---

## Frontend Architecture

### Tech Stack

- Framework: Next.js 14 (App Router)
- Styling: TailwindCSS + shadcn/ui
- Charts: Recharts + D3.js
- State: Zustand
- Real-time: WebSocket streaming
- Animations: Framer Motion

### Adaptive UI Modes

| Mode | Trigger | Layout |
|------|---------|--------|
| `chat` | Simple questions | Full-width chat |
| `comparison` | Driver/race comparisons | 40% chat, 60% comparison viz |
| `timeline` | Strategy questions | 35% chat, 65% timeline |
| `telemetry` | Speed/throttle/brake queries | 30% chat, 70% traces |
| `multi_panel` | Complex what-if scenarios | 30% chat, 45% primary, 25% secondary |

### F1 Design System

- Dark background (#0F0F0F)
- F1 red accent (#E10600) used sparingly
- Team colors for driver data
- Tire compound colors (Soft: red, Medium: yellow, Hard: white)
- Data viz colors (Positive: green, Negative: red)

---

## Observability

### Langfuse

- LLM call tracing
- Prompt monitoring
- Cost tracking
- Latency metrics

### Sentry

- Error tracking
- Performance monitoring
- Release tracking

### Structured Logging

- JSON format via structlog
- Correlation IDs across services

---

## Implementation Phases

### Phase 1: Foundation ✅ COMPLETE
- Project scaffolding + Docker Compose
- Database schemas + connections
- Basic FastAPI + Next.js setup
- FastF1 extraction for 1 race (proof of concept)
- Simple chat endpoint (direct LLM, no agent)

### Phase 2: Data Pipeline ✅ COMPLETE
- Full FastF1 ingestion pipeline
- TimescaleDB loader with hypertables
- Neo4j knowledge graph builder
- Ingest 2024 Bahrain + 2021 season (partial - rate limited)
- Backfill 2022-2024 (pending rate limit reset)

### Phase 3: Agent Core ✅ COMPLETE
- LangGraph state machine (6-node architecture: UNDERSTAND → PLAN → EXECUTE → PROCESS → EVALUATE → GENERATE)
- LLM router (Groq → Gemini → Ollama)
- Core tools: 12 tools implemented (TimescaleDB, Neo4j, Qdrant)
- WebSocket streaming
- Basic chat UI working end-to-end

### Phase 4: Frontend & UX ✅ COMPLETE
- Adaptive UI layout system
- F1 Visx visualization components (TireStrategy, GapEvolution, PositionBattle, SectorHeatmap)
- F1-themed thinking indicators with context-aware messages
- Framer Motion animations
- F1 design system

### Phase 5: Performance Optimization ✅ COMPLETE
- Materialized views for common aggregations (6 views)
- Database indexes for query performance
- Redis caching layer with TTL management
- Fast tools using pre-computed data

### Phase 6: Advanced Query Capabilities ✅ COMPLETE
- **Text-to-SQL Tool** - Allow LLM to write custom SQL queries for any data question
- **Strategy Simulator** - What-if scenario modeling (alternative pit strategies)
- **Historical Pattern Matching** - Find similar scenarios from past races
- Query validation and safety guards

### Phase 6.5: Testing & Validation ✅ COMPLETE
- Unit tests for backend tools (cache: 17 tests, SQL validation: 28 tests, strategy: 11 tests)
- All 57 backend tests passing
- Backend linting (ruff) passing - no syntax/undefined errors
- Frontend TypeScript type-check passing
- Frontend dev server running successfully
- Docker compose integration verified (all services healthy)

### Phase 7: RAG & Knowledge Expansion 🔄 IN PROGRESS
- ✅ Qdrant collections setup (race_reports, reddit_discussions, regulations, past_analyses)
- ✅ EmbeddingService with caching (BAAI/bge-base-en-v1.5)
- ✅ RAGService with hybrid retrieval (semantic + BM25-like keyword scoring)
- ✅ Vector tools refactored to use RAG service
- ✅ Health endpoint shows RAG collection stats
- 🔄 2022-2024 season data ingestion in progress
- ⬜ Additional data sources:
  - Ergast API (historical data back to 1950)
  - F1 regulations and technical documents
  - Driver/team profiles and history
- ⬜ Content ingestion scripts for regulations and race reports
- ⬜ Reranking + CRAG fallback

### Phase 8: Memory & Personalization
- Mem0 integration for long-term memory
- Session memory in Redis
- User preferences persistence
- Past analyses storage
- Favorite drivers/teams tracking

### Phase 9: Observability & Hardening
- Langfuse tracing throughout
- Sentry error tracking
- Structured logging
- Error handling + graceful degradation
- Rate limiting and query timeouts
- Test suite and evaluation framework

### Phase 10: Polish & Launch
- Mobile responsiveness
- Performance profiling and optimization
- Demo video recording
- Documentation

---

## Success Criteria

1. **Working demo** — Can answer complex F1 questions with data + visualizations
2. **Adaptive UI** — UI visibly transforms based on query type
3. **Memory works** — Remembers user preferences across sessions
4. **What-if reasoning** — Can find historical analogies for hypotheticals
5. **Production patterns** — Observability, error handling, graceful degradation
6. **Clean code** — Well-structured, typed, documented
7. **Impressive scale** — 168 races, 17GB telemetry, full knowledge graph

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| FastF1 rate limits / slow downloads | Local cache, batch ingestion overnight |
| Groq free tier limits | Fallback chain, semantic caching |
| Neo4j complexity | Start with core entities, expand incrementally |
| RAG quality issues | Multiple retrieval strategies, reranking |
| Scope creep | Strict phase gates, MVP-first |
