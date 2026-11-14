# Briefing evaluation report

- Date (UTC): 2026-11-14
- Mode: final-output gate
- Provider: mock
- Model: rule-based
- Prompt version: v2
- Run ID: 20261114T122536818290Z
- Raw scenario data: raw/20261114T122536818290Z.jsonl
- Raw-check basis: model narrative composed with plan-derived route facts.

Scenarios: 28 | Raw briefings: 28 | Validator-corrected briefings: 28

## Run summary

Fallback rate: 0/28 (0.0%) | Retry rate: 0/28 (0.0%)
Latency p50: 0.5 ms | p95: 1.2 ms | Average tokens: 492.3 (input 476.5, output 15.9)
Timeout/error records: 0 | Wait time total: 0.0 ms (separate from provider latency)

## Facts (code-computed)

These checks validate fields assembled from the route plan; they are not model-quality metrics.

| Fact check | Raw pass rate | Final pass rate |
| --- | ---: | ---: |
| route_matches_engine | 28/28 (100.0%) | 28/28 (100.0%) |
| worst_checkpoint_matches_engine | 28/28 (100.0%) | 28/28 (100.0%) |
| risk_counts_match_plan | 28/28 (100.0%) | 28/28 (100.0%) |
| risk_ranges_cover_checkpoints | 28/28 (100.0%) | 28/28 (100.0%) |
| data_gaps_match_plan | 28/28 (100.0%) | 28/28 (100.0%) |

## Narrative (model-generated)

| Narrative check | Raw pass rate | Final pass rate |
| --- | ---: | ---: |
| narrative_consistent_with_facts | 28/28 (100.0%) | 28/28 (100.0%) |
| no_false_safe | 28/28 (100.0%) | 28/28 (100.0%) |
| numbers_grounded | 28/28 (100.0%) | 28/28 (100.0%) |
| route_ids_grounded | 28/28 (100.0%) | 28/28 (100.0%) |
| place_names_grounded | 28/28 (100.0%) | 28/28 (100.0%) |

## Pass rates by scenario category

### Facts (code-computed)

| Category | Scenarios | Fact check | Raw pass rate | Final pass rate |
| --- | ---: | --- | ---: | ---: |
| normal | 8 | route_matches_engine | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | worst_checkpoint_matches_engine | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | risk_counts_match_plan | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | risk_ranges_cover_checkpoints | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | data_gaps_match_plan | 100.0% (8/8) | 100.0% (8/8) |
| severe | 5 | route_matches_engine | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | worst_checkpoint_matches_engine | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | risk_counts_match_plan | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | risk_ranges_cover_checkpoints | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | data_gaps_match_plan | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | route_matches_engine | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | worst_checkpoint_matches_engine | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | risk_counts_match_plan | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | risk_ranges_cover_checkpoints | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | data_gaps_match_plan | 100.0% (5/5) | 100.0% (5/5) |
| threshold | 4 | route_matches_engine | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | worst_checkpoint_matches_engine | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | risk_counts_match_plan | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | risk_ranges_cover_checkpoints | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | data_gaps_match_plan | 100.0% (4/4) | 100.0% (4/4) |
| all-risky | 3 | route_matches_engine | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | worst_checkpoint_matches_engine | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | risk_counts_match_plan | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | risk_ranges_cover_checkpoints | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | data_gaps_match_plan | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | route_matches_engine | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | worst_checkpoint_matches_engine | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | risk_counts_match_plan | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | risk_ranges_cover_checkpoints | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | data_gaps_match_plan | 100.0% (3/3) | 100.0% (3/3) |

### Narrative (model-generated)

| Category | Scenarios | Narrative check | Raw pass rate | Final pass rate |
| --- | ---: | --- | ---: | ---: |
| normal | 8 | narrative_consistent_with_facts | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | no_false_safe | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | numbers_grounded | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | route_ids_grounded | 100.0% (8/8) | 100.0% (8/8) |
| normal | 8 | place_names_grounded | 100.0% (8/8) | 100.0% (8/8) |
| severe | 5 | narrative_consistent_with_facts | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | no_false_safe | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | numbers_grounded | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | route_ids_grounded | 100.0% (5/5) | 100.0% (5/5) |
| severe | 5 | place_names_grounded | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | narrative_consistent_with_facts | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | no_false_safe | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | numbers_grounded | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | route_ids_grounded | 100.0% (5/5) | 100.0% (5/5) |
| forecast gap | 5 | place_names_grounded | 100.0% (5/5) | 100.0% (5/5) |
| threshold | 4 | narrative_consistent_with_facts | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | no_false_safe | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | numbers_grounded | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | route_ids_grounded | 100.0% (4/4) | 100.0% (4/4) |
| threshold | 4 | place_names_grounded | 100.0% (4/4) | 100.0% (4/4) |
| all-risky | 3 | narrative_consistent_with_facts | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | no_false_safe | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | numbers_grounded | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | route_ids_grounded | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | place_names_grounded | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | narrative_consistent_with_facts | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | no_false_safe | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | numbers_grounded | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | route_ids_grounded | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | place_names_grounded | 100.0% (3/3) | 100.0% (3/3) |

