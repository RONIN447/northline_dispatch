# Tier 1 repeated real-model evaluation (partial)

> **Superseded:** This partial snapshot predates the completed comparison in
> [tier1_prompt_selection_2026-11-13.md](./tier1_prompt_selection_2026-11-13.md).
> Use that report for the current prompt-selection decision and consolidated
> results.

- Generated (UTC): 2026-11-11 05:44
- Provider: groq
- Model: openai/gpt-oss-20b
- Prompt versions: v1 and v2
- Scenario pacing: 6-second inter-call delay in addition to the provider minimum interval.
- Status: **INCOMPLETE**. Only 2 of 6 categories were started; one v2 forecast-gap repetition has 4/5 records.
- Coverage: 31/112 expected records (8/28 distinct scenarios observed). Four category slices (near_tie_routes, normal_trip, severe_or_no_travel, threshold_boundary) were not run.
- A provider request stalled during v2 `forecast_unavailable` rep 2 and did not produce a raw result row. The reason is not established by the saved data; the run was stopped to avoid unbounded waiting.
- Metrics below are ranges across repetitions, not pooled rates or best-run results. Incomplete rep 2 values are explicitly labeled by their denominator.

## Repeated-run summary

| Category | Prompt | Repetition coverage | Fallback rate range | Retry rate range | p50 latency range | p95 latency range | Avg total tokens range |
|---|---|---:|---:|---:|---:|---:|---:|
| `all_routes_risky` | v1 | rep1: 3/3; rep2: 3/3 | 0.0-0.0% | 0.0-0.0% | 19727-38731 ms | 20651-40101 ms | 4953-4953 |
| `all_routes_risky` | v2 | rep1: 3/3; rep2: 3/3 | 0.0-0.0% | 0.0-0.0% | 42063-42891 ms | 44686-45156 ms | 5536-5538 |
| `forecast_unavailable` | v1 | rep1: 5/5; rep2: 5/5 | 0.0-0.0% | 0.0-0.0% | 25121-25866 ms | 41352-46122 ms | 4916-4951 |
| `forecast_unavailable` | v2 | rep1: 5/5; rep2: 4/5 (partial) | 0.0-0.0% | 0.0-0.0% | 36347-36709 ms | 48384-48936 ms | 5674-5828 |

## Raw pass-rate ranges by check

| Category | Prompt | Check | Range across repetitions |
|---|---|---|---:|
| `all_routes_risky` | v1 | `route_matches_engine` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v1 | `worst_checkpoint_matches_engine` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v1 | `risk_counts_match_plan` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v1 | `risk_ranges_cover_checkpoints` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v1 | `no_false_safe` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v1 | `numbers_grounded` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v1 | `route_ids_grounded` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v1 | `place_names_grounded` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `route_matches_engine` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `worst_checkpoint_matches_engine` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `risk_counts_match_plan` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `risk_ranges_cover_checkpoints` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `no_false_safe` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `numbers_grounded` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `route_ids_grounded` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `all_routes_risky` | v2 | `place_names_grounded` | 100.0-100.0% (rep1: 100.0% (3/3), rep2: 100.0% (3/3)) |
| `forecast_unavailable` | v1 | `route_matches_engine` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (5/5)) |
| `forecast_unavailable` | v1 | `worst_checkpoint_matches_engine` | 80.0-80.0% (rep1: 80.0% (4/5), rep2: 80.0% (4/5)) |
| `forecast_unavailable` | v1 | `risk_counts_match_plan` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (5/5)) |
| `forecast_unavailable` | v1 | `risk_ranges_cover_checkpoints` | 80.0-100.0% (rep1: 100.0% (5/5), rep2: 80.0% (4/5)) |
| `forecast_unavailable` | v1 | `no_false_safe` | 80.0-100.0% (rep1: 100.0% (5/5), rep2: 80.0% (4/5)) |
| `forecast_unavailable` | v1 | `numbers_grounded` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (5/5)) |
| `forecast_unavailable` | v1 | `route_ids_grounded` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (5/5)) |
| `forecast_unavailable` | v1 | `place_names_grounded` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (5/5)) |
| `forecast_unavailable` | v2 | `route_matches_engine` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (4/4)) |
| `forecast_unavailable` | v2 | `worst_checkpoint_matches_engine` | 75.0-80.0% (rep1: 80.0% (4/5), rep2: 75.0% (3/4)) |
| `forecast_unavailable` | v2 | `risk_counts_match_plan` | 80.0-100.0% (rep1: 80.0% (4/5), rep2: 100.0% (4/4)) |
| `forecast_unavailable` | v2 | `risk_ranges_cover_checkpoints` | 80.0-100.0% (rep1: 80.0% (4/5), rep2: 100.0% (4/4)) |
| `forecast_unavailable` | v2 | `no_false_safe` | 75.0-80.0% (rep1: 80.0% (4/5), rep2: 75.0% (3/4)) |
| `forecast_unavailable` | v2 | `numbers_grounded` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (4/4)) |
| `forecast_unavailable` | v2 | `route_ids_grounded` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (4/4)) |
| `forecast_unavailable` | v2 | `place_names_grounded` | 100.0-100.0% (rep1: 100.0% (5/5), rep2: 100.0% (4/4)) |

