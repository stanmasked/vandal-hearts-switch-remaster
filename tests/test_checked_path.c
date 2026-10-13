#include "checked_path.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void expect_rejected(const char *root, const char *leaf)
{
    char out[128] = "unchanged";
    assert(vh_checked_path_join(out, sizeof(out), root, leaf) == 0);
    assert(strcmp(out, "unchanged") == 0);
}

int main(void)
{
    char out[128];

    assert(vh_checked_path_join(out, sizeof(out),
                                "sdmc:/switch/vh", "card.bin") == 1);
    assert(strcmp(out, "sdmc:/switch/vh/card.bin") == 0);

    assert(vh_checked_path_join(out, sizeof(out),
                                "sdmc:/switch/vh/", "card.bin") == 1);
    assert(strcmp(out, "sdmc:/switch/vh/card.bin") == 0);

    assert(vh_checked_path_join(out, sizeof(out), "/", "save.dat") == 1);
    assert(strcmp(out, "/save.dat") == 0);

    expect_rejected(NULL, "card.bin");
    expect_rejected("", "card.bin");
    expect_rejected("root", NULL);
    expect_rejected("root", "");
    expect_rejected("root", ".");
    expect_rejected("root", "..");
    expect_rejected("root", "../outside");
    expect_rejected("root", "sub/card.bin");
    expect_rejected("root", "sub\\\\card.bin");
    expect_rejected("root", "line\nbreak");

    {
        char tiny[4] = "xyz";
        assert(vh_checked_path_join(tiny, sizeof(tiny), "root", "card") == 0);
        assert(strcmp(tiny, "xyz") == 0);
    }
    assert(vh_checked_path_join(NULL, 1, "root", "card") == 0);
    assert(vh_checked_path_join(out, 0, "root", "card") == 0);

    /* The output must not overwrite the root string while joining. */
    {
        char aliased_root[64] = "sdmc:/switch/vh";
        assert(vh_checked_path_join(aliased_root, sizeof(aliased_root),
                                    aliased_root, "card.bin") == 0);
        assert(strcmp(aliased_root, "sdmc:/switch/vh") == 0);
    }

    /* Nor may the output overwrite the leaf before it has been copied. */
    {
        char aliased_leaf[64] = "card.bin";
        assert(vh_checked_path_join(aliased_leaf, sizeof(aliased_leaf),
                                    "sdmc:/switch/vh", aliased_leaf) == 0);
        assert(strcmp(aliased_leaf, "card.bin") == 0);
    }

    puts("checked path tests: PASS");
    return 0;
}
