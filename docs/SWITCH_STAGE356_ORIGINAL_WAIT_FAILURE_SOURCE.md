# Stage356 — independent re-audit of authentic NeXium failed exit-tail wait

[Real completed NRO + NeXium #39320606595](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39320606595) passed Stage313, Stage314, Stage348 and Stage351. The original guest software sources, before any Stage356 change, yielded:

- **Stage351 code 4: `wait_failed`** (the existing single bounded `audoutWaitPlayFinish` call returned a failing service result)
- **Stage348 1379 acquired / 1378 returned / 1 abandoned** descriptor lease
- **Stage313 bounded tail attempted and not return-confirmed**
- Original Stage313 guest tail CSV SHA-256 `f0e57a34db96becbddbb7fadd34772598e9f453f7dd3fed9b2bd5e0041468296`
- Original Stage348 guest lease CSV SHA-256 `8314bc1619890356572aa16238ac4da6f87c790aee353a463be273f4991d39da`
- Original Stage351 guest reason CSV SHA-256 `70e757639b6f26a7c18c7def2d46c564ec1543ebad5e7dcddcf323c58bfb1b61`

The Stage356 CI workflow downloads the original completed run's evidence archive (not synthetic counters), **reexecutes the Stage352 byte-pinned original-source verifier** on all three original CSVs and Stage313/314/348/351 receipts, and asserts the exact failure outcome above. Its artifact contains only a short software report. Until this new independent workflow completes successfully, Stage356 is a requested follow-up verification, not a completed claim.

The failing `audoutWaitPlayFinish` result **does not reveal its underlying libnx/Horizon numeric `Result`**. The existing 12-ms maximum wait is unchanged, and the returned error could be a timeout or another service rejection; we do not attribute the older separate unclassified failures or any audible glitch to this result. PCM remains leased until the entire prior audio service session is closed, preventing an unsafe overwrite.

No physical Nintendo Switch output, DAC queue drain, speaker playback or original PlayStation music fidelity has been measured. No game assets, samples or music banks were uploaded.
