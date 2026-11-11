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
from briefing.schema import BriefingNarrative
from briefing.service import compose_briefing
from briefing.service import BriefingMetadata
from evals.checks import evaluate_checks
from evals.runner import (
    CHECK_NAMES,
    load_thresholds,
    quality_gate_failures,
    raw_model_gate_failures,
    render_comparison_report,
    render_merged_report,
    render_raw_model_gate,
    render_report,
    run_evaluations,
    write_failure_analysis,
    write_raw_results,
    write_report,
)
from evals.scenarios import load_scenarios


def _mock_briefing_and_response(plan, mode):
    response = MockProvider(mode).generate("", json.dumps(plan))
    narrative = BriefingNarrative.model_validate_json(response.text)
    return compose_briefing(plan, narrative), response


class EvaluationRunnerTests(unittest.TestCase):
    def test_runner_records_raw_final_pass_rates_interventions_and_fallbacks(self):
        scenario = next(
            scenario
            for scenario in load_scenarios()
            if scenario["category"] == "severe_or_no_travel"
        )

        def generate(plan):
            briefing, response = _mock_briefing_and_response(plan, "faulty_number")
            return (
                briefing,
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
        self.assertIn("Mode: report", report)
        self.assertIn("Model: rule-based", report)
        self.assertIn(
            "Raw-check basis: model narrative composed with plan-derived route facts.",
            report,
        )
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
                    compose_briefing(
                        scenario["plan"],
                        BriefingNarrative.model_validate_json(
                            MockProvider("normal")
                            .generate("", json.dumps(scenario["plan"]))
                            .text
                        ),
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

    def test_runner_records_timeout_and_continues_to_next_scenario(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import time

        scenarios = load_scenarios()[:2]

        def generate(plan):
            if plan is scenarios[0]["plan"]:
                time.sleep(0.05)
            briefing, response = _mock_briefing_and_response(plan, "normal")
            return briefing, BriefingMetadata(
                provider="fake",
                model="slow-test",
                prompt_version="v2",
                input_tokens=1,
                output_tokens=1,
                latency_ms=1.0,
                retry_count=0,
                raw_output=response.text,
            )

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "timeouts.jsonl"
            _, results = run_evaluations(
                scenarios,
                generate=generate,
                run_id="timeout-test",
                raw_output_path=path,
                timeout_seconds=0.01,
                provider_name="fake",
                model_name="slow-test",
                prompt_version="v2",
            )
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(results), 2)
        self.assertIn("timed out", results[0]["error"])
        self.assertIsNone(results[0]["parsed_briefing"])
        self.assertTrue(all(not passed for passed in results[0]["raw_checks"].values()))
        self.assertIsNone(records[0]["parsed_briefing"])
        self.assertIn("timed out", records[0]["error"])
        self.assertIsNone(records[1]["error"])
        self.assertEqual(records[1]["scenario_id"], scenarios[1]["id"])

    def test_raw_jsonl_records_failed_check_tokens_and_generation_metadata(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        scenario = next(
            item
            for item in load_scenarios()
            if item["category"] == "severe_or_no_travel"
        )

        def generate(plan):
            briefing, response = _mock_briefing_and_response(plan, "faulty_number")
            return (
                briefing,
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

    def test_merged_report_lists_run_ids_and_reports_timeouts(self):
        checks = {name: True for name in CHECK_NAMES}
        records = [
            {
                "run_id": "run-one",
                "repetition": 1,
                "scenario_id": "scenario-1",
                "category": "normal_trip",
                "provider": "groq",
                "model": "test-model",
                "prompt_version": "v2",
                "raw_checks": checks,
                "latency_ms": 120,
                "wait_ms": 5000,
                "input_tokens": 10,
                "output_tokens": 5,
                "retry_count": 0,
                "fallback_used": False,
            },
            {
                "run_id": "run-two",
                "repetition": 1,
                "scenario_id": "scenario-2",
                "category": "normal_trip",
                "provider": "groq",
                "model": "test-model",
                "prompt_version": "v2",
                "raw_checks": dict(checks, no_false_safe=False),
                "latency_ms": 0,
                "wait_ms": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "retry_count": 0,
                "fallback_used": False,
                "error": "Briefing generation timed out.",
            },
        ]

        report = render_merged_report(records, ["one.jsonl", "two.jsonl"])

        self.assertIn("- Run IDs: run-one, run-two", report)
        self.assertIn("Timeout/error records: 1", report)
        self.assertIn("Wait time total: 5000.0 ms", report)
        self.assertIn("| no_false_safe | 1/2 (50.0%) |", report)
        self.assertIn("Briefing generation timed out.", report)

    def test_report_lists_interventions_only_as_rule_counts(self):
        scenario = next(iter(load_scenarios()))

        def generate(plan):
            briefing, response = _mock_briefing_and_response(plan, "faulty_number")
            return (
                briefing,
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
            briefing, response = _mock_briefing_and_response(plan, "faulty_number")
            return (
                briefing,
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
            "data_gaps_match_plan": True,
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
        self.assertIn("- Mode: prompt comparison", report)
        self.assertIn("- Provider: mock", report)
        self.assertIn(
            "- Raw-check basis: model narrative composed with plan-derived route facts.",
            report,
        )
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

    def test_final_thresholds_are_all_checks_at_100_percent(self):
        thresholds = load_thresholds()
        self.assertEqual(set(thresholds), set(CHECK_NAMES))
        self.assertTrue(all(value == 1.0 for value in thresholds.values()))

    def test_raw_model_thresholds_include_minimum_rates_and_fallback_cap(self):
        thresholds = load_thresholds(section="raw_model")
        self.assertEqual(
            set(thresholds["minimum_pass_rates"]),
            {
                "no_false_safe",
                "numbers_grounded",
                "route_ids_grounded",
                "place_names_grounded",
            },
        )
        self.assertEqual(thresholds["minimum_pass_rates"]["numbers_grounded"], 0.91)
        self.assertEqual(thresholds["maximum_fallback_rate"], 0.2)

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

    def test_raw_model_gate_checks_narrative_quality_and_fallback_rate(self):
        checks = {name: True for name in CHECK_NAMES}
        passed = {
            "raw_checks": checks,
            "fallback_used": False,
        }
        failed_narrative = {
            "raw_checks": dict(checks, no_false_safe=False),
            "fallback_used": True,
        }
        thresholds = {
            "minimum_pass_rates": {
                "no_false_safe": 1.0,
                "numbers_grounded": 0.9,
            },
            "maximum_fallback_rate": 0.5,
        }
        failures = raw_model_gate_failures([passed, failed_narrative], thresholds)
        self.assertEqual(
            failures,
            [
                "no_false_safe: raw pass rate 50.0% is below required 100.0%",
                "fallback rate 50.0% must be below maximum 50.0%",
            ],
        )
        report = render_raw_model_gate([passed, failed_narrative], thresholds)
        self.assertIn("| no_false_safe | 50.0% (1/2) | 100.0% | FAIL |", report)
        self.assertIn("| fallback_rate | 50.0% (1/2) | < 50.0% | FAIL |", report)

    def test_report_header_identifies_mode_and_provider(self):
        result = {
            "id": "test-scenario",
            "provider": "mock",
            "model": "rule-based",
            "prompt_version": "v2",
            "raw_checks": {name: True for name in CHECK_NAMES},
            "final_checks": {name: True for name in CHECK_NAMES},
            "retry_count": 0,
            "latency_ms": 1,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "interventions": [],
            "fallback_used": False,
            "category": "severe_or_no_travel",
        }
        report = render_report([result], {}, 0, "test-run", mode="final-output gate")
        self.assertIn("- Mode: final-output gate", report)
        self.assertIn("- Provider: mock", report)

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

    def test_management_command_rejects_mock_provider_for_raw_gate(self):
        with patch(
            "briefing.management.commands.run_evals.get_provider",
            return_value=MockProvider(),
        ), patch(
            "briefing.management.commands.run_evals.run_evaluations"
        ) as run_evaluations:
            with self.assertRaisesRegex(CommandError, "requires a hosted model provider"):
                call_command("run_evals", "--gate-raw", "--limit", "1")
        run_evaluations.assert_not_called()

    def test_management_command_runs_raw_gate_with_hosted_provider(self):
        results = [
            {
                "provider": "groq",
                "model": "gpt-oss-20b",
                "prompt_version": "v2",
                "raw_checks": {name: True for name in CHECK_NAMES},
                "final_checks": {name: True for name in CHECK_NAMES},
                "retry_count": 0,
                "latency_ms": 1,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "interventions": [],
                "fallback_used": False,
                "category": "severe_or_no_travel",
            }
        ]
        with patch(
            "briefing.management.commands.run_evals.get_provider",
            return_value=object(),
        ), patch(
            "briefing.management.commands.run_evals.run_evaluations",
            return_value=("# report", results),
        ), patch(
            "briefing.management.commands.run_evals.render_report",
            return_value="# report\n",
        ) as render_report, patch(
            "briefing.management.commands.run_evals.write_report"
        ):
            call_command("run_evals", "--gate-raw", "--limit", "1", stdout=StringIO())
        self.assertEqual(render_report.call_args.kwargs["mode"], "raw-model gate")

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

    def test_management_command_resumes_missing_scenarios_per_repetition(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        scenarios = load_scenarios()[:2]
        existing = {
            "run_id": "resume-run",
            "repetition": 1,
            "scenario_id": scenarios[0]["id"],
            "provider": "mock",
            "model": "rule-based",
            "prompt_version": "v2",
            "category": scenarios[0]["category"],
            "raw_checks": {name: True for name in CHECK_NAMES},
            "final_checks": {name: True for name in CHECK_NAMES},
            "fallback_used": False,
            "retry_count": 0,
            "latency_ms": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "failed_checks": [],
        }
        with TemporaryDirectory() as temp_dir:
            reports = Path(temp_dir) / "reports"
            raw_dir = reports / "raw"
            raw_dir.mkdir(parents=True)
            (raw_dir / "resume-run.jsonl").write_text(
                json.dumps(existing) + "\n", encoding="utf-8"
            )
            with patch(
                "briefing.management.commands.run_evals.load_scenarios",
                return_value=scenarios,
            ), patch(
                "briefing.management.commands.run_evals.get_provider",
                return_value=MockProvider(),
            ), patch(
                "briefing.management.commands.run_evals.RAW_REPORT_DIR",
                raw_dir,
            ), patch(
                "briefing.management.commands.run_evals.REPORT_PATH",
                reports / "latest.md",
            ), patch(
                "briefing.management.commands.run_evals.run_evaluations",
                return_value=("", []),
            ) as run_evaluations, patch(
                "briefing.management.commands.run_evals.render_report",
                return_value="# report\n",
            ), patch(
                "briefing.management.commands.run_evals.quality_gate_failures",
                return_value=[],
            ), patch(
                "briefing.management.commands.run_evals.render_quality_gate",
                return_value="\n",
            ), patch("briefing.management.commands.run_evals.write_report"):
                call_command(
                    "run_evals",
                    "--resume",
                    "resume-run",
                    "--reps",
                    "2",
                    stdout=StringIO(),
                )

        self.assertEqual(run_evaluations.call_count, 2)
        self.assertEqual(
            run_evaluations.call_args_list[0].kwargs["completed_scenarios"],
            {scenarios[0]["id"]},
        )
        self.assertEqual(
            run_evaluations.call_args_list[1].kwargs["completed_scenarios"],
            set(),
        )

    def test_management_command_merges_raw_jsonl_files(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        record = {
            "run_id": "merge-run",
            "repetition": 1,
            "scenario_id": "scenario-1",
            "category": "normal_trip",
            "provider": "groq",
            "model": "test-model",
            "prompt_version": "v2",
            "raw_checks": {name: True for name in CHECK_NAMES},
            "latency_ms": 10,
            "wait_ms": 500,
            "input_tokens": 2,
            "output_tokens": 3,
            "retry_count": 0,
            "fallback_used": False,
        }
        with TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw.jsonl"
            report_path = Path(temp_dir) / "merged.md"
            raw_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            call_command(
                "run_evals",
                "--merge-runs",
                str(raw_path),
                "--output",
                str(report_path),
                stdout=StringIO(),
            )

            report = report_path.read_text(encoding="utf-8")

        self.assertIn("- Run IDs: merge-run", report)
        self.assertIn("Records: 1", report)

    def test_management_command_compares_v1_and_v2_on_same_scenarios(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        scenario = load_scenarios()[0]
        checks = {
            "route_matches_engine": True,
            "worst_checkpoint_matches_engine": True,
            "risk_counts_match_plan": True,
            "risk_ranges_cover_checkpoints": True,
            "data_gaps_match_plan": True,
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
