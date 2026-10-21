# Stage303: real Linux selected syscalls under NeXium at 21/22ms

**Research only; Draft; DO NOT MERGE.** Stacked child of [Stage302 PR #388](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/388). Original [Stage302 Actions #39517964679](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39517964679) passed both guests and captured 17/18 distinct Linux task aliases with sampled CPU tick growth at 21/22ms. Linux process task labels and wait states did not identify CPAL's underlying audio callback or its ALSA mechanism.

## What we changed for this experiment

We **do not** rebuild or modify NeXium, CPAL, ALSA, original guest game code, licensed PS1 game assets or audio. We launch the previously SHA-pinned Stage298 genuine Linux/Rustarmic NeXium ELF SHA-256 `fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a` with the exact same generated-only ROM-free research NRO SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`. Two independent GUI jobs request Pulse latency hints 21 and 22ms, then invoke the same original guest key route and 48k virtual PCM/optical checks.

The copied research-only Stage301 harness runs NeXium as a child of `strace -f`, restricting traced syscalls to `ioctl,poll,ppoll,epoll_wait,epoll_pwait,sendmsg,recvmsg`. It records `strace -ttt` realtime timestamps and two bracketing paired samples of `time.time_ns()` and `time.monotonic_ns()` before/after the guest. The auditor validates immutable ELF/NRO identities, **independently reruns the prior Stage301 guest/P/L/Pulse/PNG/PCM proof**, and privately reads the raw trace to tally selected syscalls, known `SNDRV_PCM_IOCTL_*` kernel request names and selected errno labels, plus conservatively bracket events relative to guest input/observation if the clock bridge is stable.

### Privacy and strict validation

The raw `strace` text may contain PIDs, syscall arguments, addresses, memory details and host paths. It is kept **only in `RUNNER_TEMP` and NEVER uploaded**. Uploads contain bounded counters and SHA/byte lengths of the private raw file, sanitized errno labels and coarse timing classes only. All optional `strace` PID prefixes and any raw data are stripped by the auditor. Fail closed if clock bridges are inconsistent, input assets not source-pinned, the raw trace is missing, or guest/P/L/optical/PCM evidence does not match exactly.

Do **not** equate missing `SNDRV_PCM_IOCTL_*` kernel requests with no ALSA library activity. The ALSA Pulse plugin and CPAL may be doing user-space work via IPC with no direct PCM ioctl from NeXium. Even an observed kernel `EIO` in a traced syscall is not necessarily the same error or failure site as a CPAL/ALSA callback error reported by the GUI FileLogger. `-ttt` is CLOCK_REALTIME / wall time, whereas P/L guest events are monotonic; our paired offset is an **approximate host-clock alignment only**, never proof of exact callback/event timestamp.

**Important experimental caveat:** `strace -f` uses `ptrace` for all followed guest threads and significantly perturbs execution/scheduling. A changed 21/22ms outcome is not proof of a fix or a stable causal latency boundary. These CI experiments do not verify physical Nintendo Switch audio, a permanent deadlock, original PS1 soundtrack playback, or a production solution.

Six isolated research files: analyzer, two clock samplers/harness files, generated-only negative tests, workflow and this document. No merges or game source changes.
