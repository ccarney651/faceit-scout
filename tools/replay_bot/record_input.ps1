# tools/replay_bot/record_input.ps1
# Record what the operator does in the Overwatch window, as JSON lines.
#
#   powershell -ExecutionPolicy Bypass -File record_input.ps1 -Out raw.jsonl
#
# Prints one line at the end:  RECORDED <n> events <path>
#
# Each line is one input event, in SCREEN coordinates and milliseconds from the
# start of the recording:
#
#   {"t":1234,"type":"down","button":"left","x":900,"y":540}
#   {"t":1250,"type":"move","x":902,"y":560}
#   {"t":1290,"type":"up","button":"left","x":902,"y":700}
#   {"t":2100,"type":"wheel","x":800,"y":400,"delta":-120}
#   {"t":3000,"type":"keydown","key":"DOWN","vk":40,"mods":""}
#
# recorder.js turns those into clicks, drags, scrolls and keypresses. Nothing is
# decided here - this only reports what it saw, because a decision made in
# PowerShell is a decision with no unit test behind it.
#
# HOOKED, NOT POLLED, and the first version was polled. Polling GetAsyncKeyState
# over a list of interesting keys cannot see the mouse wheel at all, records a
# drag as a click where it started, and misses any key that was not on the list
# - which cost three failed attempts at recording one options menu: the wheel
# was invisible, then dragging the scrollbar was invisible, then the arrow keys
# were too. A low-level hook sees everything the machine sees.
#
# ONLY WHILE OVERWATCH IS FOREGROUND. Recording starts from a terminal, so the
# first thing the operator does is alt-tab into the game, and the clicks that
# get them there belong to the desktop rather than to the chunk.

