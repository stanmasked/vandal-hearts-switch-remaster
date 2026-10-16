/* v66 optional hooks on pinned notaz/pcsx_rearmed GPU MMIO/DMA2 paths.
 * Disabled unless compiled with VH_MAP02_V66_PCSX_PROBE; see v66 audit.
 * These observe host-side *pre-submit* memory, NOT confirmed GPU output.
 */
#ifndef VH66_GPU_PROBE_BRIDGE_H
#define VH66_GPU_PROBE_BRIDGE_H
#include <stdint.h>
int vh68_pcsx_gp0_mmio_observe(uint32_t word);
int vh66_pcsx_gp1_observe(uint32_t word);
int vh66_pcsx_dma2_observe(const unsigned char *psx_ram_2mb, uint32_t head);
#endif
