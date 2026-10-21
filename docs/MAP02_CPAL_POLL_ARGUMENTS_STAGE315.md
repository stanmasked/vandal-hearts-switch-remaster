# MAP02 Stage315 — native CPAL poll() argument classes, descriptor-count cap and return reasons

**Research-only; stacked Draft / DO NOT MERGE.** Parent: [Stage314 PR #439](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/439), successfully verified with genuine source-pinned [GitHub Actions #39603862496](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39603862496). The original ROM-free NeXium host research ELF SHA-256 `e5ddfc61ac9435dc5a6e2dcd569766db0c444bbdeef8a3fa6a65c9c2e9fc6f25` and generated NRO SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b` remain unchanged. Neither the game nor upstream NeXium or main changes.

## Source-verified problem

In Stage314 the directly authenticated same-process native Linux CPAL callback thread entered exported libc `poll()` before guest input, then showed **no returns for 23.85 seconds and 0 subsequent CPAL callback entries at requested 21ms**. At 22ms the same type of authenticated CPAL thread completed **2267 `poll()` calls** and **2245 callbacks** in a similar bounded guest interval. Both naturally showed one active `poll()` at an arbitrary source snapshot. This does not prove permanent blocking, a missed wakeup, or the hardware latency boundary.

## What the separate Stage315 experiment actually records

Build a new research-only `LD_PRELOAD` wrapper based on Stage314, preserving previous 13 source-audited ALSA begin/return operations, native CPAL TLS marker, once-per-native-thread private TID bridge, exported `poll`/`ppoll`/`epoll_wait`/`epoll_pwait` entry-return counters and live anonymized `/proc` sampling.

At **private mmap offset 60928** within the original 65536-byte map, the 64 anonymous TLS aliases each have exactly nine relaxed-atomic uint64 counters/values:

- Last `poll()` timeout: signed `timeout_ms+1` encoding so 0 means `-1` (infinite), 1 means 0 (nonblocking), positive up to 2^31 represents a finite wait; U64_MAX means invalid negative value below -1.
- Last number of descriptors, capped to `0..64`, with 65 meaning more than 64. **No actual descriptor numbers, flags, event masks, socket names, pollfd pointers, or buffer contents.**
- Count of requested infinite, immediate, finite-positive and invalid-negative timeouts at `poll` entry.
- Count of `poll` return values categorized only as **ready (rc>0)**, **timeout/zero (rc=0)**, or **negative error (rc<0)**. No `errno` values or event masks captured.

Only the already-intercepted libc exported `poll()` call receives new pre/post relaxed atomic increments. This is **NOT** internal libc, `ppoll`, direct syscall, file descriptor eventfd readiness tracing, or a proof of CPAL state machine progress. Last-timeout and last-nfds values are snapshot readings and may describe an already active call; counts are cumulative, sampled separately, not atomic transactions.

## Two independent real source-pinned trials and hard evidence boundaries

Two real Ubuntu24.04 GitHub Actions jobs request PulseAudio hints 21ms and 22ms. They explicitly verify the compiled research Linux host SHA, unchanged ROM-free NRO SHA and original source manifest before starting GUI NeXium. The new sampler reads all old CPAL/ALSA/libc-wait counter streams plus the new poll-argument stream **with one shared monotonic timestamp every ~200ms**. Native TID is joined to sanitized anonymous `/proc` aliases in the same live process only, and raw TID and private shared memory never appear in published evidence.

A new independent Stage315 auditor must **first rerun Stage314 actual full-source evidence verification**: exact host/NRO provenance; genuine CPAL callback counters and true same native task identity; ALSA entry/return and user-space exported libc `poll` counters. It then parses the new nine-value poll metadata source and verifies strict schema, monotonic per-alias cumulative values, exact source sampling timestamps and guest first-input/last-observation coverage. It reports the last timeout class and capped descriptor-count argument, and per-native-CPAL-thread return classes, without guessing specific `POLLIN`/`POLLOUT` events.

A requested infinite timeout or last observed zero returns is NOT sufficient to prove a lost wakeup, causal CPAL/ALSA defect, indefinite blockage or a production fix. The extra preload work can perturb scheduling (as can the Stage313 once-per-thread TID syscall). No original PS1 ROM or soundtrack, physical Switch speaker/DAC testing, merge to main or original game implementation changes. All files are isolated in a stacked Draft PR.
