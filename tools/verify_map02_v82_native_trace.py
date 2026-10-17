#!/usr/bin/env python3
"""Strict independent reader for private v82 *synthetic emulator* event trace.

Never treat DMA2 start addresses as decoded GP0 words or frame pixels.
"""
import argparse
import json
from pathlib import Path

KINDS={"vblank","gp1_mmio","gpu_dma2_start","gp0_unai_handled","unai_sample_delta","unai_store_count","unai_same_store_count",
       "gpulib_a0_store_count","gpulib_a0_same_count",
       "gpulib_copy_store_count","gpulib_copy_same_count",
       "gpulib_overlap_store_count","gpulib_overlap_same_count",
       "gpulib_mask_upload_store_count","gpulib_mask_upload_same_count",
       "gpulib_wrap_store_count","gpulib_wrap_same_count",
       "async_dma_queued","async_dma_completed",
       "async_dma_store_count","async_dma_same_count",
       "async_copy_queued","async_copy_completed",
       "async_copy_store_count","async_copy_same_count",
       "async_copy_masked_completed",
       "post_async_sync_copy_stores","post_async_sync_copy_same",
       "mixed_a0_queued","mixed_a0_completed","mixed_a0_store_count",
       "mixed_a0_same_count","mixed_copy_queued","mixed_copy_completed",
       "mixed_copy_store_count","mixed_copy_same_count","mixed_masked_copies",
       "mixed_worker_steps","mixed_worker_order",
       "mixed_sync_a0_store_count","mixed_sync_copy_store_count",
       "mixed_sync_copy_same_count",
       "cycle1_a0_queued","cycle1_a0_done","cycle1_a0_stores","cycle1_copy_queued","cycle1_copy_done","cycle1_copy_stores","cycle1_copy_same","cycle1_masked_copy","cycle1_sync_a0","cycle1_sync_copy","cycle1_sync_same","cycle2_a0_queued","cycle2_a0_done","cycle2_a0_stores","cycle2_copy_queued","cycle2_copy_done","cycle2_copy_stores","cycle2_copy_same","cycle2_masked_copy","cycle2_sync_a0","cycle2_sync_copy","cycle2_sync_same",
       "pressure_tried","pressure_accepted","pressure_idle_fallback","pressure_full_fallback","pressure_peak_words","pressure_worker_completed","pressure_worker_stores","pressure_sync_stores","pressure_pending_words","pressure_worker_same","pressure_sync_same",
       "lane_detail_events","lane_aggregate_events","lane_total_events",
       "snapshot_cached_reads","snapshot_invalidation_proven",
       "snapshot_verified_reads",
       "append_round_1","append_round_2","append_round_3",
       "append_round_4","append_round_5","append_round_6",
       "append_round_7","append_round_8",
       "append_prefix_checks","append_memory_exports",
       "append_exact_rebuilds","append_stale_refusals","append_stable_reads",
       "boundary_detail_remaining","boundary_aggregate_remaining",
       "boundary_identical_serializations",
       "reset_observer_epoch","reset_serializer_scrubbed_bytes",
       "reset_stable_replays",
       "recovery_old_path_refused","recovery_new_path_published",
       "recovery_replay_refused",
       "interrupted_stage_refused","interrupted_fresh_published",
       "interrupted_stage_preserved",
       "durability_post_link_directory_sync",
       "durability_post_unlink_directory_sync",
       "durability_replay_refused",
       "reopened_private_commits","reopened_private_parent_syncs",
       "reopened_bad_bytes_refused"}
FIELDS={"kind","seq","value","cycle","frame"}

class Refused(ValueError):pass

