"""Pydantic schemas for validating weather-aware route plans."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from routing.risk_levels import NO_TRAVEL, RISK_LEVELS, SEVERE


class BriefingLocation(BaseModel):
    label: str
    lat: float
    lon: float
    timezone: str


class BriefingCheckpoint(BaseModel):
    mile: float
    lat: float
    lon: float
    eta: str
    windMph: float
    rainInHr: float
    snowInHr: float
    temperatureF: Optional[float] = None
    forecastHour: Optional[str] = None
    risk: str

    @field_validator("risk")
    @classmethod
    def validate_risk(cls, value: str) -> str:
        if value not in RISK_LEVELS:
            raise ValueError(f"Risk must be one of: {', '.join(RISK_LEVELS)}")
        return value


class BriefingRoute(BaseModel):
    id: str
    distanceMiles: float
    durationHours: float
    arrival: str
    geometry: List[List[float]]
    checkpoints: List[BriefingCheckpoint]
    severeMiles: float
    highMiles: float
    noTravelMiles: float
    averageRisk: float
    summary: str
    recommended: bool


class BriefingRoutePlan(BaseModel):
    origin: BriefingLocation
    destination: BriefingLocation
    routes: List[BriefingRoute]
    recommendedRouteId: str
    forecastHours: int

    @model_validator(mode="after")
    def recommended_route_exists(self) -> "BriefingRoutePlan":
        if not any(route.id == self.recommendedRouteId for route in self.routes):
            raise ValueError("recommendedRouteId must match a route in routes")
        return self


class WorstCheckpoint(BaseModel):
    index: int = Field(ge=0)
    level: str

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        if value not in RISK_LEVELS:
            raise ValueError(f"Level must be one of: {', '.join(RISK_LEVELS)}")
        return value


class RiskRange(BaseModel):
    start_mile: float
    end_mile: float
    level: str

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        if value not in (SEVERE, NO_TRAVEL):
            raise ValueError(f"Risk range level must be {SEVERE} or {NO_TRAVEL}")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "RiskRange":
        if self.end_mile < self.start_mile:
            raise ValueError("end_mile must be greater than or equal to start_mile")
        return self


class RouteRiskSummary(BaseModel):
    route_id: str
    worst_checkpoint: WorstCheckpoint
    severe_count: int = Field(ge=0)
    no_travel_count: int = Field(ge=0)
    risk_ranges: Optional[List[RiskRange]] = None


class Briefing(BaseModel):
    recommended_route_id: str
    summary: str
    route_risks: List[RouteRiskSummary]
    data_gaps: List[str]
    dispatcher_actions: List[str]


class BriefingNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    dispatcher_actions: List[str] = Field(max_length=3)

    @field_validator("summary")
    @classmethod
    def summary_under_word_limit(cls, value: str) -> str:
        if len(value.split()) > 80:
            raise ValueError("Summary must be under 80 words.")
        return value
