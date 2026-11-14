# Groq timeout diagnosis

- Date: 2026-11-14
- Provider/model: Groq / `openai/gpt-oss-20b`
- Method: reran the two recurring normal-trip timeouts individually with a
  90-second Groq request timeout and a 95-second evaluation timeout.
- Dashboard: the Groq usage page required login. Exact account rate and daily
  token limits could not be verified.

## Evidence from the 30-second runs

The recurring scenarios were `normal_denver_to_salt_lake_city` and
`normal_sfo_to_lax`. Their saved timeout records contain the generic error
`Briefing generation timed out after 30.0 seconds.`, `latency_ms: 0`,
`finish_reason: null`, and no model output. In each record, `wait_ms` reports
only the evaluation pacing delay (0 or 6 seconds); provider-side waits are
not recorded when the outer evaluation timeout fires.

The Denver scenario timed out four times across the saved v1/v2 attempts; San
Francisco–Los Angeles timed out three times in v2. Other records show that
these scenarios can complete: an earlier SFO v1 response incurred three HTTP
429 retries (10, 10, and 8 seconds of backoff), plus the 6-second evaluation
delay, then finished successfully.

## Isolated 90-second reruns

Both scenarios were run sequentially, alone per evaluation call, using v2.
Character length is the returned model text before parsing; finish reason and
token counts came from the provider response.

| Scenario | Result | Provider waits | Latency | Output length | Completion tokens | Finish reason |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `normal_denver_to_salt_lake_city` | Completed | None | 3.33 s | 167 chars | 46 | `stop` |
| `normal_sfo_to_lax` | Completed after HTTP 429 retries | 10 + 10 + 5 s | 1.61 s | 291 chars | 175 | `stop` |

Raw records: [timeout_diagnosis_20261114T114540656885Z.jsonl](./raw/timeout_diagnosis_20261114T114540656885Z.jsonl).

## Assessment

- **Rate limiting is directly evidenced.** The SFO rerun received HTTP 429
  responses and waited 25 seconds across three bounded retries. This is
  consistent with request-rate pressure, but the response details do not
  establish whether the account is on the free tier or whether an RPM, TPM,
  or daily quota was reached.
- **Reasoning-heavy or capped output is not supported by these reruns.** Both
  responses were short, returned `finish_reason: stop`, and used far fewer
  completion tokens than the configured 4096-token cap. This does not explain
  every historical timeout.
- **There is also a timeout-budget mismatch in the evaluator.** Its outer
  30-second deadline wraps a provider request that can make multiple
  30-second attempts with additional rate-limit backoff. When the outer
  deadline expires, it writes a generic timeout record and loses the
  in-flight provider error and wait events. Thus the original logs cannot
  distinguish a slow request from a request delayed by rate-limit retries.

**Conclusion:** rate-limit delays are the best-supported operational cause,
with an evaluator timeout/observability bug that turns a multi-attempt request
into an opaque 30-second timeout. The available evidence does not establish
free-tier daily quota exhaustion, and it does not point to reasoning output
as the cause. Check the authenticated Groq usage dashboard to identify the
account's exact limits before attributing the 429s to a particular quota.
