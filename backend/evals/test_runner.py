"""Tests for raw/final evaluation and report generation."""

import json
import os
import csv
import unittest
from io import StringIO
from unittest.mock import patch

import django
from django.core.management import call_command
from django.core.management.base import CommandError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
django.setup()

from briefing.providers import MockProvider
from briefing.schema import Briefing
from briefing.service import BriefingMetadata
from evals.checks import evaluate_checks
from evals.runner import (
    CHECK_NAMES,
    load_thresholds,
    quality_gate_failures,
    render_comparison_report,
    run_evaluations,
    write_failure_analysis,
    write_raw_results,
    write_report,
)
from evals.scenarios import load_scenarios


class EvaluationRunnerTests(unittest.TestCase):
    def test_runner_records_raw_final_pass_rates_interventions_and_fallbacks(self):
        scenario = next(
            scenario
            for scenario in load_scenarios()
            if scenario["category"] == "severe_or_no_travel"
        )

        def generate(plan):
            response = MockProvider("faulty_number").generate("", json.dumps(plan))
            return (
                Briefing.model_validate_json(response.text),
                BriefingMetadata(
                    provider="mock",
                    model="rule-based",
                    prompt_version="v1",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=0,
                    retry_count=0,
                    raw_output=response.text,
                ),
            )

        report, results = run_evaluations([scenario], generate)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["raw_checks"]["numbers_grounded"])
        self.assertTrue(all(results[0]["final_checks"].values()))
        self.assertTrue(results[0]["fallback_used"])
        self.assertIn("fallback_template", results[0]["interventions"])
        self.assertIn("Raw pass rate", report)
        self.assertIn("Fallback rate: 1/1", report)
        self.assertIn("Average tokens", report)
        self.assertIn("Final pass rate", report)
        self.assertIn("Provider: mock", report)
        self.assertIn("Model: rule-based", report)
        self.assertIn("Prompt version: v1", report)
        self.assertIn("Pass rates by scenario category", report)
        self.assertIn("| severe | 1 |", report)
        self.assertIn("fallback_template", report)
        self.assertIn("999 hours", results[0]["raw_llm_output"])
        self.assertNotIn("999 hours", results[0]["final_output"])
        self.assertEqual(
            results[0]["failed_checks"][0]["offending_tokens"]["numbers"],
            ["999"],
        )
        self.assertEqual(
            len(CHECK_NAMES),
            len(
                evaluate_checks(
                    Briefing.model_validate_json(
                        MockProvider("normal")
                        .generate("", json.dumps(scenario["plan"]))
                        .text
                    ),
                    scenario["plan"],
                )
            ),
        )

    def test_runner_reuses_one_provider_for_all_scenarios(self):
        scenarios = load_scenarios()[:2]
        provider = MockProvider("normal")
        with patch("evals.runner.get_provider", return_value=provider) as get_provider:
            _, results = run_evaluations(scenarios)

        self.assertEqual(len(results), 2)
        get_provider.assert_called_once_with()

    def test_runner_streams_completed_scenario_lines_to_raw_jsonl(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        scenarios = load_scenarios()[:2]
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "raw" / "run.jsonl"
            with patch(
                "evals.runner.get_provider", return_value=MockProvider("normal")
            ):
                run_evaluations(
                    scenarios,
                    run_id="run",
                    raw_output_path=path,
                )
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(records), 2)
        self.assertEqual(
            [record["scenario_id"] for record in records],
            [scenario["id"] for scenario in scenarios],
        )
        self.assertTrue(all(record["expected_data_gaps"] == [] for record in records))

    def test_raw_jsonl_records_failed_check_tokens_and_generation_metadata(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        scenario = next(
            item
            for item in load_scenarios()
            if item["category"] == "severe_or_no_travel"
        )

        def generate(plan):
            response = MockProvider("faulty_number").generate("", json.dumps(plan))
            return (
                Briefing.model_validate_json(response.text),
                BriefingMetadata(
                    provider="mock",
                    model="rule-based",
                    prompt_version="v1",
                    input_tokens=12,
                    output_tokens=8,
                    latency_ms=3.5,
                    retry_count=1,
                    raw_output=response.text,
                    finish_reason="stop",
                ),
            )

        _, results = run_evaluations([scenario], generate, run_id="run-1")
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "raw" / "run-1.jsonl"
            write_raw_results(results, path, "run-1")
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIn("999 hours", record["raw_model_text"])
        self.assertEqual(
            record["parsed_briefing"]["recommended_route_id"],
            scenario["plan"]["recommendedRouteId"],
        )
        self.assertIn("expected_data_gaps", record)
        self.assertEqual(record["failed_checks"][0]["check"], "numbers_grounded")
        self.assertEqual(
            record["failed_checks"][0]["offending_tokens"]["numbers"], ["999"]
        )
        self.assertEqual(record["retry_count"], 1)
        self.assertEqual(record["input_tokens"], 12)
        self.assertEqual(record["output_tokens"], 8)
        self.assertEqual(record["latency_ms"], 3.5)
        self.assertEqual(record["finish_reason"], "stop")
        self.assertTrue(record["interventions"])

    def test_report_lists_interventions_only_as_rule_counts(self):
        scenario = next(iter(load_scenarios()))

        def generate(plan):
            response = MockProvider("faulty_number").generate("", json.dumps(plan))
            return (
                Briefing.model_validate_json(response.text),
                BriefingMetadata(
                    provider="mock",
                    model="rule-based",
                    prompt_version="v1",
                    input_tokens=1,
                    output_tokens=1,
                    latency_ms=10,
                    retry_count=0,
                    raw_output=response.text,
                ),
            )

        report, _ = run_evaluations([scenario], generate)
        scenario_table = report.split("## Scenario results", 1)[1]
        self.assertIn("| Rule | Count |", report)
        self.assertNotIn("| Interventions |", scenario_table)
        self.assertNotIn("fallback_template |", scenario_table)

    def test_failure_analysis_csv_contains_raw_failure_and_validator_correction(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        scenario = next(
            item
            for item in load_scenarios()
            if item["category"] == "severe_or_no_travel"
        )

        def generate(plan):
            response = MockProvider("faulty_number").generate("", json.dumps(plan))
            return (
                Briefing.model_validate_json(response.text),
                BriefingMetadata(
                    provider="mock",
                    model="rule-based",
                    prompt_version="v1",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=0,
                    retry_count=0,
                    raw_output=response.text,
                ),
            )

        _, results = run_evaluations([scenario], generate)
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "analysis" / "failures.csv"
            write_failure_analysis(results, path)
            with path.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

        number_failure = next(
            row for row in rows if row["failed_check"] == "numbers_grounded"
        )
        self.assertEqual(number_failure["scenario_id"], scenario["id"])
        self.assertEqual(number_failure["category"], "severe")
        self.assertIn("999 hours", number_failure["raw_llm_output"])
        self.assertIn("fallback_template", number_failure["validator_action"])
        self.assertNotIn("999 hours", number_failure["final_output"])
        self.assertIn("number not supported", number_failure["reason_for_failure"])

    def test_report_is_written_to_requested_location(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reports" / "latest.md"
            write_report("# report\n", path)
            self.assertEqual(path.read_text(encoding="utf-8"), "# report\n")

    def test_comparison_report_shows_side_by_side_metrics_and_targets(self):
        checks = {
            "route_matches_engine": True,
            "worst_checkpoint_matches_engine": True,
            "risk_counts_match_plan": True,
            "risk_ranges_cover_checkpoints": True,
            "no_false_safe": True,
            "numbers_grounded": True,
            "route_ids_grounded": True,
            "place_names_grounded": True,
        }
        base_result = {
            "id": "scenario-1",
            "provider": "mock",
            "model": "rule-based",
            "raw_checks": checks,
            "fallback_used": False,
            "retry_count": 0,
            "latency_ms": 25,
            "input_tokens": 100,
            "output_tokens": 40,
            "total_tokens": 140,
        }
        report = render_comparison_report(
            {"v1": [base_result], "v2": [dict(base_result, fallback_used=True)]},
            {"v1": "run-v1", "v2": "run-v2"},
        )

        self.assertIn("| Metric | v1 | v2 |", report)
        self.assertIn("| Fallback rate | 0/1 (0.0%) | 1/1 (100.0%) |", report)
        self.assertIn("| Raw: numbers_grounded | 1/1 (100.0%) |", report)
        self.assertIn("| Raw: no_risk_downgrade (derived) | 1/1 (100.0%) |", report)
        self.assertIn("fallback under 20%", report)
        self.assertIn("raw/run-v1.jsonl", report)

    def test_comparison_report_requires_same_scenario_set(self):
        result = {
            "id": "scenario-1",
            "provider": "mock",
            "model": "rule-based",
            "raw_checks": {},
            "fallback_used": False,
            "retry_count": 0,
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        with self.assertRaisesRegex(ValueError, "same scenarios"):
            render_comparison_report(
                {"v1": [result], "v2": [dict(result, id="scenario-2")]}
            )

    def test_configured_thresholds_are_all_safety_checks_at_100_percent(self):
        thresholds = load_thresholds()
        self.assertEqual(set(thresholds), set(CHECK_NAMES))
        self.assertTrue(all(value == 1.0 for value in thresholds.values()))

    def test_quality_gate_reports_threshold_misses(self):
        checks = {name: True for name in CHECK_NAMES}
        checks["no_false_safe"] = False
        failures = quality_gate_failures(
            [{"final_checks": checks}],
            {"route_matches_engine": 1.0, "no_false_safe": 1.0},
        )
        self.assertEqual(
            failures,
            ["no_false_safe: final pass rate 0.0% is below required 100.0%"],
        )

    def test_management_command_exits_with_error_when_gate_fails(self):
        report_results = [
            {
                "final_checks": {name: True for name in CHECK_NAMES},
                "interventions": [],
                "fallback_used": False,
            }
        ]
        with patch(
            "briefing.management.commands.run_evals.run_evaluations",
            return_value=("# report", report_results),
        ), patch(
            "briefing.management.commands.run_evals.render_report",
            return_value="# report\n",
        ), patch(
            "briefing.management.commands.run_evals.quality_gate_failures",
            return_value=["no_false_safe: threshold missed"],
        ), patch(
            "briefing.management.commands.run_evals.render_quality_gate",
            return_value="\n# gate\n",
        ), patch("briefing.management.commands.run_evals.write_report"):
            with self.assertRaises(CommandError):
                call_command("run_evals", "--gate", stdout=StringIO())

    def test_management_command_filters_by_category_and_limit(self):
        report_results = [
            {
                "final_checks": {name: True for name in CHECK_NAMES},
                "interventions": [],
                "fallback_used": False,
            }
        ]
        with patch(
            "briefing.management.commands.run_evals.run_evaluations",
            return_value=("# report", report_results),
        ) as run_evaluations, patch(
            "briefing.management.commands.run_evals.render_report",
            return_value="# report\n",
        ), patch(
            "briefing.management.commands.run_evals.quality_gate_failures",
            return_value=[],
        ), patch(
            "briefing.management.commands.run_evals.render_quality_gate",
            return_value="\n# gate\n",
        ), patch("briefing.management.commands.run_evals.write_report"):
            call_command(
                "run_evals",
                "--category",
                "severe",
                "--limit",
                "2",
                stdout=StringIO(),
            )

        selected_scenarios = run_evaluations.call_args.args[0]
        self.assertEqual(len(selected_scenarios), 2)
        self.assertTrue(
            all(item["category"] == "severe_or_no_travel" for item in selected_scenarios)
        )
        self.assertEqual(len(run_evaluations.call_args.kwargs["run_id"]), 22)

    def test_management_command_compares_v1_and_v2_on_same_scenarios(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        scenario = load_scenarios()[0]
        checks = {
            "route_matches_engine": True,
            "worst_checkpoint_matches_engine": True,
            "risk_counts_match_plan": True,
            "risk_ranges_cover_checkpoints": True,
            "no_false_safe": True,
            "numbers_grounded": True,
            "route_ids_grounded": True,
            "place_names_grounded": True,
        }
        observed_versions = []

        def fake_run(scenarios, generate, **kwargs):
            _, metadata = generate(scenarios[0]["plan"])
            observed_versions.append(metadata.prompt_version)
            return "", [
                {
                    "id": scenarios[0]["id"],
                    "provider": metadata.provider,
                    "model": metadata.model,
                    "prompt_version": metadata.prompt_version,
                    "raw_checks": checks,
                    "fallback_used": False,
                    "retry_count": 0,
                    "latency_ms": 1.0,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "interventions": [],
                }
            ]

        with TemporaryDirectory() as temp_dir:
            reports = Path(temp_dir) / "reports"
            with patch(
                "briefing.management.commands.run_evals.load_scenarios",
                return_value=[scenario],
            ), patch(
                "briefing.management.commands.run_evals.get_provider",
                return_value=MockProvider(),
            ), patch(
                "briefing.management.commands.run_evals.run_evaluations",
                side_effect=fake_run,
            ) as run_evaluations, patch(
                "briefing.management.commands.run_evals.RAW_REPORT_DIR",
                reports / "raw",
            ), patch(
                "briefing.management.commands.run_evals.REPORT_PATH",
                reports / "latest.md",
            ):
                output = StringIO()
                call_command(
                    "run_evals",
                    "--compare",
                    "v1",
                    "v2",
                    stdout=output,
                )

            self.assertEqual(run_evaluations.call_count, 2)
            self.assertEqual(
                run_evaluations.call_args_list[0].args[0][0]["id"],
                run_evaluations.call_args_list[1].args[0][0]["id"],
            )
            self.assertEqual(observed_versions, ["v1", "v2"])
            generated_reports = list(reports.glob("compare_rule-based_*.md"))
            self.assertEqual(len(generated_reports), 1)
            self.assertIn("Compared 1 scenarios", output.getvalue())
