#include "archive_path.h"

#include "archive_name.h"
#include "checked_path.h"

int vh_archive_path_join(char *out, size_t out_size, const char *root,
                         const char *archive_name,
                         const char *active_card_prefix)
{
    if (!vh_archive_name_valid(archive_name, active_card_prefix)) {
        return 0;
    }

    return vh_checked_path_join(out, out_size, root, archive_name);
}