## Raw-output diagnosis

No fallback was observed in any completed record (0/31). Raw check failures were found in the saved JSONL and are listed here; these are not validator fallbacks.

| Category | Prompt | Rep | Scenario | Failed raw checks |
|---|---|---:|---|---|
| `forecast_unavailable` | v1 | 1 | `forecast_gap_1_sfo_to_lax` | `worst_checkpoint_matches_engine` |
| `forecast_unavailable` | v1 | 2 | `forecast_gap_1_sfo_to_lax` | `worst_checkpoint_matches_engine` |
| `forecast_unavailable` | v1 | 2 | `forecast_gap_3_denver_to_salt_lake_city` | `risk_ranges_cover_checkpoints`, `no_false_safe` |
| `forecast_unavailable` | v2 | 1 | `forecast_gap_1_sfo_to_lax` | `worst_checkpoint_matches_engine`, `risk_counts_match_plan`, `risk_ranges_cover_checkpoints`, `no_false_safe` |
| `forecast_unavailable` | v2 | 2 | `forecast_gap_1_sfo_to_lax` | `worst_checkpoint_matches_engine` |
| `forecast_unavailable` | v2 | 2 | `forecast_gap_4_chicago_to_detroit` | `no_false_safe` |

## Raw JSONL files

- [`tier1_all_routes_risky_v1_rep1_20261111T045933Z.jsonl`](./raw/tier1_all_routes_risky_v1_rep1_20261111T045933Z.jsonl)
- [`tier1_all_routes_risky_v1_rep2_20261111T045933Z.jsonl`](./raw/tier1_all_routes_risky_v1_rep2_20261111T045933Z.jsonl)
- [`tier1_all_routes_risky_v2_rep1_20261111T045933Z.jsonl`](./raw/tier1_all_routes_risky_v2_rep1_20261111T045933Z.jsonl)
- [`tier1_all_routes_risky_v2_rep2_20261111T045933Z.jsonl`](./raw/tier1_all_routes_risky_v2_rep2_20261111T045933Z.jsonl)
- [`tier1_forecast_unavailable_v1_rep1_20261111T050631Z.jsonl`](./raw/tier1_forecast_unavailable_v1_rep1_20261111T050631Z.jsonl)
- [`tier1_forecast_unavailable_v1_rep2_20261111T050631Z.jsonl`](./raw/tier1_forecast_unavailable_v1_rep2_20261111T050631Z.jsonl)
- [`tier1_forecast_unavailable_v2_rep1_20261111T050631Z.jsonl`](./raw/tier1_forecast_unavailable_v2_rep1_20261111T050631Z.jsonl)
- [`tier1_forecast_unavailable_v2_rep2_20261111T050631Z.jsonl`](./raw/tier1_forecast_unavailable_v2_rep2_20261111T050631Z.jsonl)

## Interpretation

- Fallback target (<20%) is met for the records actually observed, but this is not evidence for the unrun categories.
- In `forecast_unavailable`, `no_false_safe` passed 4/5 for v1 rep 2, 4/5 for v2 rep 1, and 3/4 for the partial v2 rep 2; v1 rep 1 passed 5/5. This is variable and below the desired 100% in multiple runs.
- The raw JSONL shows recurring `worst_checkpoint_matches_engine` failures for `forecast_gap_1_sfo_to_lax`; v2 rep 1 additionally failed risk counts and risk-range coverage. Other failures include `risk_ranges_cover_checkpoints` and `no_false_safe` in `forecast_gap_3_denver_to_salt_lake_city`, and `no_false_safe` in `forecast_gap_4_chicago_to_detroit`.
- Stop/diagnosis condition: no category exceeded the fallback threshold in completed records. The forecast-gap check failures have nevertheless been examined from the raw JSONL before any category transition. Evaluation did not move on to the remaining categories.
- This partial report must not be used as the final v1/v2 evaluation or as evidence that Tier 1 is complete.
