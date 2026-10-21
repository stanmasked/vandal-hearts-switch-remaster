# Vandal Hearts USA: private Octoshock BK2 movie-input handshake

**Stage after Draft PR #392.** This is a *read-only movie-content consistency check*.
It is not PlayStation emulation evidence, source GPU evidence, an established
BK2-to-emulator timing offset, or verified identification of MAP02.

## Private playback setup

Use a local copy of the complete source checkout and a compatible BizHawk
installation with Octoshock, matching original US PS1 disc/firmware and movie
sync. BizHawk/EmuHawk must actually replay the movie in **PLAY** mode; the
three-platform CI does not run BizHawk. Do not upload disc, BIOS, original BK2,
CSV exports or console output to GitHub.

Before playback, create an access-restricted folder and **new** report/CSV
from the owner-local movie. This frame window covers the already identified
first recorded Start press at zero-based index **1661**, with a few frames
on both sides:

```bash
umask 077
mkdir -p /private/vh-bk2-handshake
python3 -m tools.inspect_map02_private_bk2 \
  /private/vandalhearts.bk2 \
  --start-frame 1650 --window-frames 41 \
  --private-events-csv /private/vh-bk2-handshake/events.csv \
  > /private/vh-bk2-handshake/inspection.json
```

Start movie replay **before** zero-based frame 1650 (ideally from power-on).
Load `tools/map02_bizhawk_private_input_handshake.lua` in the Lua console.
It reads `movie.getinput(index, 1)` for input indices 1650 through 1690
inclusive, when mode is PLAY. It prints 41 records with a 17-button bitmask,
emulator counter and a candidate index; the data is *private* even if it
contains no screenshots. Capture the console lines into a new local text file
`/private/vh-bk2-handshake/console.txt`, then run:

```bash
python3 -m tools.verify_map02_private_bk2_input_handshake \
  /private/vh-bk2-handshake/inspection.json \
  /private/vh-bk2-handshake/events.csv \
  /private/vh-bk2-handshake/console.txt
```

Do not commit or upload any of these three files. The verifier requires
all 41 records, checks the first-frame baseline and every held/pressed/released
state exported by the BK2 inspector, matches the Lua controller mask for each
absolute index and refuses missing, duplicated, shifted, malformed or
non-PLAY records. Its JSON output keeps scene, native GPU/VRAM, original disc
authentication, and independently measured offset flags **false**.

## Limits and next evidence gate

The Lua probe accepts both unprefixed keys (`Start`) and controller-qualified keys (`P1 Start`) when BizHawk returns them, and fails closed if both disagree. The probe aborts if playback leaves `PLAY` mid-window. Its actual script logic is exercised by six synthetic Lua 5.4 mock cases on Linux CI; this executes Lua, **not** PS1 emulation. Separately, 17 Python tests check the offline verifier and malformed source baselines.

The Lua API reads *inputs stored in the currently loaded BizHawk movie*.
A byte-perfect comparison therefore establishes that the two readers agree
on the movie controller data and candidate frame indexing; it **does not**
prove that the PS1 core consumed the input at the same displayed frame.
In particular, `emu.framecount()-1` is a common BizHawk script convention,
not an independently calibrated timing offset. The Lua script does **not**
write joypad input, modify RAM, make screenshots or acquire VRAM.

Later MAP02 visual boundary work still requires real private playback,
actual original-scene capture, exact emulator counter, independently
verified input-to-frame alignment and genuine source/native GPU+VRAM
evidence. A long neutral gap or a passing synthetic CI job cannot replace
these observations.

This PR changes only observer, verifier, synthetic tests, documentation and
dedicated CI. Leave PR #392 and this follow-up as Draft; keep `main` unchanged.
