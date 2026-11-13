# Briefing evaluation report

- Date (UTC): 2026-11-11
- Mode: report only
- Provider: groq
- Model: openai/gpt-oss-20b
- Prompt version: v1
- Run ID: 20261111T082553297229Z
- Raw scenario data: raw/20261111T082553297229Z.jsonl
- Raw-check basis: model narrative composed with plan-derived route facts.

Scenarios: 5 | Raw briefings: 5 | Validator-corrected briefings: 5

## Run summary

Fallback rate: 2/5 (40.0%) | Retry rate: 0/5 (0.0%)
Latency p50: 0.0 ms | p95: 2231.0 ms | Average tokens: 1549.6 (input 1476.6, output 73.0)
Timeout/error records: 3 | Wait time total: 24000.0 ms (separate from provider latency)

| Check | Raw pass rate | Final pass rate |
| --- | ---: | ---: |
| route_matches_engine | 2/5 (40.0%) | 2/5 (40.0%) |
| worst_checkpoint_matches_engine | 2/5 (40.0%) | 2/5 (40.0%) |
| risk_counts_match_plan | 2/5 (40.0%) | 2/5 (40.0%) |
| risk_ranges_cover_checkpoints | 2/5 (40.0%) | 2/5 (40.0%) |
| data_gaps_match_plan | 2/5 (40.0%) | 2/5 (40.0%) |
| no_false_safe | 2/5 (40.0%) | 2/5 (40.0%) |
| numbers_grounded | 2/5 (40.0%) | 2/5 (40.0%) |
| route_ids_grounded | 2/5 (40.0%) | 2/5 (40.0%) |
| place_names_grounded | 0/5 (0.0%) | 2/5 (40.0%) |

## Pass rates by scenario category

| Category | Scenarios | Check | Raw pass rate | Final pass rate |
| --- | ---: | --- | ---: | ---: |
| severe | 5 | route_matches_engine | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | worst_checkpoint_matches_engine | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | risk_counts_match_plan | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | risk_ranges_cover_checkpoints | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | data_gaps_match_plan | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | no_false_safe | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | numbers_grounded | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | route_ids_grounded | 40.0% (2/5) | 40.0% (2/5) |
| severe | 5 | place_names_grounded | 0.0% (0/5) | 40.0% (2/5) |

## Validator interventions

Fallback template used: 2/5 scenarios.

| Rule | Count |
| --- | ---: |
| fallback_template | 2 |

## Scenario results

| Scenario | Provider | Raw checks passed | Final checks passed | Fallback |
| --- | --- | ---: | ---: | --- |
| severe_1_sfo_to_lax | groq | 8/9 | 9/9 | yes |
| severe_2_seattle_to_portland | groq | 8/9 | 9/9 | yes |
| severe_3_denver_to_salt_lake_city | groq | 0/9 | 0/9 | no |
| severe_4_chicago_to_detroit | groq | 0/9 | 0/9 | no |
| severe_5_dallas_to_houston | groq | 0/9 | 0/9 | no |

## Final-output quality gate

| Check | Final pass rate | Required | Result |
| --- | ---: | ---: | --- |
| route_matches_engine | 40.0% | 100.0% | FAIL |
| worst_checkpoint_matches_engine | 40.0% | 100.0% | FAIL |
| risk_counts_match_plan | 40.0% | 100.0% | FAIL |
| risk_ranges_cover_checkpoints | 40.0% | 100.0% | FAIL |
| data_gaps_match_plan | 40.0% | 100.0% | FAIL |
| no_false_safe | 40.0% | 100.0% | FAIL |
| numbers_grounded | 40.0% | 100.0% | FAIL |
| route_ids_grounded | 40.0% | 100.0% | FAIL |
| place_names_grounded | 40.0% | 100.0% | FAIL |
