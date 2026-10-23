using System;
using System.Runtime.InteropServices;
using System.Text;

internal static class OctoshockNative
{
    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_Util_DisassembleMIPS(
        uint pc, uint instruction, StringBuilder output, int outputCapacity);

    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_Create(out IntPtr psx, int region, IntPtr firmware512k);

    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_Destroy(IntPtr psx);
}

internal static class Program
{
    private const int SyntheticFirmwareSize = 512 * 1024;

    private static int Main()
    {
        // A pure disassembly helper: no PSX instance, BIOS, disc, save, or movie is opened.
        var output = new StringBuilder(256);
        int result = OctoshockNative.shock_Util_DisassembleMIPS(0, 0, output, output.Capacity);
        if (result != 0)
        {
            Console.Error.WriteLine("Octoshock disassembler returned " + result);
            return 1;
        }
        if (output.Length == 0)
        {
            Console.Error.WriteLine("Octoshock disassembler returned an empty string");
            return 2;
        }
        Console.WriteLine("VH_MAP02_MONO_P_INVOKE_PASS symbol=shock_Util_DisassembleMIPS result=0 output=" + output);

        // Exercise only native allocation and teardown with a zero-filled synthetic
        // 512 KiB firmware buffer. Do not power on, mount a disc, or run CPU frames.
        IntPtr firmware = Marshal.AllocHGlobal(SyntheticFirmwareSize);
        bool created = false;
        IntPtr psx = IntPtr.Zero;
        try
        {
            var zeroFirmware = new byte[SyntheticFirmwareSize];
            Marshal.Copy(zeroFirmware, 0, firmware, zeroFirmware.Length);
            result = OctoshockNative.shock_Create(out psx, 1 /* NA */, firmware);
            if (result != 0)
            {
                Console.Error.WriteLine("Octoshock synthetic shock_Create returned " + result);
                return 3;
            }
            created = true;

            result = OctoshockNative.shock_Destroy(psx);
            if (result != 0)
            {
                Console.Error.WriteLine("Octoshock synthetic shock_Destroy returned " + result);
                return 4;
            }
            created = false;
            Console.WriteLine("VH_MAP02_MONO_LIFECYCLE_PASS create=0 destroy=0 firmware=synthetic-zero-filled bytes=524288 power_on=0 disc=0 frames=0");
            return 0;
        }
        finally
        {
            if (created)
            {
                try { OctoshockNative.shock_Destroy(psx); }
                catch { /* preserve the original smoke-test failure */ }
            }
            Marshal.FreeHGlobal(firmware);
        }
    }
}
