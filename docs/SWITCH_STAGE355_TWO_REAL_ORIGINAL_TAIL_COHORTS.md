# Stage355 — repeatability across two distinct real NeXium software sources

This workflow independently downloads and reaudits the complete original archived guest **Stage313, Stage348 and Stage351 CSV sources and receipts** from [NeXium #39308380160](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39308380160) and [NeXium #39317788067](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39317788067).

Each run already completed successfully, but Stage355 reuses the strict independent Stage352 source verifier for **both entire triples**, requiring their separate authentic SHA-256 pins and the original Stage313/314/348/351 receipts. It independently insists on real software reason **7 / return_confirmed**, with PCM software ownership **1441 / 1441 / 0** in the first run and **1411 / 1411 / 0** in the second, and rejects shared source hashes or identical run IDs.

This establishes repeatability for successful software descriptor returns despite differing amounts of software pages, not hardware audio or an infallible PCM device. Original SHA-256 evidence, original source receipts and exclusive output are retained; the artifact published by Stage355 is only one short verification JSON.

**CI status:** the new Stage355 workflow must complete successfully before the independent comparison is counted as verified. Neither the earlier **1468 / 1467 / 1** failure (with unknown reason) nor DAC/speaker output, real Switch hardware, audible continuity or actual PS1 soundtrack quality can be established from two successful source comparisons. No production audio code or original game resources were changed.
