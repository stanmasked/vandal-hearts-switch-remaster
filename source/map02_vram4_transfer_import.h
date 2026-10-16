#ifndef VH_MAP02_VRAM4_TRANSFER_IMPORT_H
#define VH_MAP02_VRAM4_TRANSFER_IMPORT_H

/*
 * Private offline binary import for the MAP02 GPU transfer-ledger gate.
 *
 * Format vh.map02.transfer-packet.v1, little-endian:
 *  Header (32 bytes):
 *    [0:8]  ASCII "VHMAPGL1"
 *    [8:12] uint32 frame
 *    [12:16] uint32 submitted primitive count
 *    [16:20] uint32 transfer event count (0..512)
 *    [20:24] uint32 packet length in bytes
 *    [24:32] eight reserved zero bytes
 *  Repeated record (52-byte signed LE int32 fields, then payload):
 *    step, before_submission, operation, x,y,w,h, dest_x,dest_y,
 *    red,green,blue,payload_bytes
 *    LOAD payload: exact w*h*2 little-endian bytes (max 32768).
 *    MOVE/CLEAR: no payload. Unused fields MUST be zero.
 *
 * This importer verifies format, bounds, sequence, frame and canonical
 * encoding. A syntactically valid packet is NOT proof of provenance:
 * the user must first validate the private timeline and transfer ledger
 * using tools/export_map02_verified_vram_ledger.py. The accompanying C
 * replay still compares all snapshot bytes before drawing.
 *
 * Storage remains caller-owned, frozen and non-overlapping. Payload pointers
 * refer directly into the packet and must remain alive through replay.
 * Failure never changes caller's decoded events or output count.
 */
#include <stddef.h>
#include <stdint.h>
#include "map02_vram4_transfer_ledger.h"

#define VH_MAP02_LEDGER_PACKET_HEADER 32u
#define VH_MAP02_LEDGER_PACKET_EVENT 52u
#define VH_MAP02_LEDGER_PACKET_VERSION "VHMAPGL1"

static inline uint32_t vh_map02_ledger_packet_u32(
    const uint8_t *buffer) {
    return (uint32_t)buffer[0] |
           ((uint32_t)buffer[1] << 8u) |
           ((uint32_t)buffer[2] << 16u) |
           ((uint32_t)buffer[3] << 24u);
}

static inline int32_t vh_map02_ledger_packet_s32(
    const uint8_t *buffer) {
    const uint32_t u = vh_map02_ledger_packet_u32(buffer);
    const int64_t s = u > UINT32_C(0x7fffffff) ?
        (int64_t)u - INT64_C(4294967296) : (int64_t)u;
    return (int32_t)s;
}

