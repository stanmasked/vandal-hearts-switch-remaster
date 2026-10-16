# MAP02 independent DDA interval audit

The pure offline function `tools.map02_dda_coverage.classify` is a
**synthetic arithmetic validator**, not a producer of GPU evidence.

It uses the DDA half-open X span `[x_start, x_bound)`, an inclusive
drawing-area clip, and an explicit selected pixel. It distinguishes
unclipped X coverage, clipped coverage and vertical row rejection.

**Critical precondition:** Caller must separately establish that the X
endpoints were actually observed from the same original DDA primitive,
at this row and frame. The existing PR #52 reason codes 4–7 do not
supply such endpoints. Therefore no reason 4–7 event is automatically
upgraded to confirmed triangle coverage, no source data is modified,
and there are no new event reason codes.

Run: `python3 -m unittest discover -s tests -p test_map02_dda_coverage.py -v`.

No original MAP02 capture, physical PS1 GPU mask/STP/ABR parity, or
Nintendo Switch gameplay is verified by these arithmetic tests.
HD replacement remains disabled pending separately validated evidence.

## Strict synthetic row/event join

`tools.map02_dda_span_join.reconcile` joins an independently supplied
row span to each reason 4–7 event via exact `(frame, primitive_ordinal, y)`.
It rejects duplicate spans, duplicate rejection events, mismatched Y
clip-direction predicates, noncontiguous steps, wrong-frame joins,
invalid types and the full 64-event (possibly truncated) cap.
It does **not** claim genuine DDA span provenance: an independent
executed-`dda_part` span recorder remains to be developed and validated.

Run: `python3 -m unittest discover -s tests -p 'test_map02_dda_span_join.py' -v`.
The 11 new regression tests use fabricated data; no retail or Switch
playback has been established.
