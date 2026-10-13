#include "atomic_write.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    int fail_open;
    int fail_write;
    int fail_flush;
    int fail_close;
    int fail_replace;
    int bad_temporary_path;
    int opened;
    int wrote;
    int flushed;
    int closed;
    int replaced;
    int removed;
    int destination_value;
    int temporary_value;
} mock_fs;

static void *mock_open(void *context, const char *destination,
                       char *temporary_path, size_t capacity)
{
    mock_fs *fs = (mock_fs *)context;
    (void)destination;
    fs->opened++;
    if (fs->fail_open || capacity < sizeof("mock.tmp")) return NULL;
    if (fs->bad_temporary_path) {
        memset(temporary_path, 'x', capacity);
    } else {
        memcpy(temporary_path, "mock.tmp", sizeof("mock.tmp"));
    }
    return fs;
}

static int mock_write(void *context, void *handle,
                      const void *data, size_t size)
{
    mock_fs *fs = (mock_fs *)context;
    assert(handle == context);
    assert(data != NULL || size == 0U);
    fs->wrote++;
    if (fs->fail_write) return 0;
    fs->temporary_value = 42;
    return 1;
}

static int mock_flush(void *context, void *handle)
{
    mock_fs *fs = (mock_fs *)context;
    assert(handle == context);
    fs->flushed++;
    return !fs->fail_flush;
}

static int mock_close(void *context, void *handle)
{
    mock_fs *fs = (mock_fs *)context;
    assert(handle == context);
    fs->closed++;
    return !fs->fail_close;
}

static int mock_replace(void *context, const char *temporary,
                        const char *destination)
{
    mock_fs *fs = (mock_fs *)context;
    assert(strcmp(temporary, "mock.tmp") == 0);
    assert(strcmp(destination, "card.bin") == 0);
    fs->replaced++;
    if (fs->fail_replace) return 0;
    fs->destination_value = fs->temporary_value;
    return 1;
}

static void mock_remove(void *context, const char *temporary)
{
    mock_fs *fs = (mock_fs *)context;
    assert(strcmp(temporary, "mock.tmp") == 0);
    fs->removed++;
}

static const vh_atomic_write_ops OPS = {
    mock_open, mock_write, mock_flush, mock_close, mock_replace, mock_remove
};

static mock_fs fresh_fs(void)
{
    mock_fs fs;
    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7; /* old destination contents */
    return fs;
}

static void expect_failure_preserves_destination(mock_fs *fs)
{
    assert(fs->destination_value == 7);
    assert(fs->replaced == 0 || fs->fail_replace);
    if (fs->opened && !fs->fail_open) {
        assert(fs->closed == 1);
    }
    if (fs->opened && !fs->fail_open) {
        assert(fs->removed == 1);
    }
}

int main(void)
{
    mock_fs fs;
    const char payload[] = "synthetic card";
    vh_atomic_write_ops incomplete_ops = OPS;

    fs = fresh_fs();
    assert(vh_atomic_write(&OPS, &fs, "card.bin", payload,
                           sizeof(payload)) == 1);
    assert(fs.opened == 1 && fs.wrote == 1 && fs.flushed == 1);
    assert(fs.closed == 1 && fs.replaced == 1 && fs.removed == 0);
    assert(fs.destination_value == 42);

    fs = fresh_fs();
    fs.fail_open = 1;
    assert(vh_atomic_write(&OPS, &fs, "card.bin", payload,
                           sizeof(payload)) == 0);
    assert(fs.closed == 0 && fs.removed == 0 && fs.destination_value == 7);

    fs = fresh_fs();
    fs.bad_temporary_path = 1;
    assert(vh_atomic_write(&OPS, &fs, "card.bin", payload,
                           sizeof(payload)) == 0);
    assert(fs.closed == 1 && fs.replaced == 0);
    assert(fs.destination_value == 7);

    fs = fresh_fs();
    fs.fail_write = 1;
    assert(vh_atomic_write(&OPS, &fs, "card.bin", payload,
                           sizeof(payload)) == 0);
    expect_failure_preserves_destination(&fs);

    fs = fresh_fs();
    fs.fail_flush = 1;
    assert(vh_atomic_write(&OPS, &fs, "card.bin", payload,
                           sizeof(payload)) == 0);
    expect_failure_preserves_destination(&fs);
    assert(fs.flushed == 1 && fs.replaced == 0);

    fs = fresh_fs();
    fs.fail_close = 1;
    assert(vh_atomic_write(&OPS, &fs, "card.bin", payload,
                           sizeof(payload)) == 0);
    expect_failure_preserves_destination(&fs);
    assert(fs.replaced == 0);

    fs = fresh_fs();
    fs.fail_replace = 1;
    assert(vh_atomic_write(&OPS, &fs, "card.bin", payload,
                           sizeof(payload)) == 0);
    expect_failure_preserves_destination(&fs);
    assert(fs.replaced == 1);

    fs = fresh_fs();
    incomplete_ops.replace = NULL;
    assert(vh_atomic_write(&incomplete_ops, &fs, "card.bin", payload,
                           sizeof(payload)) == 0);
    assert(fs.opened == 0 && fs.destination_value == 7);

    assert(vh_atomic_write(NULL, NULL, "card.bin", payload,
                           sizeof(payload)) == 0);
    assert(vh_atomic_write(&OPS, &fs, "", payload, sizeof(payload)) == 0);
    assert(vh_atomic_write(&OPS, &fs, "card.bin", NULL, 1) == 0);

    puts("atomic write orchestration tests: PASS");
    return 0;
}
