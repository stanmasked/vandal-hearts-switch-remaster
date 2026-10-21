# MAP02 PC-port preflight: boot ID vs. retail executable identity

The read-only preflight is run locally with the user's own original data:

```sh
python3 -m tools.preflight_map02_pcport /path/to/VandalHearts-PcPort \
  --disc-image /private/path/to/game.bin \
  --game-exe /private/path/to/SLUS_004.47 \
  --krom-source /private/path/to/KROMDAT.BIN \
  --no-webp --no-hdvideo
```

Use absolute local paths. The report contains local paths and cryptographic hashes; keep the full JSON private and do not upload it to a public issue or workflow artifact.

## Interpret the disc fields correctly

- `disc_boot_id_family` is a runtime family inferred from the embedded PS-X EXE boot/card ID, using the same ID probes as the pinned PC port.
- `disc_boot_id_accepted_by_us_runtime` says only that the identifier belongs to the USA/Asia family accepted by the pinned US runtime.
- `disc_exact_retail_release_verified` is deliberately always `false`: the boot/card ID is not an exact retail or localization fingerprint. A translated or patched disc can preserve an original card ID.
- `retail_executable_md5_matches` is a separate build-time gate. The pinned US data generator requires the exact US `SLUS_004.47` MD5 `596bb082a2de5f1fe977dd3d7e160b03`. A USA-family boot ID does not bypass this gate.

Therefore, if a Russian/localized BIN reports `disc_boot_id_family: USA` but `retail_executable_md5_matches: false`, the report is not contradictory. It means the image carries a US-family boot/card ID, while the supplied executable is not byte-identical to the US retail executable expected by the data generator.

Do not rename a localized executable to `SLUS_004.47`, disable the MD5 guard, or mark the preflight ready by overriding checks. Use a legitimately obtained exact executable for the pinned build, or keep the PS1/BizHawk capture path separate from the PC-port data-generation path.

## Scope

The preflight is read-only. It does not extract game data, build the PC port, run the game, prove ownership, identify a particular localization, or confirm visible MAP02 pixels. A successful preflight only means that the selected prerequisites are present and satisfy the checks it performs. Real rendering still requires an actual local run and source-bound frame evidence.
