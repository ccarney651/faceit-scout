# tools/replay_bot/console/hotkey.ps1
# A global pause/resume key for the console's supervised loop (§14.3b) -
# fires even while Overwatch is focused, because that is where you are when you
# want to use it.
#
#   powershell -ExecutionPolicy Bypass -File console/hotkey.ps1
#   powershell -ExecutionPolicy Bypass -File console/hotkey.ps1 -Modifiers Ctrl+Shift -Key F9
#
# Default Ctrl+Alt+P. Toggles state/loop_pause.flag by creating or deleting it -
# the same file run.js's --code-stack loop checks between maps (never mid-map),
# and the same file the console's Pause/Resume buttons write. Whichever last
# touched it wins; there is no separate "who paused it" state, on purpose - one
# flag, one meaning, three ways to flip it.
#
# A short beep on each press is the only feedback, because the point is not
# having to look at a screen: low pitch for paused, high for resumed.
#
# THIS WINDOW MUST STAY OPEN - it is the thing listening for the key. Ctrl-C
# here (or closing the window) stops LISTENING; it does not touch a loop
# already running, which keeps going unpaused until it hits its own end.

param(
  [ValidateSet('Ctrl+Alt', 'Ctrl+Shift', 'Alt+Shift', 'Ctrl+Alt+Shift')]
  [string]$Modifiers = 'Ctrl+Alt',
  [string]$Key = 'P',
  [string]$Flag = (Join-Path $PSScriptRoot '..\state\loop_pause.flag')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms

# MOD_ALT=1 MOD_CONTROL=2 MOD_SHIFT=4 MOD_NOREPEAT=0x4000 - NOREPEAT so holding
# the key does not fire a flood of toggles.
$MOD = @{
  'Ctrl+Alt'         = 0x0003
  'Ctrl+Shift'       = 0x0006
  'Alt+Shift'        = 0x0005
  'Ctrl+Alt+Shift'   = 0x0007
}
$modFlags = [uint32]($MOD[$Modifiers] -bor 0x4000)
$vk = [uint32][System.Windows.Forms.Keys]::$Key

$dir = Split-Path $Flag -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

# RegisterHotKey needs a window handle, and WM_HOTKEY only reaches WndProc - a
# console window has neither, so this is a hidden Form subclassed in C#. Same
# pattern as play_input.ps1's Add-Type block for the rest of the Win32 surface
# this project touches directly.
$sig = @'
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public class HotkeyForm : Form {
  [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);
  [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr hWnd, int id);
  const int WM_HOTKEY = 0x0312;
  const int HOTKEY_ID = 0x4F57;   // arbitrary, just needs to be ours
  string flagPath;
  uint mods, vk;
  bool registered;

  public HotkeyForm(uint mods, uint vk, string flag) {
    this.mods = mods; this.vk = vk; this.flagPath = flag;
    this.ShowInTaskbar = false;
    this.WindowState = FormWindowState.Minimized;
    this.Opacity = 0;
  }

  protected override void OnLoad(EventArgs e) {
    base.OnLoad(e);
    this.Hide();
    registered = RegisterHotKey(this.Handle, HOTKEY_ID, mods, vk);
    if (!registered) {
      Console.WriteLine("ERR could not register the hotkey - already taken by another app?");
      this.Close();
    }
  }

  protected override void WndProc(ref Message m) {
    if (m.Msg == WM_HOTKEY && m.WParam.ToInt32() == HOTKEY_ID) {
      try {
        if (System.IO.File.Exists(flagPath)) {
          System.IO.File.Delete(flagPath);
          Console.WriteLine("RESUMED  " + DateTime.Now.ToString("HH:mm:ss"));
          Console.Beep(880, 120);
        } else {
          System.IO.File.WriteAllText(flagPath, DateTime.UtcNow.ToString("o"));
          Console.WriteLine("PAUSED   " + DateTime.Now.ToString("HH:mm:ss"));
          Console.Beep(392, 220);
        }
      } catch (Exception ex) {
        Console.WriteLine("ERR " + ex.Message);
      }
    }
    base.WndProc(ref m);
  }

  protected override void OnFormClosing(FormClosingEventArgs e) {
    if (registered) UnregisterHotKey(this.Handle, HOTKEY_ID);
    base.OnFormClosing(e);
  }
}
'@
Add-Type -TypeDefinition $sig -ReferencedAssemblies System.Windows.Forms, System.Drawing

$form = New-Object HotkeyForm($modFlags, $vk, $Flag)
if ($form.IsDisposed) { exit 1 }

Write-Output "listening for $Modifiers+$Key"
Write-Output "toggles: $Flag"
Write-Output "(present = paused; this window must stay open)"

[System.Windows.Forms.Application]::Run($form)
