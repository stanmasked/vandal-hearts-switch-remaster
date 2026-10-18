# Vandal Hearts Remake — Stage306: independent Plus/PCM capture repeatability

Stage304's first full run independently observed an EOF-censored
~5.88-second exact-zero virtual NeXium PCM run. Source-file snapshots
at actual host Plus keydown and keyup placed the zero-run onset between
those snapshots, but cannot by themselves establish a sample-accurate
guest event or audio causality.

Stage305 introduces a conservative frame-aligned onset fence and
independent 500-ms PCM source-window counts. Stage306 compares **two
different completed NeXium runtime captures**, each separately audited
with the current Stage304 and Stage305 analyzers against its own source
PCM (rather than trusting a previous summary).

## Archived original capture inputs

- NeXium workflow `39134188130`: original virtual audio capture after the
  host-control instrumentation was first introduced.
- NeXium workflow `39134382535`: independent virtual audio capture that
  originally passed the full Stage304 audit.

Both successful runs published a `nexium-runtime-evidence` artifact
containing their original virtual s16le stereo PCM, host scene markers,
real host Plus input snapshots, and source-bound Stage299–303 receipts.
No PS1 retail tracks, copyrighted game images or console keys are
added in Stage306. Historical archives are downloaded by
`actions/download-artifact@v4` using exact workflow run IDs, with
read-only `actions:read` permission.

The new workflow
`.github/workflows/stage306-independent-capture-audit.yml` independently
runs current Stage304 and Stage305 validation **again** for both
archives. It will fail closed on missing source files, changed hashes,
bad original host markers, failed stop evidence or broken frame
conservation.

## Comparison and results

`tools/compare_nexium_pcm_plus_capture_runs.py` accepts 2–8 verified
Stage305 JSON reports, with distinct workflow run IDs and distinct
original PCM SHA-256 values. Its compact comparison includes:

- The number of captures in each buffered Plus/PCM onset category.
- Whether all original zero runs start inside each recording's actual
  Plus keydown/keyup file-size bracket.
- Source PCM frame-distance minimum and maximum from the real
  buffered host Plus snapshots, by run.
- Original zero/nonzero PCM frame counts in the Stage305 source windows.
- Whether categories repeat, without forcing different real runs to
  agree or hiding variability.

Report:
`comparison-evidence/independent-plus-PCM-stage306.json`.
The comparison CI uploads only independently computed JSON receipts.

Host tests:
`python3 -m unittest discover -s tests -p 'test_compare_nexium_pcm_plus_capture_runs.py' -v`

### Scientific/technical limits

The two archives come from independent NeXium host recordings, but
the virtual audio sink, test scenario, original PCM format, and
host-buffered `stat` timing method are shared. The tool does **not**
infer independent hardware testing, faithful retail music, audible
dropouts, guest-time timestamp precision, or a causal Plus → SPU
shutdown link. Differences are reported descriptively rather than
silently averaged away. No sound engine, gameplay, audout or retail
game resources are altered.
