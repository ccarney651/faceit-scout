# tools/replay_bot/host.ps1
# One long-lived PowerShell that does the grabs and the key sends.
#
#   powershell -File host.ps1        then feed it commands on stdin
#
# Prints READY once, then one contract line per command:
#
#   GRAB <path>            -> OK <w> <h> <path>
#   KEYS <keyfile> <gapMs> -> SENT <n> keys
#   RECT                   -> OK <originX> <originY> <w> <h>
#   PING                   -> PONG
#   QUIT                   -> exits
#
# WHY THIS EXISTS: measured on the rig, a bare PowerShell spawn is 211ms, one
# that runs Add-Type is 341ms, and a whole window grab is 497ms. So more than
# two thirds of every capture was process startup, paid about twenty times a
# map. Starting once and keeping the process turns a 497ms grab into roughly
# 150ms of actual work.
#
# The three implementations here are the same Win32 calls the standalone
# scripts use, and the standalone scripts stay: they are what the probes run,
# and what still works if this host cannot start. Both paths were measured
# against the same client, and grab.js/input.js fall back to the scripts
# automatically.
#
# Two things that are not optional, both learned the hard way:
#
#   - SetProcessDPIAware() before any window call, or a 125%-scaled 2560x1440
#     display reports 2048x1152 and every crop lands in the wrong place.
#   - PrintWindow with PW_RENDERFULLCONTENT (flag 2), which reads the window
#     while it is covered; a screen copy returns black the moment anything
#     overlaps it.

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$sig = @'
using System;
using System.Runtime.InteropServices;
public class HostWin {
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)]
  public struct POINT { public int X, Y; }
}
'@
Add-Type -TypeDefinition $sig

[void][HostWin]::SetProcessDPIAware()

$KEYS = @{
  'SPACE' = 0x20; 'HOME' = 0x24; 'ESC' = 0x1B; 'ENTER' = 0x0D;
  'B' = 0x42; 'C' = 0x43; 'K' = 0x4B; 'N' = 0x4E; 'X' = 0x58; 'Z' = 0x5A
}

function Get-Overwatch {
  Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
}

function Do-Grab([string]$outPath) {
  $proc = Get-Overwatch
  if (-not $proc) { return 'ERR no running Overwatch process with a main window' }

  $hwnd = $proc.MainWindowHandle
  $r = New-Object HostWin+RECT
  [void][HostWin]::GetClientRect($hwnd, [ref]$r)
  $w = $r.Right - $r.Left
  $h = $r.Bottom - $r.Top
  if ($w -le 0 -or $h -le 0) { return ('ERR client rect is {0}x{1}' -f $w, $h) }

  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  $ok = [HostWin]::PrintWindow($hwnd, $hdc, 2)
  $g.ReleaseHdc($hdc)
  $g.Dispose()
  if (-not $ok) { $bmp.Dispose(); return 'ERR PrintWindow failed' }

  $dir = Split-Path -Parent $outPath
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory $dir | Out-Null }
  $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  return ('OK {0} {1} {2}' -f $w, $h, $outPath)
}

function Do-Keys([string]$keyFile, [int]$gapMs) {
  if (-not (Test-Path $keyFile)) { return "ERR no key file $keyFile" }
  $seq = Get-Content $keyFile | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }
  if (-not $seq) { return 'ERR key file is empty' }
  foreach ($k in $seq) {
    if (-not $KEYS.ContainsKey($k)) { return "ERR unknown key $k" }
  }

  $proc = Get-Overwatch
  if (-not $proc) { return 'ERR no Overwatch window' }

  # Keys only land in a foreground client - measured, with PostMessage,
  # SendMessage and AttachThreadInput all failing against an unfocused one.
  if ([HostWin]::GetForegroundWindow() -ne $proc.MainWindowHandle) {
    [void][HostWin]::SetForegroundWindow($proc.MainWindowHandle)
    Start-Sleep -Milliseconds 200
    if ([HostWin]::GetForegroundWindow() -ne $proc.MainWindowHandle) {
      return 'ERR could not foreground Overwatch'
    }
  }

  # $code, NOT $vk: PowerShell variable names are case-insensitive, so $vk would
  # overwrite a $VK lookup table with the integer it had just read from it.
  foreach ($k in $seq) {
    $code = $KEYS[$k]
    $scan = [byte][HostWin]::MapVirtualKey([uint32]$code, 0)
    [HostWin]::keybd_event([byte]$code, $scan, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 30
    [HostWin]::keybd_event([byte]$code, $scan, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds $gapMs
  }
  return ('SENT {0} keys' -f $seq.Count)
}

function Do-Rect {
  $proc = Get-Overwatch
  if (-not $proc) { return 'ERR no running Overwatch process with a main window' }
  $hwnd = $proc.MainWindowHandle
  $r = New-Object HostWin+RECT
  [void][HostWin]::GetClientRect($hwnd, [ref]$r)
  $w = $r.Right - $r.Left
  $h = $r.Bottom - $r.Top
  if ($w -le 0 -or $h -le 0) { return ('ERR client rect is {0}x{1}' -f $w, $h) }
  $origin = New-Object HostWin+POINT
  $origin.X = 0
  $origin.Y = 0
  if (-not [HostWin]::ClientToScreen($hwnd, [ref]$origin)) { return 'ERR ClientToScreen failed' }
  return ('OK {0} {1} {2} {3}' -f $origin.X, $origin.Y, $w, $h)
}

Write-Output 'READY'
[Console]::Out.Flush()

while ($true) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { break }        # stdin closed - the caller went away
  $line = $line.Trim()
  if (-not $line) { continue }

  $verb = ($line -split ' ', 2)[0].ToUpper()
  $rest = if ($line -match '^\S+\s+(.*)$') { $Matches[1] } else { '' }

  try {
    switch ($verb) {
      'GRAB' { $out = Do-Grab $rest }
      'KEYS' {
        # "<path> <gapMs>" - the gap is the last token, so a path with spaces
        # in it survives.
        $gap = 700
        $file = $rest
        if ($rest -match '^(.*)\s+(\d+)$') { $file = $Matches[1]; $gap = [int]$Matches[2] }
        $out = Do-Keys $file $gap
      }
      'RECT' { $out = Do-Rect }
      'PING' { $out = 'PONG' }
      'QUIT' { break }
      default { $out = "ERR unknown command $verb" }
    }
  } catch {
    $out = 'ERR ' + $_.Exception.Message
  }

  if ($verb -eq 'QUIT') { break }
  Write-Output $out
  [Console]::Out.Flush()
}