def validate(content: bytes):
    if not content or len(content)>524288 or not content.endswith(b"\n"):
        raise Refused("size or newline framing")
    try:
        strings=content.decode("ascii").splitlines()
    except UnicodeError as e:
        raise Refused("non-ASCII payload") from e
    edges=[]
    gp1=0
    prev_seq=0
    prev_kind=None
    prev_value=None
    result=[]
    for index,line in enumerate(strings,1):
        try:
            item=json.loads(line,parse_constant=lambda _: (_ for _ in ()).throw(Refused("nonfinite")))
        except (ValueError,TypeError) as e:
            raise Refused(f"invalid JSON at record {index}") from e
        if not isinstance(item,dict) or set(item)!=FIELDS or item.get("kind") not in KINDS:
            raise Refused(f"bad schema {index}")
        if any(type(item[k]) is not int or not 0<=item[k]<=0xffffffff for k in FIELDS-{"kind"}):
            raise Refused(f"bad number {index}")
        if item["seq"]!=prev_seq+1:raise Refused(f"sequence gap at {index}")
        prev_seq=item["seq"]
        if item["kind"]=="vblank":
            if item["value"]!=0:raise Refused("VBlank payload nonzero")
            if edges and (item["frame"]!=edges[-1]["frame"]+1 or
                          item["cycle"]<=edges[-1]["cycle"]):
                raise Refused("nonconsecutive VBlank frame/cycle")
            edges.append(item)
        else:
            if item["frame"]!=0:raise Refused("GPU submission asserted frame identity")
            if item["kind"]=="unai_store_count" and (prev_kind!="unai_sample_delta" or
                item["value"]==0xffffffff or item["cycle"]!=0):
                raise Refused("bad actual Unai 16-bit store count")
            if item["kind"]=="unai_same_store_count" and (prev_kind!="unai_store_count" or
                item["value"]>prev_value or item["cycle"]!=0):
                raise Refused("impossible same-value native pixel-store count")
            if (item["kind"].startswith("gpulib_") or item["kind"].startswith("async_dma_") or
                item["kind"].startswith("async_copy_") or
                item["kind"].startswith("post_async_sync_") or
                item["kind"].startswith("mixed_") or
                item["kind"].startswith("cycle1_") or
                item["kind"].startswith("cycle2_") or
                item["kind"].startswith("pressure_") or
                item["kind"].startswith("lane_") or
                item["kind"].startswith("snapshot_") or
                item["kind"].startswith("append_") or
                item["kind"].startswith("boundary_") or
                item["kind"].startswith("reset_") or
                item["kind"].startswith("recovery_") or
                item["kind"].startswith("interrupted_") or
                item["kind"].startswith("durability_") or
                item["kind"].startswith("reopened_")) and (item["cycle"]!=0 or
                item["value"]==0xffffffff):
                raise Refused("invalid aggregate gpulib store event")
            if item["kind"]=="gp1_mmio":gp1+=1
            if item["kind"]=="unai_sample_delta":
                if prev_kind!="gp0_unai_handled" or item["cycle"]!=0 or item["value"]>24:
                    raise Refused("invalid paired Unai sample comparison")
            if item["kind"]=="gp0_unai_handled" and item["cycle"]!=0:
                raise Refused("renderer GPU handler has no observed CPU cycle")
            if item["kind"]=="gp0_unai_handled" and not (
                (item["value"]>>24)==2
                or 0x20 <= (item["value"]>>24) <= 0x43
                or 0x48 <= (item["value"]>>24) <= 0x53
                or 0x58 <= (item["value"]>>24) <= 0x6b
                or 0x70 <= (item["value"]>>24) <= 0x7f
                or 0xe1 <= (item["value"]>>24) <= 0xe6):
                raise Refused("unrecognized renderer-handled opcode")
            if item["kind"]=="gpu_dma2_start" and item["value"]>0x1fffff:
                raise Refused("DMA2 start outside PSX RAM")
        result.append(item)
        prev_kind=item["kind"]
        prev_value=item["value"]
    if len(edges)!=4 or gp1<2:raise Refused("missing VBlank or GP1 evidence")
    if result[0]["kind"]=="vblank" and result[0]["frame"]==0:
        # Frame zero is permissible; avoid conflating with unknown GP1 frames.
        pass
    return {"classification":"emulator_observed_synthetic_input_only",
            "events":len(result),"vblank_edges":len(edges),"gp1_mmio":gp1,
            "gpu_dma2_start":sum(e["kind"]=="gpu_dma2_start" for e in result),
            "gp0_unai_handled":sum(e["kind"]=="gp0_unai_handled" for e in result),
            "unai_sample_delta":sum(e["kind"]=="unai_sample_delta" for e in result),
            "sampled_pixels_changed":sum(e["value"] for e in result if e["kind"]=="unai_sample_delta"),
            "gpulib_a0_stores":sum(e["value"] for e in result if e["kind"]=="gpulib_a0_store_count"),
            "gpulib_copy_stores":sum(e["value"] for e in result if e["kind"]=="gpulib_copy_store_count"),
            "unai_store_count_events":sum(e["kind"]=="unai_store_count" for e in result),
            "unai_same_store_count_events":sum(e["kind"]=="unai_same_store_count" for e in result),
            "bytes":len(content),"original_retail_MAP02_verified":False,
            "HD_replacement_approved":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_file",type=Path)
    p.add_argument("--expected-events",type=int)
    p.add_argument("--expected-bytes",type=int)
    a=p.parse_args()
    try:
        raw=a.private_file.read_bytes()
        result=validate(raw)
        if a.expected_events is not None and result["events"]!=a.expected_events:
            raise Refused("reported event count differs from stored trace")
        if a.expected_bytes is not None and result["bytes"]!=a.expected_bytes:
            raise Refused("reported byte count differs from stored trace")
    except (OSError,Refused) as exc:p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":main()
