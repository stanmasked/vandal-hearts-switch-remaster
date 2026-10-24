using System;
using System.Runtime.InteropServices;
using System.Text;

internal static class OctoshockNative
{
    [StructLayout(LayoutKind.Sequential)]
    internal struct ShockRenderOptions
    {
        public int scanline_start;
        public int scanline_end;
        public int renderType;
        public int deinterlaceMode;
        [MarshalAs(UnmanagedType.I1)]
        public bool skip;
    }

    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_Util_DisassembleMIPS(
        uint pc, uint instruction, StringBuilder output, int outputCapacity);

    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_Create(out IntPtr psx, int region, IntPtr firmware512k);

    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_SetRenderOptions(IntPtr psx, ref ShockRenderOptions options);

    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_Destroy(IntPtr psx);
}

internal static class Program
{
    private const int SyntheticFirmwareSize = 512 * 1024;
    private const int ShockNoCanDo = -2;

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

        // Check the managed layout for the render-options structure used by the
        // official Octoshock binding. The native struct is four 32-bit fields,
        // followed by a one-byte bool and three bytes of alignment padding.
        int optionsSize = Marshal.SizeOf(typeof(OctoshockNative.ShockRenderOptions));
        int skipOffset = Marshal.OffsetOf(
            typeof(OctoshockNative.ShockRenderOptions), "skip").ToInt32();
        if (optionsSize != 20 || skipOffset != 16)
        {
            Console.Error.WriteLine("Unexpected render-options layout size=" + optionsSize
                + " skip_offset=" + skipOffset);
            return 3;
        }

        // Exercise native allocation and teardown with a zero-filled synthetic
        // 512 KiB firmware buffer. Never power on, mount a disc, or run CPU frames.
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
                return 4;
            }
            created = true;
            // The pinned upstream implementation is singleton-based and explicitly
            // writes NULL to *psx. Keep this unusual but real contract under test.
            if (psx != IntPtr.Zero)
            {
                Console.Error.WriteLine("Octoshock shock_Create returned a non-null instance pointer");
                return 5;
            }

            var options = new OctoshockNative.ShockRenderOptions
            {
                scanline_start = 0,
                scanline_end = 240,
                renderType = 0,      // Normal
                deinterlaceMode = 0, // Weave
                skip = false
            };
            result = OctoshockNative.shock_SetRenderOptions(psx, ref options);
            if (result != 0)
            {
                Console.Error.WriteLine("Octoshock synthetic shock_SetRenderOptions returned " + result);
                return 6;
            }
            Console.WriteLine("VH_MAP02_MONO_RENDER_OPTIONS_PASS size=" + optionsSize
                + " skip_offset=" + skipOffset + " result=0");

            result = OctoshockNative.shock_Destroy(psx);
            if (result != 0)
            {
                Console.Error.WriteLine("Octoshock synthetic shock_Destroy returned " + result);
                return 7;
            }
            created = false;

            // The pinned core explicitly rejects destroy when no instance exists.
            // This checks its failure guard without dereferencing the stale handle.
            result = OctoshockNative.shock_Destroy(psx);
            if (result != ShockNoCanDo)
            {
                Console.Error.WriteLine("Octoshock duplicate destroy guard returned " + result);
                return 8;
            }

            Console.WriteLine("VH_MAP02_MONO_LIFECYCLE_PASS create=0 instance_pointer=null render_options=0 destroy=0 "
                + "destroy_guard=-2 firmware=synthetic-zero-filled bytes=524288 "
                + "power_on=0 disc=0 frames=0");
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
