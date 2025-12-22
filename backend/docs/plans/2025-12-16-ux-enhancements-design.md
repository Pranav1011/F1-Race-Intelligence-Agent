# F1 RIA UX Enhancements Design

**Date:** 2025-12-16
**Status:** Approved

## Overview

Comprehensive UX enhancement covering:
1. Query preprocessing (fuzzy matching, shortcuts, default context)
2. Query history and smart suggestions
3. Enhanced streaming with status updates
4. Modern analytics dashboard UI

## Design Decisions

| Feature | Choice |
|---------|--------|
| UI Style | Modern Analytics Dashboard (Claude/ChatGPT-like) |
| LLM Responsiveness | Streaming with status updates (Perplexity-style) |
| Query Expansion | Smart inference from natural language |
| Layout | Chat-centered (70%) + collapsible artifact panel |
| Query History | Smart suggestions based on patterns |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js)                      │
├─────────────────────────────────────────────────────────────┤
│  QueryPreprocessor → Chat UI → Streaming Handler → Artifacts │
│         ↓                              ↑                     │
│  [Fuzzy Match]                   [Status Updates]            │
│  [Smart Expand]                  [Progress Chips]            │
│  [Default Year]                                              │
└─────────────────────────────────────────────────────────────┘
                              ↕ WebSocket
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                       │
├─────────────────────────────────────────────────────────────┤
│  QueryPreprocessor → Agent Pipeline → Response Streamer      │
│         ↓                   ↓                                │
│  [Normalize names]    [Redis Cache]                          │
│  [Expand shortcuts]   [Query History]                        │
│  [Infer context]      [Smart Suggestions]                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Module 1: Query Preprocessing

**Location:** `backend/preprocessing/`

### Files
- `query_preprocessor.py` - Main preprocessor class
- `fuzzy_matcher.py` - Levenshtein-based name correction
- `query_expander.py` - Shortcut and pattern expansion
- `intent_classifier.py` - Fast pre-LLM intent detection

### Data Files
- `data/drivers.json` - Drivers with aliases, codes, full names
- `data/teams.json` - Teams with variations
- `data/circuits.json` - Tracks with common names

### Fuzzy Matching Rules
```python
# Typo correction (Levenshtein distance ≤ 2)
"verstapen" → "Verstappen"
"hamiltin" → "Hamilton"

# Alias expansion
"Max" → "Verstappen"
"Checo" → "Perez"
"Charles" → "Leclerc"

# Team normalization
"RB" → "Red Bull Racing"
"Merc" → "Mercedes"
"Ferrari" → "Scuderia Ferrari"
```

### Smart Inference Patterns
```python
# Comparison detection
"X vs Y" → comparison mode
"compare X and Y" → comparison mode
"how does X stack up against Y" → comparison mode
"X or Y" → comparison mode

# Default year injection
No year mentioned → inject current year (2024)
"last year" → 2023
"this season" → 2024
```

---

## Module 2: Query History & Suggestions

**Location:** `backend/history/`

### Redis Schema
```
f1:history:{user_id}:queries    → List[QueryRecord] (last 100)
f1:history:{user_id}:entities   → Dict[entity, count]
f1:history:{user_id}:patterns   → Dict[pattern, count]
```

### QueryRecord Structure
```python
@dataclass
class QueryRecord:
    query: str
    normalized_query: str
    entities: List[str]  # ["VER", "NOR", "Monaco"]
    query_type: str
    timestamp: datetime
    response_quality: float  # Optional user feedback
```

### Suggestion Types
1. **favorite_driver** - Based on entity frequency
2. **follow_up** - Context-aware next questions
3. **temporal** - Race weekend / post-race suggestions
4. **trending** - Popular queries (future)

### API Endpoints
```
GET  /api/suggestions              → Personalized suggestions
POST /api/history/query            → Log a query
GET  /api/history/recent?limit=10  → Recent queries
DELETE /api/history                → Clear history
```

---

## Module 3: Enhanced Streaming

### WebSocket Event Types
```typescript
type WSEvent =
  | { type: 'status', message: string, step: number, total: number }
  | { type: 'interpreted', original: string, interpreted: string, entities: Entity[] }
  | { type: 'token', content: string }
  | { type: 'data_card', id: string, title: string, data: any }
  | { type: 'visualization', spec: VizSpec }
  | { type: 'suggestions', items: Suggestion[] }
  | { type: 'done', metadata: ResponseMeta }
  | { type: 'error', message: string, code: string }
```

### Status Messages by Node
```python
UNDERSTAND: "Understanding your question..."
PLAN:       "Planning data retrieval..."
EXECUTE:    "Fetching {tool_name}..." (per tool)
ENRICH:     "Adding context..."
GENERATE:   "Generating response..."
```