static inline int vh_map02_vram_ledger_import_packet(
    const uint8_t *packet, size_t bytes,
    uint64_t expected_frame, size_t expected_submissions,
    VhMap02VramTransfer *out, size_t capacity,
    size_t *out_count) {
    size_t i, count, pass;
    if (!packet || !out || !out_count ||
        bytes < VH_MAP02_LEDGER_PACKET_HEADER ||
        expected_frame == 0u || expected_frame > UINT32_MAX ||
        expected_submissions < 2u ||
        expected_submissions > VH_MAP02_VRAM4_FRAME_MAX_FACES ||
        memcmp(packet,VH_MAP02_LEDGER_PACKET_VERSION,8u) ||
        vh_map02_ledger_packet_u32(packet+8u) != expected_frame ||
        vh_map02_ledger_packet_u32(packet+12u) != expected_submissions ||
        vh_map02_ledger_packet_u32(packet+20u) != bytes)
        return 0;
    count = (size_t)vh_map02_ledger_packet_u32(packet+16u);
    if (count > VH_MAP02_VRAM_LEDGER_MAX_EVENTS || count > capacity ||
        vh_map02_vram_ledger_ranges_overlap(
            packet, bytes, out, count * sizeof *out) ||
        vh_map02_vram_ledger_ranges_overlap(
            packet, bytes, out_count, sizeof *out_count) ||
        vh_map02_vram_ledger_ranges_overlap(
            out, count * sizeof *out, out_count, sizeof *out_count))
        return 0;
    for (i=24u; i<32u; ++i)
        if (packet[i] != 0u) return 0;

    /* Two passes guarantee all-or-nothing even for malformed final events.
     * The caller promises the packet stays immutable during both passes. */
    for (pass=0u; pass<2u; ++pass) {
        size_t offset = VH_MAP02_LEDGER_PACKET_HEADER;
        size_t previous_boundary = 0u;
        for (i=0u; i<count; ++i) {
            int32_t f[13];
            VhMap02VramTransfer ev = {0};
            size_t j;
            if (bytes-offset < VH_MAP02_LEDGER_PACKET_EVENT)
                return 0;
            for (j=0u; j<13u; ++j)
                f[j]=vh_map02_ledger_packet_s32(
                    packet+offset+j*4u);
            offset += VH_MAP02_LEDGER_PACKET_EVENT;
            if (f[0] < 0 || f[1] < 0 || f[12] < 0 ||
                (size_t)f[12] > bytes-offset ||
                (size_t)f[12] > VH_MAP02_VRAM_LEDGER_MAX_WORDS*2u ||
                (f[2] != VH_MAP02_VRAM_OP_MOVE &&
                 (f[7] != 0 || f[8] != 0)) ||
                (f[2] != VH_MAP02_VRAM_OP_CLEAR &&
                 (f[9] != 0 || f[10] != 0 || f[11] != 0)))
                return 0;
            ev.frame = expected_frame;
            ev.step = (size_t)f[0];
            ev.before_submission = (size_t)f[1];
            ev.operation = f[2];
            ev.x=f[3]; ev.y=f[4]; ev.w=f[5]; ev.h=f[6];
            ev.dest_x=f[7]; ev.dest_y=f[8];
            ev.red=f[9]; ev.green=f[10]; ev.blue=f[11];
            ev.load_bytes=(size_t)f[12];
            ev.load_le=ev.load_bytes ? packet+offset : NULL;
            if (!vh_map02_vram_ledger_event_valid(
                    &ev,i,expected_frame,expected_submissions) ||
                ev.before_submission < previous_boundary)
                return 0;
            previous_boundary=ev.before_submission;
            offset += ev.load_bytes;
            if (pass == 1u)
                out[i]=ev;
        }
        if (offset != bytes) return 0;
    }
    *out_count=count;
    return 1;
}

/* Staging from an externally verified private packet into the existing
 * complete GPU replay gate. Neither output scene nor imported count is
 * modified if the packet, VRAM timeline, or transfer replay fails. */
static inline int vh_map02_vram4_timeline_build_from_packet(
    const VhMap02Vram4TimelineInput *input,
    VhMap02Vram4FrameWorkspace *workspace,
    const uint8_t *packet, size_t packet_bytes,
    VhMap02VramTransfer *events, size_t event_capacity,
    uint8_t *scratch_vram, size_t scratch_bytes) {
    size_t events_count = 0u;
    size_t event_bytes;
    /* Decoder outputs are caller-writable. Guard ALL output and evidence
     * spans before importing even the first event: otherwise a valid
     * packet could overwrite its own camera, VRAM or OT inputs. */
    if (!input || !workspace || !packet || !events || !scratch_vram ||
        event_capacity == 0u ||
        event_capacity > VH_MAP02_VRAM_LEDGER_MAX_EVENTS ||
        !vh_map02_vram4_timeline_preflight(input, workspace))
        return 0;
    event_bytes = event_capacity * sizeof *events;
    if (!vh_map02_vram4_timeline_buffer_is_isolated(
            input, workspace, events, event_bytes) ||
        !vh_map02_vram4_timeline_buffer_is_isolated(
            input, workspace, packet, packet_bytes) ||
        !vh_map02_vram4_timeline_buffer_is_isolated(
            input, workspace, scratch_vram, scratch_bytes) ||
        vh_map02_vram_ledger_ranges_overlap(
            events, event_bytes, packet, packet_bytes) ||
        vh_map02_vram_ledger_ranges_overlap(
            events, event_bytes, scratch_vram, scratch_bytes) ||
        vh_map02_vram_ledger_ranges_overlap(
            packet, packet_bytes, scratch_vram, scratch_bytes))
        return 0;
    if (!vh_map02_vram_ledger_import_packet(
            packet,packet_bytes,input->frame,input->count,
            events,event_capacity,&events_count))
        return 0;
    return vh_map02_vram4_timeline_build_with_ledger(
        input,workspace,events,events_count,scratch_vram,scratch_bytes);
}

#endif
