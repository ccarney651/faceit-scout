# tools/replay_bot/play_input.ps1
# Replay a recorded chunk into the Overwatch window.
#
#   powershell -ExecutionPolicy Bypass -File play_input.ps1 -Plan plan.json
#
# Prints one line on success:  PLAYED <n> events
#
# The plan is what recorder.js resolved: SCREEN coordinates, this replay's code
# already substituted for the placeholder, and the waits already clamped. This
# script decides nothing - it moves the pointer, presses, and types. Every
# judgement worth testing was made in Node.
#
# FOCUS IS TAKEN, for the same measured reason send_keys.ps1 takes it: nothing
# reaches an unfocused client. A click still moves the pointer without focus,
# which is worse than failing - it would land on whatever is in front.
#
# The plan comes in through a file rather than an argument, again like
# send_keys.ps1: a path is one token with nothing in it for Node's quoting and
# PowerShell's -File re-parsing to disagree about.

param(
  [Parameter(Mandatory = $true)][string]$Plan,
  [switch]$NoFocus,
  # Walk the plan and do everything except touch the machine: no pointer, no
  # keys, no clipboard. Every cast, lookup and binding still runs, so a plan
  # that dry-runs clean is a plan that will not fall over halfway through a
  # sequence with the mouse already somewhere in a menu.
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$sig = @'
using System;
using System.Runtime.InteropServices;
public class PlayWin {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  // `data` is a DWORD in the Win32 header, but it carries a SIGNED wheel delta
  // (-120 for one notch down). Declared int because the marshalled width is
  // identical and PowerShell refuses to cast a negative number to uint32.
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, int data, UIntPtr extra);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
  [DllImport("user32.dll")] public static extern short VkKeyScan(char ch);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
Add-Type -TypeDefinition $sig

[void][PlayWin]::SetProcessDPIAware()

# Named keys the recorder can emit. Single characters go through VkKeyScan
# instead, so the code's letters and digits need no table.
#
# $NAMED, and the locals below are $code and $vkey - NOT $vk. PowerShell
# variable names are case-insensitive, so a `$vk = $VK[$k]` overwrites the very
# table it read from, and the failure surfaces one iteration later as "cannot
# index into a null array". That cost an evening once already.
$NAMED = @{
  'BACK' = 0x08; 'TAB' = 0x09; 'ENTER' = 0x0D; 'ESC' = 0x1B; 'SPACE' = 0x20
}

$MOUSE = @{
  'left'  = @{ down = 0x0002; up = 0x0004 }
  'right' = @{ down = 0x0008; up = 0x0010 }
}

$WHEEL = 0x0800
$WHEEL_DELTA = 120
$SHIFT = 0x10
$CTRL = 0x11
$ALT = 0x12
$KEYUP = 2
$MODKEY = @{ 'shift' = $SHIFT; 'ctrl' = $CTRL; 'alt' = $ALT }
$VK_V = 0x56

if (-not (Test-Path $Plan)) { Write-Output "ERR no plan file $Plan"; exit 1 }

# ConvertFrom-Json hands a JSON array back as ONE object in Windows PowerShell
# 5.1, so piping it into @() wraps it again and $events ends up holding a single
# element that is the whole array. The loop below then runs once with $e as the
# array, and $e.waitMs member-enumerates into five values - which is where
# "Cannot convert System.Object[] to System.Int32" came from, with the mouse
# fortunately still untouched.
#
# Reading the file in one string and forcing enumeration keeps each event an
# event.
$parsed = ConvertFrom-Json ([System.IO.File]::ReadAllText($Plan))
$events = @()
foreach ($item in $parsed) { $events += $item }
if ($events.Count -eq 0) { Write-Output 'ERR plan is empty'; exit 1 }

$proc = Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc -and -not $DryRun) { Write-Output 'ERR no Overwatch window'; exit 1 }

if (-not $NoFocus -and -not $DryRun) {
  [void][PlayWin]::SetForegroundWindow($proc.MainWindowHandle)
  Start-Sleep -Milliseconds 220
  if ([PlayWin]::GetForegroundWindow() -ne $proc.MainWindowHandle) {
    Write-Output 'ERR could not foreground Overwatch'
    exit 1
  }
}

