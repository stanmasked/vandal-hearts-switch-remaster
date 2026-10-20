# Stage366 — preserve original SDL2 portlib installer failure

This stage keeps the SDL2 NRO job **failed** when the external devkitPro
package mirror returns HTTP 403. The independent native **libnx/audout**
music NRO remains a separate CI path. Stage366 changes **only CI
diagnostics**; it does not alter PCM transport, guest audio, libnx
calls, game code or playback semantics.

## Confirmed predecessor: commit 2ddc2ab0

On [GitHub Actions #39351557481](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351557481),
job **118396657619** failed during the step
`Install Nintendo Switch SDL2 development libraries`. Its original job log contains:

```text
:: Synchronizing package databases...
curl: (22) The requested URL returned error: 403
error: failed to synchronize all databases (error invoking external downloader)
```

GitHub marked the later NRO compilation, native music tests and NRO
upload steps as **skipped**. This is evidence of an external dependency
retrieval blocker, **not** evidence of a Switch C compiler error or
successfully built SDL2 binary. The existing
`classify_switch_portlib_install.py` explicitly returns non-zero.

## CI change

The `switch-audio-nro.yml` installation step now writes the raw
`dkp-pacman` log to `stage366-sdl2-install.log` in the
working directory. When installation fails, the already-existing
classifier's JSON diagnosis and GitHub error annotation are also piped
through `tee` into `stage366-sdl2-diagnostic.txt`. Bash
`set -o pipefail` keeps the classifier's non-zero exit status.

The following `actions/upload-artifact@v4` step runs with
`if: always()` and attempts to save both files in
`stage366-sdl2-portlib-install-evidence`, even if installation
fails. It intentionally does not mark compilation or SDL2 availability
as passing. `if-no-files-found: warn` handles failures before an
install log exists without hiding the original failed step.

A new synthetic regression test
`tests/test_stage366_sdl2_portlib_evidence.py` requires this
failure-preserving control flow and rejects mislabeling unrelated
compiler or package-not-found errors as HTTP 403.

## Verification boundaries

Until a new CI run completes, this change is **not** claimed to have
preserved an actual artifact. The next run must show both the original
failed install step and the upload step separately before Stage366
artifact capture is confirmed.

Stage365 remains independently successful on
[GitHub Actions #39351366143](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351366143).
The origin of the old authentic `audoutWait` `0xEA01` is still
unresolved. No acoustic verification on physical Nintendo Switch is
implied.
