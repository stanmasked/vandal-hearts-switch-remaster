# Stage343 — source-verified identical-NRO audio software observations

The fourth complete original [NeXium #39182548276](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39182548276) and [independent source replay Stage342 #39183433971](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39183433971) **both passed** strict original Stage303–305, Stage334, corrected Stage336 and the four-run Stage337 audit.

## Same binary, different original software timing

Original **third** NeXium #39175592570 and **fourth** #39182548276 were separately executed game audio captures, with distinct original guest/host CSV SHA-256 values but the *same NRO executable* SHA-256:

1ddd4eb8ca74ec1234973cfdfa5c46b4e8af0fea770962151b317b333a1b766c

| Source-authenticated metric | Third | Fourth | Fourth minus third |
| --- | ---: | ---: | ---: |
| Final normal PlayBuffer guest software service-call duration (ns) | 18,486,979 | 25,438,021 | **+6,951,042** |
| Previous fifteen normal guest software calls: lower median (ns) | 32,374,948 | 26,170,625 | **−6,204,323** |
| Previous median minus final software call (ns) | +13,887,969 | +732,604 | **−13,155,365** |
| First host control monotonic interval (ns) | 324,470,642 | 350,024,814 | **+25,554,172** |
| Second host control monotonic interval (ns) | 4,220,779,386 | 4,269,756,021 | **+48,976,635** |

These values demonstrate **non-identical observed guest software service-call timings for the same executable** across two real *virtual guest* runs, even though the last call remains shorter than its preceding-call median in both captures. This is a bounded comparison, not a diagnosed audible dropout, hardware scheduling cause, host-to-guest clock mapping, or original PS1 music fidelity claim.

Stage343 adds a source-derived guard that consumes **only the passed source-authentic Stage342 report**, verifies the original source-attestation flags and all four different CSV digest types per capture, validates guest software medians and historical own-clock differences, and checks the third/fourth NRO SHA-256 is bit-identical. It publishes a new compact receipt without absolute host or guest epochs or PCM. Twelve synthetic negative/positive tests reject source reuse, altered observations, mismatched NRO hashes, historical rejected-run substitution, and false hardware-sound claims.

The independent Stage343 CI must pass before its new compact report is considered verified; successful Stage342 remains the independent evidence for the original four captures. Four selected NeXium sessions are not a population confidence interval, physical Nintendo Switch speaker measurement or proof of causal software jitter.
