/*
 * Stage308 unlicensed synthetic thread-local provenance proof.
 * This is NOT a NeXium/CPAL runtime test.
 */
#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>

struct work { int marks; int cycles; int open_rc, config_rc, prep_rc, close_rc; };
static void *run(void *arg) {
  struct work *w=(struct work *)arg;
  snd_pcm_t *pcm=NULL;
  w->open_rc=snd_pcm_open(&pcm,"null",SND_PCM_STREAM_PLAYBACK,0);
  if (w->open_rc<0 || !pcm) return NULL;
  /* A fresh ALSA handle is SETUP, not PREPARED: set actual PCM parameters
   * so snd_pcm_prepare() is tested on a valid stream, not -EBADFD. */
  w->config_rc=snd_pcm_set_params(
      pcm,SND_PCM_FORMAT_S16_LE,SND_PCM_ACCESS_RW_INTERLEAVED,
      2,48000,1,20000);
  if (w->config_rc!=0) {
    w->close_rc=snd_pcm_close(pcm);
    return NULL;
  }
  void (*tag)(void)=dlsym(RTLD_DEFAULT,"vh_map02_stage308_cpal_callback_mark");
  w->prep_rc=0;
  for (int i=0;i<w->cycles;i++) {
    if (tag && i<w->marks) tag();
    int rc=snd_pcm_prepare(pcm);
    if (rc!=0)w->prep_rc=rc;
  }
  w->close_rc=snd_pcm_close(pcm);
  return NULL;
}
int main(void) {
  struct work a={.marks=7,.cycles=10};
  struct work b={.marks=0,.cycles=15};
  pthread_t one,two;
  if (pthread_create(&one,NULL,run,&a)!=0) return 10;
  if (pthread_create(&two,NULL,run,&b)!=0) return 11;
  if (pthread_join(one,NULL)!=0 || pthread_join(two,NULL)!=0) return 12;
  printf("first=(%d,%d,%d,%d) second=(%d,%d,%d,%d)\n",
         a.open_rc,a.config_rc,a.prep_rc,a.close_rc,
         b.open_rc,b.config_rc,b.prep_rc,b.close_rc);
  return (a.open_rc || a.config_rc || a.prep_rc || a.close_rc ||
          b.open_rc || b.config_rc || b.prep_rc || b.close_rc) ? 1 : 0;
}