param(
  [Parameter(Mandatory = $true)][string]$Out,
  [int]$MaxSeconds = 120
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms

$sig = @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;

public class Rec {
  public delegate IntPtr HookProc(int nCode, IntPtr wParam, IntPtr lParam);

  [DllImport("user32.dll", SetLastError = true)]
  public static extern IntPtr SetWindowsHookEx(int idHook, HookProc lpfn, IntPtr hMod, uint threadId);
  [DllImport("user32.dll")] public static extern bool UnhookWindowsHookEx(IntPtr hhk);
  [DllImport("user32.dll")] public static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);
  [DllImport("kernel32.dll")] public static extern IntPtr GetModuleHandle(string name);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vKey);

  [StructLayout(LayoutKind.Sequential)]
  public struct POINT { public int x; public int y; }

  [StructLayout(LayoutKind.Sequential)]
  public struct MSLLHOOKSTRUCT {
    public POINT pt; public uint mouseData; public uint flags; public uint time; public IntPtr extra;
  }

  [StructLayout(LayoutKind.Sequential)]
  public struct KBDLLHOOKSTRUCT {
    public uint vkCode; public uint scanCode; public uint flags; public uint time; public IntPtr extra;
  }

  const int WH_KEYBOARD_LL = 13, WH_MOUSE_LL = 14;
  const int WM_KEYDOWN = 0x0100, WM_KEYUP = 0x0101, WM_SYSKEYDOWN = 0x0104, WM_SYSKEYUP = 0x0105;
  const int WM_MOUSEMOVE = 0x0200, WM_LBUTTONDOWN = 0x0201, WM_LBUTTONUP = 0x0202;
  const int WM_RBUTTONDOWN = 0x0204, WM_RBUTTONUP = 0x0205, WM_MOUSEWHEEL = 0x020A;
  const int STOP_VK = 0x79;   // F10, which ends the recording and is not recorded

  // The delegates are held in static fields on purpose: passed inline they are
  // collected while Windows still holds the pointer, and the process dies
  // somewhere inside a callback that no longer exists.
  static HookProc mouseProc, keyProc;
  static IntPtr mouseHook, keyHook;
  static Stopwatch clock;
  static IntPtr target;
  static int buttonsDown;
  static int lastMoveMs = -1000;

  public static List<string> Lines = new List<string>();
  public static bool Stopped;

  static int Now() { return (int)clock.ElapsedMilliseconds; }
  static bool Ours() { return GetForegroundWindow() == target; }
  static bool Held(int vk) { return (GetAsyncKeyState(vk) & 0x8000) != 0; }

  static string Mods() {
    List<string> m = new List<string>();
    if (Held(0x11)) m.Add("ctrl");
    if (Held(0x10)) m.Add("shift");
    if (Held(0x12)) m.Add("alt");
    return string.Join(",", m.ToArray());
  }

  // Named where a name is clearer than a number; the vk travels alongside
  // regardless, so playback never has to reverse a name it does not know.
  static string KeyName(int vk) {
    switch (vk) {
      case 0x08: return "BACK";   case 0x09: return "TAB";
      case 0x0D: return "ENTER";  case 0x1B: return "ESC";
      case 0x20: return "SPACE";  case 0x25: return "LEFT";
      case 0x26: return "UP";     case 0x27: return "RIGHT";
      case 0x28: return "DOWN";   case 0x21: return "PAGEUP";
      case 0x22: return "PAGEDOWN"; case 0x23: return "END";
      case 0x24: return "HOME";   case 0x2E: return "DELETE";
    }
    if ((vk >= 0x30 && vk <= 0x39) || (vk >= 0x41 && vk <= 0x5A)) {
      return ((char)vk).ToString();
    }
    return "VK" + vk.ToString(CultureInfo.InvariantCulture);
  }

  static void Add(string json) { Lines.Add(json); }

  static IntPtr OnMouse(int nCode, IntPtr wParam, IntPtr lParam) {
    if (nCode >= 0 && Ours()) {
      MSLLHOOKSTRUCT d = (MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(MSLLHOOKSTRUCT));
      int msg = (int)wParam;
      int t = Now();

      if (msg == WM_LBUTTONDOWN || msg == WM_RBUTTONDOWN) {
        buttonsDown++;
        Add(string.Format(CultureInfo.InvariantCulture,
          "{{\"t\":{0},\"type\":\"down\",\"button\":\"{1}\",\"x\":{2},\"y\":{3}}}",
          t, msg == WM_LBUTTONDOWN ? "left" : "right", d.pt.x, d.pt.y));
      } else if (msg == WM_LBUTTONUP || msg == WM_RBUTTONUP) {
        if (buttonsDown > 0) buttonsDown--;
        Add(string.Format(CultureInfo.InvariantCulture,
          "{{\"t\":{0},\"type\":\"up\",\"button\":\"{1}\",\"x\":{2},\"y\":{3}}}",
          t, msg == WM_LBUTTONUP ? "left" : "right", d.pt.x, d.pt.y));
      } else if (msg == WM_MOUSEWHEEL) {
        short delta = (short)((d.mouseData >> 16) & 0xFFFF);
        Add(string.Format(CultureInfo.InvariantCulture,
          "{{\"t\":{0},\"type\":\"wheel\",\"x\":{1},\"y\":{2},\"delta\":{3}}}",
          t, d.pt.x, d.pt.y, delta));
      } else if (msg == WM_MOUSEMOVE && buttonsDown > 0 && t - lastMoveMs >= 15) {
        // Only while a button is held, and thinned: a drag is a path, and idle
        // pointer wandering is not an action anybody performed.
        lastMoveMs = t;
        Add(string.Format(CultureInfo.InvariantCulture,
          "{{\"t\":{0},\"type\":\"move\",\"x\":{1},\"y\":{2}}}", t, d.pt.x, d.pt.y));
      }
    }
    return CallNextHookEx(mouseHook, nCode, wParam, lParam);
  }

  static IntPtr OnKey(int nCode, IntPtr wParam, IntPtr lParam) {
    if (nCode >= 0) {
      KBDLLHOOKSTRUCT d = (KBDLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(KBDLLHOOKSTRUCT));
      int msg = (int)wParam;
      int vk = (int)d.vkCode;

      if (vk == STOP_VK) {
        if (msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN) Stopped = true;
      } else if (Ours() && vk != 0x10 && vk != 0x11 && vk != 0x12 &&
                 vk != 0xA0 && vk != 0xA1 && vk != 0xA2 && vk != 0xA3 &&
                 vk != 0xA4 && vk != 0xA5) {
        // Modifiers are recorded as the state of the keys around them, not as
        // events of their own - a chunk wants "Ctrl+V", not three keystrokes.
        string kind = (msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN) ? "keydown"
          : (msg == WM_KEYUP || msg == WM_SYSKEYUP) ? "keyup" : null;
        if (kind != null) {
          Add(string.Format(CultureInfo.InvariantCulture,
            "{{\"t\":{0},\"type\":\"{1}\",\"key\":\"{2}\",\"vk\":{3},\"mods\":\"{4}\"}}",
            Now(), kind, KeyName(vk), vk, Mods()));
        }
      }
    }
    return CallNextHookEx(keyHook, nCode, wParam, lParam);
  }

  public static void Start(IntPtr overwatch) {
    target = overwatch;
    clock = Stopwatch.StartNew();
    mouseProc = new HookProc(OnMouse);
    keyProc = new HookProc(OnKey);
    IntPtr mod = GetModuleHandle(null);
    mouseHook = SetWindowsHookEx(WH_MOUSE_LL, mouseProc, mod, 0);
    keyHook = SetWindowsHookEx(WH_KEYBOARD_LL, keyProc, mod, 0);
  }

  public static bool Installed() { return mouseHook != IntPtr.Zero && keyHook != IntPtr.Zero; }

  public static void Stop() {
    if (mouseHook != IntPtr.Zero) UnhookWindowsHookEx(mouseHook);
    if (keyHook != IntPtr.Zero) UnhookWindowsHookEx(keyHook);
    mouseHook = IntPtr.Zero;
    keyHook = IntPtr.Zero;
  }
}
'@
Add-Type -TypeDefinition $sig -ReferencedAssemblies System.Windows.Forms

$proc = Get-Process -Name 'Overwatch' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $proc) {
  Write-Output 'ERR no running Overwatch process with a main window'
  exit 1
}

[Rec]::Start($proc.MainWindowHandle)
if (-not [Rec]::Installed()) {
  Write-Output 'ERR could not install the input hooks'
  exit 1
}

# Low-level hooks only fire while the installing thread pumps messages, so this
# loop is not a poll - it is what makes the callbacks run at all.
$deadline = (Get-Date).AddSeconds($MaxSeconds)
while (-not [Rec]::Stopped -and (Get-Date) -lt $deadline) {
  [System.Windows.Forms.Application]::DoEvents()
  Start-Sleep -Milliseconds 5
}
[Rec]::Stop()

$lines = @([Rec]::Lines)

# NOT Set-Content -Encoding utf8: in Windows PowerShell 5.1 that writes a BOM,
# and the BOM lands in front of the first JSON line, where JSON.parse reports
# only "Unexpected token" and points at a character nothing can see.
$noBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($Out, $lines, $noBom)
Write-Output ('RECORDED {0} events {1}' -f $lines.Count, $Out)
