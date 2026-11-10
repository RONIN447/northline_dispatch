# Briefing evaluation report

- Date (UTC): 2026-11-07
- Provider: groq
- Model: openai/gpt-oss-20b
- Prompt version: v1
- Run ID: 20261107T171854374356Z
- Raw scenario data: raw/20261107T171854374356Z.jsonl

Scenarios: 3 | Raw briefings: 3 | Validator-corrected briefings: 3

## Run summary

Fallback rate: 3/3 (100.0%) | Retry rate: 0/3 (0.0%)
Latency p50: 20319.4 ms | p95: 27952.4 ms | Average tokens: 4788.3 (input 4326.0, output 462.3)

| Check | Raw pass rate | Final pass rate |
| --- | ---: | ---: |
| route_matches_engine | 3/3 (100.0%) | 3/3 (100.0%) |
| severe_coverage | 3/3 (100.0%) | 3/3 (100.0%) |
| no_risk_downgrade | 3/3 (100.0%) | 3/3 (100.0%) |
| no_false_safe | 0/3 (0.0%) | 3/3 (100.0%) |
| numbers_grounded | 1/3 (33.3%) | 3/3 (100.0%) |
| route_ids_grounded | 3/3 (100.0%) | 3/3 (100.0%) |
| place_names_grounded | 2/3 (66.7%) | 3/3 (100.0%) |

## Pass rates by scenario category

| Category | Scenarios | Check | Raw pass rate | Final pass rate |
| --- | ---: | --- | ---: | ---: |
| all-risky | 3 | route_matches_engine | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | severe_coverage | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | no_risk_downgrade | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | no_false_safe | 0.0% (0/3) | 100.0% (3/3) |
| all-risky | 3 | numbers_grounded | 33.3% (1/3) | 100.0% (3/3) |
| all-risky | 3 | route_ids_grounded | 100.0% (3/3) | 100.0% (3/3) |
| all-risky | 3 | place_names_grounded | 66.7% (2/3) | 100.0% (3/3) |

## Validator interventions

Fallback template used: 3/3 scenarios.

| Rule | Count |
| --- | ---: |
| add_required_risky_checkpoint | 153 |
| fallback_template | 3 |
| restore_data_gaps | 3 |

## Scenario results

| Scenario | Provider | Raw checks passed | Final checks passed | Fallback |
| --- | --- | ---: | ---: | --- |
| all_routes_risky_1_sfo_to_lax | groq | 5/7 | 7/7 | yes |
| all_routes_risky_2_denver_to_salt_lake_city | groq | 5/7 | 7/7 | yes |
| all_routes_risky_3_boston_to_new_york | groq | 5/7 | 7/7 | yes |

## Final-output quality gate

| Check | Final pass rate | Required | Result |
| --- | ---: | ---: | --- |
| route_matches_engine | 100.0% | 100.0% | PASS |
| severe_coverage | 100.0% | 100.0% | PASS |
| no_risk_downgrade | 100.0% | 100.0% | PASS |
| no_false_safe | 100.0% | 100.0% | PASS |
| numbers_grounded | 100.0% | 100.0% | PASS |
| route_ids_grounded | 100.0% | 100.0% | PASS |
| place_names_grounded | 100.0% | 100.0% | PASS |
