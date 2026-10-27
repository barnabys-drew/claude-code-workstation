# Windows side of the Stream Deck plugin (Windows PowerShell 5.1): media
# controls, raising a window to the front, and window screenshots.
#
# Reads commands on stdin, one per line:
#   toggle        play/pause the browser's media session
#   next / prev   skip to the next or previous track
#   vol <delta>   change the browser's mixer volume, e.g. "vol 5" or "vol -5"
#   raise <proc>  bring that process's main window to the front, e.g. "raise wezterm-gui"
#   shot          screenshot the foreground window to the clipboard and Pictures\Screenshots
#   refresh       re-emit the current state
# Writes one JSON object per line on stdout whenever the state changes:
#   {"status":"playing","title":..,"artist":..,"volume":42,"muted":false}
# and, after a shot, {"shot":"C:\\...\\window-....png"} or {"shot":null,"error":..}.
#
# "The browser" is whichever process owns the Windows media session (Chrome
# for YouTube Music); volume changes only that app's slider in the mixer.
param([string]$App = 'chrome')

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class AppVolume {
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}

    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceEnumerator {
        int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
        int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
    }
    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDevice {
        int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
    }
    [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionManager2 {
        int GetAudioSessionControl(IntPtr a, int b, out IntPtr c);
        int GetSimpleAudioVolume(IntPtr a, int b, out IntPtr c);
        int GetSessionEnumerator(out IAudioSessionEnumerator sessions);
    }
    [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionEnumerator {
        int GetCount(out int count);
        int GetSession(int index, out IAudioSessionControl2 session);
    }
    [ComImport, Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionControl2 {
        // IAudioSessionControl
        int GetState(out int state);
        int GetDisplayName(out IntPtr name);
        int SetDisplayName(IntPtr name, IntPtr ctx);
        int GetIconPath(out IntPtr path);
        int SetIconPath(IntPtr path, IntPtr ctx);
        int GetGroupingParam(out Guid param);
        int SetGroupingParam(ref Guid param, IntPtr ctx);
        int RegisterAudioSessionNotification(IntPtr n);
        int UnregisterAudioSessionNotification(IntPtr n);
        // IAudioSessionControl2
        int GetSessionIdentifier(out IntPtr id);
        int GetSessionInstanceIdentifier(out IntPtr id);
        int GetProcessId(out uint pid);
    }
    [ComImport, Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISimpleAudioVolume {
        int SetMasterVolume(float level, ref Guid ctx);
        int GetMasterVolume(out float level);
        int SetMute(bool mute, ref Guid ctx);
        int GetMute(out bool mute);
    }

    static System.Collections.Generic.List<ISimpleAudioVolume> Sessions(string process) {
        var found = new System.Collections.Generic.List<ISimpleAudioVolume>();
        var en = (IMMDeviceEnumerator)new MMDeviceEnumerator();
        IMMDevice dev;
        Marshal.ThrowExceptionForHR(en.GetDefaultAudioEndpoint(0, 1, out dev)); // eRender, eMultimedia
        var iid = typeof(IAudioSessionManager2).GUID;
        object o;
        Marshal.ThrowExceptionForHR(dev.Activate(ref iid, 23, IntPtr.Zero, out o)); // CLSCTX_ALL
        IAudioSessionEnumerator sessions;
        Marshal.ThrowExceptionForHR(((IAudioSessionManager2)o).GetSessionEnumerator(out sessions));
        int n; sessions.GetCount(out n);
        for (int i = 0; i < n; i++) {
            IAudioSessionControl2 s; sessions.GetSession(i, out s);
            uint pid; s.GetProcessId(out pid);
            if (pid == 0) continue;
            try {
                if (string.Equals(System.Diagnostics.Process.GetProcessById((int)pid).ProcessName, process,
                                  StringComparison.OrdinalIgnoreCase))
                    found.Add((ISimpleAudioVolume)s);
            } catch (ArgumentException) { } // process exited
        }
        return found;
    }

    // Returns the app's volume 0-100 after applying delta, or -1 if it has no audio session.
    public static int Change(string process, int delta) {
        var list = Sessions(process);
        if (list.Count == 0) return -1;
        float cur; list[0].GetMasterVolume(out cur);
        float next = Math.Max(0f, Math.Min(1f, (float)Math.Round(cur * 100 + delta) / 100f));
        var ctx = Guid.Empty;
        if (delta != 0) foreach (var v in list) { v.SetMasterVolume(next, ref ctx); if (delta > 0) v.SetMute(false, ref ctx); }
        return (int)Math.Round(next * 100);
    }

    public static bool Muted(string process) {
        var list = Sessions(process);
        if (list.Count == 0) return false;
        bool m; list[0].GetMute(out m); return m;
    }
}

public static class Window {
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);

    public static bool Raise(string process) {
        foreach (var p in System.Diagnostics.Process.GetProcessesByName(process)) {
            var h = p.MainWindowHandle;
            if (h == IntPtr.Zero) continue;
            if (IsIconic(h)) ShowWindow(h, 9); // SW_RESTORE
            // Windows only lets the foreground app hand focus away; a synthetic Alt
            // tap counts as user input and lifts that lock for this call.
            keybd_event(0x12, 0, 0, UIntPtr.Zero);
            bool ok = SetForegroundWindow(h);
            keybd_event(0x12, 0, 2, UIntPtr.Zero);
            return ok;
        }
        return false;
    }
}

public static class Shot {
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);

    // Saves the foreground window as a PNG and puts it on the clipboard; returns the path.
    public static string Window(string dir) {
        // Per-monitor DPI aware, or the bounds come back scaled on a 125%/150% display.
        SetProcessDpiAwarenessContext(new IntPtr(-4));
        var h = GetForegroundWindow();
        if (h == IntPtr.Zero) throw new InvalidOperationException("no foreground window");
        RECT r;
        // The extended frame is the visible window, without the invisible resize border and shadow.
        Marshal.ThrowExceptionForHR(DwmGetWindowAttribute(h, 9, out r, Marshal.SizeOf(typeof(RECT))));
        int w = r.Right - r.Left, ht = r.Bottom - r.Top;
        if (w <= 0 || ht <= 0) throw new InvalidOperationException("window has no size");
        using (var bmp = new System.Drawing.Bitmap(w, ht)) {
            using (var g = System.Drawing.Graphics.FromImage(bmp))
                g.CopyFromScreen(r.Left, r.Top, 0, 0, bmp.Size);
            System.IO.Directory.CreateDirectory(dir);
            var file = System.IO.Path.Combine(dir, "window-" + DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss") + ".png");
            bmp.Save(file, System.Drawing.Imaging.ImageFormat.Png);
            // copy=true keeps the image on the clipboard independent of this process.
            System.Windows.Forms.Clipboard.SetDataObject(new System.Drawing.Bitmap(bmp), true);
            return file;
        }
    }
}
'@ -ReferencedAssemblies System.Drawing, System.Windows.Forms

# WinRT plumbing: PowerShell 5.1 can't await, so wrap IAsyncOperation in a Task.
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op, [Type]$type) {
    $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result
}
$null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
$manager = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) `
    ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])

function Get-Session {
    $all = $manager.GetSessions()
    $mine = $all | Where-Object { $_.SourceAppUserModelId -like "*$App*" } | Select-Object -First 1
    if ($mine) { $mine } else { $null }
}

# No album art: PowerShell 5.1 can't read the thumbnail stream, and a compiled
# helper can't reach the media service at all. The key shows the title instead.
$last = $null
function Emit([bool]$force) {
    $s = Get-Session
    $state = [ordered]@{ status = 'none'; title = $null; artist = $null; volume = -1; muted = $false }
    if ($s) {
        $props = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
        $state.status = $s.GetPlaybackInfo().PlaybackStatus.ToString().ToLower()
        $state.title = $props.Title; $state.artist = $props.Artist
    }
    $state.volume = [AppVolume]::Change($App, 0)
    $state.muted = [AppVolume]::Muted($App)
    $json = $state | ConvertTo-Json -Compress
    if ($force -or $json -ne $script:last) { [Console]::Out.WriteLine($json); [Console]::Out.Flush(); $script:last = $json }
}

$shotDir = Join-Path ([Environment]::GetFolderPath('MyPictures')) 'Screenshots'

# Not [Console]::In: its ReadLineAsync is synchronous under the hood, so the
# loop blocked until a command arrived and never polled. A StreamReader over
# the raw stream reads on a pool thread.
$stdin = New-Object IO.StreamReader([Console]::OpenStandardInput(), [Text.Encoding]::UTF8)
$pending = $stdin.ReadLineAsync()
$nextPoll = [DateTime]::MinValue
while ($true) {
    if ($pending.IsCompleted) {
        $line = $pending.Result
        if ($null -eq $line) { break } # plugin went away
        $parts = $line.Trim() -split '\s+'
        try {
            switch ($parts[0]) {
                'toggle' { $s = Get-Session; if ($s) { Await ($s.TryTogglePlayPauseAsync()) ([bool]) | Out-Null; Start-Sleep -Milliseconds 150 } }
                'next' { $s = Get-Session; if ($s) { Await ($s.TrySkipNextAsync()) ([bool]) | Out-Null; Start-Sleep -Milliseconds 300 } }
                'prev' { $s = Get-Session; if ($s) { Await ($s.TrySkipPreviousAsync()) ([bool]) | Out-Null; Start-Sleep -Milliseconds 300 } }
                'vol' { [AppVolume]::Change($App, [int]$parts[1]) | Out-Null }
                'raise' { [Window]::Raise($parts[1]) | Out-Null }
                'shot' {
                    try { $out = @{ shot = [Shot]::Window($shotDir) } } catch { $out = @{ shot = $null; error = "$_" } }
                    [Console]::Out.WriteLine(($out | ConvertTo-Json -Compress)); [Console]::Out.Flush()
                }
            }
            Emit ($parts[0] -eq 'refresh')
        } catch { [Console]::Error.WriteLine("media bridge: $_") }
        $pending = $stdin.ReadLineAsync()
    }
    if ([DateTime]::Now -ge $nextPoll) {
        try { Emit $false } catch { [Console]::Error.WriteLine("media bridge: $_") }
        $nextPoll = [DateTime]::Now.AddSeconds(1)
    }
    Start-Sleep -Milliseconds 50
}
