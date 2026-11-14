"""Deterministic guardrails for generated dispatch briefings."""

from dataclasses import dataclass
from typing import List, Tuple

from briefing.facts import compute_briefing_facts
from briefing.schema import Briefing
from evals.checks import (
    evaluate_checks,
    validate_briefing,
)


@dataclass(frozen=True)
class Intervention:
    rule: str
    detail: str


class BriefingValidationError(RuntimeError):
    """Raised when a composed briefing fails shared safety checks."""


def enforce(plan: dict, briefing: Briefing) -> Tuple[Briefing, List[Intervention], bool]:
    """Validate a composed briefing and replace unsafe narrative with a template."""
    final = briefing.model_copy(deep=True)
    interventions = []
    fallback_used = False

    grounding_errors = validate_briefing(final, plan)
    if any(
        error in grounding_errors
        for error in (
            "unsupported_number",
            "unsupported_route_id",
            "unsupported_place_name",
            "false_safe_claim",
            "recommended_route_claim_mismatch",
            "risk_level_claim_mismatch",
            "forecast_gap_claim_mismatch",
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
    facts = compute_briefing_facts(plan)
    recommended_route_id = facts.recommended_route_id
    route = next(
        route for route in plan["routes"] if route["id"] == recommended_route_id
    )
    actions = ["Review checkpoint conditions before dispatch."]
    if facts.data_gaps:
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
        route_risks=facts.route_risks,
        data_gaps=facts.data_gaps,
        dispatcher_actions=actions,
    )
