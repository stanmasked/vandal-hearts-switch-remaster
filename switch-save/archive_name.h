#ifndef VH_ARCHIVE_NAME_H
#define VH_ARCHIVE_NAME_H

/* Validate an archive basename against the active card's trusted prefix.
 * The prefix is the region-specific card ID, e.g. "BASLUS-00447VH".
 * No filesystem access is performed.
 */
int vh_archive_name_valid(const char *name, const char *active_card_prefix);

#endif
