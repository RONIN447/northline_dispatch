# Forecast-gap failure diagnosis

Reviewed the saved real-Groq JSONL records for `forecast_gap_1`, `forecast_gap_3`,
and `forecast_gap_4` from both prompt versions and repetitions. The source rows
are linked in the [partial repeated-evaluation report](./tier1_repeated_partial_2026-11-11.md).

## `forecast_gap_1_sfo_to_lax`

The plan's required data gap is
`route-3-routability checkpoint 2 is missing windMph.` The plan/engine's worst
checkpoints are:

| Route | Plan/engine worst checkpoint |
|---|---|
| `route-1-routability` | index 15, No Travel |
| `route-2-routability` | index 15, No Travel |
| `route-3-routability` | index 2, Severe |

| Prompt / repetition | Model `data_gaps` | Model worst-checkpoint fields | Assessment |
|---|---|---|---|
| v1 / rep 1 | Correct: `route-3-routability checkpoint 2 is missing windMph.` | route 1: index 15, No Travel; route 2: index 14, No Travel; route 3: index 2, Severe | The plan is right; route 2's index is wrong. |
| v1 / rep 2 | Correct: `route-3-routability checkpoint 2 is missing windMph.` | route 1: index 15, No Travel; route 2: index 14, No Travel; route 3: index 2, Severe | The plan is right; route 2's index is wrong. |
| v2 / rep 1 | Empty list; omits the plan's wind gap. | route 1: index 14, No Travel; route 2: index 14, No Travel; route 3: index 14, High | The plan is right; all three model indices/levels are wrong, and the gap was omitted. |
| v2 / rep 2 | Correct: `route-3-routability checkpoint 2 is missing windMph.` | route 1: index 14, No Travel; route 2: index 13, No Travel; route 3: index 2, Severe | The plan is right; route 1 and route 2 indices are wrong. |

This is a real model error, not a detector issue. In particular, the model
repeatedly reports a nearby checkpoint instead of the sole No Travel checkpoint
at index 15 on routes 1 and 2.

## `forecast_gap_3_denver_to_salt_lake_city`

The plan requires
`route-1-routability checkpoint 2 is missing windMph.` Its worst checkpoints
are route 3 index 0 Low, route 2 index 0 Low, and route 1 index 2 Severe.
Route 1 also requires a Severe range from mile 50 to mile 50.

The failing v1 / rep 2 output returned an empty `data_gaps` list. Its worst
checkpoint fields matched the plan on all three routes. It returned
`risk_ranges: null` for all three routes, omitting route 1's required Severe
range. The plan is right: the output omitted a known data gap and a required
risk range. These are real model errors.

## `forecast_gap_4_chicago_to_detroit`

The plan requires
`route-1-routability checkpoint 2 is missing windMph.` Its worst checkpoints
are route 2 index 0 Low, route 3 index 0 Low, and route 1 index 2 Severe.

The failing v2 / rep 2 output returned
`route-1 checkpoint 2 is missing windMph.` The route ID is abbreviated, so the
gap string does not match the plan's exact route ID. The model's worst
checkpoint fields matched the plan on all three routes. The plan is right about
the gap wording and the model is right about the worst checkpoints; the gap
wording remains a model error because the route ID is not exact.

## Check-rule correction

`evaluate_checks` previously folded exact forecast-gap matching into
`no_false_safe`. That made the forecast-gap omissions in `forecast_gap_3` and
the abbreviated gap in `forecast_gap_4` appear to be unsafe reassurance even
though the text did not make a false-safe claim. Split this into
`data_gaps_match_plan` and made `no_false_safe` report only the unsafe-claim
check. The plan validator already checked forecast gaps independently.

The new check is required at 100% in the final gate and has a 91% minimum in
the raw-model gate, preserving the previous raw threshold. A regression test
confirms that omitting a gap fails `data_gaps_match_plan` without failing
`no_false_safe`; the existing unsafe-claim mutation still tests
`no_false_safe`.
