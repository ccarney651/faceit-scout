# tools/replay_bot/probe_input.ps1
# Send one key to the Overwatch window and report which method was used.
#
#   powershell -File probe_input.ps1 -Key SPACE -Method Post
#
# Two methods, and the difference decides whether this can be a background job:
#
#   Post  - PostMessage WM_KEYDOWN/WM_KEYUP straight to the window handle. Needs
#           NO focus, so the machine stays usable. Many games ignore it because
#           they read RawInput rather than the message queue; a replay viewer is
#           UI rather than gameplay, so it may well not.
#   Input - SendInput, the standard path. Goes to whatever has focus, so the
#           window must be foregrounded first and the machine is then occupied.
#
# Prints SENT <method> <key> on success. Whether the game ACTED on it is not
# something this script can know - the caller compares frames before and after.

param(
  [Parameter(Mandatory = $true)][string]$Key,
  [ValidateSet('Post', 'Input', 'Send', 'Attach')][string]$Method = 'Post'
)

$ErrorActionPreference = 'Stop'

$sig = @'
using System;
using System.Runtime.InteropServices;
public class Inp {
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint from, uint to, bool attach);
  [DllImport("user32.dll")] public static extern IntPtr SetFocus(IntPtr h);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
}
'@
Add-Type -TypeDefinition $sig

$VK = @{ 'SPACE' = 0x20; 'X' = 0x58; 'Z' = 0x5A; 'N' = 0x4E; 'K' = 0x4B; 'B' = 0x42; 'HOME' = 0x24 }
if (-not $VK.ContainsKey($Key)) { Write-Output "ERR unknown key $Key"; exit 1 }
$vk = $VK[$Key]

$proc = Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) { Write-Output 'ERR no Overwatch window'; exit 1 }
$hwnd = $proc.MainWindowHandle

$WM_KEYDOWN = 0x0100
$WM_KEYUP = 0x0101

if ($Method -eq 'Post') {
  # lParam encodes repeat count and scan code. Some apps check it, so build it
  # properly rather than passing zero and hoping.
  $scan = [Inp]::MapVirtualKey([uint32]$vk, 0)
  $down = [IntPtr](1 -bor ($scan -shl 16))
  $up = [IntPtr](1 -bor ($scan -shl 16) -bor (1 -shl 30) -bor (1 -shl 31))
  [void][Inp]::PostMessage($hwnd, $WM_KEYDOWN, [IntPtr]$vk, $down)
  Start-Sleep -Milliseconds 60
  [void][Inp]::PostMessage($hwnd, $WM_KEYUP, [IntPtr]$vk, $up)
}
elseif ($Method -eq 'Send') {
  # Synchronous delivery. Same message, but processed inline by the target's
  # window procedure rather than queued, which some apps handle differently.
  $scan = [Inp]::MapVirtualKey([uint32]$vk, 0)
  $down = [IntPtr](1 -bor ($scan -shl 16))
  $up = [IntPtr](1 -bor ($scan -shl 16) -bor (1 -shl 30) -bor (1 -shl 31))
  [void][Inp]::SendMessage($hwnd, $WM_KEYDOWN, [IntPtr]$vk, $down)
  Start-Sleep -Milliseconds 60
  [void][Inp]::SendMessage($hwnd, $WM_KEYUP, [IntPtr]$vk, $up)
}
elseif ($Method -eq 'Attach') {
  # Attach our input thread to the game's, so from the game's point of view the
  # keyboard focus state is shared with us. This is the technique that could
  # preserve background operation: it can let SetFocus and posted keys land
  # without ever foregrounding the window and stealing the desktop.
  $target = [Inp]::GetWindowThreadProcessId($hwnd, [IntPtr]::Zero)
  $me = [Inp]::GetCurrentThreadId()
  $attached = [Inp]::AttachThreadInput($me, $target, $true)
  try {
    [void][Inp]::SetFocus($hwnd)
    $scan = [Inp]::MapVirtualKey([uint32]$vk, 0)
    $down = [IntPtr](1 -bor ($scan -shl 16))
    $up = [IntPtr](1 -bor ($scan -shl 16) -bor (1 -shl 30) -bor (1 -shl 31))
    [void][Inp]::PostMessage($hwnd, $WM_KEYDOWN, [IntPtr]$vk, $down)
    Start-Sleep -Milliseconds 60
    [void][Inp]::PostMessage($hwnd, $WM_KEYUP, [IntPtr]$vk, $up)
  }
  finally {
    if ($attached) { [void][Inp]::AttachThreadInput($me, $target, $false) }
  }
  Write-Output ("ATTACHED {0}" -f $attached)
}
else {
  [void][Inp]::SetForegroundWindow($hwnd)
  Start-Sleep -Milliseconds 250
  $scan = [byte][Inp]::MapVirtualKey([uint32]$vk, 0)
  [Inp]::keybd_event([byte]$vk, $scan, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 60
  [Inp]::keybd_event([byte]$vk, $scan, 2, [UIntPtr]::Zero)
}

Write-Output ("SENT {0} {1}" -f $Method, $Key)

# Appended: report which window actually had focus when the key was sent, so a
# "Post worked" result can never again be confounded by the game happening to be
# foregrounded. Without this the probe cannot tell PostMessage-without-focus
# from PostMessage-that-did-not-need-to-be.
$fg = [Inp]::GetForegroundWindow()
$fgProc = (Get-Process | Where-Object { $_.MainWindowHandle -eq $fg } | Select-Object -First 1)
$fgName = if ($fgProc) { $fgProc.ProcessName } else { 'unknown' }
Write-Output ("FOREGROUND {0} (ow={1})" -f $fgName, ($fg -eq $hwnd))
