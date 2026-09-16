# tools/replay_bot/probe_grab.ps1
# Find out, empirically, whether this machine will hand us pixels from the
# Overwatch window - and by which method.
#
# PrintWindow classically returns solid black for Direct3D content, because the
# game renders through a swapchain rather than GDI. PW_RENDERFULLCONTENT (flag
# 2) fixes that for many DX apps and not for others; which camp Overwatch is in
# is a fact about this machine, not something to reason about from first
# principles. So: try both, save both, and look.
#
#   powershell -ExecutionPolicy Bypass -File tools/replay_bot/probe_grab.ps1
#
# Writes probe-printwindow.png and probe-bitblt.png into frames/, and reports
# the window rect plus how dark each result came out. A near-zero mean means
# that method produced black and is unusable.

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$sig = @'
using System;
using System.Runtime.InteropServices;
public class Win {
  [DllImport("user32.dll", SetLastError=true)]
  public static extern IntPtr FindWindow(string cls, string name);
  [DllImport("user32.dll")]
  public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")]
  public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")]
  public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")]
  public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)]
  public struct POINT { public int X, Y; }
}
'@
Add-Type -TypeDefinition $sig

# MUST come before any window or GDI call. Without it Windows hands a
# non-DPI-aware process VIRTUALISED coordinates: on a 125%-scaled 2560x1440
# display the client rect reads 2048x1152, and a capture at that size against
# geometry frozen at 2560x1440 puts every crop in the wrong place. The numbers
# look entirely reasonable either way, which is what makes it dangerous.
[void][Win]::SetProcessDPIAware()

# Located by PROCESS, not by FindWindow. FindWindow(null, "Overwatch") returns
# zero here even though the title matches exactly, and chasing why is wasted
# effort when the process already hands us the handle.
$proc = Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) {
  Write-Output 'NOT FOUND: no running Overwatch process with a main window'
  exit 1
}
$hwnd = $proc.MainWindowHandle
Write-Output ("title     : '{0}'" -f $proc.MainWindowTitle)

$r = New-Object Win+RECT
[void][Win]::GetClientRect($hwnd, [ref]$r)
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top

$org = New-Object Win+POINT
$org.X = 0; $org.Y = 0
[void][Win]::ClientToScreen($hwnd, [ref]$org)

Write-Output ("hwnd      : {0}" -f $hwnd)
Write-Output ("visible   : {0}" -f [Win]::IsWindowVisible($hwnd))
Write-Output ("client    : {0}x{1}" -f $w, $h)
Write-Output ("screen at : {0},{1}" -f $org.X, $org.Y)

$dir = Join-Path $PSScriptRoot 'frames'
if (-not (Test-Path $dir)) { New-Item -ItemType Directory $dir | Out-Null }

# Mean luminance of a sample grid. Black output means the method failed, and
# that is the whole question this probe exists to answer.
function Get-Mean($bmp) {
  $sum = 0.0; $n = 0
  for ($y = 0; $y -lt $bmp.Height; $y += 40) {
    for ($x = 0; $x -lt $bmp.Width; $x += 40) {
      $c = $bmp.GetPixel($x, $y)
      $sum += (0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B); $n++
    }
  }
  if ($n -eq 0) { return 0 }
  return [math]::Round($sum / $n, 2)
}

# 1. PrintWindow with PW_RENDERFULLCONTENT - works even when occluded, if it
#    works at all.
$bmp1 = New-Object System.Drawing.Bitmap $w, $h
$g1 = [System.Drawing.Graphics]::FromImage($bmp1)
$hdc = $g1.GetHdc()
$okPW = [Win]::PrintWindow($hwnd, $hdc, 2)
$g1.ReleaseHdc($hdc)
$g1.Dispose()
$p1 = Join-Path $dir 'probe-printwindow.png'
$bmp1.Save($p1, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output ("PrintWindow returned {0}, mean luma {1} -> {2}" -f $okPW, (Get-Mean $bmp1), $p1)
$bmp1.Dispose()

# 2. BitBlt from the screen at the window's rect - reliable for D3D, but only
#    captures what is actually on screen, so it breaks under occlusion.
$bmp2 = New-Object System.Drawing.Bitmap $w, $h
$g2 = [System.Drawing.Graphics]::FromImage($bmp2)
$g2.CopyFromScreen($org.X, $org.Y, 0, 0, (New-Object System.Drawing.Size $w, $h))
$g2.Dispose()
$p2 = Join-Path $dir 'probe-bitblt.png'
$bmp2.Save($p2, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output ("CopyFromScreen mean luma {0} -> {1}" -f (Get-Mean $bmp2), $p2)
$bmp2.Dispose()
