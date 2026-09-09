# tools/replay_bot/window_rect.ps1
# Where the Overwatch client area is on screen, right now.
#
#   powershell -ExecutionPolicy Bypass -File window_rect.ps1
#
# Prints one line:  OK <originX> <originY> <width> <height>
#
# The origin is what makes recorded clicks survive a moved window: chunks store
# client-relative coordinates, and this is the offset that puts them back on
# screen. The size is the guard - a chunk recorded in a differently sized client
# area is refused rather than scaled.
#
# SetProcessDPIAware() FIRST, for the same reason as grab_window.ps1: without
# it a 125%-scaled 2560x1440 display reports 2048x1152, and every coordinate
# derived from that is wrong by a quarter while looking entirely plausible.

$ErrorActionPreference = 'Stop'

$sig = @'
using System;
using System.Runtime.InteropServices;
public class RectWin {
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)]
  public struct POINT { public int X, Y; }
}
'@
Add-Type -TypeDefinition $sig

[void][RectWin]::SetProcessDPIAware()

# By process, not FindWindow - FindWindow(null,"Overwatch") returns zero on this
# machine despite an exact title match.
$proc = Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) {
  Write-Output 'ERR no running Overwatch process with a main window'
  exit 1
}

$hwnd = $proc.MainWindowHandle
$r = New-Object RectWin+RECT
[void][RectWin]::GetClientRect($hwnd, [ref]$r)
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
if ($w -le 0 -or $h -le 0) {
  Write-Output ('ERR client rect is {0}x{1}' -f $w, $h)
  exit 1
}

$origin = New-Object RectWin+POINT
$origin.X = 0
$origin.Y = 0
if (-not [RectWin]::ClientToScreen($hwnd, [ref]$origin)) {
  Write-Output 'ERR ClientToScreen failed'
  exit 1
}

Write-Output ('OK {0} {1} {2} {3}' -f $origin.X, $origin.Y, $w, $h)
