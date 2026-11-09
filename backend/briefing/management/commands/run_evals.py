"""Run the golden briefing evaluation suite."""

from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from briefing.providers import get_provider
from briefing.service import generate_briefing
from evals.runner import (
    CATEGORY_LABELS,
    RAW_REPORT_DIR,
    create_run_id,
    REPORT_PATH,
    quality_gate_failures,
    render_report,
    render_quality_gate,
    run_evaluations,
    write_failure_analysis,
    write_report,
)
from evals.scenarios import load_scenarios


class Command(BaseCommand):
    help = "Evaluate raw and validator-corrected briefings on the golden scenarios."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gate",
            action="store_true",
            help="Exit with an error if final pass rates miss configured thresholds.",
        )
        parser.add_argument(
            "--output",
            default=str(REPORT_PATH),
            help="Write the report to this path instead of evals/reports/latest.md.",
        )
        parser.add_argument(
            "--failure-analysis",
            help="Export raw failed checks and validator corrections to this CSV path.",
        )
        parser.add_argument(
            "--limit",
            type=_positive_int,
            help="Evaluate only the first N scenarios after category filtering.",
        )
        parser.add_argument(
            "--category",
            help="Evaluate one scenario category (ID or report label).",
        )

    def handle(self, *args, **options):
        report_path = Path(options["output"])
        try:
            scenarios = load_scenarios()
            category = options["category"]
            if category:
                category_id = _category_id(category)
                scenarios = [
                    scenario
                    for scenario in scenarios
                    if scenario.get("category") == category_id
                ]
            if options["limit"] is not None:
                scenarios = scenarios[: options["limit"]]
            run_id = create_run_id()
            raw_path = RAW_REPORT_DIR / "{}.jsonl".format(run_id)
            provider = get_provider()
            generate = lambda plan: generate_briefing(plan, provider=provider)
            results = []
            for batch in _scenario_batches(scenarios, 4):
                _, batch_results = run_evaluations(
                    batch,
                    generate=generate,
                    run_id=run_id,
                    raw_output_path=raw_path,
                    append_raw_output=bool(results),
                )
                results.extend(batch_results)
            intervention_counts = Counter(
                rule for result in results for rule in result["interventions"]
            )
            fallback_count = sum(result["fallback_used"] for result in results)
            report = render_report(
                results, intervention_counts, fallback_count, run_id
            )
            failures = quality_gate_failures(results)
            report += render_quality_gate(results)
            write_report(report, report_path)
            if options["failure_analysis"]:
                write_failure_analysis(results, Path(options["failure_analysis"]))
        except ValueError as error:
            raise CommandError(str(error)) from error
        except Exception as error:
            raise CommandError(
                "Briefing evaluation failed ({}): {}".format(
                    type(error).__name__, error
                )
            ) from error
        self.stdout.write(
            self.style.SUCCESS(
                "Evaluated {} scenarios; report written to {}.".format(
                    len(results), report_path.resolve()
                )
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Raw scenario details written to {}.".format(raw_path.resolve())
            )
        )
        if options["failure_analysis"]:
            self.stdout.write(
                self.style.SUCCESS(
                    "Failure analysis written to {}.".format(
                        Path(options["failure_analysis"]).resolve()
                    )
                )
            )
        if options["gate"] and failures:
            raise CommandError(
                "Evaluation quality gate failed: {}".format("; ".join(failures))
            )
        if options["gate"]:
            self.stdout.write(self.style.SUCCESS("Evaluation quality gate passed."))


def _positive_int(value):
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError("--limit must be a positive integer.") from error
    if parsed < 1:
        raise ValueError("--limit must be a positive integer.")
    return parsed


def _category_id(value):
    normalized = value.strip().casefold()
    for category_id, label in CATEGORY_LABELS.items():
        if normalized in {category_id.casefold(), label.casefold()}:
            return category_id
    choices = ", ".join(
        "{} ({})".format(category_id, label)
        for category_id, label in CATEGORY_LABELS.items()
    )
    raise ValueError("Unknown category {!r}. Choose from: {}.".format(value, choices))


def _scenario_batches(scenarios, batch_size):
    categories = dict.fromkeys(
        scenario.get("category", "uncategorized") for scenario in scenarios
    )
    for category in categories:
        category_scenarios = [
            scenario
            for scenario in scenarios
            if scenario.get("category", "uncategorized") == category
        ]
        for start in range(0, len(category_scenarios), batch_size):
            yield category_scenarios[start : start + batch_size]
