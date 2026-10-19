# Stage354 — deterministic long-run PCM lease stress

This host-only test exercises the unchanged exact-token VhAudioBufferLease and the same Stage353 result decision helpers used by the production exit-tail path. It runs three 2048-page synthetic PCM sequences with seven rotating service return patterns.

For each page it hashes the synthesized 256 signed 16-bit samples, acquires the descriptor lease, injects exactly one of: append failure, wait failure, empty returned list, foreign descriptor, NULL descriptor, matching descriptor, or matching descriptor with a count of two. It then verifies that failure cannot return PCM ownership until the whole service session is closed; successful exact returns release exactly one descriptor.

After **every page**, the test checks leased = released + abandoned; accepted <= released; the PCM hash is unchanged while the lease is active; the Stage351 original post-join eight-row CSV writer accepts the resulting canonical status and the reason code equals the injected branch. Each result category must occur in every permutation.

The dedicated Stage354 workflow builds this same source under GCC and Clang, optimized and UBSan. No music banks, SPU, real Switch services, NeXium capture, DAC data, guest PCM or physical audio are involved. This cannot identify the reason for the older guest-tail failure that was captured before Stage351 classification. Production PCM processing and existing CSV schemas are unchanged.
