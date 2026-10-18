#ifndef VH_AUDIO_WORKER_STOP_GATE_H
#define VH_AUDIO_WORKER_STOP_GATE_H

/* Stage319: isolate the EXISTING single mailbox-running check and
 * first stop-observed software clock stamp in a portable testable gate.
 *
 * On running==true this is ONE mailbox atomic load, zero guest clock
 * queries, zero witness writes, no allocation, no output calls.
 * Only when that single read returns false is the software clock read.
 * False means the audio worker must leave its existing producer loop.
 */
#include <stdint.h>
#include "vh_game_music_mailbox.h"
#include "vh_audio_exit_worker_stop_witness.h"

typedef uint64_t (*VhAudioWorkerGuestClockNow)(void);

static inline int vh_audio_worker_stop_gate_continue(
        const VhGameMusicMailbox *box,
        VhAudioExitWorkerStopWitness *witness,
        VhAudioWorkerGuestClockNow now) {
    /* Exactly one existing atomic running-flag read per outer
     * audio-loop iteration, and no clock call while producing PCM. */
    /* Missing mailbox has no observed stop transition. Leave audio
     * safely, but DO NOT manufacture a timestamp for nonexistent
     * input state. On the real nonnull mailbox this retains the
     * original single running-flag atomic read. */
    if (!box) return 0;
    if (vh_game_music_mailbox_running(box))
        return 1;
    /* A missing clock is an unobserved timestamp, not a forged one.
     * Stopping gameplay/audio still works without diagnostic source. */
    if (witness && now && !vh_audio_exit_worker_stop_read(witness))
        (void)vh_audio_exit_worker_stop_mark(witness,now());
    return 0;
}
#endif
