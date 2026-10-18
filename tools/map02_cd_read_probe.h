/* Explicit, opt-in observer of actual original PC CdRead / LoadCdFile MAP02.
 * Only US pinned source, raw sector LBA 0x1bcc, exactly 12 sectors.
 * Collect counters, CRC32 and SHA-256, never raw game contents or stdout.
 */
#ifndef VH_MAP02_CD_READ_PROBE_H
#define VH_MAP02_CD_READ_PROBE_H
#include <stddef.h>
void vh_map02_cd_loader_claim(int cdf, int target_cdf, int lba, int sectors);
void vh_map02_cd_read_start(int lba, int sectors);
void vh_map02_cd_read_sector(int lba, const unsigned char *user2048);
void vh_map02_cd_read_finish(int lba, int sectors, const unsigned char *transferred);
void vh_map02_cd_loader_complete(int cdf, int target_cdf, int state);
int vh_map02_cd_probe_format_jsonl(char *out, size_t size);
/* Export only a completed observer's original 12-sector CRC32; never data. */
int vh_map02_cd_probe_raw_crc32(unsigned *out);
int vh_map02_cd_probe_failed(void);
#endif
