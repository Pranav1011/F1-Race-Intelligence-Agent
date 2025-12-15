# F1 Race Intelligence Agent - Implementation Reference

This document contains detailed implementation patterns and code references to guide development. Use this if context is lost during conversation.

---

## Table of Contents

1. [Data Layer Schemas](#data-layer-schemas)
2. [FastF1 Extraction](#fastf1-extraction)
3. [TimescaleDB Loader](#timescaledb-loader)
4. [Neo4j Knowledge Graph](#neo4j-knowledge-graph)
5. [Agent Architecture](#agent-architecture)
6. [RAG Pipeline](#rag-pipeline)
7. [Memory System](#memory-system)
8. [Frontend Patterns](#frontend-patterns)
9. [API Streaming](#api-streaming)

---

## Data Layer Schemas

### TimescaleDB Tables

```sql
-- Sessions reference table
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    year INT NOT NULL,
    round_number INT NOT NULL,
    event_name TEXT NOT NULL,
    session_type TEXT NOT NULL,
    circuit TEXT NOT NULL,
    session_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Lap times table
CREATE TABLE lap_times (
    id SERIAL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    driver_id TEXT NOT NULL,
    team TEXT NOT NULL,
    lap_number INT NOT NULL,
    lap_time_seconds DOUBLE PRECISION,
    sector_1_seconds DOUBLE PRECISION,
    sector_2_seconds DOUBLE PRECISION,
    sector_3_seconds DOUBLE PRECISION,
    compound TEXT,
    tire_life INT,
    stint INT,
    position INT,
    is_personal_best BOOLEAN,
    is_deleted BOOLEAN,
    deleted_reason TEXT,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, driver_id, lap_number)
);

-- Telemetry hypertable (partitioned by time)
CREATE TABLE telemetry (
    time TIMESTAMPTZ NOT NULL,
    session_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    lap_number INT,
    distance DOUBLE PRECISION,
    speed DOUBLE PRECISION,
    rpm INT,
    gear INT,
    throttle DOUBLE PRECISION,
    brake DOUBLE PRECISION,
    drs INT,
    position_x DOUBLE PRECISION,
    position_y DOUBLE PRECISION,
    position_z DOUBLE PRECISION
);

SELECT create_hypertable('telemetry', 'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 hour'
);

-- Weather hypertable
CREATE TABLE weather (
    time TIMESTAMPTZ NOT NULL,
    session_id TEXT NOT NULL,
    air_temp DOUBLE PRECISION,
    track_temp DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    pressure DOUBLE PRECISION,
    wind_speed DOUBLE PRECISION,
    wind_direction INT,
    rainfall BOOLEAN
);

SELECT create_hypertable('weather', 'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Indexes
CREATE INDEX idx_lap_times_session_driver ON lap_times(session_id, driver_id);
CREATE INDEX idx_telemetry_session_driver ON telemetry(session_id, driver_id, time DESC);
CREATE INDEX idx_telemetry_lap ON telemetry(session_id, driver_id, lap_number);
```

### Neo4j Node Types (35)

```
Competition: Season, Race, Session, Circuit, Corner, Sector, Championship
Participants: Driver, Team, TeamPrincipal, RaceEngineer, Manufacturer
Race Events: Stint, PitStop, Overtake, Incident, Penalty, SafetyCar, RedFlag, VSC, StrategyDecision
Technical: TireCompound, TireSet, CarSetup, WeatherCondition
Results: RaceResult, QualifyingResult, ChampionshipStanding, FastestLap, PolePosition
```

### Key Neo4j Relationships

```cypher
(Driver)-[:DROVE_FOR {year}]->(Team)
(Driver)-[:FINISHED {position, points, status}]->(Race)
(Race)-[:PART_OF]->(Season)
(Race)-[:HELD_AT]->(Circuit)
(Stint)-[:USED_COMPOUND]->(TireCompound)
(Driver)-[:HAD_STINT]->(Stint)
(Stint)-[:DURING]->(Race)
(Driver)-[:MADE_PITSTOP]->(PitStop)
(PitStop)-[:DURING]->(Race)
(Driver)-[:OVERTOOK {lap, corner}]->(Driver)
(Driver)-[:UNDERCUT]->(Driver)
(PitStop)-[:DURING]->(SafetyCar)
(Incident)-[:CAUSED]->(Penalty)
(WeatherCondition)-[:OCCURRED_DURING]->(Session)
```

---

## FastF1 Extraction

```python
# ingestion/extractors/fastf1_extractor.py

import fastf1
from fastf1.core import Session
from pathlib import Path
from dataclasses import dataclass
import pandas as pd
import logging

logger = logging.getLogger(__name__)

@dataclass
class RaceWeekend:
    year: int
    round_number: int
    event_name: str
    circuit: str
    sessions: list[str]

@dataclass
class ExtractedSession:
    year: int
    round_number: int
    event_name: str
    session_type: str
    laps: pd.DataFrame
    telemetry: dict[str, pd.DataFrame]  # driver_id -> telemetry
    results: pd.DataFrame
    weather: pd.DataFrame


class FastF1Extractor:
    def __init__(self, cache_dir: str = "~/.fastf1_cache"):
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(self.cache_dir))

    def get_available_races(self, start_year: int = 2018, end_year: int = 2024) -> list[RaceWeekend]:
        races = []
        for year in range(start_year, end_year + 1):
            schedule = fastf1.get_event_schedule(year)
            for _, event in schedule.iterrows():
                if event['EventFormat'] == 'testing':
                    continue
                races.append(RaceWeekend(
                    year=year,
                    round_number=event['RoundNumber'],
                    event_name=event['EventName'],
                    circuit=event['Location'],
                    sessions=self._get_session_types(event['EventFormat'])
                ))
        return races

    def extract_session(self, year: int, round_number: int, session_type: str) -> ExtractedSession:
        logger.info(f"Extracting {year} Round {round_number} {session_type}")

        session = fastf1.get_session(year, round_number, session_type)
        session.load(telemetry=True, weather=True, messages=True)

        laps = self._extract_laps(session)
        telemetry = self._extract_telemetry(session)
        results = self._extract_results(session)
        weather = self._extract_weather(session)

        return ExtractedSession(
            year=year,
            round_number=round_number,
            event_name=session.event['EventName'],
            session_type=session_type,
            laps=laps,
            telemetry=telemetry,
            results=results,
            weather=weather
        )

    def _extract_laps(self, session: Session) -> pd.DataFrame:
        laps = session.laps.copy()
        laps = laps[[
            'Driver', 'DriverNumber', 'Team', 'LapNumber', 'LapTime',
            'Sector1Time', 'Sector2Time', 'Sector3Time',
            'Compound', 'TyreLife', 'Stint',
            'IsPersonalBest', 'Position', 'Deleted', 'DeletedReason'
        ]].copy()

        time_cols = ['LapTime', 'Sector1Time', 'Sector2Time', 'Sector3Time']
        for col in time_cols:
            laps[f'{col}Seconds'] = laps[col].dt.total_seconds()
        return laps

    def _extract_telemetry(self, session: Session) -> dict[str, pd.DataFrame]:
        telemetry = {}
        for driver in session.drivers:
            try:
                driver_laps = session.laps.pick_driver(driver)
                driver_tel = driver_laps.get_telemetry()
                if driver_tel is not None and len(driver_tel) > 0:
                    driver_tel = driver_tel[[
                        'Date', 'SessionTime', 'DriverAhead', 'DistanceToDriverAhead',
                        'Time', 'RPM', 'Speed', 'nGear', 'Throttle', 'Brake',
                        'DRS', 'Distance', 'X', 'Y', 'Z'
                    ]].copy()
                    driver_tel['Driver'] = driver
                    telemetry[driver] = driver_tel
            except Exception as e:
                logger.warning(f"Failed to extract telemetry for {driver}: {e}")
        return telemetry

    def _extract_results(self, session: Session) -> pd.DataFrame:
        return session.results[[
            'DriverNumber', 'Abbreviation', 'FullName', 'TeamName',
            'Position', 'GridPosition', 'Status', 'Points', 'Time'
        ]].copy()

    def _extract_weather(self, session: Session) -> pd.DataFrame:
        if session.weather_data is None:
            return pd.DataFrame()
        return session.weather_data[[
            'Time', 'AirTemp', 'TrackTemp', 'Humidity',
            'Pressure', 'WindSpeed', 'WindDirection', 'Rainfall'
        ]].copy()

    def _get_session_types(self, event_format: str) -> list[str]:
        if event_format == 'conventional':
            return ['FP1', 'FP2', 'FP3', 'Q', 'R']
        elif event_format == 'sprint':
            return ['FP1', 'Q', 'SQ', 'S', 'R']
        elif event_format == 'sprint_shootout':
            return ['FP1', 'Q', 'SS', 'S', 'R']
        return ['R']
```

---

## TimescaleDB Loader

```python
# ingestion/loaders/timescale_loader.py

import asyncpg
from datetime import datetime

class TimescaleLoader:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pool = None

    async def initialize(self):
        self.pool = await asyncpg.create_pool(self.connection_string)
        await self._create_schema()

    async def _create_schema(self):
        # Execute schema SQL from above
        pass

    async def load_session(self, session_data):
        session_id = f"{session_data.year}_{session_data.round_number}_{session_data.session_type}"
        async with self.pool.acquire() as conn:
            # Insert session metadata
            await conn.execute("""
                INSERT INTO sessions (session_id, year, round_number, event_name, session_type, circuit)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (session_id) DO NOTHING
            """, session_id, session_data.year, session_data.round_number,
                session_data.event_name, session_data.session_type, "")

            await self._load_laps(conn, session_id, session_data.laps)
            await self._load_telemetry(conn, session_id, session_data.telemetry)
            await self._load_weather(conn, session_id, session_data.weather)

    async def _load_telemetry(self, conn, session_id: str, telemetry: dict):
        for driver_id, tel_df in telemetry.items():
            records = [
                (row['Date'], session_id, driver_id, None,
                 row['Distance'], row['Speed'], row['RPM'], row['nGear'],
                 row['Throttle'], row['Brake'], row['DRS'],
                 row['X'], row['Y'], row['Z'])
                for _, row in tel_df.iterrows()
            ]
            await conn.executemany("""
                INSERT INTO telemetry
                (time, session_id, driver_id, lap_number, distance, speed, rpm, gear,
                 throttle, brake, drs, position_x, position_y, position_z)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """, records)
```

---

## Neo4j Knowledge Graph

```python
# ingestion/loaders/neo4j_loader.py

from neo4j import AsyncGraphDatabase

class Neo4jLoader:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def initialize(self):
        async with self.driver.session() as session:
            await session.run("""
                CREATE CONSTRAINT driver_id IF NOT EXISTS FOR (d:Driver) REQUIRE d.id IS UNIQUE;
                CREATE CONSTRAINT team_id IF NOT EXISTS FOR (t:Team) REQUIRE t.id IS UNIQUE;
                CREATE CONSTRAINT race_id IF NOT EXISTS FOR (r:Race) REQUIRE r.id IS UNIQUE;
                CREATE CONSTRAINT circuit_id IF NOT EXISTS FOR (c:Circuit) REQUIRE c.id IS UNIQUE;
                CREATE CONSTRAINT season_year IF NOT EXISTS FOR (s:Season) REQUIRE s.year IS UNIQUE;
            """)

    async def load_race_weekend(self, session_data, results):
        race_id = f"{session_data.year}_{session_data.round_number}"
        async with self.driver.session() as session:
            # Create Season
            await session.run("MERGE (s:Season {year: $year})", year=session_data.year)

            # Create Circuit
            await session.run("""
                MERGE (c:Circuit {id: $circuit_id})
                SET c.name = $name
            """, circuit_id=session_data.event_name.lower().replace(" ", "_"),
                name=session_data.event_name)

            # Create Race with relationships
            await session.run("""
                MATCH (s:Season {year: $year})
                MATCH (c:Circuit {id: $circuit_id})
                MERGE (r:Race {id: $race_id})
                SET r.name = $name, r.round = $round
                MERGE (r)-[:PART_OF]->(s)
                MERGE (r)-[:HELD_AT]->(c)
            """, year=session_data.year,
                circuit_id=session_data.event_name.lower().replace(" ", "_"),
                race_id=race_id, name=session_data.event_name,
                round=session_data.round_number)

            # Create Driver, Team, Results
            for _, row in results.iterrows():
                await session.run("""
                    MERGE (d:Driver {id: $driver_id})
                    SET d.name = $driver_name, d.abbreviation = $abbreviation
                    MERGE (t:Team {id: $team_id})
                    SET t.name = $team_name
                    MATCH (s:Season {year: $year})
                    MERGE (d)-[:DROVE_FOR {year: $year}]->(t)
                    MATCH (r:Race {id: $race_id})
                    MERGE (d)-[result:FINISHED]->(r)
                    SET result.position = $position,
                        result.grid = $grid,
                        result.points = $points,
                        result.status = $status
                """,
                    driver_id=row['Abbreviation'],
                    driver_name=row['FullName'],
                    abbreviation=row['Abbreviation'],
                    team_id=row['TeamName'].lower().replace(" ", "_"),
                    team_name=row['TeamName'],
                    year=session_data.year,
                    race_id=race_id,
                    position=int(row['Position']) if pd.notna(row['Position']) else None,
                    grid=int(row['GridPosition']) if pd.notna(row['GridPosition']) else None,
                    points=float(row['Points']) if pd.notna(row['Points']) else 0,
                    status=row['Status']
                )
```

---

## Agent Architecture

### State Schema

```python
# agent/state.py

from enum import Enum
from typing import Optional
from pydantic import BaseModel
from langgraph.graph import MessagesState

class UIMode(str, Enum):
    CHAT = "chat"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    TELEMETRY = "telemetry"
    STANDINGS = "standings"
    MULTI_PANEL = "multi_panel"

class F1AgentState(MessagesState):
    query_type: Optional[str] = None
    entities: dict = {}
    ui_mode: UIMode = UIMode.CHAT
    visualizations: list[dict] = []
    retrieved_docs: list[str] = []
    telemetry_data: Optional[dict] = None
    graph_results: Optional[dict] = None
    user_preferences: dict = {}
    session_context: list[str] = []
```

### Tools List

```python
tools = [
    # Data Retrieval
    Tool(name="query_telemetry", description="Get raw telemetry for a driver in a session"),
    Tool(name="query_lap_times", description="Get lap times, sector times, tire compounds"),
    Tool(name="query_knowledge_graph", description="Execute Cypher query against F1 knowledge graph"),

    # Analysis
    Tool(name="compare_drivers", description="Head-to-head comparison between drivers"),
    Tool(name="analyze_tire_degradation", description="Calculate tire deg curves"),
    Tool(name="analyze_strategy", description="Break down pit stops, stints, undercuts"),

    # Simulation
    Tool(name="find_similar_scenarios", description="Find historical races for what-if reasoning"),

    # RAG
    Tool(name="search_race_context", description="Search articles and discussions"),
    Tool(name="search_regulations", description="Search FIA regulations"),

    # Visualization
    Tool(name="generate_chart", description="Generate chart specification for frontend"),

    # Memory
    Tool(name="recall_user_preferences", description="Get user preferences from Mem0"),
    Tool(name="store_user_fact", description="Store fact about user"),
]
```

### LLM Router

```python
# agent/llm.py

class LLMRouter:
    def __init__(self):
        self.groq = GroqClient()      # Primary: fast, free
        self.gemini = GeminiClient()   # Backup + vision
        self.ollama = OllamaClient()   # Local fallback

    async def route(self, task_type: str, requires_vision: bool = False):
        if requires_vision:
            return self.gemini
        if await self.groq.is_available():
            return self.groq
        if await self.gemini.is_available():
            return self.gemini
        return self.ollama
```

---

## RAG Pipeline

### Hybrid Retrieval

```python
# rag/retriever.py

class HybridRetriever:
    def __init__(self):
        self.qdrant = QdrantClient(host="localhost", port=6333)
        self.dense_encoder = SentenceTransformer("BAAI/bge-base-en-v1.5")
        self.sparse_encoder = BM25Encoder()

    async def search(self, query: str, collection: str, limit: int = 10, alpha: float = 0.5):
        dense_vec = self.dense_encoder.encode(query)
        sparse_vec = self.sparse_encoder.encode(query)

        results = self.qdrant.query_points(
            collection_name=collection,
            prefetch=[
                Prefetch(query=dense_vec, using="dense", limit=limit * 2),
                Prefetch(query=SparseVector(**sparse_vec), using="sparse", limit=limit * 2)
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit
        )
        return results
```

### CRAG Pattern

```python
# rag/crag.py

class CorrectiveRAG:
    def __init__(self):
        self.retriever = HybridRetriever()
        self.reranker = Reranker()
        self.confidence_threshold = 0.6

    async def retrieve_with_fallback(self, query: str, collection: str):
        docs = await self.retriever.search(query, collection, limit=20)
        ranked_docs = await self.reranker.rerank(query, docs, top_k=5)
        confidence = self._assess_confidence(query, ranked_docs)

        if confidence >= self.confidence_threshold:
            return RetrievalResult(documents=ranked_docs, confidence=confidence, source="primary_rag")

        # Fallback to alternative sources
        fallback_docs = await self._fallback_retrieval(query)
        all_docs = ranked_docs + fallback_docs
        final_docs = await self.reranker.rerank(query, all_docs, top_k=5)

        return RetrievalResult(documents=final_docs, confidence=confidence, source="crag_fallback")
```

---

## Memory System

### Mem0 Integration

```python
# memory/user_memory.py

from mem0 import Memory

class UserMemory:
    def __init__(self):
        self.memory = Memory.from_config({
            "vector_store": {
                "provider": "qdrant",
                "config": {"host": "localhost", "port": 6333, "collection_name": "user_memories"}
            },
            "llm": {
                "provider": "groq",
                "config": {"model": "llama-3.3-70b-versatile"}
            }
        })

    async def remember(self, user_id: str, conversation: list[dict]):
        self.memory.add(messages=conversation, user_id=user_id)

    async def recall(self, user_id: str, query: str) -> list[str]:
        results = self.memory.search(query=query, user_id=user_id, limit=5)
        return [r["memory"] for r in results]
```

---

## Frontend Patterns

### Adaptive UI Modes

```typescript
// stores/ui-store.ts
type UIMode = 'chat' | 'comparison' | 'timeline' | 'telemetry' | 'standings' | 'multi_panel';

const layoutConfigs = {
  chat: { panels: [{ type: 'chat', width: '100%' }] },
  comparison: { panels: [{ type: 'chat', width: '40%' }, { type: 'comparison_viz', width: '60%' }] },
  timeline: { panels: [{ type: 'chat', width: '35%' }, { type: 'timeline_viz', width: '65%' }] },
  telemetry: { panels: [{ type: 'chat', width: '30%' }, { type: 'telemetry_charts', width: '70%' }] },
  multi_panel: { panels: [{ type: 'chat', width: '30%' }, { type: 'primary_viz', width: '45%' }, { type: 'secondary_viz', width: '25%' }] }
};
```

### F1 Color System

```typescript
// tailwind.config.ts
teams: {
  redbull: '#3671C6',
  ferrari: '#F91536',
  mercedes: '#6CD3BF',
  mclaren: '#F58020',
  astonmartin: '#229971',
  alpine: '#0093CC',
  williams: '#64C4FF',
  rb: '#6692FF',
  kick: '#52E252',
  haas: '#B6BABD',
},
tires: {
  soft: '#FF3333',
  medium: '#FFD700',
  hard: '#EEEEEE',
  intermediate: '#43B02A',
  wet: '#0067AD',
}
```

---

## API Streaming

### WebSocket Protocol

```
Client → Server: {"type": "message", "content": "...", "session_id": "..."}
Server → Client: {"type": "token", "token": "..."} (streaming)
Server → Client: {"type": "tool_start", "tool": {...}}
Server → Client: {"type": "tool_end", "tool_id": "..."}
Server → Client: {"type": "ui_mode", "mode": "..."}
Server → Client: {"type": "visualization", "spec": {...}}
Server → Client: {"type": "done"}
```

---

## Implementation Phases Summary

1. **Foundation** ✅ - Project setup, Docker, scaffolding
2. **Data Pipeline** ✅ - FastF1 → TimescaleDB → Neo4j ingestion
3. **Agent Core** ✅ - LangGraph + LLM Router (Groq primary) + tools + Chat API
4. **RAG System** - Qdrant + hybrid retrieval + reranking
5. **Memory** - Mem0 + Redis session state
6. **Frontend Polish** - Adaptive UI + visualizations
7. **Observability** - Langfuse + Sentry + hardening

---

## Key Decisions Reference

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent Framework | LangGraph | Stateful cycles, checkpointing |
| Primary LLM | Groq (Llama 3.3 70B) | Free, fast |
| Backup LLM | Gemini | Free, vision |
| Local LLM | Ollama | Offline dev |
| Time-Series | TimescaleDB | PostgreSQL compatibility |
| Graph DB | Neo4j | Rich relationships |
| Vector DB | Qdrant | Hybrid search |
| Memory | Mem0 | Agent-focused |
| Frontend | Next.js 14 | Production quality |
| Styling | Tailwind + shadcn/ui | Fast development |
