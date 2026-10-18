# Weight and cutoff evidence

`analyze_shot` exposes `weight_observation` and `termination` at **all** detail
levels. They use the full-resolution log, not the five averaged curve samples.
Existing summary, diagnostics and `final_weight_g` semantics are unchanged.

## Weight

- `final_weight_g`: firmware header only; zero header remains `null` here.
- `weight_observation.header_final_weight_g`: preserves a raw zero as `0.0`.
- `last_positive_scale_sample`: last finite positive `v` whose own sample has
  `bluetooth_scale_connected=true`. Includes exact logged time, sample index,
  extended-recording flag, source and a quality disclaimer. It is **not** a
  verified settled yield or a maximum-weight fallback. Single spikes or stale
  BLE values are not automatically validated by a connection flag.
- `last_active_positive_scale_sample`: same selection, requiring an explicit
  `extended_recording=false`; useful when post-stop observations exist.
- No confirmed BLE flag means `v` is not promoted to grams. In particular,
  volumetric flow-model readings, `ev`, integrated flow and pumped `wp` are not
  substitutes for scale yield.
- `zero_after_stop_observed`: a confirmed BLE zero occurs after an earlier positive
  scale sample and is explicitly flagged as extended recording. A later positive
  tail-drip rebound does not erase this event. `first_post_stop_zero_time_s` and
  `last_positive_scale_sample_before_post_stop_zero` retain its time and preceding
  weight; a rebound's value may represent only tail drips, not the whole cup.
  This reports a pattern; it does **not** identify whether a tare, cup removal,
  driver or firmware reset caused it.
- `settled_final_weight_verified` is false: this interface does not independently
  verify settled cup weight, even when a firmware header is populated.
- Missing header, non-BLE positive `v`, incomplete log and post-stop zero patterns
  have explicit warning codes. No inferred ratio should be calculated from the
  last positive observation as if it were verified final yield.

## Termination

V5+ 512-byte headers store `finalExitReason` at byte 459 and the little-endian
`brewDelayMs` at bytes 460–461. Every 29-byte phase transition stores a reason
at byte +3. Code 0 means unknown/legacy; unknown future codes retain their
numeric value and are labelled `UNKNOWN`, never guessed as successful cutoff.
A zero delay byte pair is reported as unknown (`null`): old files used these
bytes as padding, so a genuinely configured zero is indistinguishable there.
V4 has no such metadata and returns null codes/delay.

Codes: 1 `TARGET_VOLUMETRIC`, 2 `TARGET_PRESSURE`, 3 `TARGET_FLOW`,
4 `TARGET_PUMPED`, 5 `DURATION`, 6 `SAFETY`, 7 `ABORTED`.

Each phase's `transition_reason` explains why the **previous** phase ended
when the named phase was entered. It is not the named phase's own exit reason.
The final phase exit is in `termination.final_exit_reason`.

`last_active_sample_time_s` and `first_extended_recording_sample_time_s` bracket
the transition to post-stop recording, when both explicit flags exist. Neither
is an exact pump-off timestamp. `recording_duration_s` (and the unchanged
`duration_seconds`) include extended recording. No missing flag is treated as
proof of active brewing; pressure/flow thresholds do not invent a stop time.
Existing extraction summaries retain their original log-based timing semantics.

## Regression fixture

`tests/fixtures/000058.slog` is the saved genuine v7 regression log, not generated
telemetry. It has a zero final-weight header, a last positive BLE observation of
23.6g at 43.199s, the preceding active observation 23.3g at 42.949s, post-stop
zeros, a duration exit, a recorded 500ms delay and total log duration 44.699s.
All three detail levels must preserve these facts. Synthetic cases in
`test_shot_observations.py` are explicitly labelled and test edge conditions.

This MCP-only change does not change machine profiles, safeguards, scale
configuration or firmware. Restart/reload the serving MCP instance before
claiming a live tool is fixed; a successful offline replay is not deployment.
