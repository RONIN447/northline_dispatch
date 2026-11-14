"""Run raw and validator-corrected briefings against the golden scenarios."""

from collections import Counter
import csv
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import queue
import threading
import time

from briefing.facts import compute_briefing_facts
from briefing.providers import get_provider
from briefing.validator import enforce
from evals.checks import evaluate_checks
from evals.grounding import find_offending_tokens
from evals.scenarios import load_scenarios

FACT_CHECK_NAMES = (
    "route_matches_engine",
    "worst_checkpoint_matches_engine",
    "risk_counts_match_plan",
    "risk_ranges_cover_checkpoints",
    "data_gaps_match_plan",
)
NARRATIVE_CHECK_NAMES = (
    "narrative_consistent_with_facts",
    "no_false_safe",
    "numbers_grounded",
    "route_ids_grounded",
    "place_names_grounded",
)
CHECK_NAMES = FACT_CHECK_NAMES + NARRATIVE_CHECK_NAMES
FAILURE_REASONS = {
    "route_matches_engine": "The generated recommendation did not match the engine-selected route.",
    "worst_checkpoint_matches_engine": "The reported worst checkpoint did not match the engine.",
    "risk_counts_match_plan": "Reported Severe or No Travel counts did not match the plan.",
    "risk_ranges_cover_checkpoints": "One or more Severe or No Travel checkpoints fell outside the listed risk ranges.",
    "data_gaps_match_plan": "The reported forecast gaps did not match missing weather fields in the plan.",
    "narrative_consistent_with_facts": "The model narrative contradicted a code-computed route, risk, or forecast-gap fact.",
    "no_false_safe": "The briefing made an unsafe reassurance claim.",
    "numbers_grounded": "The briefing included a number not supported by the route plan.",
    "route_ids_grounded": "The briefing included a route ID not present in the route plan.",
    "place_names_grounded": "The briefing included a place name not grounded in the route plan.",
}
CATEGORY_LABELS = {
    "normal_trip": "normal",
    "severe_or_no_travel": "severe",
    "forecast_unavailable": "forecast gap",
    "threshold_boundary": "threshold",
    "all_routes_risky": "all-risky",
    "near_tie_routes": "near-tie",
}
REPORT_PATH = Path(__file__).resolve().parent / "reports" / "latest.md"
RAW_REPORT_DIR = REPORT_PATH.parent / "raw"
THRESHOLDS_PATH = Path(__file__).resolve().parent / "thresholds.yaml"
_logger = logging.getLogger(__name__)


