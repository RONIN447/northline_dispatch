"""Shared deterministic validation checks for generated dispatch briefings."""

import re
from typing import Dict, List

from briefing.facts import compute_briefing_facts, expected_data_gaps, expected_route_risks
from briefing.schema import Briefing
from evals.grounding import _ROUTE_ID_PATTERN, check_grounding
from routing.risk_levels import NO_TRAVEL, RISK_SCORES, SEVERE

_WEATHER_FIELDS = ("windMph", "rainInHr", "snowInHr")
_RISK_LEVEL_PATTERN = re.compile(
    r"\b(?P<verb>is|has|shows|faces|carries|rated as|worst(?:\s+checkpoint)?"
    r"(?:\s+risk)?\s+is|worst(?:\s+checkpoint)?\s*:\s*)\s*"
    r"(?:the\s+|a\s+)?(?P<level>No\s+Travel|Low|Moderate|High|Severe)"
    r"(?:\s+risk)?\b",
    re.IGNORECASE,
)
_NO_GAP_CLAIM = re.compile(
    r"\b(?:forecast|weather)(?:\s+data)?\s+gaps?\s*:\s*"
    r"(?:none|no(?:ne)?|not\s+present)\b|"
    r"\bno\s+(?:required\s+)?(?:forecast|weather)(?:\s+data)?\s+gaps?\b|"
    r"\b(?:all|every)\s+(?:required\s+)?(?:weather|forecast)\s+data\s+"
    r"(?:is|are)\s+available\b",
    re.IGNORECASE,
)
_GAP_PRESENT_CLAIM = re.compile(
    r"\b(?:forecast|weather)(?:\s+data)?\s+gaps?\s*:\s*"
    r"(?!\s*(?:none|no\b|not\s+present\b))[^.!?;\n]+|"
    r"\b(?:forecast|weather)(?:\s+data)?\s+gaps?\s+"
    r"(?:exist|are\s+present|remain\s+present)\b|"
    r"\b(?:weather|forecast)\s+data\s+(?:is|are)\s+"
    r"(?:missing|unavailable)\b",
    re.IGNORECASE,
)
_RECOMMENDED_ROUTE_ID = re.compile(
    r"\b(?:recommend(?:ed|ation)?|choose|chosen|select|selected)\b"
    r"[^.!?;\n]{0,60}?(?P<route>route[-_\s]+\d+(?:[-_][A-Za-z0-9]+)*)\b|"
    r"(?P<reverse>route[-_\s]+\d+(?:[-_][A-Za-z0-9]+)*)\b"
    r"[^.!?;\n]{0,40}\b(?:is|as)\s+(?:the\s+)?"
    r"(?:recommended|safest|best)\b",
    re.IGNORECASE,
)
_FALSE_SAFE_CLAIM = re.compile(
    r"\b(?:safe(?:\s+to\s+(?:travel|drive|dispatch))?|"
    r"(?:the\s+)?route is clear|no\s+(?:weather\s+)?(?:risk|hazard)|"
    r"no\s+elevated\s+risk|proceed with (?:the )?(?:recommended )?route)\b",
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
    errors.extend(narrative_consistency_errors(briefing, route_plan))

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
        RISK_SCORES.get(checkpoint.get("risk"), 0)
        >= RISK_SCORES["Moderate"]
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
        "narrative_consistent_with_facts": not narrative_consistency_errors(
            briefing, route_plan
        ),
        "no_false_safe": not false_safe_claim,
        "numbers_grounded": "unsupported_number" not in grounding_errors,
        "route_ids_grounded": "unsupported_route_id" not in grounding_errors,
        "place_names_grounded": "unsupported_place_name" not in grounding_errors,
    }


def narrative_consistency_errors(briefing: Briefing, route_plan: dict) -> List[str]:
    """Return conflicts between model narrative claims and computed plan facts."""
    facts = compute_briefing_facts(route_plan)
    claims = "{} {}".format(briefing.summary, " ".join(briefing.dispatcher_actions))
    errors = []
    if _has_wrong_recommendation_claim(claims, facts.recommended_route_id, route_plan):
        errors.append("recommended_route_claim_mismatch")
    if _has_wrong_risk_claim(claims, facts.route_risks, route_plan):
        errors.append("risk_level_claim_mismatch")
    has_gaps = bool(facts.data_gaps)
    if (has_gaps and _NO_GAP_CLAIM.search(claims)) or (
        not has_gaps and _GAP_PRESENT_CLAIM.search(claims)
    ):
        errors.append("forecast_gap_claim_mismatch")
    return errors


def _has_wrong_recommendation_claim(claims, recommended_route_id, route_plan):
    for sentence in re.split(r"[.!?;\n]+", claims):
        for match in _RECOMMENDED_ROUTE_ID.finditer(sentence):
            route_id = match.group("route") or match.group("reverse")
            resolved = _resolve_route_id(route_id, route_plan)
            if resolved is not None and resolved != recommended_route_id:
                return True
    return False


def _has_wrong_risk_claim(claims, route_risks, route_plan):
    worst_by_route = {
        summary.route_id: summary.worst_checkpoint.level
        for summary in route_risks
    }
    levels_by_route = {
        route["id"]: {checkpoint.get("risk") for checkpoint in route["checkpoints"]}
        for route in route_plan["routes"]
    }
    recommended_route_id = route_plan["recommendedRouteId"]
    for sentence in re.split(r"[.!?;\n]+", claims):
        route_ids = {
            resolved
            for match in _ROUTE_ID_PATTERN.finditer(sentence)
            if (resolved := _resolve_route_id(match.group(), route_plan)) is not None
        }
        if re.search(r"\brecommended\s+route\b", sentence, re.IGNORECASE):
            route_ids.add(recommended_route_id)
        if not route_ids:
            continue
        match = _RISK_LEVEL_PATTERN.search(sentence)
        if not match:
            continue
        level = re.sub(r"\s+", " ", match.group("level")).title()
        verb = re.sub(r"\s+", " ", match.group("verb")).casefold()
        for route_id in route_ids:
            if verb.startswith("worst") or verb == "is":
                if level != worst_by_route[route_id]:
                    return True
            elif level not in levels_by_route[route_id]:
                return True
    return False


def _resolve_route_id(candidate, route_plan):
    normalized = re.sub(r"[^a-z0-9]", "", candidate.casefold())
    for route in route_plan["routes"]:
        route_id = str(route["id"])
        if normalized == re.sub(r"[^a-z0-9]", "", route_id.casefold()):
            return route_id
        prefix = re.match(r"route[-_\s]*(\d+)", route_id, re.IGNORECASE)
        if prefix and normalized == "route{}".format(prefix.group(1)):
            return route_id
    return None


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
