# MAP02 Stage304 — userspace ALSA symbol visibility preflight

Research-only stacked on [Stage303 Draft PR #391](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/391). **Draft / DO NOT MERGE.**

Stage303 actual [Actions #39519732823](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39519732823) authenticated 21/22ms ROM-free generated guest testing, saw 0 versus 1682 post-input CPAL callbacks and many kernel poll/recvmsg calls but **zero identifiable kernel SNDRV_PCM_IOCTL requests**. This does not show whether userspace ALSA library entrypoints were active.

Stage304 is a **capability preflight** before choosing an intrusive trace mechanism. It queries the actual Ubuntu 24.04 GitHub Actions Linux runner's installed `libasound.so.2` and its exported `snd_pcm_avail_delay`, `snd_pcm_prepare`, `snd_pcm_recover`, `snd_pcm_writei`, `snd_pcm_readi`, `snd_pcm_start`, `snd_pcm_drop`, `snd_pcm_pause`, `snd_pcm_status` using `nm -D`. It also reads `kernel.perf_event_paranoid` and whether the current unprivileged runner can write `/sys/kernel/tracing/uprobe_events`. Reports a library ELF SHA-256, exported-symbol booleans and permission availability only; no raw addresses or host/private paths are exported.

**It does not attach to NeXium, run the guest or capture a single actual ALSA function invocation.** A present exported symbol is *not* evidence the process called that function; a missing uprobe permission is *not* evidence ALSA cannot run. Do not claim a validated ALSA error mechanism or repaired guest audio. The next truly causal experiment requires a permitted tracing backend, explicit thread attribution and opt-in real guest evidence, with tracing perturbation documented.

Four isolated research-only files, no main/game/source changes, no proprietary PS1 ROM or music, no emulator ELF/NRO modification.
