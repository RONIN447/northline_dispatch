"""Deterministic briefing facts derived from a validated route plan."""

from typing import List

from pydantic import BaseModel, ConfigDict

from briefing.schema import RouteRiskSummary
from routing.risk_levels import NO_TRAVEL, RISK_SCORES, SEVERE

_WEATHER_FIELDS = ("windMph", "rainInHr", "snowInHr")


class BriefingFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommended_route_id: str
    route_risks: List[RouteRiskSummary]
    data_gaps: List[str]


def compute_briefing_facts(route_plan: dict) -> BriefingFacts:
    """Compute recommendation, per-route risks, and forecast gaps from the plan."""
    route_ids = {route["id"] for route in route_plan["routes"]}
    recommended_route_id = route_plan["recommendedRouteId"]
    if recommended_route_id not in route_ids:
        raise ValueError("recommendedRouteId must match a route in routes.")
    return BriefingFacts(
        recommended_route_id=recommended_route_id,
        route_risks=[
            RouteRiskSummary.model_validate(item)
            for item in expected_route_risks(route_plan)
        ],
        data_gaps=expected_data_gaps(route_plan),
    )


def expected_route_risks(route_plan: dict) -> List[dict]:
    """Build canonical per-route risk summaries from rated checkpoints."""
    expected = []
    for route in route_plan["routes"]:
        checkpoints = route["checkpoints"]
        if not checkpoints:
            raise ValueError("Route {} has no checkpoints.".format(route["id"]))
        for checkpoint in checkpoints:
            if checkpoint.get("risk") not in RISK_SCORES:
                raise ValueError("Route plan contains an unknown checkpoint risk.")

        worst_index = max(
            range(len(checkpoints)),
            key=lambda index: RISK_SCORES[checkpoints[index]["risk"]],
        )
        risk_summary = {
            "route_id": route["id"],
            "worst_checkpoint": {
                "index": worst_index,
                "level": checkpoints[worst_index]["risk"],
            },
            "severe_count": sum(
                checkpoint["risk"] == SEVERE for checkpoint in checkpoints
            ),
            "no_travel_count": sum(
                checkpoint["risk"] == NO_TRAVEL for checkpoint in checkpoints
            ),
        }
        risk_ranges = []
        current_range = None
        for checkpoint in checkpoints:
            level = checkpoint["risk"]
            if level in (SEVERE, NO_TRAVEL):
                if current_range is not None and current_range["level"] == level:
                    current_range["end_mile"] = checkpoint["mile"]
                else:
                    current_range = {
                        "start_mile": checkpoint["mile"],
                        "end_mile": checkpoint["mile"],
                        "level": level,
                    }
                    risk_ranges.append(current_range)
            else:
                current_range = None
        if risk_ranges:
            risk_summary["risk_ranges"] = risk_ranges
        expected.append(risk_summary)
    return expected


def expected_data_gaps(route_plan: dict) -> List[str]:
    """Return canonical descriptions for missing required checkpoint weather."""
    expected = []
    for route in route_plan["routes"]:
        for index, checkpoint in enumerate(route["checkpoints"]):
            missing = [
                field
                for field in _WEATHER_FIELDS
                if checkpoint.get(field) is None
            ]
            if missing:
                expected.append(
                    "{} checkpoint {} is missing {}.".format(
                        route["id"], index, ", ".join(missing)
                    )
                )
    return expected