def create_run_id():
    """Return a UTC run identifier precise enough to avoid concurrent collisions."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def run_evaluations(
    scenarios=None,
    generate=None,
    run_id=None,
    raw_output_path=None,
    append_raw_output=False,
    repetition=1,
    delay_seconds=0.0,
    timeout_seconds=30.0,
    completed_scenarios=None,
    provider_name=None,
    model_name=None,
    prompt_version=None,
):
    """Evaluate scenarios, recording per-call timeouts and optional pacing."""
    if scenarios is None:
        scenarios = load_scenarios()
    if run_id is None:
        run_id = create_run_id()
    if generate is None:
        from briefing.service import generate_briefing

        provider = get_provider()
        generate = lambda plan: generate_briefing(plan, provider=provider)

    if raw_output_path is not None:
        raw_output_path = Path(raw_output_path)
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        if not append_raw_output:
            raw_output_path.write_text("", encoding="utf-8")

    results = []
    intervention_counts = Counter()
    fallback_count = 0
    completed_scenarios = set(completed_scenarios or ())
    first_call = True
    for scenario in scenarios:
        if scenario["id"] in completed_scenarios:
            continue
        wait_events = []
        if not first_call and delay_seconds:
            _logger.info(
                "Evaluation pacing wait run_id=%s repetition=%s scenario_id=%s "
                "duration_seconds=%.3f",
                run_id,
                repetition,
                scenario["id"],
                delay_seconds,
            )
            time.sleep(delay_seconds)
            wait_events.append(
                {
                    "reason": "evaluation pacing delay",
                    "duration_ms": delay_seconds * 1000,
                }
            )
        first_call = False
        plan = scenario["plan"]
        code_facts = compute_briefing_facts(plan).model_dump(mode="json")
        try:
            raw, metadata = _call_with_timeout(generate, plan, timeout_seconds)
        except TimeoutError:
            error = "Briefing generation timed out after {:.1f} seconds.".format(
                timeout_seconds
            )
            result = _timeout_result(
                scenario,
                run_id,
                repetition,
                error,
                wait_events,
                provider_name,
                model_name,
                prompt_version,
                code_facts,
            )
            results.append(result)
            if raw_output_path is not None:
                write_raw_results(results[-1:], raw_output_path, run_id, append=True)
            completed_scenarios.add(scenario["id"])
            continue
        wait_events.extend(metadata.wait_events or [])
        raw_checks = evaluate_checks(raw, plan)
        offending_tokens = find_offending_tokens(raw, plan)
        final, interventions, fallback_used = enforce(plan, raw)
        final_checks = evaluate_checks(final, plan)
        intervention_counts.update(item.rule for item in interventions)
        fallback_count += int(fallback_used)
        results.append(
            {
                "id": scenario["id"],
                "run_id": run_id,
                "repetition": repetition,
                "error": None,
                "category": scenario.get("category", "uncategorized"),
                "provider": metadata.provider,
                "model": metadata.model,
                "prompt_version": metadata.prompt_version,
                "raw_llm_output": metadata.raw_output
                or json.dumps(
                    {
                        "summary": raw.summary,
                        "dispatcher_actions": raw.dispatcher_actions,
                    },
                    ensure_ascii=False,
                ),
                "parsed_narrative": {
                    "summary": raw.summary,
                    "dispatcher_actions": raw.dispatcher_actions,
                },
                "code_facts": code_facts,
                "expected_data_gaps": code_facts["data_gaps"],
                "final_output": final.model_dump_json(indent=2),
                "raw_checks": raw_checks,
                "final_checks": final_checks,
                "failed_checks": [
                    {
                        "check": check,
                        "offending_tokens": _offending_tokens_for_check(
                            check, offending_tokens, raw, plan
                        ),
                    }
                    for check in CHECK_NAMES
                    if not raw_checks[check]
                ],
                "input_tokens": metadata.input_tokens,
                "output_tokens": metadata.output_tokens,
                "total_tokens": metadata.input_tokens + metadata.output_tokens,
                "latency_ms": metadata.latency_ms,
                "finish_reason": metadata.finish_reason,
                "wait_ms": metadata.wait_ms + sum(
                    event["duration_ms"]
                    for event in wait_events
                    if event["reason"] == "evaluation pacing delay"
                ),
                "wait_events": wait_events,
                "retry_count": metadata.retry_count,
                "interventions": [item.rule for item in interventions],
                "intervention_details": [
                    {"rule": item.rule, "detail": item.detail}
                    for item in interventions
                ],
                "fallback_used": fallback_used,
            }
        )
        if raw_output_path is not None:
            write_raw_results(
                results[-1:], raw_output_path, run_id, append=True
            )
        completed_scenarios.add(scenario["id"])

    report = render_report(results, intervention_counts, fallback_count, run_id)
    return report, results


def _call_with_timeout(generate, plan, timeout_seconds):
    result_queue = queue.Queue(maxsize=1)

    def invoke():
        try:
            result_queue.put((True, generate(plan)))
        except Exception as error:
            result_queue.put((False, error))

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        raise TimeoutError()
    succeeded, result = result_queue.get_nowait()
    if not succeeded:
        raise result
    return result


def _timeout_result(
    scenario,
    run_id,
    repetition,
    error,
    wait_events,
    provider_name,
    model_name,
    prompt_version,
    code_facts,
):
    checks = {check: True for check in FACT_CHECK_NAMES}
    checks.update({check: False for check in NARRATIVE_CHECK_NAMES})
    return {
        "id": scenario["id"],
        "run_id": run_id,
        "repetition": repetition,
        "error": error,
        "category": scenario.get("category", "uncategorized"),
        "provider": provider_name or "unknown",
        "model": model_name or "unknown",
        "prompt_version": prompt_version or "unknown",
        "raw_llm_output": "",
        "parsed_narrative": None,
        "code_facts": code_facts,
        "expected_data_gaps": code_facts["data_gaps"],
        "final_output": "",
        "raw_checks": checks,
        "final_checks": checks.copy(),
        "failed_checks": [
            {
                "check": check,
                "offending_tokens": {
                    name: [] for name in ("numbers", "route_ids", "place_names")
                },
            }
            for check in NARRATIVE_CHECK_NAMES
        ],
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0.0,
        "wait_ms": sum(event["duration_ms"] for event in wait_events),
        "wait_events": wait_events,
        "finish_reason": None,
        "retry_count": 0,
        "interventions": [],
        "intervention_details": [],
        "fallback_used": False,
    }


def _offending_tokens_for_check(check, offending_tokens, briefing, route_plan):
    tokens = {name: [] for name in ("numbers", "route_ids", "place_names")}
    if check == "numbers_grounded":
        tokens["numbers"] = offending_tokens["numbers"]
    elif check == "route_ids_grounded":
        tokens["route_ids"] = offending_tokens["route_ids"]
    elif check == "place_names_grounded":
        tokens["place_names"] = offending_tokens["place_names"]
    elif (
        check == "route_matches_engine"
        and briefing.recommended_route_id != route_plan["recommendedRouteId"]
    ):
        tokens["route_ids"] = [briefing.recommended_route_id]
    return tokens


def render_report(
    results, intervention_counts, fallback_count, run_id=None, mode="report"
):
    """Render aggregate raw/final pass rates and correction counts as Markdown."""
    total = len(results)
    providers = sorted({result["provider"] for result in results})
    models = sorted({result["model"] for result in results})
    prompt_versions = sorted({result["prompt_version"] for result in results})
    lines = [
        "# Briefing evaluation report",
        "",
        "- Date (UTC): {}".format(datetime.now(timezone.utc).date().isoformat()),
        "- Mode: {}".format(mode),
        "- Provider: {}".format(", ".join(providers) or "unknown"),
        "- Model: {}".format(", ".join(models) or "unknown"),
        "- Prompt version: {}".format(", ".join(prompt_versions) or "unknown"),
        "- Run ID: {}".format(run_id or "unknown"),
        "- Raw scenario data: raw/{}.jsonl".format(run_id or "unknown"),
        "- Raw-check basis: model narrative composed with plan-derived route facts.",
        "",
        "Scenarios: {} | Raw briefings: {} | Validator-corrected briefings: {}".format(
            total, total, total
        ),
        "",
        "## Run summary",
        "",
        "Fallback rate: {}/{} ({:.1f}%) | Retry rate: {}/{} ({:.1f}%)".format(
            fallback_count,
            total,
            _percentage(fallback_count, total),
            sum(result["retry_count"] > 0 for result in results),
            total,
            _percentage(sum(result["retry_count"] > 0 for result in results), total),
        ),
        "Latency p50: {:.1f} ms | p95: {:.1f} ms | Average tokens: {:.1f} "
        "(input {:.1f}, output {:.1f})".format(
            _percentile([result["latency_ms"] for result in results], 50),
            _percentile([result["latency_ms"] for result in results], 95),
            _average([result["total_tokens"] for result in results]),
            _average([result["input_tokens"] for result in results]),
            _average([result["output_tokens"] for result in results]),
        ),
        "Timeout/error records: {} | Wait time total: {:.1f} ms "
        "(separate from provider latency)".format(
            sum(bool(result.get("error")) for result in results),
            sum(result.get("wait_ms", 0.0) for result in results),
        ),
        "",
        "## Facts (code-computed)",
        "",
        "These checks validate fields assembled from the route plan; they are not "
        "model-quality metrics.",
        "",
        "| Fact check | Raw pass rate | Final pass rate |",
        "| --- | ---: | ---: |",
    ]
    for check in FACT_CHECK_NAMES:
        raw_passes = sum(result["raw_checks"][check] for result in results)
        final_passes = sum(result["final_checks"][check] for result in results)
        lines.append(
            "| {} | {}/{} ({:.1f}%) | {}/{} ({:.1f}%) |".format(
                check,
                raw_passes,
                total,
                _percentage(raw_passes, total),
                final_passes,
                total,
                _percentage(final_passes, total),
            )
        )

    lines.extend(
        [
            "",
            "## Narrative (model-generated)",
            "",
            "| Narrative check | Raw pass rate | Final pass rate |",
            "| --- | ---: | ---: |",
        ]
    )
    for check in NARRATIVE_CHECK_NAMES:
        raw_passes = sum(result["raw_checks"][check] for result in results)
        final_passes = sum(result["final_checks"][check] for result in results)
        lines.append(
            "| {} | {}/{} ({:.1f}%) | {}/{} ({:.1f}%) |".format(
                check,
                raw_passes,
                total,
                _percentage(raw_passes, total),
                final_passes,
                total,
                _percentage(final_passes, total),
            )
        )

    lines.extend(
        [
            "",
            "## Pass rates by scenario category",
            "",
            "### Facts (code-computed)",
            "",
            "| Category | Scenarios | Fact check | Raw pass rate | Final pass rate |",
            "| --- | ---: | --- | ---: | ---: |",
        ]
    )
    observed_categories = {result["category"] for result in results}
    categories = [category for category in CATEGORY_LABELS if category in observed_categories]
    categories.extend(sorted(observed_categories - set(CATEGORY_LABELS)))
    for category in categories:
        category_results = [
            result for result in results if result["category"] == category
        ]
        category_total = len(category_results)
        for check in FACT_CHECK_NAMES:
            raw_passes = sum(
                result["raw_checks"][check] for result in category_results
            )
            final_passes = sum(
                result["final_checks"][check] for result in category_results
            )
            lines.append(
                "| {} | {} | {} | {:.1f}% ({}/{}) | {:.1f}% ({}/{}) |".format(
                    CATEGORY_LABELS.get(category, category),
                    category_total,
                    check,
                    _percentage(raw_passes, category_total),
                    raw_passes,
                    category_total,
                    _percentage(final_passes, category_total),
                    final_passes,
                    category_total,
                )
            )

    lines.extend(
        [
            "",
            "### Narrative (model-generated)",
            "",
            "| Category | Scenarios | Narrative check | Raw pass rate | Final pass rate |",
            "| --- | ---: | --- | ---: | ---: |",
        ]
    )
    for category in categories:
        category_results = [
            result for result in results if result["category"] == category
        ]
        category_total = len(category_results)
        for check in NARRATIVE_CHECK_NAMES:
            raw_passes = sum(
                result["raw_checks"][check] for result in category_results
            )
            final_passes = sum(
                result["final_checks"][check] for result in category_results
            )
            lines.append(
                "| {} | {} | {} | {:.1f}% ({}/{}) | {:.1f}% ({}/{}) |".format(
                    CATEGORY_LABELS.get(category, category),
                    category_total,
                    check,
                    _percentage(raw_passes, category_total),
                    raw_passes,
                    category_total,
                    _percentage(final_passes, category_total),
                    final_passes,
                    category_total,
                )
            )

    lines.extend(
        [
            "",
            "## Validator interventions",
            "",
            "Fallback template used: {}/{} scenarios.".format(fallback_count, total),
        ]
    )
    if intervention_counts:
        lines.extend(["", "| Rule | Count |", "| --- | ---: |"])
        for rule, count in sorted(intervention_counts.items()):
            lines.append("| {} | {} |".format(rule, count))
    else:
        lines.extend(["", "No validator interventions were required."])
    lines.extend(
        [
            "",
            "## Scenario results",
            "",
            "| Scenario | Provider | Code facts | Raw narrative | Final narrative | Fallback |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for result in results:
        fact_passes = sum(result["raw_checks"][check] for check in FACT_CHECK_NAMES)
        raw_narrative_passes = sum(
            result["raw_checks"][check] for check in NARRATIVE_CHECK_NAMES
        )
        final_narrative_passes = sum(
            result["final_checks"][check] for check in NARRATIVE_CHECK_NAMES
        )
        lines.append(
            "| {} | {} | {}/{} | {}/{} | {}/{} | {} |".format(
                result["id"],
                result["provider"],
                fact_passes,
                len(FACT_CHECK_NAMES),
                raw_narrative_passes,
                len(NARRATIVE_CHECK_NAMES),
                final_narrative_passes,
                len(NARRATIVE_CHECK_NAMES),
                "yes" if result["fallback_used"] else "no",
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_comparison_report(results_by_version, run_ids=None):
    """Render a side-by-side comparison of two prompt-version evaluation runs."""
    versions = list(results_by_version)
    if len(versions) != 2 or any(version not in {"v1", "v2"} for version in versions):
        raise ValueError("Prompt comparison requires exactly v1 and v2 results.")
    if set(versions) != {"v1", "v2"}:
        raise ValueError("Prompt comparison requires both v1 and v2 results.")
    v1_results = results_by_version["v1"]
    v2_results = results_by_version["v2"]
    if not v1_results or not v2_results:
        raise ValueError("Prompt comparison requires non-empty scenario results.")
    if [result["id"] for result in v1_results] != [
        result["id"] for result in v2_results
    ]:
        raise ValueError("Prompt versions must be evaluated on the same scenarios.")

    all_results = v1_results + v2_results
    providers = sorted({result["provider"] for result in all_results})
    models = sorted({result["model"] for result in all_results})
    total = len(v1_results)
    lines = [
        "# Prompt comparison evaluation",
        "",
        "- Date (UTC): {}".format(datetime.now(timezone.utc).date().isoformat()),
        "- Mode: prompt comparison",
        "- Provider: {}".format(", ".join(providers) or "unknown"),
        "- Model: {}".format(", ".join(models) or "unknown"),
        "- Scenarios per version: {}".format(total),
        "- Scenario set: identical across v1 and v2",
        "- Raw-check basis: model narrative composed with plan-derived route facts.",
    ]
    for version in ("v1", "v2"):
        run_id = (run_ids or {}).get(version, "unknown")
        lines.append(
            "- {} raw scenario data: raw/{}.jsonl".format(version, run_id)
        )
    lines.extend(
        [
            "",
            "## Side-by-side results",
            "",
            "| Metric | v1 | v2 |",
            "| --- | ---: | ---: |",
        ]
    )
    for version in ("v1", "v2"):
        results = results_by_version[version]
        fallback_count = sum(result["fallback_used"] for result in results)
        retry_count = sum(result["retry_count"] > 0 for result in results)
        values = {
            "Fallback rate": "{}/{} ({:.1f}%)".format(
                fallback_count, total, _percentage(fallback_count, total)
            ),
            "Retry rate": "{}/{} ({:.1f}%)".format(
                retry_count, total, _percentage(retry_count, total)
            ),
            "Latency p50": "{:.1f} ms".format(
                _percentile([result["latency_ms"] for result in results], 50)
            ),
            "Latency p95": "{:.1f} ms".format(
                _percentile([result["latency_ms"] for result in results], 95)
            ),
            "Average tokens": "{:.1f} (input {:.1f}, output {:.1f})".format(
                _average([result["total_tokens"] for result in results]),
                _average([result["input_tokens"] for result in results]),
                _average([result["output_tokens"] for result in results]),
            ),
        }
        for check in FACT_CHECK_NAMES:
            passed = sum(result["raw_checks"].get(check, False) for result in results)
            values["Code facts: {}".format(check)] = "{}/{} ({:.1f}%)".format(
                passed, total, _percentage(passed, total)
            )
        for check in NARRATIVE_CHECK_NAMES:
            passed = sum(result["raw_checks"].get(check, False) for result in results)
            values["Model narrative: {}".format(check)] = "{}/{} ({:.1f}%)".format(
                passed, total, _percentage(passed, total)
            )
        if version == "v1":
            v1_values = values
        else:
            v2_values = values
    for metric, v1_value in v1_values.items():
        lines.append("| {} | {} | {} |".format(metric, v1_value, v2_values[metric]))

    lines.extend(
        [
            "",
            "## Functional targets",
            "",
            "Targets: fallback rate under 20%; model narrative consistency, "
            "no_false_safe, and each raw grounding check above 90%. Route and risk "
            "facts are application-computed and checked separately by the final-output gate.",
            "",
            "| Target | v1 | v2 |",
            "| --- | --- | --- |",
        ]
    )
    for version in ("v1", "v2"):
        results = results_by_version[version]
        total = len(results)
        rates = {
            "fallback": _percentage(
                sum(result["fallback_used"] for result in results), total
            ),
            "narrative_consistent_with_facts": _percentage(
                sum(
                    result["raw_checks"].get(
                        "narrative_consistent_with_facts", False
                    )
                    for result in results
                ),
                total,
            ),
            "no_false_safe": _percentage(
                sum(result["raw_checks"]["no_false_safe"] for result in results),
                total,
            ),
            "numbers_grounded": _percentage(
                sum(result["raw_checks"]["numbers_grounded"] for result in results),
                total,
            ),
            "route_ids_grounded": _percentage(
                sum(result["raw_checks"]["route_ids_grounded"] for result in results),
                total,
            ),
            "place_names_grounded": _percentage(
                sum(result["raw_checks"]["place_names_grounded"] for result in results),
                total,
            ),
        }
        target_results = {
            "fallback under 20%": rates["fallback"] < 20,
            "narrative consistency above 90%": (
                rates["narrative_consistent_with_facts"] > 90
            ),
            "narrative no_false_safe above 90%": rates["no_false_safe"] > 90,
            "numbers_grounded above 90%": rates["numbers_grounded"] > 90,
            "route_ids_grounded above 90%": rates["route_ids_grounded"] > 90,
            "place_names_grounded above 90%": rates["place_names_grounded"] > 90,
        }
        if version == "v1":
            v1_targets = target_results
        else:
            v2_targets = target_results
    for target, v1_pass in v1_targets.items():
        lines.append(
            "| {} | {} | {} |".format(
                target,
                "PASS" if v1_pass else "NOT MET",
                "PASS" if v2_targets[target] else "NOT MET",
            )
        )
    lines.extend(
        [
            "",
            "Route selection, risk summaries, and forecast gaps are code-computed "
            "facts. Narrative metrics evaluate only model-written prose and actions; "
            "the final-output gate verifies the assembled response.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report, path=REPORT_PATH):
    """Persist a completed report, creating the report directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def write_raw_results(results, path, run_id, append=False):
    """Write one self-contained diagnostic JSON object per scenario."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as output_file:
        for result in results:
            record = {
                "run_id": run_id,
                "repetition": result.get("repetition", 1),
                "scenario_id": result["id"],
                "error": result.get("error"),
                "category": result["category"],
                "provider": result["provider"],
                "model": result["model"],
                "prompt_version": result["prompt_version"],
                "raw_model_text": result["raw_llm_output"],
                "model_narrative": result["parsed_narrative"],
                "code_facts": result["code_facts"],
                "expected_data_gaps": result["expected_data_gaps"],
                "raw_checks": result["raw_checks"],
                "final_checks": result["final_checks"],
                "failed_checks": result["failed_checks"],
                "retry_count": result["retry_count"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "latency_ms": result["latency_ms"],
                "wait_ms": result.get("wait_ms", 0.0),
                "wait_events": result.get("wait_events", []),
                "finish_reason": result["finish_reason"],
                "interventions": result["intervention_details"],
                "fallback_used": result["fallback_used"],
            }
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_raw_results(paths):
    """Load JSONL records from one or more evaluation runs with line-level errors."""
    records = []
    for path in paths:
        path = Path(path)
        with path.open(encoding="utf-8") as input_file:
            for line_number, line in enumerate(input_file, 1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(
                        "{}:{} is not valid JSONL.".format(path, line_number)
                    ) from error
    return records


def render_merged_report(records, raw_paths):
    """Render one aggregate report from saved raw JSONL records."""
    if not records:
        raise ValueError("No evaluation records were found in the selected JSONL files.")
    run_ids = list(dict.fromkeys(record.get("run_id", "unknown") for record in records))
    providers = sorted({record.get("provider", "unknown") for record in records})
    models = sorted({record.get("model", "unknown") for record in records})
    prompts = sorted({record.get("prompt_version", "unknown") for record in records})
    total = len(records)
    lines = [
        "# Merged briefing evaluation report",
        "",
        "- Date (UTC): {}".format(datetime.now(timezone.utc).date().isoformat()),
        "- Mode: merged raw-model report",
        "- Provider: {}".format(", ".join(providers)),
        "- Model: {}".format(", ".join(models)),
        "- Prompt version(s): {}".format(", ".join(prompts)),
        "- Run IDs: {}".format(", ".join(run_ids)),
        "- Metrics separate code-computed facts from model-generated narrative.",
        "",
        "Records: {} | Timeout/error records: {}".format(
            total, sum(bool(record.get("error")) for record in records)
        ),
        "Fallback rate: {}/{} ({:.1f}%) | Retry rate: {}/{} ({:.1f}%)".format(
            sum(bool(record.get("fallback_used")) for record in records),
            total,
            _percentage(
                sum(bool(record.get("fallback_used")) for record in records), total
            ),
            sum(int(record.get("retry_count", 0)) > 0 for record in records),
            total,
            _percentage(
                sum(int(record.get("retry_count", 0)) > 0 for record in records),
                total,
            ),
        ),
        "Latency p50: {:.1f} ms | p95: {:.1f} ms | Average tokens: {:.1f}".format(
            _percentile(
                [float(record.get("latency_ms", 0.0)) for record in records], 50
            ),
            _percentile(
                [float(record.get("latency_ms", 0.0)) for record in records], 95
            ),
            _average(
                [
                    int(record.get("input_tokens", 0))
                    + int(record.get("output_tokens", 0))
                    for record in records
                ]
            ),
        ),
        "Wait time total: {:.1f} ms (excluded from provider latency).".format(
            sum(float(record.get("wait_ms", 0.0)) for record in records)
        ),
        "",
        "## Facts (code-computed)",
        "",
        "| Fact check | Pass rate |",
        "| --- | ---: |",
    ]
    for check in FACT_CHECK_NAMES:
        passed = sum(
            bool(record.get("raw_checks", {}).get(check, False))
            for record in records
        )
        lines.append(
            "| {} | {}/{} ({:.1f}%) |".format(
                check, passed, total, _percentage(passed, total)
            )
        )
    lines.extend(
        [
            "",
            "## Narrative (model-generated)",
            "",
            "| Narrative check | Raw pass rate |",
            "| --- | ---: |",
        ]
    )
    for check in NARRATIVE_CHECK_NAMES:
        passed = sum(
            bool(record.get("raw_checks", {}).get(check, False))
            for record in records
        )
        lines.append(
            "| {} | {}/{} ({:.1f}%) |".format(
                check, passed, total, _percentage(passed, total)
            )
        )
    lines.extend(["", "## Input JSONL files", ""])
    lines.extend("- `{}`".format(Path(path).resolve()) for path in raw_paths)
    lines.extend(["", "## Scenario records", "", "| Run ID | Rep | Category | Scenario | Error |", "|---|---:|---|---|---|"])
    for record in records:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                record.get("run_id", "unknown"),
                record.get("repetition", 1),
                record.get("category", "unknown"),
                record.get("scenario_id", "unknown"),
                record.get("error") or "",
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_failure_analysis(results, path):
    """Write one CSV row per raw failed check with generated and corrected output."""
    fieldnames = (
        "scenario_id",
        "category",
        "failed_check",
        "raw_llm_output",
        "validator_action",
        "final_output",
        "reason_for_failure",
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            for check in CHECK_NAMES:
                if result["raw_checks"][check]:
                    continue
                writer.writerow(
                    {
                        "scenario_id": result["id"],
                        "category": CATEGORY_LABELS.get(
                            result["category"], result["category"]
                        ),
                        "failed_check": check,
                        "raw_llm_output": result["raw_llm_output"],
                        "validator_action": "; ".join(
                            "{}: {}".format(item["rule"], item["detail"])
                            for item in result["intervention_details"]
                        ),
                        "final_output": result["final_output"],
                        "reason_for_failure": FAILURE_REASONS[check],
                    }
                )


def load_thresholds(path=THRESHOLDS_PATH, section="final"):
    """Load and validate the final-output or raw-model gate thresholds."""
    import yaml

    with path.open(encoding="utf-8") as threshold_file:
        config = yaml.safe_load(threshold_file)
    if not isinstance(config, dict):
        raise ValueError("Thresholds must define final and raw_model sections.")

    final = config.get("final")
    if not isinstance(final, dict):
        raise ValueError("Thresholds must define a final mapping.")
    _validate_pass_rates(final, set(CHECK_NAMES), "final")

    raw_model = config.get("raw_model")
    raw_pass_rates = (
        raw_model.get("minimum_pass_rates") if isinstance(raw_model, dict) else None
    )
    if not isinstance(raw_pass_rates, dict):
        raise ValueError("Thresholds must define raw_model.minimum_pass_rates.")
    _validate_pass_rates(
        raw_pass_rates,
        set(NARRATIVE_CHECK_NAMES),
        "raw_model.minimum_pass_rates",
        required={
            "narrative_consistent_with_facts",
            "no_false_safe",
            "numbers_grounded",
            "route_ids_grounded",
            "place_names_grounded",
        },
    )
    maximum_fallback_rate = raw_model.get("maximum_fallback_rate")
    _validate_rate(maximum_fallback_rate, "raw_model.maximum_fallback_rate")

    if section == "final":
        return final
    if section == "raw_model":
        return {
            "minimum_pass_rates": raw_pass_rates,
            "maximum_fallback_rate": maximum_fallback_rate,
        }
    raise ValueError("Threshold section must be 'final' or 'raw_model'.")


def _validate_pass_rates(rates, allowed, label, required=None):
    unknown = set(rates) - allowed
    if unknown:
        raise ValueError(
            "Unknown {} checks: {}".format(label, ", ".join(sorted(unknown)))
        )
    missing = (required or allowed) - set(rates)
    if missing:
        raise ValueError(
            "Missing {} thresholds: {}".format(label, ", ".join(sorted(missing)))
        )
    for check, threshold in rates.items():
        _validate_rate(threshold, "{}.{}".format(label, check))


def _validate_rate(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Threshold for {} must be a number.".format(label))
    if not 0 <= value <= 1:
        raise ValueError("Threshold for {} must be between 0 and 1.".format(label))


def quality_gate_failures(results, thresholds=None):
    """Return final pass-rate threshold violations for the requested checks."""
    if thresholds is None:
        thresholds = load_thresholds(section="final")
    total = len(results)
    failures = []
    for check, minimum in thresholds.items():
        passed = sum(result["final_checks"][check] for result in results)
        rate = passed / total if total else 0.0
        if rate < minimum:
            failures.append(
                "{}: final pass rate {:.1%} is below required {:.1%}".format(
                    check, rate, minimum
                )
            )
    return failures


def raw_model_gate_failures(results, thresholds=None):
    """Return raw-output and fallback-rate threshold violations."""
    if thresholds is None:
        thresholds = load_thresholds(section="raw_model")
    minimum_rates = thresholds["minimum_pass_rates"]
    total = len(results)
    failures = []
    for check, minimum in minimum_rates.items():
        passed = sum(result["raw_checks"][check] for result in results)
        rate = passed / total if total else 0.0
        if rate < minimum:
            failures.append(
                "{}: raw pass rate {:.1%} is below required {:.1%}".format(
                    check, rate, minimum
                )
            )
    fallback_count = sum(result["fallback_used"] for result in results)
    fallback_rate = fallback_count / total if total else 0.0
    maximum_fallback_rate = thresholds["maximum_fallback_rate"]
    if fallback_rate >= maximum_fallback_rate:
        failures.append(
            "fallback rate {:.1%} must be below maximum {:.1%}".format(
                fallback_rate, maximum_fallback_rate
            )
        )
    return failures


def render_quality_gate(results, thresholds=None):
    """Render final pass rates against the configured CI thresholds."""
    if thresholds is None:
        thresholds = load_thresholds()
    total = len(results)
    lines = ["", "## Final-output quality gate", ""]
    lines.extend(
        [
            "| Check | Final pass rate | Required | Result |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for check, minimum in thresholds.items():
        passed = sum(result["final_checks"][check] for result in results)
        rate = passed / total if total else 0.0
        result = "PASS" if rate >= minimum else "FAIL"
        lines.append(
            "| {} | {:.1%} | {:.1%} | {} |".format(
                check, rate, minimum, result
            )
        )
    return "\n".join(lines) + "\n"


def render_raw_model_gate(results, thresholds=None):
    """Render raw-model pass rates and fallback rate against configured targets."""
    if thresholds is None:
        thresholds = load_thresholds(section="raw_model")
    total = len(results)
    lines = [
        "",
        "## Raw-model quality gate",
        "",
        "Only narrative checks are gated here; route selection, risk summaries, and "
        "forecast gaps are computed from the plan and checked by the final-output gate.",
        "",
        "| Check | Raw pass rate | Minimum | Result |",
        "| --- | ---: | ---: | --- |",
    ]
    for check, minimum in thresholds["minimum_pass_rates"].items():
        passed = sum(result["raw_checks"][check] for result in results)
        rate = passed / total if total else 0.0
        outcome = "PASS" if rate >= minimum else "FAIL"
        lines.append(
            "| {} | {:.1%} ({}/{}) | {:.1%} | {} |".format(
                check, rate, passed, total, minimum, outcome
            )
        )
    fallback_count = sum(result["fallback_used"] for result in results)
    fallback_rate = fallback_count / total if total else 0.0
    maximum = thresholds["maximum_fallback_rate"]
    outcome = "PASS" if fallback_rate < maximum else "FAIL"
    lines.append(
        "| fallback_rate | {:.1%} ({}/{}) | < {:.1%} | {} |".format(
            fallback_rate, fallback_count, total, maximum, outcome
        )
    )
    return "\n".join(lines) + "\n"


def _percentage(passes, total):
    return 100.0 * passes / total if total else 0.0


def _average(values):
    return sum(values) / len(values) if values else 0.0


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
