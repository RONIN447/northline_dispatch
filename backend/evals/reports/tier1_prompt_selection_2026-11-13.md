# Tier 1 prompt selection: v1 vs v2

- Date (UTC): 2026-11-13
- Mode: repeated raw-model evaluation and offline replay of saved responses
- Provider / model: Groq / `openai/gpt-oss-20b`
- Scenario set: 28 scenarios in six categories
- Requested schedule: v1 once, v2 twice; all-risky and forecast-gap categories have two repetitions for each prompt.
- Pacing: 6-second evaluation delay between calls. Provider/evaluation waits are logged separately from latency.

## Decision

**Select v1 as the current shipping prompt; do not treat this as Tier 1 release
sign-off.** In the first-repetition comparison, v1 returned usable responses
for 20/28 scenarios and v2 for 19/28. Among completed responses, both prompts
passed the narrative grounding and `no_false_safe` checks after replay with the
current detector. V2 did not demonstrate a broad enough quality improvement to
offset its weaker response coverage and higher token use in the earlier
three-scenario comparison.

This selection is provisional: neither prompt met the 100% `no_risk_downgrade`
target in the forecast-gap category, and severe/threshold calls timed out
heavily. Do not mark the real-model Tier 1 gate complete based on these runs.
The deployment decision should remain gated until those missing outputs are
re-run and the forecast-gap failures are resolved.

## Coverage and run metrics

Timeouts are shown as errors, not fallbacks, and are excluded from response
quality denominators and latency percentiles. `Fallback (logged -> replay)`
shows the original run's fallback flag and the result of replaying its saved
parsed briefing through the current validator. The replay is offline; it is
not a new model call. Retries were zero for all completed records.

| Category | Prompt / repetition | Responses / attempts | Timeouts | Fallback (logged -> replay) | Retry rate | p50 latency | p95 latency | Avg tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| All risky (3) | v1 rep 1 | 3/3 | 0 | 0/3 -> 0/3 | 0% | 19.7 s | 20.7 s | 4,953 |
| All risky (3) | v1 rep 2 | 3/3 | 0 | 0/3 -> 0/3 | 0% | 38.7 s | 40.1 s | 4,953 |
| All risky (3) | v2 rep 1 | 3/3 | 0 | 0/3 -> 0/3 | 0% | 42.1 s | 45.2 s | 5,536 |
| All risky (3) | v2 rep 2 | 3/3 | 0 | 0/3 -> 0/3 | 0% | 42.9 s | 44.7 s | 5,538 |
| Forecast gap (5) | v1 rep 1 | 5/5 | 0 | 0/5 -> 0/5 | 0% | 25.1 s | 41.4 s | 4,916 |
| Forecast gap (5) | v1 rep 2 | 5/5 | 0 | 0/5 -> 0/5 | 0% | 25.9 s | 46.1 s | 4,951 |
| Forecast gap (5) | v2 rep 1 | 5/5 | 0 | 0/5 -> 0/5 | 0% | 36.3 s | 48.9 s | 5,674 |
| Forecast gap (5) | v2 rep 2 | 5/5 | 0 | 0/5 -> 0/5 | 0% | 28.7 s | 48.2 s | 5,422 |
| Threshold (4) | v1 rep 1 | 0/4 | 4 | n/a | n/a | n/a | n/a | n/a |
| Threshold (4) | v2 rep 1 | 2/4 | 2 | 0/2 -> 0/2 | 0% | 1.8 s | 2.7 s | 4,766 |
| Threshold (4) | v2 rep 2 | 0/4 | 4 | n/a | n/a | n/a | n/a | n/a |
| Severe (5) | v1 rep 1 | 2/5 | 3 | 2/2 -> 0/2 | 0% | 1.7 s | 2.5 s | 3,874 |
| Severe (5) | v2 rep 1 | 0/5 | 5 | n/a | n/a | n/a | n/a | n/a |
| Severe (5) | v2 rep 2 | 1/5 | 4 | 0/1 -> 0/1 | 0% | 0.9 s | 0.9 s | 3,322 |
| Near tie (3) | v1 rep 1 | 3/3 | 0 | 1/3 -> 0/3 | 0% | 0.9 s | 2.0 s | 3,673 |
| Near tie (3) | v2 rep 1 | 3/3 | 0 | 0/3 -> 0/3 | 0% | 1.1 s | 2.2 s | 3,998 |
| Near tie (3) | v2 rep 2 | 2/3 | 1 | 0/2 -> 0/2 | 0% | 0.9 s | 0.9 s | 3,584 |
| Normal (8) | v1 rep 1 | 7/8 | 1 | 2/7 -> 0/7 | 0% | 1.0 s | 1.9 s | 3,867 |
| Normal (8) | v2 rep 1 | 6/8 | 2 | 0/6 -> 0/6 | 0% | 0.9 s | 1.8 s | 4,008 |
| Normal (8) | v2 rep 2 | 6/8 | 2 | 0/6 -> 0/6 | 0% | 0.9 s | 1.0 s | 4,013 |

