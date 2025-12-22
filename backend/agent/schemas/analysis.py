"""Schemas for data processing and analysis results."""

from enum import Enum
from pydantic import BaseModel, Field


class ChartType(str, Enum):
    """Supported visualization types."""
    # Line charts
    LAP_PROGRESSION = "lap_progression"     # Line chart of lap times
    LAP_COMPARISON = "lap_comparison"       # Head-to-head lap time comparison
    DELTA_LINE = "delta_line"               # Lap-by-lap time delta between drivers

    # Distribution charts
    BOX_PLOT = "box_plot"                   # Lap time distribution/consistency
    HISTOGRAM = "histogram"                 # Lap time frequency distribution
    VIOLIN_PLOT = "violin_plot"             # Distribution comparison

    # Bar charts
    BAR_CHART = "bar_chart"                 # Generic bar chart
    SECTOR_COMPARISON = "sector_comparison" # Grouped bar for sectors

    # F1-specific charts
    POSITION_BATTLE = "position_battle"     # Race trace / position changes
    TIRE_STRATEGY = "tire_strategy"         # Gantt-style strategy timeline
    GAP_EVOLUTION = "gap_evolution"         # Gap to leader over laps
    RACE_PROGRESS = "race_progress"         # Animated race replay with car icons
    SPEED_TRACE = "speed_trace"             # Telemetry speed overlay

    # Other
    SCATTER = "scatter"                     # Scatter plot (e.g., tire deg)
    TABLE = "table"                         # Data table


class LapAnalysis(BaseModel):
    """Aggregated lap time analysis for a driver."""

    driver: str = Field(description="Driver code")
    total_laps: int = Field(default=0)
    fastest_lap: float | None = Field(default=None, description="Fastest lap in seconds")
    fastest_lap_number: int | None = Field(default=None)
    average_pace: float | None = Field(default=None, description="Average lap time in seconds")
    consistency: float | None = Field(default=None, description="Std deviation of lap times")
    sector_1_best: float | None = Field(default=None)
    sector_2_best: float | None = Field(default=None)
    sector_3_best: float | None = Field(default=None)


class StintSummary(BaseModel):
    """Summary of a single stint."""

    stint_number: int
    compound: str = Field(description="Tire compound (SOFT, MEDIUM, HARD)")
    start_lap: int
    end_lap: int
    total_laps: int
    average_pace: float | None = Field(default=None)
    degradation_per_lap: float | None = Field(default=None, description="Seconds lost per lap")
    pit_in_lap: int | None = Field(default=None)


class DriverComparison(BaseModel):
    """Head-to-head comparison between two drivers."""

    driver_1: str
    driver_2: str
    driver_1_avg_pace: float | None = Field(default=None)
    driver_2_avg_pace: float | None = Field(default=None)
    pace_delta: float | None = Field(default=None, description="Positive = driver_1 faster")
    driver_1_fastest: float | None = Field(default=None)
    driver_2_fastest: float | None = Field(default=None)
    fastest_lap_delta: float | None = Field(default=None)
    sector_deltas: dict[str, float] = Field(
        default_factory=dict,
        description="Sector-by-sector delta (S1, S2, S3)"
    )
    laps_compared: int = Field(default=0)


class VisualizationSpec(BaseModel):
    """Specification for frontend chart rendering."""

    id: str = Field(description="Unique ID for this visualization")
    type: ChartType = Field(description="Type of chart to render")
    title: str = Field(description="Chart title")
    data: list[dict] = Field(
        default_factory=list,
        description="Data points for the chart"
    )
    config: dict = Field(
        default_factory=dict,
        description="Chart-specific configuration"
    )
    drivers: list[str] = Field(
        default_factory=list,
        description="Drivers in the chart (for color coding)"
    )
    annotations: list[dict] = Field(
        default_factory=list,
        description="Annotations (pit stops, incidents, etc.)"
    )


class ProcessedAnalysis(BaseModel):
    """Output of the PROCESS node - aggregated analysis ready for LLM."""

    # Aggregated data
    lap_analysis: dict[str, LapAnalysis] = Field(
        default_factory=dict,
        description="Per-driver lap analysis"
    )
    stint_summaries: dict[str, list[StintSummary]] = Field(
        default_factory=dict,
        description="Per-driver stint summaries"
    )
    comparisons: list[DriverComparison] = Field(
        default_factory=list,
        description="Driver comparisons"
    )

    # Key insights (pre-computed for LLM)
    key_insights: list[str] = Field(
        default_factory=list,
        description="Pre-computed key findings"
    )

    # Data quality metrics
    completeness_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="How complete is the data (0-1)"
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="How reliable is the data (0-1)"
    )
    missing_data: list[str] = Field(
        default_factory=list,
        description="Data we couldn't fetch"
    )

    # Visualization recommendations
    recommended_viz: list[ChartType] = Field(
        default_factory=list,
        description="Recommended chart types for this analysis"
    )


class EvaluationResult(BaseModel):
    """Output of the EVALUATE node - decision on data sufficiency."""

    is_sufficient: bool = Field(
        description="Is the data sufficient to generate a good response?"
    )
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall quality score"
    )
    feedback: str = Field(
        default="",
        description="Feedback for PLAN node if looping back"
    )
    iteration: int = Field(
        default=0,
        description="Current iteration count"
    )