# $mods is a list of virtual-key codes to hold down around the press - shift
# for a capital, ctrl for a paste. They go down before and up after, in the
# order any human would.
function Send-Key([int]$code, [int]$holdMs, $mods) {
  if ($script:DryRun) {
    Write-Output ("WOULD key vk=0x{0:X2} hold={1} mods={2}" -f $code, $holdMs, ($mods -join '+'))
    return
  }
  $scan = [byte][PlayWin]::MapVirtualKey([uint32]$code, 0)
  foreach ($m in $mods) { [PlayWin]::keybd_event([byte]$m, 0, 0, [UIntPtr]::Zero) }
  if ($mods.Count -gt 0) { Start-Sleep -Milliseconds 30 }
  [PlayWin]::keybd_event([byte]$code, $scan, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds ([Math]::Max(20, $holdMs))
  [PlayWin]::keybd_event([byte]$code, $scan, $KEYUP, [UIntPtr]::Zero)
  foreach ($m in $mods) { [PlayWin]::keybd_event([byte]$m, 0, $KEYUP, [UIntPtr]::Zero) }
  Start-Sleep -Milliseconds 30
}

$played = 0
foreach ($e in $events) {
  # Every failure in here gets a LINE NUMBER. The last one arrived as a bare
  # "Cannot convert System.Object[] to System.Int32" with nothing to point at,
  # and this project has already lost an evening to an error with no line.
  try {
    if ([int]$e.waitMs -gt 0 -and -not $DryRun) { Start-Sleep -Milliseconds ([int]$e.waitMs) }

    switch ($e.type) {
    'click' {
      $flags = $MOUSE[[string]$e.button]
      if (-not $flags) { Write-Output ("ERR unknown button {0}" -f $e.button); exit 1 }
      if ($DryRun) {
        Write-Output ("WOULD click {0} at {1},{2} hold={3}" -f $e.button, [int]$e.x, [int]$e.y, [int]$e.holdMs)
      } else {
        [void][PlayWin]::SetCursorPos([int]$e.x, [int]$e.y)
        # The pointer has to arrive before it presses: menus light a button on
        # hover, and a click delivered in the same instant can be eaten.
        Start-Sleep -Milliseconds 60
        [PlayWin]::mouse_event([uint32]$flags.down, 0, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds ([Math]::Max(30, [int]$e.holdMs))
        [PlayWin]::mouse_event([uint32]$flags.up, 0, 0, 0, [UIntPtr]::Zero)
      }
      $played++
    }
    'drag' {
      # A press that moved. Replayed as press, follow the path, release - not as
      # a click at the start, which is what a scrollbar drag used to become and
      # why it did nothing at all.
      $flags = $MOUSE[[string]$e.button]
      if (-not $flags) { Write-Output ("ERR unknown button {0}" -f $e.button); exit 1 }
      if ($DryRun) {
        Write-Output ("WOULD drag {0} from {1},{2} to {3},{4} via {5} points" -f
          $e.button, [int]$e.x, [int]$e.y, [int]$e.toX, [int]$e.toY, @($e.path).Count)
      } else {
        [void][PlayWin]::SetCursorPos([int]$e.x, [int]$e.y)
        Start-Sleep -Milliseconds 60
        [PlayWin]::mouse_event([uint32]$flags.down, 0, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 40
        foreach ($pt in @($e.path)) {
          [void][PlayWin]::SetCursorPos([int]$pt.x, [int]$pt.y)
          Start-Sleep -Milliseconds 25
        }
        [void][PlayWin]::SetCursorPos([int]$e.toX, [int]$e.toY)
        # Dwell at the final position before releasing: the client's scrubber
        # lags a fast drag, and a 60ms settle let it release while the playhead
        # was still catching up (probe_drag: a long drag landed 100s short).
        Start-Sleep -Milliseconds 150
        [PlayWin]::mouse_event([uint32]$flags.up, 0, 0, 0, [UIntPtr]::Zero)
      }
      $played++
    }
    'scroll' {
      # One notch at a time, with a gap: menus treat a wheel as discrete steps,
      # and a single giant delta is not the same gesture as turning a wheel.
      $notches = [int]$e.notches
      if ($DryRun) {
        Write-Output ("WOULD scroll {0} notches at {1},{2}" -f $notches, [int]$e.x, [int]$e.y)
      } else {
        [void][PlayWin]::SetCursorPos([int]$e.x, [int]$e.y)
        Start-Sleep -Milliseconds 60
        $step = $WHEEL_DELTA
        if ($notches -lt 0) { $step = -$WHEEL_DELTA }
        for ($i = 0; $i -lt [Math]::Abs($notches); $i++) {
          [PlayWin]::mouse_event([uint32]$WHEEL, 0, 0, [int]$step, [UIntPtr]::Zero)
          Start-Sleep -Milliseconds 40
        }
      }
      $played++
    }
    'key' {
      $name = [string]$e.key
      $hold = @()
      foreach ($m in @($e.mods)) {
        if (-not $m) { continue }
        if (-not $MODKEY.ContainsKey([string]$m)) { Write-Output ("ERR unknown modifier {0}" -f $m); exit 1 }
        $hold += $MODKEY[[string]$m]
      }
      # The recorded virtual-key code wins where there is one: it is what the
      # machine actually saw, and it covers keys no name table here knows -
      # arrows, page up, anything the operator reaches for in a menu.
      if ($null -ne $e.vk) {
        Send-Key ([int]$e.vk) ([int]$e.holdMs) $hold
      } elseif ($NAMED.ContainsKey($name)) {
        Send-Key $NAMED[$name] ([int]$e.holdMs) $hold
      } elseif ($name.Length -eq 1) {
        $scanned = [PlayWin]::VkKeyScan([char]$name)
        if ($scanned -eq -1) { Write-Output ("ERR unmappable key {0}" -f $name); exit 1 }
        if ((($scanned -shr 8) -band 1) -ne 0 -and $hold -notcontains $SHIFT) { $hold += $SHIFT }
        Send-Key ($scanned -band 0xFF) ([int]$e.holdMs) $hold
      } else {
        Write-Output ("ERR unknown key {0}" -f $name)
        exit 1
      }
      $played++
    }
    'text' {
      foreach ($ch in [char[]][string]$e.value) {
        $scanned = [PlayWin]::VkKeyScan($ch)
        if ($scanned -eq -1) { Write-Output ("ERR unmappable character {0}" -f $ch); exit 1 }
        $shifted = @()
        if ((($scanned -shr 8) -band 1) -ne 0) { $shifted += $SHIFT }
        Send-Key ($scanned -band 0xFF) 40 $shifted
      }
      $played++
    }
    'paste' {
      # THE CLIPBOARD IS THE BOT'S TO SET. The operator's own flow is to copy a
      # code before importing, and this does the same thing for it - so a chunk
      # plays correctly on its own, with nothing to remember to copy first.
      #
      # Set-Clipboard then Ctrl+V, rather than typing the six characters: the
      # client accepted a paste when the chunk was recorded, and one clipboard
      # write cannot half-land the way six keystrokes can.
      $value = [string]$e.value
      if (-not $value) { Write-Output 'ERR paste with no value'; exit 1 }
      if ($DryRun) {
        Write-Output ("WOULD set clipboard to {0} and press Ctrl+V" -f $value)
      } else {
        Set-Clipboard -Value $value
        Start-Sleep -Milliseconds 120
      }
      Send-Key $VK_V ([Math]::Max(40, [int]$e.holdMs)) @($CTRL)
      $played++
    }
    default {
      Write-Output ("ERR unknown event type {0}" -f $e.type)
      exit 1
    }
    }
  } catch {
    Write-Output ("ERR event {0} ({1}) failed at line {2}: {3}" -f
      $played, $e.type, $_.InvocationInfo.ScriptLineNumber, $_.Exception.Message)
    exit 1
  }
}

Write-Output ("PLAYED {0} events" -f $played)
