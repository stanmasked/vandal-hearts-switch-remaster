# Vandal Hearts Remake — Stage348 original guest PCM lease source audit

Stage347 writes a new guest software-only `audio-lease-reconciliation-000.csv` after the game audio worker joins. The original NeXium input mirror is reached through `guest-sd-root.txt`, with the guest source under `sdmc/switch/vandal-hearts-remake/`. No raw audio or absolute host/guest timestamps are included.

Stage348's strict auditor reads **the original saved guest CSV bytes**, requires the canonical schema and eight ordered numeric rows, rejects duplicate or symbolic-link sources, leading-zero or overflowing numbers, and verifies `acquired = released + abandoned_sessions` and `accepted_pages_submitted <= released`. It rejects saturated counters and false claims of a successful hardware capture. An exact SHA-256 of the original source bytes is preserved with a separate audit receipt; the original CSV is not invented or altered.

Sixteen negative/positive tests validate the parser, guest SD locator, byte-for-byte preserved source, double-use rejection and deliberately forged software counters. The dedicated Stage348 CI checks that **the auditor correctly accepts/rejects synthetic files**, but it is deliberately not a claim that a new actual NeXium run has produced a guest source.

Future guest verification is permitted only after the original NRO runs to completion, creates exactly one authentic guest CSV and its source paths are observed by NeXium. A green synthetic audit or complete software ownership lifecycle cannot prove physical Switch speaker playback, DAC buffering, absence of audible drops, or fidelity to original PS1 music.
