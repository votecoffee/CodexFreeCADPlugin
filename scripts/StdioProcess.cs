// Root CMD convenience launcher. Codex's published route starts pythonw directly.
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class FreeCADStdioProcess
{
    [StructLayout(LayoutKind.Sequential)]
    struct Startup
    {
        public uint cb;
        public IntPtr reserved, desktop, title;
        public uint x, y, width, height, charsX, charsY, fill, flags;
        public ushort show, reservedBytes;
        public IntPtr reservedData, input, output, error;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct ProcessInfo { public IntPtr process, thread; public uint pid, tid; }

    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int id);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool DuplicateHandle(IntPtr sourceProcess, IntPtr source, IntPtr targetProcess,
        out IntPtr target, uint access, bool inherit, uint options);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessW(string application, StringBuilder command, IntPtr processAttributes,
        IntPtr threadAttributes, bool inherit, uint flags, IntPtr environment, string cwd,
        ref Startup startup, out ProcessInfo process);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetExitCodeProcess(IntPtr process, out uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);

    static IntPtr WireHandle(int id)
    {
        IntPtr original = GetStdHandle(id), copy;
        if (original == IntPtr.Zero || original == new IntPtr(-1))
            throw new InvalidOperationException("Run.cmd requires inherited stdin, stdout and stderr handles.");
        if (!DuplicateHandle(GetCurrentProcess(), original, GetCurrentProcess(), out copy, 0, true, 2))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        return copy;
    }

    public static int Run(string application, string arguments, string cwd)
    {
        Startup startup = new Startup();
        startup.cb = (uint)Marshal.SizeOf(typeof(Startup));
        startup.flags = 0x100; // STARTF_USESTDHANDLES: GUI pythonw otherwise loses the wire.
        ProcessInfo child = new ProcessInfo();
        try
        {
            startup.input = WireHandle(-10);
            startup.output = WireHandle(-11);
            startup.error = WireHandle(-12);
            StringBuilder command = new StringBuilder("\"" + application + "\" " + arguments);
            if (!CreateProcessW(application, command, IntPtr.Zero, IntPtr.Zero, true, 0x08000000,
                IntPtr.Zero, cwd, ref startup, out child))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            if (WaitForSingleObject(child.process, 0xffffffff) != 0)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            uint code;
            if (!GetExitCodeProcess(child.process, out code))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            return unchecked((int)code);
        }
        finally
        {
            foreach (IntPtr handle in new IntPtr[] { child.thread, child.process,
                startup.input, startup.output, startup.error })
                if (handle != IntPtr.Zero) CloseHandle(handle);
        }
    }
}
