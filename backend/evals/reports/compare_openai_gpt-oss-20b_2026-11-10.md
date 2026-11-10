# Prompt comparison evaluation

- Date (UTC): 2026-11-10
- Mode: prompt comparison
- Provider: groq
- Model: openai/gpt-oss-20b
- Scenarios per version: 3
- Scenario set: identical across v1 and v2
- v1 raw scenario data: raw/compare_v1_20261110T123115313485Z.jsonl
- v2 raw scenario data: raw/compare_v2_20261110T123211841786Z.jsonl

## Side-by-side results

| Metric | v1 | v2 |
| --- | ---: | ---: |
| Fallback rate | 0/3 (0.0%) | 0/3 (0.0%) |
| Retry rate | 0/3 (0.0%) | 0/3 (0.0%) |
| Latency p50 | 24130.3 ms | 41839.3 ms |
| Latency p95 | 29171.6 ms | 50558.9 ms |
| Average tokens | 4991.3 (input 4716.0, output 275.3) | 5544.7 (input 5263.0, output 281.7) |
| Raw: route_matches_engine | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: worst_checkpoint_matches_engine | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: risk_counts_match_plan | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: risk_ranges_cover_checkpoints | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: no_false_safe | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: numbers_grounded | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: route_ids_grounded | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: place_names_grounded | 3/3 (100.0%) | 3/3 (100.0%) |
| Raw: no_risk_downgrade (derived) | 3/3 (100.0%) | 3/3 (100.0%) |

## Functional targets

Targets: fallback rate under 20%; raw route_matches_engine and derived no_risk_downgrade at 100%; each raw grounding check above 90%.

| Target | v1 | v2 |
| --- | --- | --- |
| fallback under 20% | PASS | PASS |
| route_matches_engine at 100% | PASS | PASS |
| no_risk_downgrade at 100% | PASS | PASS |
| numbers_grounded above 90% | PASS | PASS |
| route_ids_grounded above 90% | PASS | PASS |
| place_names_grounded above 90% | PASS | PASS |

The derived no_risk_downgrade rate requires all raw worst-checkpoint, risk-count, and risk-range checks to pass for a scenario.
