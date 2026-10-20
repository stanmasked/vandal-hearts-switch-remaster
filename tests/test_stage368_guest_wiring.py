#!/usr/bin/env python3
"""Stage368 non-invasive guest source wiring and strict export regression."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
C=(ROOT/"source/vh_switch_game_audio.c")
MAIN=(ROOT/"source/main.c")
HEAD=(ROOT/"source/vh_audio_exit_wait_descriptor_stage368.h")
class Stage368GuestWiring(unittest.TestCase):
    def test_existing_one_bounded_service_wait_unchanged(self):
        source=C.read_text()
        self.assertEqual(source.count("audoutWaitPlayFinish("),1)
        self.assertIn("&released,&released_count,UINT64_C(12000000)",source)
        start=source.index("static int output_tail_submit_bounded")
        end=source.index("static void publish_audio_diagnostics",start)
        tail=source[start:end]
        self.assertIn("vh_audio_tail_stage353_wait_checked(",tail)
        self.assertIn("vh_tail368_record(",tail)
        self.assertLess(tail.index("vh_audio_tail_stage353_wait_checked("),
                        tail.index("vh_tail368_record("))
        self.assertNotIn("scene_trace_now_ns(",tail)
        self.assertNotIn("audoutGetAudioOutBufferCount(",tail)
        self.assertNotIn("audoutPlayBuffer(",tail)
    def test_stage368_records_only_tuple_and_post_join_export(self):
        source=C.read_text()
        self.assertIn("vh_tail368_reset(&exit_tail_wait_descriptor)",source)
        self.assertIn("vh_tail368_write_csv(",source)
        self.assertIn("if (!stream || thread_started) return -1;",source)
        header=HEAD.read_text()
        for unsafe in ("armGetSystemTick(", "audoutWaitPlayFinish(",
                       "audoutGetAudioOutBufferCount(", "malloc(", "free("):
            self.assertNotIn(unsafe,header)
        self.assertNotIn("%p",header)
    def test_distinct_exclusive_csv_without_legacy_modification(self):
        main=MAIN.read_text()
        self.assertIn('"/audio-exit-wait-descriptor-%03u.csv"',main)
        self.assertIn("vh_switch_game_audio_wait_descriptor_dump(",main)
        self.assertIn("O_WRONLY|O_CREAT|O_EXCL",main)
        self.assertIn("rows!=8 || flushed!=0 || closed!=0",main)
        self.assertIn("vh_switch_game_audio_stop();",main)
        self.assertLess(main.index("vh_switch_game_audio_stop();"),
                        main.index('"/audio-exit-wait-descriptor-%03u.csv"'))
if __name__=="__main__":
    unittest.main()