Across the requested repetitions, v1 had 28 successful responses and 8
timeouts in 36 attempts; v2 had 36 successful responses and 20 timeouts in 56
attempts. V1 had at least one successful response for 20/28 distinct scenarios;
v2 had at least one for 22/28 after two repetitions. The extra v2 repetition
means those distinct-coverage totals are not a one-to-one prompt comparison.

An additional v2 normal run (6/8 responses, 2 timeouts) and an earlier
interrupted v2 near-tie run (0/3 responses) are retained as supplemental
records, but excluded from the scheduled-repetition table. The user-requested
v2 repetitions are the two listed above.

## Raw checks, replayed with current checks

Each cell gives the range across repetitions, with the successful-response
denominators retained. Timeouts are not counted as failed model claims.
`No-risk` is the derived `no_risk_downgrade` check; grounding columns cover
numbers, route IDs, and place names respectively.

| Category | Prompt | Route | Worst checkpoint | Risk counts | Risk ranges | Data gaps | No false safe | Numbers | Route IDs | Places | No-risk |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| All risky | v1 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| All risky | v2 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Forecast gap | v1 | 100% | 80% | 100% | 80-100% | 80-100% | 100% | 100% | 100% | 100% | 60-80% |
| Forecast gap | v2 | 100% | 80% | 80-100% | 80-100% | 80% | 100% | 100% | 100% | 100% | 80% |
| Threshold | v1 | n/a (0 responses) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| Threshold | v2 | 100% (2 responses) | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Severe | v1 | 100% (2 responses) | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Severe | v2 | 100% (1 response) | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Near tie | v1 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Near tie | v2 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Normal | v1 | 100% (7 responses) | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| Normal | v2 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

Forecast gaps remain the functional weakness: neither prompt reached 100% on
worst-checkpoint matching or derived `no_risk_downgrade`. V1's no-risk range
was 60-80% across repetitions; v2 was 80% in both. The other completed
responses passed `route_matches_engine`, `no_false_safe`, and the three
grounding checks after replay.

## Fallback diagnosis and detector changes

Five v1 responses were originally marked as fallbacks by the then-current
grounding detector:

- Two severe and two normal responses used ordinary dispatcher verbs such as
  `Notify`, `Provide`, `Confirm`, `Ensure`, and `Maintain`; these were
  misclassified as unsupported place names.
- One near-tie response stated the supplied 48-hour forecast horizon; the
  detector did not include the plan-level `forecastHours` value.
- A normal response used `Oct` from a supplied ETA.

The detector now treats those verbs and ETA month names as ordinary prose and
grounds numeric plan-level values. Regression tests confirm unknown place names
remain rejected and `49` is still rejected when the plan supplies a 48-hour
horizon. Replaying all five saved fallback narratives with the fixed validator
produced 0/5 fallbacks. This is a rule correction, not a relaxation of the
grounding target; the original fallback flags remain in the raw JSONL.

## Raw JSONL sources

The 28-scenario mock snapshot `raw/20261111T055726688839Z.jsonl` is excluded
from all real-model metrics.

- All risky: [v1 rep 1](./raw/tier1_all_routes_risky_v1_rep1_20261111T045933Z.jsonl), [v1 rep 2](./raw/tier1_all_routes_risky_v1_rep2_20261111T045933Z.jsonl), [v2 rep 1](./raw/tier1_all_routes_risky_v2_rep1_20261111T045933Z.jsonl), [v2 rep 2](./raw/tier1_all_routes_risky_v2_rep2_20261111T045933Z.jsonl).
- Forecast gap: [v1 rep 1](./raw/tier1_forecast_unavailable_v1_rep1_20261111T050631Z.jsonl), [v1 rep 2](./raw/tier1_forecast_unavailable_v1_rep2_20261111T050631Z.jsonl), [v2 rep 1](./raw/tier1_forecast_unavailable_v2_rep1_20261111T050631Z.jsonl), [v2 rep 2 (completed by resume)](./raw/tier1_forecast_unavailable_v2_rep2_20261111T050631Z.jsonl).
- Threshold: [v1](./raw/20261111T063529461980Z.jsonl), [v2 reps 1-2](./raw/20261111T063127829138Z.jsonl).
- Severe: [v1](./raw/20261111T082553297229Z.jsonl), [v2 reps 1-2](./raw/20261111T063823291240Z.jsonl).
- Near tie: [v1](./raw/20261113T120001816228Z.jsonl), [v2 reps 1-2](./raw/20261113T115809648818Z.jsonl), [interrupted supplemental v2 attempt](./raw/20261111T082806508916Z.jsonl).
- Normal: [v1](./raw/20261113T115328583776Z.jsonl), [v2 reps 1-2](./raw/20261113T114433598858Z.jsonl), [supplemental v2 attempt](./raw/20261113T113838442933Z.jsonl).

## Validation

The evaluator grounding and runner suites pass: 41 tests. They include
regressions for dispatcher verbs, ETA months, forecast-horizon grounding,
unsupported place names, and legacy JSONL report rendering.
