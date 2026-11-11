"""Shared deterministic validation checks for generated dispatch briefings."""

import re
from typing import Dict, List

from evals.grounding import check_grounding
from briefing.schema import Briefing
from routing.risk_levels import HIGH, NO_TRAVEL, RISK_SCORES, SEVERE

_WEATHER_FIELDS = ("windMph", "rainInHr", "snowInHr")
_FALSE_SAFE_CLAIM = re.compile(
    r"\b(?:safe(?:\s+to\s+(?:travel|drive|dispatch))?|"
    r"(?:the\s+)?route is clear|no\s+(?:weather\s+)?(?:risk|hazard)|"
    r"proceed with (?:the )?(?:recommended )?route)\b",
    re.IGNORECASE,
)


def validate_briefing(briefing: Briefing, route_plan: dict) -> List[str]:
    """Return stable check identifiers for unsupported or unsafe briefing claims."""
    errors = []
    routes = route_plan["routes"]
    recommended_route_id = route_plan["recommendedRouteId"]
    route_ids = {route["id"] for route in routes}

    if (
        briefing.recommended_route_id != recommended_route_id
        or briefing.recommended_route_id not in route_ids
    ):
        errors.append("recommended_route_mismatch")

    expected_risks = expected_route_risks(route_plan)
    expected_gaps = set(expected_data_gaps(route_plan))
    actual_risks = {item.route_id: item for item in briefing.route_risks}
    expected_by_route = {item["route_id"]: item for item in expected_risks}
    route_summaries_match = (
        len(actual_risks) == len(briefing.route_risks)
        and set(actual_risks) == set(expected_by_route)
    )
    worst_checkpoint_matches = route_summaries_match and all(
        actual_risks[route_id].worst_checkpoint.model_dump()
        == expected["worst_checkpoint"]
        for route_id, expected in expected_by_route.items()
    )
    risk_counts_match = route_summaries_match and all(
        actual_risks[route_id].severe_count == expected["severe_count"]
        and actual_risks[route_id].no_travel_count == expected["no_travel_count"]
        for route_id, expected in expected_by_route.items()
    )
    if not worst_checkpoint_matches:
        errors.append("worst_checkpoint_mismatch")
    if not risk_counts_match:
        errors.append("risk_count_mismatch")
    if not _risk_ranges_cover_checkpoints(briefing, route_plan):
        errors.append("risk_range_coverage_mismatch")
    if set(briefing.data_gaps) != expected_gaps or len(set(briefing.data_gaps)) != len(
        briefing.data_gaps
    ):
        errors.append("data_gap_mismatch")

    if _has_false_safe_claim(briefing, route_plan):
        errors.append("false_safe_claim")

    errors.extend(check_grounding(briefing, route_plan))
    return errors


def _has_false_safe_claim(briefing: Briefing, route_plan: dict) -> bool:
    recommended_route = next(
        route
        for route in route_plan["routes"]
        if route["id"] == route_plan["recommendedRouteId"]
    )
    recommended_has_risk_or_gap = any(
        RISK_SCORES.get(checkpoint.get("risk"), 0) >= RISK_SCORES[HIGH]
        or any(checkpoint.get(field) is None for field in _WEATHER_FIELDS)
        for checkpoint in recommended_route["checkpoints"]
    )
    claims = "{} {}".format(briefing.summary, " ".join(briefing.dispatcher_actions))
    claims_without_negated_safe = re.sub(
        r"\b(?:not|never|do not|don't|cannot|can't)\s+(?:be\s+)?safe\b",
        "",
        claims,
        flags=re.IGNORECASE,
    )
    return recommended_has_risk_or_gap and bool(
        _FALSE_SAFE_CLAIM.search(claims_without_negated_safe)
    )


def evaluate_checks(briefing: Briefing, route_plan: dict) -> Dict[str, bool]:
    """Evaluate named safety and grounding checks independently."""
    route_ids = {route["id"] for route in route_plan["routes"]}
    expected_risks = expected_route_risks(route_plan)
    expected_by_route = {item["route_id"]: item for item in expected_risks}
    actual_by_route = {item.route_id: item for item in briefing.route_risks}
    unique_routes = len(actual_by_route) == len(briefing.route_risks)
    route_set_matches = unique_routes and set(actual_by_route) == set(expected_by_route)
    worst_checkpoint_matches = route_set_matches and all(
        actual_by_route[route_id].worst_checkpoint.model_dump()
        == expected["worst_checkpoint"]
        for route_id, expected in expected_by_route.items()
    )
    risk_counts_match = route_set_matches and all(
        actual_by_route[route_id].severe_count == expected["severe_count"]
        and actual_by_route[route_id].no_travel_count == expected["no_travel_count"]
        for route_id, expected in expected_by_route.items()
    )
    expected_gaps = set(expected_data_gaps(route_plan))
    false_safe_claim = _has_false_safe_claim(briefing, route_plan)
    grounding_errors = check_grounding(briefing, route_plan)
    return {
        "route_matches_engine": (
            briefing.recommended_route_id == route_plan["recommendedRouteId"]
            and briefing.recommended_route_id in route_ids
        ),
        "worst_checkpoint_matches_engine": worst_checkpoint_matches,
        "risk_counts_match_plan": risk_counts_match,
        "risk_ranges_cover_checkpoints": _risk_ranges_cover_checkpoints(
            briefing, route_plan
        ),
        "data_gaps_match_plan": (
            expected_gaps == set(briefing.data_gaps)
            and len(briefing.data_gaps) == len(expected_gaps)
        ),
        "no_false_safe": not false_safe_claim,
        "numbers_grounded": "unsupported_number" not in grounding_errors,
        "route_ids_grounded": "unsupported_route_id" not in grounding_errors,
        "place_names_grounded": "unsupported_place_name" not in grounding_errors,
    }


def expected_route_risks(route_plan: dict) -> List[dict]:
    """Build canonical per-route risk summaries from engine-rated checkpoints."""
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


def _risk_ranges_cover_checkpoints(briefing: Briefing, route_plan: dict) -> bool:
    summaries = {item.route_id: item for item in briefing.route_risks}
    if len(summaries) != len(briefing.route_risks):
        return False
    for route in route_plan["routes"]:
        summary = summaries.get(route["id"])
        if summary is None:
            return False
        for checkpoint in route["checkpoints"]:
            level = checkpoint.get("risk")
            if level not in (SEVERE, NO_TRAVEL):
                continue
            mile = checkpoint["mile"]
            if not any(
                risk_range.level == level
                and risk_range.start_mile <= mile <= risk_range.end_mile
                for risk_range in summary.risk_ranges or []
            ):
                return False
    return True


def expected_data_gaps(route_plan: dict) -> List[str]:
    """Return canonical gap descriptions for missing checkpoint weather fields."""
    expected = []
    for route in route_plan["routes"]:
        for index, checkpoint in enumerate(route["checkpoints"]):
            missing = [field for field in _WEATHER_FIELDS if checkpoint.get(field) is None]
            if missing:
                expected.append(
                    "{} checkpoint {} is missing {}.".format(
                        route["id"], index, ", ".join(missing)
                    )
                )
    return expected
