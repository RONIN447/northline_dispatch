# Briefing evaluation report

- Date (UTC): 2026-11-13
- Mode: report only
- Provider: groq
- Model: openai/gpt-oss-20b
- Prompt version: v1
- Run ID: 20261113T120001816228Z
- Raw scenario data: raw/20261113T120001816228Z.jsonl
- Raw-check basis: model narrative composed with plan-derived route facts.

Scenarios: 3 | Raw briefings: 3 | Validator-corrected briefings: 3

## Run summary

Fallback rate: 1/3 (33.3%) | Retry rate: 0/3 (0.0%)
Latency p50: 937.2 ms | p95: 1983.5 ms | Average tokens: 3673.3 (input 3549.3, output 124.0)
Timeout/error records: 0 | Wait time total: 0.0 ms (separate from provider latency)

| Check | Raw pass rate | Final pass rate |
| --- | ---: | ---: |
| route_matches_engine | 3/3 (100.0%) | 3/3 (100.0%) |
| worst_checkpoint_matches_engine | 3/3 (100.0%) | 3/3 (100.0%) |
| risk_counts_match_plan | 3/3 (100.0%) | 3/3 (100.0%) |
| risk_ranges_cover_checkpoints | 3/3 (100.0%) | 3/3 (100.0%) |
| data_gaps_match_plan | 3/3 (100.0%) | 3/3 (100.0%) |
| no_false_safe | 3/3 (100.0%) | 3/3 (100.0%) |
| numbers_grounded | 2/3 (66.7%) | 3/3 (100.0%) |
| route_ids_grounded | 3/3 (100.0%) | 3/3 (100.0%) |
| place_names_grounded | 3/3 (100.0%) | 3/3 (100.0%) |

## Pass rates by scenario category

| Category | Scenarios | Check | Raw pass rate | Final pass rate |
| --- | ---: | --- | ---: | ---: |
| near-tie | 3 | route_matches_engine | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | worst_checkpoint_matches_engine | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | risk_counts_match_plan | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | risk_ranges_cover_checkpoints | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | data_gaps_match_plan | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | no_false_safe | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | numbers_grounded | 66.7% (2/3) | 100.0% (3/3) |
| near-tie | 3 | route_ids_grounded | 100.0% (3/3) | 100.0% (3/3) |
| near-tie | 3 | place_names_grounded | 100.0% (3/3) | 100.0% (3/3) |

## Validator interventions

Fallback template used: 1/3 scenarios.

No validator interventions were required.

## Scenario results

| Scenario | Provider | Raw checks passed | Final checks passed | Fallback |
| --- | --- | ---: | ---: | --- |
| near_tie_1_sfo_to_lax | groq | 9/9 | 9/9 | no |
| near_tie_2_chicago_to_detroit | groq | 8/9 | 9/9 | yes |
| near_tie_3_boston_to_new_york | groq | 9/9 | 9/9 | no |

## Final-output quality gate

| Check | Final pass rate | Required | Result |
| --- | ---: | ---: | --- |
| route_matches_engine | 100.0% | 100.0% | PASS |
| worst_checkpoint_matches_engine | 100.0% | 100.0% | PASS |
| risk_counts_match_plan | 100.0% | 100.0% | PASS |
| risk_ranges_cover_checkpoints | 100.0% | 100.0% | PASS |
| data_gaps_match_plan | 100.0% | 100.0% | PASS |
| no_false_safe | 100.0% | 100.0% | PASS |
| numbers_grounded | 100.0% | 100.0% | PASS |
| route_ids_grounded | 100.0% | 100.0% | PASS |
| place_names_grounded | 100.0% | 100.0% | PASS |
