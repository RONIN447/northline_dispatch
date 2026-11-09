"""Fault injection tests for the independent briefing evaluation checks."""

import json
import unittest

from briefing.providers import MockProvider
from briefing.schema import Briefing
from briefing.validator import enforce
from evals.checks import evaluate_checks, expected_data_gaps
from evals.grounding import check_grounding, find_offending_tokens
from evals.scenarios import load_scenarios


class BriefingCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scenarios = load_scenarios()
        cls.severe_scenario = next(
            scenario
            for scenario in scenarios
            if scenario["category"] == "severe_or_no_travel"
        )
        cls.gap_scenario = next(
            scenario
            for scenario in scenarios
            if scenario["category"] == "forecast_unavailable"
        )

    def test_each_check_fails_for_a_matching_faulty_mock_and_final_passes(self):
        cases = (
            ("faulty_route", self.severe_scenario, "route_matches_engine"),
            ("faulty_missing_checkpoint", self.severe_scenario, "severe_coverage"),
            ("faulty_downgrade", self.severe_scenario, "no_risk_downgrade"),
            ("faulty_no_gap", self.gap_scenario, "no_false_safe"),
            ("faulty_safe", self.severe_scenario, "no_false_safe"),
            ("faulty_number", self.severe_scenario, "numbers_grounded"),
            ("faulty_route_id", self.severe_scenario, "route_ids_grounded"),
            ("faulty_place", self.severe_scenario, "place_names_grounded"),
        )
        for mode, scenario, failed_check in cases:
            with self.subTest(mode=mode, check=failed_check):
                response = MockProvider(mode).generate("", json.dumps(scenario["plan"]))
                raw = Briefing.model_validate_json(response.text)
                raw_checks = evaluate_checks(raw, scenario["plan"])
                self.assertFalse(raw_checks[failed_check])

                final, _, _ = enforce(scenario["plan"], raw)
                final_checks = evaluate_checks(final, scenario["plan"])
                self.assertTrue(all(final_checks.values()), final_checks)

    def test_rule_based_mock_passes_all_checks_on_all_scenarios(self):
        for scenario in load_scenarios():
            with self.subTest(scenario=scenario["id"]):
                response = MockProvider("normal").generate(
                    "", json.dumps(scenario["plan"])
                )
                briefing = Briefing.model_validate_json(response.text)
                self.assertTrue(
                    all(evaluate_checks(briefing, scenario["plan"]).values())
                )

    def test_expected_data_gaps_is_empty_when_required_forecasts_exist(self):
        plan = self._plan_with_checkpoints(
            [
                {"windMph": 10, "rainInHr": 0, "snowInHr": 0, "temperatureF": None},
            ]
        )

        self.assertEqual(expected_data_gaps(plan), [])

    def test_expected_data_gaps_reports_one_missing_required_field(self):
        plan = self._plan_with_checkpoints(
            [
                {"windMph": None, "rainInHr": 0, "snowInHr": 0, "temperatureF": None},
            ]
        )

        self.assertEqual(
            expected_data_gaps(plan),
            ["route-1 checkpoint 0 is missing windMph."],
        )

    def test_expected_data_gaps_reports_all_missing_fields_in_plan_order(self):
        plan = self._plan_with_checkpoints(
            [
                {"windMph": None, "rainInHr": None, "snowInHr": None},
                {"windMph": 10, "rainInHr": None, "snowInHr": None},
            ],
            route_id="route-1",
        )
        plan["routes"].append(
            {
                "id": "route-2",
                "checkpoints": [
                    {"windMph": None, "rainInHr": 0, "snowInHr": 0},
                ],
            }
        )

        self.assertEqual(
            expected_data_gaps(plan),
            [
                "route-1 checkpoint 0 is missing windMph, rainInHr, snowInHr.",
                "route-1 checkpoint 1 is missing rainInHr, snowInHr.",
                "route-2 checkpoint 0 is missing windMph.",
            ],
        )

    @staticmethod
    def _plan_with_checkpoints(checkpoints, route_id="route-1"):
        return {
            "routes": [{"id": route_id, "checkpoints": checkpoints}],
        }


class BriefingGroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scenarios = {item["id"]: item for item in load_scenarios()}
        cls.sfo_scenario = scenarios["all_routes_risky_1_sfo_to_lax"]
        cls.denver_scenario = scenarios["all_routes_risky_2_denver_to_salt_lake_city"]
        cls.boston_scenario = scenarios["all_routes_risky_3_boston_to_new_york"]
        cls.mutation_scenarios = (
            cls.sfo_scenario,
            cls.denver_scenario,
            cls.boston_scenario,
        )

    def test_exact_groq_rounded_distances_and_places_are_grounded(self):
        cases = (
            (
                self.sfo_scenario,
                "381 miles \u00b7 7.1 hr \u00b7 San Francisco, California, United States "
                "to Los Angeles, California, United States",
            ),
            (
                self.denver_scenario,
                "520 miles \u00b7 9.0 hr \u00b7 Denver, Colorado, United States "
                "to Salt Lake City, Utah, United States",
            ),
            (
                self.boston_scenario,
                "214 miles \u00b7 4.7 hr \u00b7 Boston, Massachusetts, United States "
                "to New York, New York, United States",
            ),
        )
        for scenario, summary in cases:
            with self.subTest(scenario=scenario["id"]):
                briefing = self._briefing(scenario, summary)
                self.assertEqual(check_grounding(briefing, scenario["plan"]), [])
                self.assertEqual(
                    find_offending_tokens(briefing, scenario["plan"]),
                    {"numbers": [], "route_ids": [], "place_names": []},
                )

    def test_exact_groq_ordinary_sentence_words_are_not_place_names(self):
        summary = (
            "All checkpoints on the recommended route have a High risk rating; "
            "no Severe or No Travel risks are present. The route is 520.4 miles "
            "and takes 9 hours."
        )
        briefing = self._briefing(self.denver_scenario, summary)

        self.assertNotIn(
            "unsupported_place_name",
            check_grounding(briefing, self.denver_scenario["plan"]),
        )
        self.assertNotIn(
            "All",
            find_offending_tokens(briefing, self.denver_scenario["plan"])["place_names"],
        )

    def test_formatted_route_id_variants_normalize_to_plan_route(self):
        plan = self.sfo_scenario["plan"]
        for route_text in ("ROUTE_1_ROUTABILITY", "Route 1", "route-1-routability"):
            with self.subTest(route_text=route_text):
                briefing = self._briefing(
                    self.sfo_scenario,
                    "Recommended route: {}.".format(route_text),
                )
                self.assertNotIn(
                    "unsupported_route_id", check_grounding(briefing, plan)
                )
                self.assertEqual(
                    find_offending_tokens(briefing, plan)["route_ids"], []
                )

    def test_checkpoint_counts_indices_eta_and_summed_miles_are_grounded(self):
        plan = self.sfo_scenario["plan"]
        summary = (
            "The routes total 1,190.1 miles across 52 checkpoints. "
            "Checkpoint 16 is at mile 400; ETA 2026-10-21T18:00."
        )
        briefing = self._briefing(self.sfo_scenario, summary)

        self.assertNotIn("unsupported_number", check_grounding(briefing, plan))
        self.assertEqual(
            find_offending_tokens(briefing, plan)["numbers"],
            [],
        )

    def test_invented_number_route_id_and_place_name_still_fail(self):
        scenario = self.sfo_scenario
        briefing = self._briefing(
            scenario,
            "Route route-999 is 999 hours from Phoenix.",
        )

        self.assertEqual(
            check_grounding(briefing, scenario["plan"]),
            [
                "unsupported_route_id",
                "unsupported_number",
                "unsupported_place_name",
            ],
        )
        self.assertEqual(
            find_offending_tokens(briefing, scenario["plan"]),
            {
                "numbers": ["999"],
                "route_ids": ["route-999"],
                "place_names": ["Phoenix"],
            },
        )

    def test_grounding_mutations_are_rejected_for_multiple_saved_plans(self):
        for scenario in self.mutation_scenarios:
            plan = scenario["plan"]
            valid = self._valid_briefing(scenario)
            route_distance = plan["routes"][0]["distanceMiles"]
            off_by_one = "{:g}".format(route_distance + 1)
            mutations = (
                ("numbers_grounded", "The wind speed is 99 mph.", "99"),
                ("numbers_grounded", "The invented distance is 9876 miles.", "9876"),
                (
                    "numbers_grounded",
                    "The distance is {} miles.".format(off_by_one),
                    off_by_one,
                ),
                (
                    "route_ids_grounded",
                    "Use route-999-not-in-plan.",
                    "route-999-not-in-plan",
                ),
                (
                    "place_names_grounded",
                    "The route passes through Quetzaltenango.",
                    "Quetzaltenango",
                ),
            )
            for check_name, text, offending_token in mutations:
                with self.subTest(scenario=scenario["id"], mutation=text):
                    mutated = valid.model_copy(
                        update={"summary": "{} {}".format(valid.summary, text)}
                    )
                    checks = evaluate_checks(mutated, plan)

                    self.assertFalse(checks[check_name])
                    self.assertEqual(
                        checks["numbers_grounded"],
                        check_name != "numbers_grounded",
                    )
                    self.assertEqual(
                        checks["route_ids_grounded"],
                        check_name != "route_ids_grounded",
                    )
                    self.assertEqual(
                        checks["place_names_grounded"],
                        check_name != "place_names_grounded",
                    )
                    tokens = find_offending_tokens(mutated, plan)
                    token_group = {
                        "numbers_grounded": "numbers",
                        "route_ids_grounded": "route_ids",
                        "place_names_grounded": "place_names",
                    }[check_name]
                    self.assertIn(offending_token, tokens[token_group])

    @staticmethod
    def _briefing(scenario, summary):
        response = MockProvider("normal").generate(
            "", json.dumps(scenario["plan"])
        )
        briefing = Briefing.model_validate_json(response.text)
        briefing.summary = summary
        briefing.dispatcher_actions = []
        return briefing

    @staticmethod
    def _valid_briefing(scenario):
        response = MockProvider("normal").generate(
            "", json.dumps(scenario["plan"])
        )
        briefing = Briefing.model_validate_json(response.text)
        if not all(evaluate_checks(briefing, scenario["plan"]).values()):
            raise AssertionError("The mutation baseline briefing must pass all checks.")
        return briefing