### Backend Emitter
```python
class StatusEmitter:
    async def emit(self, message: str, step: int, total: int):
        await self.websocket.send_json({
            "type": "status",
            "message": message,
            "step": step,
            "total": total
        })
```

---

## Module 4: Frontend UI

### Color Palette
```css
--bg-primary:      #0a0a0a;
--bg-surface:      #141414;
--bg-surface-hover: #1a1a1a;
--border:          #262626;
--text-primary:    #fafafa;
--text-secondary:  #a1a1a1;
--accent:          #e10600;
--success:         #22c55e;
```

### Layout Structure
```
┌────────────────────────────────────────────────────────────┐
│ Header (56px): Logo | Command Palette | Settings           │
├──────────┬─────────────────────────────┬───────────────────┤
│ Sidebar  │      Chat Area (flex-1)     │  Artifact Panel   │
│ (240px)  │                             │  (400px, toggle)  │
│ ──────── │  Messages                   │                   │
│ Sessions │  - User bubbles (right)     │  Visualizations   │
│          │  - AI bubbles (left)        │  Data Tables      │
│ ──────── │  - Inline DataCards         │                   │
│ Suggest  │                             │                   │
│          │  ──────────────────────     │                   │
│          │  Input + StatusChip         │                   │
└──────────┴─────────────────────────────┴───────────────────┘
```

### New Components

#### StatusChip
```tsx
<StatusChip
  message="Fetching lap times..."
  step={2}
  total={4}
/>
```

#### DataCard
```tsx
<DataCard
  title="Lap Time Comparison"
  expandable
  data={tableData}
/>
```

#### SuggestionPills
```tsx
<SuggestionPills
  suggestions={["VER vs NOR", "Monaco 2024", "Pit strategies"]}
  onSelect={handleSelect}
/>
```

#### QueryInterpretation
```tsx
<QueryInterpretation
  original="verstapen vs norris monaco"
  interpreted="Verstappen vs Norris at Monaco 2024"
  onEdit={handleEdit}
/>
```

---

## Implementation Phases

### Phase 1: Backend Preprocessing
- [ ] Create `preprocessing/` module structure
- [ ] Implement `FuzzyMatcher` with Levenshtein
- [ ] Implement `QueryExpander` with pattern detection
- [ ] Create driver/team/circuit JSON data
- [ ] Integrate into WebSocket handler
- [ ] Add unit tests

### Phase 2: Query History & Suggestions
- [ ] Create `history/` module structure
- [ ] Implement Redis storage for queries
- [ ] Implement entity frequency tracking
- [ ] Create suggestion engine
- [ ] Add API endpoints
- [ ] Add unit tests

### Phase 3: Enhanced Streaming
- [ ] Define new WebSocket event types
- [ ] Create `StatusEmitter` class
- [ ] Add status emissions to each agent node
- [ ] Update frontend WebSocket handler
- [ ] Add interpreted query display

### Phase 4: Frontend UI Overhaul
- [ ] Update Tailwind config with new colors
- [ ] Create StatusChip component
- [ ] Create DataCard component
- [ ] Create SuggestionPills component
- [ ] Redesign Sidebar with suggestions
- [ ] Redesign message bubbles
- [ ] Add artifact panel toggle
- [ ] Polish animations

### Phase 5: Integration & Polish
- [ ] End-to-end testing
- [ ] Error state handling
- [ ] Loading state polish
- [ ] Performance optimization
- [ ] Documentation

---

## File Structure (New)

```
backend/
├── preprocessing/
│   ├── __init__.py
│   ├── query_preprocessor.py
│   ├── fuzzy_matcher.py
│   ├── query_expander.py
│   └── intent_classifier.py
├── history/
│   ├── __init__.py
│   ├── query_history.py
│   └── suggestion_engine.py
├── data/
│   ├── drivers.json
│   ├── teams.json
│   └── circuits.json
└── api/
    └── routers/
        ├── suggestions.py (new)
        └── history.py (new)

frontend/
├── components/
│   ├── ui/
│   │   ├── StatusChip.tsx
│   │   ├── DataCard.tsx
│   │   ├── SuggestionPills.tsx
│   │   └── QueryInterpretation.tsx
│   ├── chat/
│   │   ├── ChatArea.tsx (updated)
│   │   ├── MessageBubble.tsx (updated)
│   │   └── MessageInput.tsx (updated)
│   └── layout/
│       ├── Sidebar.tsx (updated)
│       └── ArtifactPanel.tsx (updated)
└── styles/
    └── globals.css (updated colors)
```
