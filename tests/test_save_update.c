#include "save_update.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { CARD_HEADER_US = 384, CARD_SIZE = 512, SLOT_CAP = 1024 };
typedef enum {
    FAIL_NONE,
    FAIL_READ_INITIAL,
    FAIL_READ_SECOND_INITIAL,
    FAIL_OPEN,
    FAIL_WRITE,
    FAIL_FLUSH,
    FAIL_CLOSE,
    FAIL_READBACK,
    FAIL_VERIFY_CORRUPT
} fail_stage;

typedef struct {
    uint8_t slots[2][SLOT_CAP];
    size_t sizes[2];
    fail_stage fail;
    int read_calls;
    int writes;
    unsigned int last_write_slot;
} memory_store;

static uint32_t crc32_bytes(const uint8_t *data, size_t size)
{
    uint32_t crc = UINT32_C(0xffffffff);
    size_t i;
    for (i = 0; i < size; ++i) {
        unsigned int bit;
        crc ^= data[i];
        for (bit = 0; bit < 8; ++bit) {
            crc = (crc & 1U) != 0U
                ? (crc >> 1) ^ UINT32_C(0xedb88320)
                : crc >> 1;
        }
    }
    return ~crc;
}

static void write_u32_le(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static void make_card(uint8_t card[CARD_SIZE], uint8_t marker)
{
    uint8_t *listing;
    memset(card, 0, CARD_SIZE);
    card[0] = 'S'; card[1] = 'C'; card[2] = 0x12; card[3] = 0x02;
    card[10] = marker;
    listing = card + CARD_HEADER_US;
    write_u32_le(listing, crc32_bytes(listing + 4, 124U));
}

static vh_save_io_result read_slot(void *context, unsigned int slot,
                                   uint8_t *buffer, size_t capacity,
                                   size_t *size_out)
{
    memory_store *store = (memory_store *)context;
    ++store->read_calls;
    if ((store->fail == FAIL_READ_INITIAL && store->read_calls <= 2) ||
        (store->fail == FAIL_READ_SECOND_INITIAL && store->read_calls == 2) ||
        (store->fail == FAIL_READBACK && store->read_calls > 2)) {
        return VH_SAVE_IO_ERROR;
    }
    if (store->sizes[slot] == 0U) {
        *size_out = 0U;
        return VH_SAVE_IO_MISSING;
    }
    if (store->sizes[slot] > capacity) return VH_SAVE_IO_ERROR;
    memcpy(buffer, store->slots[slot], store->sizes[slot]);
    *size_out = store->sizes[slot];
    if (store->fail == FAIL_VERIFY_CORRUPT && store->read_calls > 2) {
        buffer[store->sizes[slot] - 1U] ^= 0x40U;
    }
    return VH_SAVE_IO_OK;
}

static int open_write(void *context, unsigned int slot)
{
    memory_store *store = (memory_store *)context;
    if (store->fail == FAIL_OPEN) return 0;
    store->sizes[slot] = 0U;
    return 1;
}

static int write_all(void *context, unsigned int slot,
                     const uint8_t *data, size_t size)
{
    memory_store *store = (memory_store *)context;
    if (store->fail == FAIL_WRITE) return 0;
    if (size > SLOT_CAP) return 0;
    memcpy(store->slots[slot], data, size);
    store->sizes[slot] = size;
    ++store->writes;
    store->last_write_slot = slot;
    return 1;
}

static int flush_slot(void *context, unsigned int slot)
{
    memory_store *store = (memory_store *)context;
    (void)slot;
    return store->fail != FAIL_FLUSH;
}

static int close_slot(void *context, unsigned int slot)
{
    memory_store *store = (memory_store *)context;
    (void)slot;
    return store->fail != FAIL_CLOSE;
}

static const vh_save_update_ops OPS = {
    read_slot, open_write, write_all, flush_slot, close_slot
};

static void seed(memory_store *store, const uint8_t card[CARD_SIZE],
                 uint64_t generation)
{
    size_t size = 0U;
    memset(store, 0, sizeof(*store));
    assert(vh_save_slot_encode(store->slots[0], SLOT_CAP, generation,
                               card, CARD_SIZE, CARD_HEADER_US, &size));
    store->sizes[0] = size;
}

static vh_save_update_result update(memory_store *store,
                                    const uint8_t card[CARD_SIZE])
{
    uint8_t a[SLOT_CAP], b[SLOT_CAP], verify[SLOT_CAP];
    return vh_save_slot_update(&OPS, store, CARD_HEADER_US, card, CARD_SIZE,
                               a, b, SLOT_CAP, verify, SLOT_CAP, NULL, NULL);
}

static void assert_old_slot_preserved(const memory_store *store,
                                       const uint8_t *old_container,
                                       size_t old_size)
{
    assert(store->sizes[0] == old_size);
    assert(memcmp(store->slots[0], old_container, old_size) == 0);
}

int main(void)
{
    memory_store store;
    uint8_t old_card[CARD_SIZE], new_card[CARD_SIZE];
    fail_stage failures[] = {FAIL_OPEN, FAIL_WRITE, FAIL_FLUSH, FAIL_CLOSE,
                             FAIL_READBACK, FAIL_VERIFY_CORRUPT};
    size_t i;
    size_t old_size;
    size_t alternate_size;
    uint8_t old_container[SLOT_CAP];
    uint8_t alternate_container[SLOT_CAP];
    uint8_t invalid_card[CARD_SIZE];
    uint8_t a[SLOT_CAP], b[SLOT_CAP], verify[SLOT_CAP];
    uint8_t overlap_buffers[SLOT_CAP * 3U];
    uint64_t generation = 0U;
    unsigned int selected = 99U;
    uint64_t untouched_generation = UINT64_C(123456789);
    unsigned int untouched_selected = 42U;

    make_card(old_card, 0x11U);
    make_card(new_card, 0x22U);

    seed(&store, old_card, 5U);

    /* Partially overlapping scratch ranges must be rejected before I/O. */
    assert(vh_save_slot_update(&OPS, &store, CARD_HEADER_US, new_card,
                               CARD_SIZE, overlap_buffers,
                               overlap_buffers + SLOT_CAP - 1U, SLOT_CAP,
                               overlap_buffers + SLOT_CAP * 2U, SLOT_CAP,
                               NULL, NULL) == VH_SAVE_UPDATE_INVALID_ARGUMENT);
    assert(store.read_calls == 0 && store.writes == 0);

    assert(update(&store, new_card) == VH_SAVE_UPDATE_OK);
    assert(vh_save_slot_select(store.slots[0], store.sizes[0],
                               store.slots[1], store.sizes[1],
                               CARD_HEADER_US, &selected) == VH_SAVE_SLOT_VALID);
    assert(selected == 1U);
    assert(vh_save_slot_validate(store.slots[1], store.sizes[1],
                                 CARD_HEADER_US, &generation, NULL, NULL));
    assert(generation == 6U);

    for (i = 0U; i < sizeof(failures) / sizeof(failures[0]); ++i) {
        seed(&store, old_card, 5U);
        old_size = store.sizes[0];
        memcpy(old_container, store.slots[0], old_size);
        store.fail = failures[i];
        assert(update(&store, new_card) != VH_SAVE_UPDATE_OK);
        assert_old_slot_preserved(&store, old_container, old_size);
    }

    seed(&store, old_card, 5U);
    old_size = store.sizes[0];
    memcpy(old_container, store.slots[0], old_size);
    store.fail = FAIL_READ_INITIAL;
    assert(vh_save_slot_update(&OPS, &store, CARD_HEADER_US, new_card,
                               CARD_SIZE, a, b, SLOT_CAP, verify, SLOT_CAP,
                               &untouched_selected, &untouched_generation)
           == VH_SAVE_UPDATE_IO_FAILURE);
    assert(untouched_selected == 42U);
    assert(untouched_generation == UINT64_C(123456789));
    assert(store.writes == 0);
    assert_old_slot_preserved(&store, old_container, old_size);

    /* Even a valid slot A cannot be used if reading slot B errors. */
    seed(&store, old_card, 5U);
    old_size = store.sizes[0];
    memcpy(old_container, store.slots[0], old_size);
    store.fail = FAIL_READ_SECOND_INITIAL;
    assert(update(&store, new_card) == VH_SAVE_UPDATE_IO_FAILURE);
    assert(store.writes == 0);
    assert_old_slot_preserved(&store, old_container, old_size);

    seed(&store, old_card, UINT64_MAX);
    old_size = store.sizes[0];
    memcpy(old_container, store.slots[0], old_size);
    assert(vh_save_slot_update(&OPS, &store, CARD_HEADER_US, new_card,
                               CARD_SIZE, a, b, SLOT_CAP, verify, SLOT_CAP,
                               NULL, NULL) == VH_SAVE_UPDATE_GENERATION_EXHAUSTED);
    assert(store.writes == 0);
    assert_old_slot_preserved(&store, old_container, old_size);

    memset(&store, 0, sizeof(store));
    assert(update(&store, new_card) == VH_SAVE_UPDATE_NO_VALID_BASE);
    assert(store.writes == 0);


    /* When slot B is the active generation, the coordinator writes slot A. */
    seed(&store, old_card, 5U);
    assert(vh_save_slot_encode(store.slots[1], SLOT_CAP, 6U, new_card,
                               CARD_SIZE, CARD_HEADER_US, &store.sizes[1]));
    assert(update(&store, old_card) == VH_SAVE_UPDATE_OK);
    assert(store.last_write_slot == 0U);
    assert(vh_save_slot_select(store.slots[0], store.sizes[0],
                               store.slots[1], store.sizes[1],
                               CARD_HEADER_US, &selected) == VH_SAVE_SLOT_VALID);
    assert(selected == 0U);

    /* Equal-generation divergent payloads must not be overwritten. */
    seed(&store, old_card, 5U);
    assert(vh_save_slot_encode(store.slots[1], SLOT_CAP, 5U, new_card,
                               CARD_SIZE, CARD_HEADER_US, &store.sizes[1]));
    memcpy(old_container, store.slots[0], store.sizes[0]);
    old_size = store.sizes[0];
    alternate_size = store.sizes[1];
    memcpy(alternate_container, store.slots[1], alternate_size);
    assert(update(&store, old_card) == VH_SAVE_UPDATE_AMBIGUOUS_BASE);
    assert(store.writes == 0);
    assert(store.sizes[0] == old_size &&
           memcmp(store.slots[0], old_container, old_size) == 0);
    assert(store.sizes[1] == alternate_size);
    assert(memcmp(store.slots[1], alternate_container, alternate_size) == 0);

    /* Invalid replacement image is rejected before any target mutation. */
    seed(&store, old_card, 5U);
    memcpy(old_container, store.slots[0], store.sizes[0]);
    old_size = store.sizes[0];
    memcpy(invalid_card, new_card, sizeof(invalid_card));
    invalid_card[0] = 'X';
    assert(update(&store, invalid_card) == VH_SAVE_UPDATE_INVALID_ARGUMENT);
    assert(store.writes == 0);
    assert_old_slot_preserved(&store, old_container, old_size);

    puts("save update coordinator tests: PASS");
    return 0;
}
