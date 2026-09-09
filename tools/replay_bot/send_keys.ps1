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

# The key sequence comes from a file rather than an argument. That started as a
# workaround for a misdiagnosis (see below) but is kept because a path is one
# token with nothing in it for Node's quoting and PowerShell's -File re-parsing
# to disagree about, and a long seek can be fifty keys.
param(
  [Parameter(Mandatory = $true)][string]$KeyFile,
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

if (-not (Test-Path $KeyFile)) { Write-Output "ERR no key file $KeyFile"; exit 1 }
$seq = Get-Content $KeyFile | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }
if (-not $seq) { Write-Output 'ERR key file is empty'; exit 1 }
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

# $code, NOT $vk. POWERSHELL VARIABLE NAMES ARE CASE-INSENSITIVE, so `$vk` and
# the `$VK` lookup table above are ONE VARIABLE. Writing `$vk = $VK[$k]` here
# overwrote the table with the integer it had just read: the first key sent
# fine, and every run of two or more keys died on the second iteration trying
# to index an integer, reporting only "Cannot index into a null array" with no
# hint at the cause. Three unrelated theories about argument separators were
# tried and discarded before anyone read the line number.
foreach ($k in $seq) {
  $code = $VK[$k]
  $scan = [byte][Keys]::MapVirtualKey([uint32]$code, 0)
  [Keys]::keybd_event([byte]$code, $scan, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 30
  [Keys]::keybd_event([byte]$code, $scan, 2, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds $GapMs
}

Write-Output ("SENT {0} keys" -f $seq.Count)
