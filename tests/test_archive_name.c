#include "archive_name.h"

#include <assert.h>
#include <stdio.h>

int main(void)
{
    const char *us = "BASLUS-00447VH";
    const char *jp = "BISLPM-86007VH";

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
    puts("archive name validation tests: PASS");
    return 0;
}
