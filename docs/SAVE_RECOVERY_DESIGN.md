# Save recovery design without rename-over-existing

Status: the versioned container codec, slot selector, and callback-driven update coordinator are implemented as host-testable C in `switch-save/save_slot.c` and `switch-save/save_update.c`. The coordinator is not connected to a filesystem backend or game API, and device testing is not implemented. Do not connect it to game saves yet.

## Why consider a different transaction model?

The libnx source audit establishes that a rename API exists, but does not establish safe replacement of an existing destination or power-loss durability. Deleting the old destination before renaming a temporary file would introduce a window in which neither the old nor the new save is available. This design avoids depending on rename-over-existing for the active memory-card image.

## Two-slot generation scheme

Store two independently validated save containers, for example `card.a` and `card.b`, in the app's selected save root. Each container has a small versioned envelope followed by the unchanged PS1 memory-card image:

- fixed magic and envelope format version;
- monotonically increasing 64-bit generation number;
- declared payload length;
- checksum of the envelope fields and payload (with the checksum field excluded from its own calculation);
- raw memory-card image bytes.

The envelope checksum detects torn or corrupted containers; the existing card-image validator remains responsible for the PS1 header, listing CRC, and occupied-record CRC checks. The envelope is not a replacement for card validation.

### Startup selection

1. Read each slot independently with a strict size bound.
2. Reject a slot if its envelope, length, checksum, or embedded memory-card image is invalid.
3. If exactly one slot is valid, use it.
4. If both are valid, use the higher generation.
5. If neither is valid, report recovery failure; do not silently create or overwrite a card.
6. If both valid slots have the same generation but different payloads, report an ambiguous recovery state rather than choosing arbitrarily.

### Updating a save

1. Keep the currently selected valid slot untouched.
2. Choose the other slot as the write target. Create it exclusively if absent; if it exists, truncate/write only that non-current slot.
3. Write a complete envelope and card image, check every write result and byte count, flush, and close using only the guarantees actually available from the backend.
4. Reopen the target and validate its complete envelope and embedded card image.
5. Report success only after read-back validation succeeds. The higher generation becomes authoritative on the next selection pass.
6. If any stage fails, the previous current slot's bytes remain untouched. The inactive target may be missing, damaged, or—if the write completed despite a later flush/close/read-back error—may contain a valid higher generation. Therefore an error return means the update was not verified by this call, not that the old generation is guaranteed to remain selected after restart. Recovery always validates both slots and selects the highest valid generation.

This scheme does not need a separate active-slot pointer or a rename-over-existing operation. It also does not by itself guarantee power-loss durability: filesystem behavior, flush semantics, close limitations, SD removal, and possible corruption of both slots still require target-device testing. If the backend cannot establish that a successful write/flush can be read back, the UI must not claim durable success.

## Compatibility and integration constraints

- This is a proposed storage layout, not the existing PC port's on-disk format. Keep desktop save files and archive files unchanged unless a deliberate migration/export design is added.
- The game-facing save API must resolve the selected slot before every read and route writes through the two-slot coordinator; simply adding this scheme beside a single active-card path would not protect the actual game save.
- Backups should contain the ordinary memory-card image, not the internal envelope, unless a versioned container format is intentionally exposed.
- Generation overflow must be handled explicitly; do not wrap to zero and then compare generations as if they were ordinary values.
- A restore must validate the archive name, read the complete bounded archive, validate the memory-card image and region, then write it as a new generation. It must not modify the currently selected slot in place.
- Slot names and paths must be constructed from a trusted save root and fixed slot names. No archive-supplied path may become a slot path.

## Host tests and current implementation scope

`vh_save_slot_update()` is a host-testable coordinator driven by injected I/O callbacks. It refuses to proceed if either slot read reports an I/O error, refuses to overwrite when neither slot is valid or the base is ambiguous, never writes the selected current slot, rejects generation `UINT64_MAX` rather than wrapping, checks write/flush/close results, and reopens the target for full read-back validation. The caller must serialize concurrent updates; the coordinator has no internal lock. The optional selected-slot and generation outputs are published only after verified success; the coordinator rejects output objects that overlap each other or the card/scratch buffers. Host tests exercise success in both slot directions, reject missing required I/O callbacks before backend activity, reject overlapping encode and coordinator scratch ranges and aliased result outputs, verify that failed codec validation/encoding, failed update operations, and invalid or ambiguous selection leave output arguments unchanged, initial-read failures (including a failed slot-B read when slot A is valid and a backend-reported size larger than the supplied buffer), open/write/flush/close/read-back failures, corrupted read-back, no valid base, ambiguous equal-generation payloads, invalid new card images, and generation exhaustion. The previous current slot is checked byte-for-byte after failures. These are simulated callback tests, not a filesystem durability test.



- Both slots invalid; one valid slot; two valid slots in either generation order.
- Newer slot corrupt, truncated, wrong version, wrong length, bad envelope checksum, or invalid embedded card image; fall back only to the older valid slot.
- Equal generations with equal payloads and equal generations with different payloads.
- Failure at every write, short-write, flush, close, reopen, read-back, and validation stage; the previous current slot remains selected.
- Simulated interruption after truncation, partial header, partial payload, complete payload before flush, and successful read-back.
- Generation boundary and overflow handling.
- Wrong-region restore and malformed archive rejection before target-slot mutation.
- Concurrent save requests are serialized or explicitly rejected.

Only after these host tests pass should the coordinator be connected to the save API. Before enabling it for users, repeat interruption, storage-removal, remount, and read-back tests on the actual target filesystem. This design is a recovery proposal, not evidence that the current Switch port can save or load game data.
