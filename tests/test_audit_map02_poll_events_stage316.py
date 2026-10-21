"""Stage316 ordinal event source synthetic negatives. NOT NeXium evidence."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_poll_events_stage316 import (
    read_source,summarize,decode_active_request,decode_last_return)
from capture_map02_poll_events_stage316 import (
    POLL_EVENT_FIELDS,POLL_EVENT_HEADER,POLL_EVENT_LAST_FIELDS)

class OrdinalPollEventTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.path=Path(t.name)/"sanitized.csv"
        self.records=[]
        for i in range(45):
            tm=1_000_000_000+i*200_000_000
            self.records.append(("P",tm,-1,2,*([0]*(len(POLL_EVENT_FIELDS)+len(POLL_EVENT_LAST_FIELDS)-1))))
            # CPAL alias 1 has a request that can remain pending across guest input.
            # Code 0x89: valid, ordinal 0 requests IN and ordinal 1 requests OUT.
            # 0xa9: last completed call returned ready with those same categories.
            self.records.append(("M",tm,1,1,0,0,1,1,0,0,1,0,0x89,0xa9))
            if i:
                # Alias 0 progresses; its categories must never be attributed to CPAL.
                self.records.append(("M",tm,0,i,0,i,0,i,0,i,0,0,0,0xa5))
        self.write()
    def write(self,header=POLL_EVENT_HEADER):
        with self.path.open("w",encoding="ascii",newline="") as f:
            c=csv.writer(f);c.writerow(header);c.writerows(self.records)
    def test_stalled_cpal_active_request_survives_guest_window(self):
        frames,sha=read_source(self.path)
        r=summarize(frames,1_050_000_000,9_000_000_000,{1})
        c=r["cpal_proven_native_thread_poll_event_categories"]
        self.assertEqual(len(c),1)
        self.assertEqual(c[0]["ordinal0_requested_POLLIN_guest_delta"],0)
        self.assertEqual(c[0]["ordinal1_requested_POLLOUT_guest_delta"],0)
        req=c[0]["active_poll_request_categories_at_final_observation"]
        self.assertTrue(req["valid_two_position_pollfd_snapshot"])
        self.assertTrue(req["ordinal0_requested_POLLIN"])
        self.assertTrue(req["ordinal1_requested_POLLOUT"])
        self.assertTrue(c[0]["last_completed_poll_return_categories_at_final_observation"]
                        ["this_is_last_completed_return_not_the_active_request_result"])
        self.assertEqual(len(sha),64)
    def test_active_other_thread_not_misattributed_to_cpal(self):
        f,_=read_source(self.path);r=summarize(f,1_050_000_000,9_000_000_000,{1})
        other=next(x for x in r["all_anonymous_tls_poll_event_categories"]
                   if x["anonymous_same_process_native_TLS_alias"]==0)
        self.assertFalse(other["source_proven_preinput_CPAL_callback_thread"])
        self.assertGreater(other["ordinal0_returned_POLLIN_guest_delta"],25)
    def test_no_positive_cpal_marker_means_no_claim(self):
        f,_=read_source(self.path);r=summarize(f,1_050_000_000,9_000_000_000,set())
        self.assertEqual(r["cpal_proven_native_thread_poll_event_categories"],[])
    def test_raw_fd_header_fails_closed(self):
        self.write(("kind","monotonic_ns","native_fd",*POLL_EVENT_FIELDS,*POLL_EVENT_LAST_FIELDS))
        with self.assertRaisesRegex(ValueError,"source changed"):
            read_source(self.path)
    def test_noninteger_counter_rejected(self):
        row=list(self.records[1]);row[5]="POLLIN";self.records[1]=row;self.write()
        with self.assertRaisesRegex(ValueError,"nonnumeric"):read_source(self.path)
    def test_decreasing_cumulative_counter_rejected(self):
        k=next(i for i,r in enumerate(self.records) if r[0]=="M"
               and r[2]==0 and r[1]>5_000_000_000)
        v=list(self.records[k]);v[3]=0;self.records[k]=v;self.write()
        with self.assertRaisesRegex(ValueError,"decreased"):read_source(self.path)
    def test_forged_tls_alias_refused(self):
        row=list(self.records[1]);row[2]=64;self.records[1]=row;self.write()
        with self.assertRaisesRegex(ValueError,"metadata alias"):read_source(self.path)
    def test_duplicate_alias_same_sample_refused(self):
        self.records.insert(2,self.records[1]);self.write()
        with self.assertRaisesRegex(ValueError,"Duplicated"):read_source(self.path)
    def test_nonmonotonic_sample_time_rejected(self):
        k=next(i for i,r in enumerate(self.records) if r[0]=="P" and r[1]>4_000_000_000)
        row=list(self.records[k]);row[1]=1_000_000_000
        self.records[k]=row;self.write()
        with self.assertRaisesRegex(ValueError,"regression"):read_source(self.path)
    def test_stale_guest_timestamps_rejected(self):
        f,_=read_source(self.path)
        with self.assertRaisesRegex(ValueError,"do not bracket"):
            summarize(f,12_000_000_000,13_000_000_000,{1})
    def test_symlink_source_refused(self):
        orig=self.path.parent/"original.csv";self.path.rename(orig)
        self.path.symlink_to(orig)
        with self.assertRaisesRegex(ValueError,"unavailable"):read_source(self.path)
    def test_invalid_last_request_reserved_bits_rejected(self):
        row=list(self.records[1]);row[-2]=0x99;self.records[1]=row;self.write()
        with self.assertRaisesRegex(ValueError,"requested poll event code"):read_source(self.path)
    def test_invalid_last_return_without_status_rejected(self):
        row=list(self.records[1]);row[-1]=0x80;self.records[1]=row;self.write()
        with self.assertRaisesRegex(ValueError,"return code"):read_source(self.path)
    def test_last_return_must_match_cumulative_category_counters(self):
        row=list(self.records[1])
        row[7]=0
        self.records[1]=row;self.write()
        with self.assertRaisesRegex(ValueError,"return category contradicts cumulative"):
            read_source(self.path)
    def test_decode_unknown_request_not_mistaken_for_no_requested_events(self):
        r=decode_active_request(0)
        self.assertFalse(r["valid_two_position_pollfd_snapshot"])
        self.assertIsNone(r["ordinal0_requested_POLLIN"])
    def test_decode_completed_timeout_distinct_from_active_request(self):
        r=decode_last_return(0xc0)
        self.assertEqual(r["last_completed_poll_return_class"],"timeout_zero_return")
        self.assertIsNone(r["ordinal0_returned_POLLIN"])
    def test_completed_poll_request_is_not_reported_as_active(self):
        frames,_=read_source(self.path)
        r=summarize(frames,1_050_000_000,9_000_000_000,{1})
        other=next(x for x in r["all_anonymous_tls_poll_event_categories"]
                   if x["anonymous_same_process_native_TLS_alias"]==0)
        active=other["active_poll_request_categories_at_final_observation"]
        self.assertFalse(active["valid_two_position_pollfd_snapshot"])
        self.assertIsNone(active["ordinal0_requested_POLLIN"])
        self.assertEqual(other["last_completed_poll_return_categories_at_final_observation"]
                         ["last_completed_poll_return_class"],"ready_positive_return")
    def test_transient_active_poll_is_not_lost_when_final_sample_is_inactive(self):
        # Clear alias 1's active code only at the last source sample in the
        # guest window; the earlier in-flight request must remain in the audit.
        k=max(i for i,row in enumerate(self.records)
              if row[0]=="M" and row[2]==1 and row[1]<=9_000_000_000)
        row=list(self.records[k]);row[12]=0;self.records[k]=row;self.write()
        frames,_=read_source(self.path)
        r=summarize(frames,1_050_000_000,9_000_000_000,{1})
        c=r["cpal_proven_native_thread_poll_event_categories"][0]
        self.assertTrue(c["active_poll_request_categories_at_first_post_input_sample"]
                        ["valid_two_position_pollfd_snapshot"])
        self.assertFalse(c["active_poll_request_categories_at_final_observation"]
                         ["valid_two_position_pollfd_snapshot"])
        self.assertIn(0x89,c["active_poll_request_codes_observed_during_guest_window"])
        self.assertTrue(r["sampling_does_not_prove_exact_state_at_guest_input_timestamp"])

    def test_poll_cancellation_cleanup_is_registered_and_preserves_last_return(self):
        source=(Path(__file__).resolve().parents[1]/"tools"/
                "map02_poll_events_stage316.c").read_text()
        self.assertIn("#include <pthread.h>",source)
        self.assertIn("static void vh_poll_event_cancel_cleanup(void *opaque)",source)
        self.assertIn("__atomic_fetch_and(&s->poll_event_state[alias], ~UINT64_C(0xff),",source)
        body=source[source.index("int poll(struct pollfd *fds,nfds_t nfds,int timeout) {"):]
        body=body[:body.index("\n}")]
        self.assertLess(body.index("pthread_cleanup_push("),body.index("vh_poll_event_entry("))
        self.assertLess(body.index("vh_poll_event_return("),body.index("pthread_cleanup_pop(0)"))

if __name__=="__main__":unittest.main()
