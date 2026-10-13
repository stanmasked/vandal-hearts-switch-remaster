# Working with the upstream PC port

The source audit is pinned to upstream commit `14552fffa0e0b47e02b57592e274fc6e7a649923`. To fetch that exact revision into a local cache for inspection:

```sh
bash scripts/fetch_upstream_pcport.sh
```

The script checks out the pinned commit under `.cache/upstream-pc-port/`, which is ignored by Git. It does not execute the upstream build, download game discs, or copy proprietary game data into this repository.

To choose a different local destination:

```sh
bash scripts/fetch_upstream_pcport.sh /tmp/vandal-hearts-pcport
```

The upstream source has platform-specific assumptions and mixed rights. Fetching it is not evidence of Switch compatibility; before building it, audit the selected source paths, dependencies, generated files, and rights notices. Do not commit disc images, game executables, BIOS/SDK files, extracted assets, or generated copyrighted data.

The current CI artifacts are only diagnostic homebrew programs:
- `switch-smoke-test.nro`: console output and controller input.
- `switch-graphics-smoke-test.nro`: framebuffer color bars.

Neither artifact contains Vandal Hearts engine code or game data.