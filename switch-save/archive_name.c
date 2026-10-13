#include "archive_name.h"

#include <stddef.h>
#include <string.h>

enum { VH_ARCHIVE_NAME_MAX = 255 };

static int allowed(unsigned char c)
{
    return (c >= 'a' && c <= 'z') ||
           (c >= 'A' && c <= 'Z') ||
           (c >= '0' && c <= '9') ||
           c == '.' || c == '-' || c == '_';
}

int vh_archive_name_valid(const char *name, const char *active_card_prefix)
{
    const unsigned char *p;
    size_t name_len;
    size_t prefix_len;

    if (name == NULL || active_card_prefix == NULL ||
        active_card_prefix[0] == '\0') {
        return 0;
    }

    name_len = strlen(name);
    prefix_len = strlen(active_card_prefix);
    if (name_len == 0U || name_len > VH_ARCHIVE_NAME_MAX ||
        prefix_len == 0U || name_len <= prefix_len + 1U ||
        strncmp(name, active_card_prefix, prefix_len) != 0 ||
        name[prefix_len] != '.' || strstr(name, "..") != NULL) {
        return 0;
    }

    for (p = (const unsigned char *)name; *p != '\0'; ++p) {
        if (!allowed(*p)) {
            return 0;
        }
    }

    return 1;
}
