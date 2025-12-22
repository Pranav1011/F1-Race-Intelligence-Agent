"""
Enhanced streaming utilities for F1 RIA.

Provides:
- F1-themed status messages
- Tool execution progress tracking
- Structured WebSocket events
"""

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any


class StreamStage(str, Enum):
    """Stages in the agent processing pipeline."""
    PREPROCESSING = "preprocessing"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    EXECUTING = "executing"
    PROCESSING = "processing"
    EVALUATING = "evaluating"
    ENRICHING = "enriching"
    GENERATING = "generating"
    VALIDATING = "validating"
    COMPLETE = "complete"


@dataclass
class StatusMessage:
    """A status message for the UI."""
    stage: StreamStage
    message: str
    detail: str | None = None
    progress: float | None = None  # 0.0 to 1.0
    tool: str | None = None


# F1-themed status messages for each stage
STATUS_MESSAGES = {
    StreamStage.PREPROCESSING: [
        "Consulting the pit wall...",
        "Radio check, radio check...",
        "Warming up the tyres...",
    ],
    StreamStage.UNDERSTANDING: [
        "Copy, we are checking...",
        "Analyzing telemetry...",
        "Processing your request...",
    ],
    StreamStage.PLANNING: [
        "Strategy meeting in progress...",
        "Plan A, B, or C?",
        "Calculating optimal strategy...",
        "Mapping out the race plan...",
    ],
    StreamStage.EXECUTING: [
        "Lights out, data retrieval!",
        "Braking late into the data...",
        "Flat out through the corners...",
        "DRS enabled, accelerating...",
        "Push push push!",
    ],
    StreamStage.PROCESSING: [
        "Crunching the numbers...",
        "Analyzing sector times...",
        "Processing telemetry data...",
        "Building the leaderboard...",
    ],
    StreamStage.EVALUATING: [
        "Box box, quality check...",
        "Reviewing the data...",
        "Cross-checking analysis...",
        "Verifying accuracy...",
    ],
    StreamStage.ENRICHING: [
        "Adding context from archives...",
        "Checking historical records...",
        "Gathering expert insights...",
        "Reading race reports...",
    ],
    StreamStage.GENERATING: [
        "Composing response...",
        "Hammer time!",
        "Final sector, almost there...",
        "Drafting the analysis...",
    ],
    StreamStage.VALIDATING: [
        "P1 in sight, final checks...",
        "Crossing the finish line...",
        "Victory lap incoming...",
        "Checkered flag ready...",
    ],
    StreamStage.COMPLETE: [
        "And that's P1!",
        "Excellent job, everyone!",
        "Get in there!",
        "Simply lovely!",
    ],
}

# Tool-specific status messages
TOOL_MESSAGES = {
    "get_session_results": "Retrieving race results...",
    "get_lap_times": "Analyzing lap times...",
    "get_pit_stops": "Reviewing pit strategy...",
    "get_season_standings": "Fetching championship standings...",
    "get_head_to_head": "Comparing drivers head-to-head...",
    "get_driver_stint_summary": "Analyzing tire stints...",
    "get_tire_degradation": "Calculating deg rates...",
    "get_qualifying_stats": "Reviewing qualifying data...",
    "get_overtaking_analysis": "Counting overtakes...",
    "get_fastest_lap_stats": "Finding fastest laps...",
    "search_race_reports": "Reading race reports...",
    "search_reddit": "Checking community insights...",
    "get_regulation_context": "Consulting the rulebook...",
}


def get_status_message(stage: StreamStage) -> str:
    """Get a random status message for a stage."""
    messages = STATUS_MESSAGES.get(stage, ["Processing..."])
    return random.choice(messages)


def get_tool_message(tool_name: str) -> str:
    """Get a status message for a tool execution."""
    return TOOL_MESSAGES.get(tool_name, f"Running {tool_name}...")


