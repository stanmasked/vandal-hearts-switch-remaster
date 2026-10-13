#include "archive_name.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    const char *us = "BASLUS-00447VH";
    const char *jp = "BISLPM-86007VH";
    char boundary_name[257];
    size_t prefix_len;
    size_t i;

    assert(vh_archive_name_valid("BASLUS-00447VH.20261013-203000", us));
    assert(vh_archive_name_valid("BASLUS-00447VH.manual_backup-1", us));
    assert(vh_archive_name_valid("BISLPM-86007VH.20261013-203000", jp));
    assert(!vh_archive_name_valid("BISLPM-86007VH.20261013-203000", us));
    assert(!vh_archive_name_valid("BASLUS-00447VH", us));
    assert(!vh_archive_name_valid("BASLUS-00447VH.", us));
    assert(!vh_archive_name_valid("BASLUS-00447VH..backup", us));
    assert(!vh_archive_name_valid("BASLUS-00447VH.sub/file", us));
    assert(!vh_archive_name_valid("BASLUS-00447VH.sub\\\\file", us));
    assert(!vh_archive_name_valid("BASLUS-00447VH.bad name", us));
    assert(!vh_archive_name_valid("", us));
    assert(!vh_archive_name_valid("BASLUS-00447VH.backup", NULL));

    /* The 255-byte maximum is inclusive; 256 bytes must be rejected. */
    prefix_len = strlen(us);
    memcpy(boundary_name, us, prefix_len);
    boundary_name[prefix_len] = '.';
    for (i = prefix_len + 1U; i < 255U; ++i) boundary_name[i] = 'a';
    boundary_name[255] = '\0';
    assert(vh_archive_name_valid(boundary_name, us));
    boundary_name[255] = 'a';
    boundary_name[256] = '\0';
    assert(!vh_archive_name_valid(boundary_name, us));
    puts("archive name validation tests: PASS");
    return 0;
}
