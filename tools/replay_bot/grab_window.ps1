# tools/replay_bot/grab_window.ps1
# Capture the Overwatch client area to a PNG.
#
#   powershell -ExecutionPolicy Bypass -File grab_window.ps1 -Out frame.png
#
# Prints one line on success:  OK <width> <height> <path>
# Anything else is a failure and grab.js treats it as one.
#
# Two findings from probe_grab.ps1 are baked in here, and both were invisible
# until measured on this machine:
#
#  1. SetProcessDPIAware() MUST run before any window call. Without it Windows
#     hands back virtualised coordinates - a 125%-scaled 2560x1440 display
#     reports 2048x1152 - and geometry frozen at the real size then lands every
#     crop in the wrong place. Both numbers look perfectly plausible.
#
#  2. PrintWindow with PW_RENDERFULLCONTENT (flag 2) is what works. Overwatch
#     renders through a D3D swapchain, so plain GDI capture usually returns
#     black; measured here PrintWindow gives a real image (mean luma ~55) while
#     CopyFromScreen gives ~5 whenever the window is behind anything. Only
#     PrintWindow survives occlusion, which is the whole point of a background
#     job - the machine stays usable while the bot works.

param([Parameter(Mandatory = $true)][string]$Out)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$sig = @'
using System;
using System.Runtime.InteropServices;
public class GrabWin {
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left, Top, Right, Bottom; }
}
'@
Add-Type -TypeDefinition $sig

[void][GrabWin]::SetProcessDPIAware()

# By process, not FindWindow - FindWindow(null,"Overwatch") returns zero on this
# machine despite an exact title match.
$proc = Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) {
  Write-Output 'ERR no running Overwatch process with a main window'
  exit 1
}

$hwnd = $proc.MainWindowHandle
$r = New-Object GrabWin+RECT
[void][GrabWin]::GetClientRect($hwnd, [ref]$r)
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
if ($w -le 0 -or $h -le 0) {
  Write-Output ('ERR client rect is {0}x{1}' -f $w, $h)
  exit 1
}

$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [GrabWin]::PrintWindow($hwnd, $hdc, 2)
$g.ReleaseHdc($hdc)
$g.Dispose()

if (-not $ok) {
  $bmp.Dispose()
  Write-Output 'ERR PrintWindow failed'
  exit 1
}

$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory $dir | Out-Null }
# Same rule as host.ps1: the extension chooses the encoder, and the two paths
# must not disagree about what a .bmp means.
$fmt = if ($Out -match '\.bmp$') {
  [System.Drawing.Imaging.ImageFormat]::Bmp
} else {
  [System.Drawing.Imaging.ImageFormat]::Png
}
$bmp.Save($Out, $fmt)
$bmp.Dispose()

Write-Output ('OK {0} {1} {2}' -f $w, $h, $Out)
