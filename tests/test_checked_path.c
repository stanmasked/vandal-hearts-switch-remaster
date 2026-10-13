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

    puts("checked path tests: PASS");
    return 0;
}
