#include "archive_path.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    char path[128];
    const char *valid = "BASLUS-00447VH.20261013-203000";

    memset(path, 0, sizeof(path));
    assert(vh_archive_path_join(path, sizeof(path), "sdmc:/switch/vh/saves/.archive",
                                valid, "BASLUS-00447VH"));
    assert(strcmp(path, "sdmc:/switch/vh/saves/.archive/BASLUS-00447VH.20261013-203000") == 0);

    strcpy(path, "unchanged");
    assert(!vh_archive_path_join(path, sizeof(path), "sdmc:/switch/vh/saves/.archive",
                                "../BASLUS-00447VH.backup", "BASLUS-00447VH"));
    assert(strcmp(path, "unchanged") == 0);

    assert(!vh_archive_path_join(path, sizeof(path), "sdmc:/switch/vh/saves/.archive",
                                "BISLPM-86007VH.20261013-203000", "BASLUS-00447VH"));
    assert(strcmp(path, "unchanged") == 0);

    assert(!vh_archive_path_join(path, 8, "sdmc:/switch/vh/saves/.archive",
                                valid, "BASLUS-00447VH"));
    assert(strcmp(path, "unchanged") == 0);

    puts("archive path helper tests: PASS");
    return 0;
}
