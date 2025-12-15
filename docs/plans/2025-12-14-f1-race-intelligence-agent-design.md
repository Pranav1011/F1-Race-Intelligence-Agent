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

### Phase 1: Foundation (Week 1-2)
- Project scaffolding + Docker Compose
- Database schemas + connections
- Basic FastAPI + Next.js setup
- FastF1 extraction for 1 race (proof of concept)
- Simple chat endpoint (direct LLM, no agent)

### Phase 2: Data Pipeline (Week 2-3)
- Full FastF1 ingestion pipeline
- TimescaleDB loader with hypertables
- Neo4j knowledge graph builder
- Ingest 2024 season first
- Backfill 2018-2023

### Phase 3: Agent Core (Week 3-4)
- LangGraph state machine
- LLM router (Groq → Gemini → Ollama)
- Core tools: query_telemetry, query_lap_times, compare_drivers
- WebSocket streaming
- Basic chat UI working end-to-end

### Phase 4: RAG System (Week 4-5)
- Qdrant collections setup
- Hybrid retrieval implementation
- Article/Reddit scraping + ingestion
- Reranking + CRAG fallback
- Tools: search_race_context, search_regulations

### Phase 5: Memory & Intelligence (Week 5-6)
- Mem0 integration
- Session memory in Redis
- Past analyses storage
- find_similar_scenarios tool (what-if)
- Knowledge graph queries for rich context

### Phase 6: Frontend Polish (Week 6-7)
- Adaptive UI layout system
- All visualization components
- Framer Motion animations
- F1 design system polish
- Mobile responsiveness

### Phase 7: Observability & Hardening (Week 7-8)
- Langfuse tracing throughout
- Sentry error tracking
- Structured logging
- Error handling + graceful degradation
- Demo video recording

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
