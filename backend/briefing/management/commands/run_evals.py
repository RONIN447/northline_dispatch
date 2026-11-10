"""Run the golden briefing evaluation suite."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re

from django.core.management.base import BaseCommand, CommandError

from briefing.prompt import PROMPT_VERSION, get_system_prompt
from briefing.providers import MockProvider, get_provider
from briefing.service import generate_briefing
from evals.runner import (
    CATEGORY_LABELS,
    RAW_REPORT_DIR,
    create_run_id,
    REPORT_PATH,
    quality_gate_failures,
    render_report,
    render_comparison_report,
    raw_model_gate_failures,
    render_quality_gate,
    render_raw_model_gate,
    run_evaluations,
    write_failure_analysis,
    write_report,
)
from evals.scenarios import load_scenarios


class Command(BaseCommand):
    help = "Evaluate raw and validator-corrected briefings on the golden scenarios."

    def add_arguments(self, parser):
        gate_group = parser.add_mutually_exclusive_group()
        gate_group.add_argument(
            "--gate",
            action="store_true",
            help="Exit with an error if final-output pass rates miss configured thresholds.",
        )
        gate_group.add_argument(
            "--gate-raw",
            action="store_true",
            help="Manually gate raw model output; refuses to run with the mock provider.",
        )
        parser.add_argument(
            "--output",
            help="Write the report to this path instead of its default location.",
        )
        prompt_group = parser.add_mutually_exclusive_group()
        prompt_group.add_argument(
            "--prompt",
            choices=("v1", "v2"),
            help="Use one prompt version for the evaluation.",
        )
        prompt_group.add_argument(
            "--compare",
            nargs=2,
            choices=("v1", "v2"),
            metavar=("VERSION_A", "VERSION_B"),
            help="Run both prompt versions on the same scenarios and compare them.",
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
        try:
            if options["compare"]:
                if (
                    options["gate"]
                    or options["gate_raw"]
                    or options["failure_analysis"]
                ):
                    raise ValueError(
                        "Gate options and --failure-analysis cannot be combined with --compare."
                    )
                if set(options["compare"]) != {"v1", "v2"}:
                    raise ValueError("--compare must specify v1 and v2 once each.")
                self._handle_comparison(options)
                return

            prompt_version = options["prompt"] or PROMPT_VERSION
            get_system_prompt(prompt_version)
            report_path = Path(options["output"] or REPORT_PATH)
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
            if not scenarios:
                raise ValueError("No scenarios matched the requested filters.")
            run_id = create_run_id()
            raw_path = RAW_REPORT_DIR / "{}.jsonl".format(run_id)
            provider = get_provider()
            if options["gate_raw"] and isinstance(provider, MockProvider):
                raise ValueError(
                    "--gate-raw requires a hosted model provider; mock output "
                    "cannot be used for the raw-model gate."
                )
            results = []
            for batch in _scenario_batches(scenarios, 4):
                _, batch_results = run_evaluations(
                    batch,
                    generate=lambda plan: generate_briefing(
                        plan, provider=provider, prompt_version=prompt_version
                    ),
                    run_id=run_id,
                    raw_output_path=raw_path,
                    append_raw_output=bool(results),
                )
                results.extend(batch_results)
            intervention_counts = Counter(
                rule for result in results for rule in result["interventions"]
            )
            fallback_count = sum(result["fallback_used"] for result in results)
            mode = (
                "raw-model gate"
                if options["gate_raw"]
                else "final-output gate"
                if options["gate"]
                else "report only"
            )
            report = render_report(
                results, intervention_counts, fallback_count, run_id, mode=mode
            )
            if options["gate_raw"]:
                failures = raw_model_gate_failures(results)
                report += render_raw_model_gate(results)
            else:
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
        if options["gate_raw"] and failures:
            raise CommandError(
                "Raw-model evaluation gate failed: {}".format("; ".join(failures))
            )
        if options["gate"]:
            self.stdout.write(self.style.SUCCESS("Evaluation quality gate passed."))
        if options["gate_raw"]:
            self.stdout.write(self.style.SUCCESS("Raw-model evaluation gate passed."))

    def _handle_comparison(self, options):
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
        if not scenarios:
            raise ValueError("No scenarios matched the requested filters.")

        provider = get_provider()
        results_by_version = {}
        run_ids = {}
        for version in ("v1", "v2"):
            get_system_prompt(version)
            run_id = "compare_{}_{}".format(version, create_run_id())
            run_ids[version] = run_id
            raw_path = RAW_REPORT_DIR / "{}.jsonl".format(run_id)
            version_results = []
            for batch in _scenario_batches(deepcopy(scenarios), 4):
                _, batch_results = run_evaluations(
                    batch,
                    generate=lambda plan, selected_version=version: generate_briefing(
                        plan,
                        provider=provider,
                        prompt_version=selected_version,
                    ),
                    run_id=run_id,
                    raw_output_path=raw_path,
                    append_raw_output=bool(version_results),
                )
                version_results.extend(batch_results)
            results_by_version[version] = version_results

        report = render_comparison_report(results_by_version, run_ids)
        if options["output"]:
            report_path = Path(options["output"])
        else:
            model_name = _safe_model_name(results_by_version["v1"])
            date = datetime.now(timezone.utc).date().isoformat()
            report_path = REPORT_PATH.parent / "compare_{}_{}.md".format(
                model_name, date
            )
        write_report(report, report_path)
        self.stdout.write(
            self.style.SUCCESS(
                "Compared {} scenarios for v1 and v2; report written to {}.".format(
                    len(results_by_version["v1"]), report_path.resolve()
                )
            )
        )
        for version in ("v1", "v2"):
            self.stdout.write(
                self.style.SUCCESS(
                    "{} raw scenario details written to {}.".format(
                        version,
                        (RAW_REPORT_DIR / "{}.jsonl".format(run_ids[version])).resolve(),
                    )
                )
            )


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


def _safe_model_name(results):
    models = sorted({result["model"] for result in results})
    model_name = "_".join(models) if models else "unknown"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model_name).strip("._-") or "unknown"
