# tools/replay_bot/send_keys.ps1
# Send a sequence of keys to the Overwatch window, in one process.
#
#   powershell -File send_keys.ps1 -Keys "B,X,X,X" [-NoFocus]
#
# Prints  SENT <n> keys  on success.
#
# ONE SPAWN, MANY KEYS. Starting a PowerShell process costs the better part of a
# second, and a seek can be fifty presses; sent one at a time that is forty
# seconds of doing nothing but starting processes.
#
# Focus is taken because it has to be. PostMessage, SendMessage and
# AttachThreadInput were all measured against an unfocused Overwatch on this rig
# and none of them delivered - the viewer reads the message queue, but only
# while it is foreground. That is why this job runs overnight rather than in the
# background, and why focus is taken ONCE here for a whole batch instead of per
# key.

param(
  [Parameter(Mandatory = $true)][string]$Keys,
  [switch]$NoFocus,
  [int]$GapMs = 45
)

$ErrorActionPreference = 'Stop'

$sig = @'
using System;
using System.Runtime.InteropServices;
public class Keys {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
Add-Type -TypeDefinition $sig

$VK = @{
  'SPACE' = 0x20; 'HOME' = 0x24; 'ESC' = 0x1B; 'ENTER' = 0x0D;
  'B' = 0x42; 'C' = 0x43; 'K' = 0x4B; 'N' = 0x4E; 'X' = 0x58; 'Z' = 0x5A
}

$seq = $Keys.Split(',') | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }
foreach ($k in $seq) {
  if (-not $VK.ContainsKey($k)) { Write-Output "ERR unknown key $k"; exit 1 }
}

$proc = Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) { Write-Output 'ERR no Overwatch window'; exit 1 }

if (-not $NoFocus) {
  [void][Keys]::SetForegroundWindow($proc.MainWindowHandle)
  Start-Sleep -Milliseconds 220
  if ([Keys]::GetForegroundWindow() -ne $proc.MainWindowHandle) {
    Write-Output 'ERR could not foreground Overwatch'
    exit 1
  }
}

foreach ($k in $seq) {
  $vk = $VK[$k]
  $scan = [byte][Keys]::MapVirtualKey([uint32]$vk, 0)
  [Keys]::keybd_event([byte]$vk, $scan, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 30
  [Keys]::keybd_event([byte]$vk, $scan, 2, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds $GapMs
}

Write-Output ("SENT {0} keys" -f $seq.Count)
