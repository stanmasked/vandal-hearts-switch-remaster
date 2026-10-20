# MAP02 Stage302 — bounded read-only Linux task observation

**Research-only / Draft / DO NOT MERGE.** Parent: [Stage301 PR #386](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/386), new true [Stage301 paired real guests Actions #39514787380](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39514787380).

## What is known

The same ROM-free opt-in NeXium Linux ELF returned successfully from CPAL `stream.play()` in both 21ms and 22ms guests. In the actual Stage301 21ms trial it had no CPAL callback increments after guest input, no nonzero captured PCM, and did not pass eight optical guest CRC pages. At 22ms it had **2264** guest-window callback increments, **509830** nonzero samples and eight optical CRC pages passed. PulseAudio input subscriptions, including the transient connect/disconnect events, did NOT themselves prove why callbacks stopped or started.

## New bounded guest experiment

Run independent new generated NRO trials at requested 21/22ms Pulse hints, using the exact original immutable Stage298 Linux/Rustarmic NeXium ELF SHA-256 `fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a`, exact ROM-free generated NRO SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`, unchanged guest keyboard route, unchanged CPAL callbacks, original P and L time series, original virtual PCM and optical screenshot validators.

After the new GUI/NRO process is spawned, a separate **unprivileged read-only** process samples `/proc/<pid>/task/*/stat`, `comm`, and `wchan` at 250ms intervals. The observer never attaches with `ptrace`, injects a shared library, modifies NeXium memory or calls into the guest/ALSA/CPAL backend. It emits only: a **per-run anonymous task alias** (not Linux PID/TID), a weak `AUDIO_NAMED` versus `UNATTRIBUTED` label, Linux task state, cumulative user+system kernel CPU ticks, and an **allowlisted wait-channel bucket** (for example futex/poll/schedule, or OTHER/UNKNOWN). It does not emit raw thread names, OS thread IDs, host paths, process command lines or raw wait symbols.

The Stage302 auditor re-runs Stage301's exact archived guest NRO/ELF/P/L/optical/PCM/Pulse receipt validation using the **new** run identity, then independently re-parses the bounded task file and compares observation timestamps with the real guest input and final-observation markers. No output forces the existence of a recognizable CPAL thread name, a CPU tick increase, or a fixed 21/22ms contrast. Missing task reads during thread exit are expected and are not evidence of a deadlock.

## Interpretation / privacy

The Linux task `AUDIO_NAMED` classification only recognizes the presence of `audio`, `alsa`, or `cpal` in the kernel thread name. It **does not establish** that an observed thread is CPAL's true audio data callback or the underlying physical device I/O thread. `/proc/task/wchan` is a coarse scheduler waiting point, **not** a stack trace or cause diagnosis. CPU tick changes can prove only that a sampled OS task accrued CPU time between two snapshots; they do not show whether guest PCM was delivered through that thread. CPU tick stasis is not proof of permanent deadlock.

These external observations may themselves change Linux scheduling. They cannot establish a precise hardware period from a requested 21/22ms Pulse hint, nor original PS1 music playback, backend recovery/root cause, actual Switch audio or a production game fix. No original licensed game data, audio recordings, upstream NeXium edits or new production code are used. Only five research-only files: sampler, Stage301 launcher copy with observer, independent audit, falsification tests and this document plus one isolated CI workflow.