class StreamingContext:
    """
    Context manager for tracking streaming progress.

    Usage:
        async with StreamingContext(websocket) as ctx:
            await ctx.status(StreamStage.UNDERSTANDING, "Analyzing query...")
            await ctx.tool_start("get_lap_times", {"driver": "VER"})
            # ... tool execution ...
            await ctx.tool_end("get_lap_times")
    """

    def __init__(self, send_func):
        """
        Initialize streaming context.

        Args:
            send_func: Async function to send JSON messages
        """
        self.send = send_func
        self.current_stage: StreamStage | None = None
        self.active_tools: dict[str, dict] = {}
        self.tool_count = 0
        self.tools_completed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Send completion if not already done
        if self.current_stage != StreamStage.COMPLETE:
            await self.complete()

    async def status(
        self,
        stage: StreamStage,
        message: str | None = None,
        detail: str | None = None,
        progress: float | None = None,
    ):
        """Send a status update."""
        self.current_stage = stage
        await self.send({
            "type": "status",
            "stage": stage.value,
            "message": message or get_status_message(stage),
            "detail": detail,
            "progress": progress,
        })

    async def tool_start(
        self,
        tool_name: str,
        params: dict | None = None,
        tool_id: str | None = None,
    ):
        """Notify that a tool has started execution."""
        self.tool_count += 1
        tid = tool_id or f"{tool_name}_{self.tool_count}"
        self.active_tools[tid] = {
            "name": tool_name,
            "params": params or {},
        }

        await self.send({
            "type": "tool_start",
            "tool_id": tid,
            "tool_name": tool_name,
            "message": get_tool_message(tool_name),
            "params": params,
        })

        return tid

    async def tool_progress(
        self,
        tool_id: str,
        progress: float,
        message: str | None = None,
    ):
        """Update progress for a running tool."""
        await self.send({
            "type": "tool_progress",
            "tool_id": tool_id,
            "progress": progress,
            "message": message,
        })

    async def tool_end(
        self,
        tool_id: str,
        success: bool = True,
        result_summary: str | None = None,
    ):
        """Notify that a tool has completed."""
        self.tools_completed += 1
        tool_info = self.active_tools.pop(tool_id, {})

        await self.send({
            "type": "tool_end",
            "tool_id": tool_id,
            "tool_name": tool_info.get("name"),
            "success": success,
            "result_summary": result_summary,
        })

        # Update overall progress
        if self.tool_count > 0:
            progress = self.tools_completed / self.tool_count
            await self.status(
                StreamStage.EXECUTING,
                progress=progress,
            )

    async def interpreted(
        self,
        original: str,
        expanded: str,
        corrections: list[dict],
        intent: str,
        confidence: float,
    ):
        """Send interpreted query info."""
        await self.send({
            "type": "interpreted",
            "original": original,
            "expanded": expanded,
            "corrections": corrections,
            "intent": intent,
            "confidence": confidence,
        })

    async def metadata(
        self,
        query_type: str,
        response_type: str,
        confidence: float,
    ):
        """Send query metadata."""
        await self.send({
            "type": "metadata",
            "query_type": query_type,
            "response_type": response_type,
            "confidence": confidence,
        })

    async def visualization(self, spec: dict):
        """Send a visualization specification."""
        await self.send({
            "type": "visualization",
            "spec": spec,
        })

    async def token(self, text: str):
        """Send a streaming token."""
        await self.send({
            "type": "token",
            "token": text,
        })

    async def complete(self, error: str | None = None):
        """Send completion message."""
        self.current_stage = StreamStage.COMPLETE
        await self.send({
            "type": "done",
            "error": error,
            "message": get_status_message(StreamStage.COMPLETE) if not error else None,
        })

    async def error(self, message: str):
        """Send an error message."""
        await self.send({
            "type": "error",
            "error": message,
        })


# WebSocket event types for frontend reference
WEBSOCKET_EVENTS = {
    "session": {
        "description": "Session ID confirmation",
        "fields": ["session_id"],
    },
    "interpreted": {
        "description": "Preprocessed query information",
        "fields": ["original", "expanded", "corrections", "intent", "confidence"],
    },
    "status": {
        "description": "Processing stage status",
        "fields": ["stage", "message", "detail", "progress"],
    },
    "tool_start": {
        "description": "Tool execution started",
        "fields": ["tool_id", "tool_name", "message", "params"],
    },
    "tool_progress": {
        "description": "Tool execution progress",
        "fields": ["tool_id", "progress", "message"],
    },
    "tool_end": {
        "description": "Tool execution completed",
        "fields": ["tool_id", "tool_name", "success", "result_summary"],
    },
    "metadata": {
        "description": "Query metadata",
        "fields": ["query_type", "response_type", "confidence"],
    },
    "visualization": {
        "description": "Chart/visualization specification",
        "fields": ["spec"],
    },
    "token": {
        "description": "Streaming response token",
        "fields": ["token"],
    },
    "done": {
        "description": "Processing complete",
        "fields": ["error", "message"],
    },
    "error": {
        "description": "Error occurred",
        "fields": ["error"],
    },
}
