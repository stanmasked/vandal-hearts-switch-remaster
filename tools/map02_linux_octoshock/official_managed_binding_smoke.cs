using System;
using System.Text;
using BizHawk.Emulation.Cores.Sony.PSX;

// Calls the pinned official BizHawk 2.11 managed binding, not a duplicate
// P/Invoke declaration. Only synthetic zero-filled firmware is allocated;
// this test never powers on the PSX core or opens a disc/movie.
internal static class OfficialBizHawkOctoshockBindingSmoke
{
    private const int SyntheticFirmwareSize = 512 * 1024;
    private const int ShockNoCanDo = -2;

    private static int Main()
    {
        var output = new StringBuilder(256);
        int result = OctoshockDll.shock_Util_DisassembleMIPS(0, 0, output, output.Capacity);
        if (result != 0 || output.Length == 0)
        {
            Console.Error.WriteLine("official BizHawk disassembler binding failed");
            return 1;
        }
        Console.WriteLine("VH_MAP02_OFFICIAL_MANAGED_P_INVOKE_PASS symbol=shock_Util_DisassembleMIPS result=0");

        var firmware = new byte[SyntheticFirmwareSize];
        IntPtr psx = IntPtr.Zero;
        bool created = false;
        try
        {
            unsafe
            {
                fixed (byte* pFirmware = firmware)
                {
                    result = OctoshockDll.shock_Create(
                        out psx, OctoshockDll.eRegion.NA, pFirmware);
                }
            }
            if (result != 0)
            {
                Console.Error.WriteLine("official BizHawk shock_Create binding failed");
                return 2;
            }
            created = true;
            if (psx != IntPtr.Zero)
            {
                Console.Error.WriteLine("unexpected Octoshock singleton pointer contract");
                return 3;
            }

            var options = new OctoshockDll.ShockRenderOptions
            {
                scanline_start = 0,
                scanline_end = 240,
                renderType = (OctoshockDll.eShockRenderType)0,
                deinterlaceMode = (OctoshockDll.eShockDeinterlaceMode)0,
                skip = false
            };
            result = OctoshockDll.shock_SetRenderOptions(psx, ref options);
            if (result != 0)
            {
                Console.Error.WriteLine("official BizHawk shock_SetRenderOptions binding failed");
                return 4;
            }

            result = OctoshockDll.shock_Destroy(psx);
            if (result != 0)
            {
                Console.Error.WriteLine("official BizHawk shock_Destroy binding failed");
                return 5;
            }
            created = false;

            result = OctoshockDll.shock_Destroy(psx);
            if (result != ShockNoCanDo)
            {
                Console.Error.WriteLine("official BizHawk duplicate-destroy guard changed");
                return 6;
            }
            Console.WriteLine(
                "VH_MAP02_OFFICIAL_MANAGED_LIFECYCLE_PASS create=0 render_options=0 destroy=0 "
                + "destroy_guard=-2 synthetic_zero_firmware_bytes=524288 power_on=0 disc=0 frames=0");
            return 0;
        }
        finally
        {
            if (created)
            {
                try { OctoshockDll.shock_Destroy(psx); }
                catch { /* preserve the primary failure */ }
            }
        }
    }
}
