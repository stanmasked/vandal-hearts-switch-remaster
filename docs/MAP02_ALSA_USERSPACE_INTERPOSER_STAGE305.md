# MAP02 Stage305 — real userspace ALSA interception of the unchanged NeXium ELF

**Research-only, Draft, DO NOT MERGE.** Parent: [Stage304 PR #395](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/395), whose real Ubuntu 24.04 runner [Actions #39557329550](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39557329550) confirmed all nine selected `snd_pcm_*` exports but tracefs `uprobe_events` denied and `perf_event_paranoid=4`. That prior capability probe did **not** observe any actual ALSA call.

## Experiments and source pins

Stage305 adds a separate **experimental C `LD_PRELOAD` ALSA userspace interposer** around the following exported APIs:
`snd_pcm_avail_delay`, `snd_pcm_prepare`, `snd_pcm_recover`,
`snd_pcm_status`, `snd_pcm_start`, `snd_pcm_drop`, `snd_pcm_pause`,
`snd_pcm_writei`, `snd_pcm_readi`.

Each wrapper forwards to the real function via `dlsym(RTLD_NEXT)`, returns **the exact same return value**, and increments only two atomic counters: total call count, and one return category (**nonnegative/success**, negative `EIO`, `EPIPE`, `EAGAIN` or other negative). Anonymous per-execution-thread TLS slots (up to 64) live in a private 65536-byte mmap file. A separate Python process takes timestamped read-only snapshots every 200ms into a sanitized CSV, with no logging or disk I/O inside the ALSA wrappers. It writes **no raw PCM samples, ALSA pointer, call arguments, PID, TID, process name, hostname or native thread name** to the evidence stream. TLS slot IDs cannot establish the CPAL source thread or identify its Linux TID. When no exposed symbol is called, a zero count is a genuine zero **for those interposed functions only**, not evidence the whole ALSA library is inactive; private library-internal or `dlsym(handle,...)` references could bypass it.

Every GitHub job compiles the same standalone opt-in interposer, and **first tests it against the unlicensed ALSA `null` device**, verifying (a) exact printed source-return-code parity **with and without** the shim, and (b) actual nonzero target symbol counters in the synthetic process. Both synthetic runs use no original game content, original PS1 audio or ROM. A separate source-pinned manifest captures the C shim's newly built ELF SHA-256 and preflight assertions.

Only after that proof, two independent `ubuntu-24.04` CI jobs at requested Pulse latency hints **21ms and 22ms** boot precisely the **existing compiled Stage298 Linux/Rustarmic NeXium ELF** SHA-256 `fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a` and precisely the **unchanged original generated ROM-free Stage294/Stage299 research NRO** SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`. There are **no game, ROM, NeXium upstream, CPAL, compiled guest or production branch edits**. The regular synthetic guest keyboard path, 48k PCM virtual monitor, optical guest CRC, independent CPAL P/L monotonic sampling and Pulse sink input observer are preserved from the prior run.

The opt-in research launcher gives `LD_PRELOAD` **only to NeXium**, not the separate PulseAudio daemon, native virtual audio recorder or Python observers. The raw 64KB interposer mmap named `alsa-userspace-counter-PRIVATE.bin` is for the runner only and MUST NOT be uploaded. The workflow uploads only the sanitized ALSA CSV + source-based receipt and preexisting source-pinned NeXium/guest/P-L/Pulse optical evidence. CI fails closed if the original ELF/NRO/guest truth cannot be independently re-parsed, if monotonic ALSA sampling does not bound actual guest input, if the generated interface is not source-proven on ALSA `null`, or if the branch changes files outside the eight research-only additions.

## Scope and limitations

This is **actual observation of the exported ALSA function wrappers in a preloaded guest process**, not source-level identification of CPAL's actual data callback. `LD_PRELOAD` itself may perturb scheduling, change symbol resolution, and alter exactly the timing boundary under study, so **21ms vs 22ms observations here cannot be used as an uninstrumented reliability measurement**. Atomic totals from two reads do not reveal an exact per-function call timestamp or whether the call came from one particular NeXium subsystem. Capturing any negative result class such as `EIO` does not by itself prove which layer caused it, and `EAGAIN` can be normal nonblocking behavior.

No original Vandal Hearts music, physical Nintendo Switch audio DAC/speaker, permanent AudioOut deadlock, ALSA root cause or production audio fix is proven solely by this experiment. Research-only Draft; preserve the main branch.
