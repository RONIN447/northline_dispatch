"""Deterministic guardrails for generated dispatch briefings."""

from dataclasses import dataclass
from typing import List, Tuple

from briefing.schema import Briefing, RouteRiskSummary
from evals.checks import (
    evaluate_checks,
    expected_data_gaps,
    expected_route_risks,
    validate_briefing,
)


@dataclass(frozen=True)
class Intervention:
    rule: str
    detail: str


class BriefingValidationError(RuntimeError):
    """Raised if validator corrections cannot satisfy the shared safety checks."""


def enforce(plan: dict, briefing: Briefing) -> Tuple[Briefing, List[Intervention], bool]:
    """Return a corrected briefing, structured interventions, and fallback status."""
    final = briefing.model_copy(deep=True)
    interventions = []
    fallback_used = False

    recommended_route_id = plan["recommendedRouteId"]
    if final.recommended_route_id != recommended_route_id:
        interventions.append(
            Intervention(
                rule="canonical_recommended_route",
                detail="Changed recommended route to {}.".format(recommended_route_id),
            )
        )
        final.recommended_route_id = recommended_route_id

    canonical_gaps = expected_data_gaps(plan)
    if final.data_gaps != canonical_gaps:
        interventions.append(
            Intervention(
                rule="restore_data_gaps",
                detail="Replaced briefing data gaps with the plan's canonical missing-weather list.",
            )
        )
        final.data_gaps = canonical_gaps

    expected_risks = [
        RouteRiskSummary.model_validate(item)
        for item in expected_route_risks(plan)
    ]
    expected_by_route = {item.route_id: item for item in expected_risks}
    actual_by_route = {}
    for item in final.route_risks:
        expected = expected_by_route.get(item.route_id)
        if expected is None:
            interventions.append(
                Intervention(
                    rule="remove_unexpected_route_risk",
                    detail="Removed a risk summary for unknown route {}.".format(
                        item.route_id
                    ),
                )
            )
            continue
        if item.route_id in actual_by_route:
            interventions.append(
                Intervention(
                    rule="remove_duplicate_route_risk",
                    detail="Removed duplicate risk summary for route {}.".format(
                        item.route_id
                    ),
                )
            )
            continue
        actual_by_route[item.route_id] = item
        if item.worst_checkpoint != expected.worst_checkpoint:
            interventions.append(
                Intervention(
                    rule="restore_worst_checkpoint",
                    detail="Restored the engine's worst checkpoint for route {}.".format(
                        item.route_id
                    ),
                )
            )
        if (
            item.severe_count != expected.severe_count
            or item.no_travel_count != expected.no_travel_count
        ):
            interventions.append(
                Intervention(
                    rule="restore_risk_counts",
                    detail="Replaced Severe and No Travel counts for route {} with plan counts.".format(
                        item.route_id
                    ),
                )
            )
        if item.risk_ranges != expected.risk_ranges:
            interventions.append(
                Intervention(
                    rule="restore_risk_ranges",
                    detail="Replaced risk ranges for route {} with plan-derived ranges.".format(
                        item.route_id
                    ),
                )
            )

    for item in expected_risks:
        if item.route_id not in actual_by_route:
            interventions.append(
                Intervention(
                    rule="add_route_risk",
                    detail="Added the plan-derived risk summary for route {}.".format(
                        item.route_id
                    ),
                )
            )
    if [item.route_id for item in final.route_risks if item.route_id in expected_by_route] != [
        item.route_id for item in expected_risks if item.route_id in actual_by_route
    ]:
        interventions.append(
            Intervention(
                rule="order_route_risks",
                detail="Ordered route risk summaries to match the route plan.",
            )
        )
    final.route_risks = expected_risks

    grounding_errors = validate_briefing(final, plan)
    if any(
        error in grounding_errors
        for error in (
            "unsupported_number",
            "unsupported_route_id",
            "unsupported_place_name",
            "false_safe_claim",
        )
    ):
        final = _template_briefing(plan)
        fallback_used = True
        interventions.append(
            Intervention(
                rule="fallback_template",
                detail="Replaced ungrounded summary/actions with a deterministic plan-based template.",
            )
        )

    remaining_errors = validate_briefing(final, plan)
    failed_checks = [
        check
        for check, passed in evaluate_checks(final, plan).items()
        if not passed
    ]
    if remaining_errors or failed_checks:
        raise BriefingValidationError(
            "Briefing validator could not satisfy shared checks: {}".format(
                ", ".join(remaining_errors + failed_checks)
            )
        )
    return final, interventions, fallback_used


def _template_briefing(plan: dict) -> Briefing:
    recommended_route_id = plan["recommendedRouteId"]
    route = next(
        route for route in plan["routes"] if route["id"] == recommended_route_id
    )
    route_risks = [
        RouteRiskSummary.model_validate(item)
        for item in expected_route_risks(plan)
    ]
    data_gaps = expected_data_gaps(plan)
    actions = ["Review checkpoint conditions before dispatch."]
    if data_gaps:
        actions.append("Review the listed forecast data gaps before dispatch.")
    return Briefing(
        recommended_route_id=recommended_route_id,
        summary=(
            "Recommended route: {} ({} mi, {} hr); severe exposure {} mi, "
            "high-risk exposure {} mi, no-travel exposure {} mi."
        ).format(
            recommended_route_id,
            route["distanceMiles"],
            route["durationHours"],
            route["severeMiles"],
            route["highMiles"],
            route["noTravelMiles"],
        ),
        route_risks=route_risks,
        data_gaps=data_gaps,
        dispatcher_actions=actions,
    )
