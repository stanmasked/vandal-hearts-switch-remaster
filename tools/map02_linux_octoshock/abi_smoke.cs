using System;
using System.Runtime.InteropServices;
using System.Text;

internal static class OctoshockNative
{
    [DllImport("octoshock.dll", CallingConvention = CallingConvention.Cdecl, ExactSpelling = true)]
    internal static extern int shock_Util_DisassembleMIPS(
        uint pc, uint instruction, StringBuilder output, int outputCapacity);
}

internal static class Program
{
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
        return 0;
    }
}
