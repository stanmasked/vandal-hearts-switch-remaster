#ifndef VH_SAVE_UPDATE_H
#define VH_SAVE_UPDATE_H

#include "save_slot.h"

#include <stddef.h>
#include <stdint.h>

typedef enum {
    VH_SAVE_IO_ERROR = -1,
    VH_SAVE_IO_MISSING = 0,
    VH_SAVE_IO_OK = 1
} vh_save_io_result;

typedef struct {
    /* OK means the complete slot was read; MISSING means it does not exist.
       ERROR must abort the update rather than being treated as an invalid slot. */
    vh_save_io_result (*read_slot)(void *context, unsigned int slot,
                                   uint8_t *buffer, size_t capacity,
                                   size_t *size_out);
    /* open_write must truncate/create only the specified slot, never its peer. */
    int (*open_write)(void *context, unsigned int slot);
    int (*write_all)(void *context, unsigned int slot,
                     const uint8_t *data, size_t size);
    int (*flush)(void *context, unsigned int slot);
    /* Called after every successful open_write, even after write/flush failure. */
    int (*close)(void *context, unsigned int slot);
} vh_save_update_ops;

typedef enum {
    VH_SAVE_UPDATE_OK = 1,
    VH_SAVE_UPDATE_INVALID_ARGUMENT = 0,
    VH_SAVE_UPDATE_IO_FAILURE = -1,
    VH_SAVE_UPDATE_NO_VALID_BASE = -2,
    VH_SAVE_UPDATE_AMBIGUOUS_BASE = -3,
    VH_SAVE_UPDATE_GENERATION_EXHAUSTED = -4,
    VH_SAVE_UPDATE_VERIFY_FAILURE = -5
} vh_save_update_result;

/*
 * Write a new generation into the non-current slot. The caller supplies three
 * disjoint scratch buffers: one per slot and a read-back buffer. Each must be
 * large enough for VH_SAVE_SLOT_HEADER_SIZE + the largest supported card image.
 * All I/O callbacks are required; no filesystem durability is implied. The
 * caller must serialize updates; this coordinator contains no lock. The function
 * rejects overlapping scratch-buffer ranges and any overlap with card_image.
 * selected_slot_out and generation_out are written only on verified success;
 * The coordinator rejects output objects that overlap each other or the
 * card/scratch buffers.
 * The close callback must consume/close
 * the open target even when it reports failure.
 */
vh_save_update_result vh_save_slot_update(
    const vh_save_update_ops *ops, void *context,
    size_t expected_header_size,
    const uint8_t *card_image, size_t card_image_size,
    uint8_t *slot_a_buffer, uint8_t *slot_b_buffer, size_t slot_capacity,
    uint8_t *verify_buffer, size_t verify_capacity,
    unsigned int *selected_slot_out, uint64_t *generation_out);

#endif
