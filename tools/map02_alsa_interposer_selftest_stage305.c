/*
 * Stage305 only: unlicensed synthetic ALSA "null" playback test.
 * Compares identical public API return codes with/without LD_PRELOAD.
 * Does not prove interception of CPAL's actual audio callback.
 */
#include <alsa/asoundlib.h>
#include <stdio.h>
int main(void) {
  snd_pcm_t *pcm = NULL;
  int opened = snd_pcm_open(&pcm, "null", SND_PCM_STREAM_PLAYBACK, 0);
  if (opened < 0 || !pcm) return 5;
  snd_pcm_status_t *status = NULL;
  if (snd_pcm_status_malloc(&status) != 0) return 6;
  int status_rc = snd_pcm_status(pcm, status);
  int prepare_rc = snd_pcm_prepare(pcm);
  snd_pcm_sframes_t avail = -1, delay = -1;
  int avail_rc = snd_pcm_avail_delay(pcm, &avail, &delay);
  snd_pcm_status_free(status);
  int drop_rc = snd_pcm_drop(pcm);
  int close_rc = snd_pcm_close(pcm);
  printf("opened=%d status=%d prepare=%d avail=%d drop=%d close=%d\n",
         opened,status_rc,prepare_rc,avail_rc,drop_rc,close_rc);
  return 0;
}