## Validator interventions

Fallback template used: 0/28 scenarios.

No validator interventions were required.

## Scenario results

| Scenario | Provider | Code facts | Raw narrative | Final narrative | Fallback |
| --- | --- | ---: | ---: | ---: | --- |
| all_routes_risky_1_sfo_to_lax | mock | 5/5 | 5/5 | 5/5 | no |
| all_routes_risky_2_denver_to_salt_lake_city | mock | 5/5 | 5/5 | 5/5 | no |
| all_routes_risky_3_boston_to_new_york | mock | 5/5 | 5/5 | 5/5 | no |
| forecast_gap_1_sfo_to_lax | mock | 5/5 | 5/5 | 5/5 | no |
| forecast_gap_2_seattle_to_portland | mock | 5/5 | 5/5 | 5/5 | no |
| forecast_gap_3_denver_to_salt_lake_city | mock | 5/5 | 5/5 | 5/5 | no |
| forecast_gap_4_chicago_to_detroit | mock | 5/5 | 5/5 | 5/5 | no |
| forecast_gap_5_dallas_to_houston | mock | 5/5 | 5/5 | 5/5 | no |
| near_tie_1_sfo_to_lax | mock | 5/5 | 5/5 | 5/5 | no |
| near_tie_2_chicago_to_detroit | mock | 5/5 | 5/5 | 5/5 | no |
| near_tie_3_boston_to_new_york | mock | 5/5 | 5/5 | 5/5 | no |
| normal_atlanta_to_nashville | mock | 5/5 | 5/5 | 5/5 | no |
| normal_boston_to_new_york | mock | 5/5 | 5/5 | 5/5 | no |
| normal_chicago_to_detroit | mock | 5/5 | 5/5 | 5/5 | no |
| normal_dallas_to_houston | mock | 5/5 | 5/5 | 5/5 | no |
| normal_denver_to_salt_lake_city | mock | 5/5 | 5/5 | 5/5 | no |
| normal_minneapolis_to_kansas_city | mock | 5/5 | 5/5 | 5/5 | no |
| normal_seattle_to_portland | mock | 5/5 | 5/5 | 5/5 | no |
| normal_sfo_to_lax | mock | 5/5 | 5/5 | 5/5 | no |
| severe_1_sfo_to_lax | mock | 5/5 | 5/5 | 5/5 | no |
| severe_2_seattle_to_portland | mock | 5/5 | 5/5 | 5/5 | no |
| severe_3_denver_to_salt_lake_city | mock | 5/5 | 5/5 | 5/5 | no |
| severe_4_chicago_to_detroit | mock | 5/5 | 5/5 | 5/5 | no |
| severe_5_dallas_to_houston | mock | 5/5 | 5/5 | 5/5 | no |
| threshold_wind_35_0_load_40000 | mock | 5/5 | 5/5 | 5/5 | no |
| threshold_wind_44_9_load_41000 | mock | 5/5 | 5/5 | 5/5 | no |
| threshold_wind_45_0_load_30000 | mock | 5/5 | 5/5 | 5/5 | no |
| threshold_wind_45_0_load_30001 | mock | 5/5 | 5/5 | 5/5 | no |

## Final-output quality gate

| Check | Final pass rate | Required | Result |
| --- | ---: | ---: | --- |
| route_matches_engine | 100.0% | 100.0% | PASS |
| worst_checkpoint_matches_engine | 100.0% | 100.0% | PASS |
| risk_counts_match_plan | 100.0% | 100.0% | PASS |
| risk_ranges_cover_checkpoints | 100.0% | 100.0% | PASS |
| data_gaps_match_plan | 100.0% | 100.0% | PASS |
| narrative_consistent_with_facts | 100.0% | 100.0% | PASS |
| no_false_safe | 100.0% | 100.0% | PASS |
| numbers_grounded | 100.0% | 100.0% | PASS |
| route_ids_grounded | 100.0% | 100.0% | PASS |
| place_names_grounded | 100.0% | 100.0% | PASS |
