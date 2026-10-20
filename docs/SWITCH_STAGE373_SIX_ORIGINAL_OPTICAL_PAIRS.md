# Stage373 — independent optical re-audit of six archived original NeXium guest audio exits

## Motivation and source provenance

[Stage371 original run 39396243731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39396243731),
[second original run 39398650528](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39398650528), and
[current-head successful original run 39406193313](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39406193313) each produced two **distinct** original guest captures. All three are completed GitHub workflows with a same-NRO SHA-256 of
`cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b`. Each original run's guest observer already verified the respective Stage351, Stage357, and Stage368 CSV returns as `Result=0`, with **one matching released descriptor** per trial. The Stage372 independent archival audit passed for the first pair.

Stage371 intentionally only CRC-validated the PNG *file structure*; it did not decode the **guest event pixels**. Stage373's [dedicated workflow](../.github/workflows/stage373-six-original-optical-replay.yml) downloads all three **previously produced** source artifacts directly from GitHub, verifies completed successful source workflow jobs, run/attempt/head/merge-parent provenance and pinned original file digests, and then independently decodes the original framebuffer events. This is **a replay**, not six new NeXium sessions or any hardware test.

## Independent pixel decoder

`tools/audit_stage373_six_optical_originals.py` deliberately does **not** use Pillow or the previous Stage267 optical decoder. It verifies the original 1280×720 RGB PNG image chunks and CRC, independently decompresses PNG IDAT and reconstructs per-row PNG filters 0–4 within an explicit memory bound, locates and verifies the magenta border geometry and corner fiducials, then reads the actual **112×66 framebuffer bit matrix (7,392 bits)**. The decoded 924-byte packet must have exact magic `VHFBTRC1`, 23 optical events, no dropped events, canonical reserved bytes and a valid independent packet CRC32.

Each accepted original packet has four complete alternating FOCUS/FIELD/FOCUS/FIELD transitions, each consisting of chronologically ordered `INPUT`, `POST`, `ACCEPT`, `SUBMIT_CALL`, `RELEASE_RETURN` events, plus three unmatched startup events. The independent guest-clock correlation requires the last observed scene event to precede the original Stage360 exit-tail begin time. Original Stage351/357/368 CSVs are also read from each archive; their hashes are bound to the Stage371 receipt and pinned independent original reason hashes. The optional Stage360 probe/lease data are checked **as software diagnostic records**: they are not a real-time service queue measurement at shutdown.

The six original guest files remain untouched and are never pushed to the GitHub repository. Only the compact source-bound JSON verdict is uploaded by CI. The test file `tests/test_audit_stage373_six_optical_originals.py` contains **synthetic** positive and adversarial controls for image geometry, PNG CRC, framebuffer packet CRC, canonical CSV, incorrect GitHub origin and dwell-time substitution. Passing synthetic tests alone never proves an authentic run.

## Evidence limitations

- Each of six original guest software exits had a successful `audoutWaitPlayFinish` return and one matching released descriptor; both 6-second and 12-second trials were conducted three times with their own original guest receipts.
- Four complete musical scene transitions are *guest software event logs*, not music samples at the DAC or audible speaker sound. The four `RELEASE_RETURN` entries indicate buffer return, **not** speaker onset.
- The guest exit interval includes the tail append and wait, not exclusively the time inside `audoutWaitPlayFinish`.
- Two dwell durations do not form a controlled causal experiment, and old historical `0xEA01` has a timeout **classification** but no uniquely demonstrated reason why that wait expired.
- No direct exit-time audout queue depth or physical Nintendo Switch speaker output is observed. The actual Switch console remains **HARDWARE NOT TESTED**.
- Stage373 introduces **no changes** to PCM rendering, music, libnx audio service calls, buffer ownership policy or the existing 12-ms bounded tail wait.
