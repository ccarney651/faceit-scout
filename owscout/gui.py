"""A simple desktop app wrapping the owscout workflow (build step: usability).

Non-techy teammates never touch the CLI: they click **Calibrate**, load the
hero-gallery image once, pick a code, and start hotkey capture; **Publish** writes
the dashboard sync file. Everything the CLI does, behind buttons.

Tkinter (bundled with Python, no extra install) so this packages to a single
``.exe`` with PyInstaller. All heavy work runs on worker threads; progress is
funnelled through a queue and drained on the Tk main loop, so the window never
freezes and no Tk call happens off-thread. Runtime-only — not unit-tested.
"""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from .db import Database


def _base_dir() -> str:
    """A stable folder for owscout's data, independent of where the app is
    launched from — so calibration and refs persist between sessions. Prefer
    $OWSCOUT_HOME, else the repo dir (the parent of the owscout package)."""
    home = os.getenv("OWSCOUT_HOME")
    if home:
        return home
    return str(Path(__file__).resolve().parent.parent)


def _default_db() -> str:
    return os.getenv("OWSCOUT_DB") or os.path.join(_base_dir(), "owscout.sqlite3")


def _default_faceit() -> str:
    return os.getenv("FACEIT_DB") or os.path.join(_base_dir(), "faceit.sqlite3")


class _App:  # pragma: no cover - GUI runtime only
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.q: "queue.Queue[Callable[[], Any]]" = queue.Queue()
        self.busy = False

        self.root = tk.Tk()
        self.root.title("owscout — OW2 comp scouting")
        self.root.geometry("760x620")
        self.root.minsize(640, 520)

        pad = {"padx": 10, "pady": 6}
        # --- paths ----------------------------------------------------------
        paths = ttk.LabelFrame(self.root, text="Databases")
        paths.pack(fill="x", **pad)
        self.db_var = tk.StringVar(value=_default_db())
        self.faceit_var = tk.StringVar(value=_default_faceit())
        for i, (lbl, var) in enumerate((("owscout DB", self.db_var),
                                        ("faceit DB", self.faceit_var))):
            ttk.Label(paths, text=lbl, width=11).grid(row=i, column=0, sticky="w", padx=6, pady=3)
            ttk.Entry(paths, textvariable=var).grid(row=i, column=1, sticky="ew", padx=6, pady=3)
        paths.columnconfigure(1, weight=1)

        # --- 1. setup -------------------------------------------------------
        setup = ttk.LabelFrame(self.root, text="1. One-time setup")
        setup.pack(fill="x", **pad)
        ttk.Button(setup, text="Calibrate (drag ROI boxes)",
                   command=self._calibrate).grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.sheet_btn = ttk.Button(setup, text="Build hero library (load gallery)…",
                                    command=self._load_sheet)
        self.sheet_btn.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        ttk.Button(setup, text="Check refs",
                   command=self._verify_refs).grid(row=0, column=2, padx=6, pady=6, sticky="w")
        self.setup_status = ttk.Label(setup, text="", foreground="#555")
        self.setup_status.grid(row=1, column=0, columnspan=3, padx=6, sticky="w")
        # Accuracy upgrade: teach the tool the real in-game HUD portraits.
        ttk.Separator(setup, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=(8, 4))
        ttk.Label(setup, text="Best accuracy — teach owscout your in-game portraits:",
                  foreground="#333").grid(row=3, column=0, columnspan=3, padx=6, sticky="w")
        self.learn_btn = ttk.Button(setup, text="⭐ Learn heroes from a replay…",
                                    command=self._open_learn)
        self.learn_btn.grid(row=4, column=0, columnspan=2, padx=6, pady=(2, 8), sticky="w")
        ttk.Button(setup, text="➕ Add new hero",
                   command=self._add_hero).grid(row=4, column=2, padx=6, pady=(2, 8), sticky="w")

        # --- 2. capture -----------------------------------------------------
        cap = ttk.LabelFrame(self.root, text="2. Capture a replay (Master division)")
        cap.pack(fill="x", **pad)
        ttk.Label(cap, text="Code").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.code_var = tk.StringVar()
        self.code_box = ttk.Combobox(cap, textvariable=self.code_var, width=34, state="readonly")
        self.code_box.grid(row=0, column=1, padx=6, pady=4, sticky="ew")
        self.code_box.bind("<<ComboboxSelected>>", lambda _e: self._on_code_selected())
        ttk.Button(cap, text="↻", width=3, command=self._refresh_codes).grid(row=0, column=2, padx=2)
        ttk.Button(cap, text="Copy code", command=self._copy_code).grid(row=0, column=3, padx=2)
        # Left team: pick by clicking whichever team is on the LEFT of the HUD.
        ttk.Label(cap, text="Left team").grid(row=1, column=0, padx=6, pady=4, sticky="nw")
        self.side_a_var = tk.StringVar()
        self.team_frame = ttk.Frame(cap)
        self.team_frame.grid(row=1, column=1, columnspan=3, padx=6, pady=4, sticky="w")
        self.roster_lbl = ttk.Label(cap, text="(pick a code to see the teams)",
                                    foreground="#555", justify="left")
        self.roster_lbl.grid(row=2, column=1, columnspan=3, padx=6, pady=2, sticky="w")
        ttk.Label(cap, text="Hotkey").grid(row=3, column=0, padx=6, pady=4, sticky="w")
        self.hotkey_var = tk.StringVar(value="f8")
        ttk.Entry(cap, textvariable=self.hotkey_var, width=8).grid(row=3, column=1, padx=6, pady=4, sticky="w")
        self.cap_btn = ttk.Button(cap, text="Start hotkey capture", command=self._capture)
        self.cap_btn.grid(row=4, column=1, padx=6, pady=6, sticky="w")
        cap.columnconfigure(1, weight=1)

        # --- 3. review + publish -------------------------------------------
        pub = ttk.LabelFrame(self.root, text="3. Review, then publish")
        pub.pack(fill="x", **pad)
        ttk.Button(pub, text="📋 Review captured maps…",
                   command=self._open_review).grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ttk.Button(pub, text="Export finalized comps → owscout_comps.json",
                   command=self._publish).grid(row=0, column=1, padx=6, pady=6, sticky="w")
        ttk.Label(pub, text="Captures are drafts until you review + finalize them; "
                            "only finalized maps are exported.",
                  foreground="#555").grid(row=1, column=0, columnspan=2, padx=6, sticky="w")

        # --- log ------------------------------------------------------------
        logf = ttk.LabelFrame(self.root, text="Log")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=10, wrap="word", state="disabled",
                           bg="#111", fg="#ddd", font=("Consolas", 9))
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

        self._stop_capture: Optional[Callable[[], None]] = None
        self.root.after(80, self._drain)
        self._refresh_codes()
        self._verify_refs()

    # --- infra --------------------------------------------------------------

    def _emit(self, msg: str) -> None:
        """Thread-safe log write (queued, applied on the main loop)."""
        self.q.put(lambda: self._write(msg))

    def _write(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain(self) -> None:
        # One failing UI callback must never kill the drain loop — otherwise every
        # later queued update (status, previews, logs) silently stops and the app
        # looks frozen. Catch per-callback, and always reschedule via finally.
        try:
            while True:
                cb = self.q.get_nowait()
                try:
                    cb()
                except Exception as exc:  # noqa: BLE001
                    self._write(f"ui error: {exc}")
        except queue.Empty:
            pass
        finally:
            self.root.after(80, self._drain)

    def _run(self, fn: Callable[[], None], *, lock: bool = True) -> None:
        if lock and self.busy:
            self._emit("busy — wait for the current task to finish.")
            return

        def worker() -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 - surface any failure to the log
                self._emit(f"error: {exc}")
            finally:
                if lock:
                    self.busy = False
                    self.q.put(lambda: self.cap_btn.configure(state="normal"))

        if lock:
            self.busy = True
        threading.Thread(target=worker, daemon=True).start()

    def _open_db(self) -> Database:
        return Database(self.db_var.get())

    # --- actions ------------------------------------------------------------

    def _calibrate(self) -> None:
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Recalibrate ROI boxes?",
            "This starts a NEW calibration and DETACHES every hero you've learned "
            "from the current profile — you'd have to learn them all again.\n\n"
            "You only need this once, or after a HUD/resolution change. Continue?",
            icon="warning", default="no", parent=self.root):
            self._emit("calibrate: cancelled (your learned heroes are untouched).")
            return
        from .calibrate import default_frame_dir, run_calibration
        for msg in (
            "CALIBRATE — first get an Overwatch observer/replay view on screen (the",
            "  bar of 10 hero portraits along the top). A screenshot window will open:",
            "  1. Drag a box tightly around the LEFT team's 5 portraits, press ENTER.",
            "  2. Drag a box around the RIGHT team's 5 portraits, press ENTER.",
            "  3. A preview shows the 5+5 slots — press any key to save (or close the",
            "     window and redo if they don't line up). That's it.",
            "  (Tip: box just the portrait row — including the names below is fine.)",
        ):
            self._emit(msg)

        def go() -> None:
            with self._open_db() as db:
                run_calibration(db, hud_variant="default", team_size=5,
                                frame_dir=default_frame_dir(self.db_var.get()))
            self._emit("calibrate: saved. You can close the calibrate window now.")
            self.q.put(self._verify_refs)
        self._run(go)

    def _load_sheet(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select the all-heroes gallery screenshot",
            filetypes=[("PNG", "*.png"), ("All", "*.*")])
        if not path:
            return
        from .refs import default_refs_dir, run_refs_from_sheet
        self._emit(f"refs: reading {os.path.basename(path)} …")

        def go() -> None:
            with self._open_db() as db:
                n = run_refs_from_sheet(db, self.faceit_var.get(), path,
                                        hud_variant="default",
                                        refs_dir=default_refs_dir(self.db_var.get()))
            self._emit(f"refs: stored {n} portraits. Verify the labeled image in refs/.")
            self.q.put(self._verify_refs)
        self._run(go)

    def _add_hero(self) -> None:
        """Register a hero not yet in faceit's roster (a new OW2 release), then
        it shows up in Learn heroes and in matching."""
        import tkinter as tk
        from tkinter import ttk, messagebox
        dlg = tk.Toplevel(self.root)
        dlg.title("Add new hero")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        frm = ttk.Frame(dlg)
        frm.pack(padx=14, pady=12)
        ttk.Label(frm, text="Hero name").grid(row=0, column=0, sticky="w", pady=4)
        name_var = tk.StringVar()
        ttk.Entry(frm, textvariable=name_var, width=24).grid(row=0, column=1, pady=4)
        ttk.Label(frm, text="Role").grid(row=1, column=0, sticky="w", pady=4)
        role_var = tk.StringVar(value="damage")
        ttk.Combobox(frm, textvariable=role_var, values=("tank", "damage", "support"),
                     state="readonly", width=21).grid(row=1, column=1, pady=4)

        def save() -> None:
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Add hero", "Enter a name.", parent=dlg)
                return
            try:
                with self._open_db() as db:
                    guid = db.add_custom_hero(name, role_var.get())
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Add hero", str(exc), parent=dlg)
                return
            self._emit(f"added hero {name} ({role_var.get()}) as {guid} — now learn its "
                       "portrait in Learn heroes.")
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(pady=(0, 12))
        ttk.Button(btns, text="Add", command=save).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="left")

    def _open_review(self) -> None:
        try:
            _ReviewWindow(self)
        except Exception as exc:  # noqa: BLE001
            self._emit(f"review: {exc}")

    def _open_learn(self) -> None:
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Open Learn heroes?",
            "Opens the hero-portrait learning tool. Your existing refs are kept — "
            "a hero only changes when you confirm/save it here.\n\n"
            "(Inside, avoid ‘Calibrate one portrait’ unless you mean to move the "
            "learn box.) Continue?",
            default="yes", parent=self.root):
            return
        try:
            _LearnWindow(self)
        except Exception as exc:  # noqa: BLE001
            self._emit(f"learn: {exc}")

    def _verify_refs(self) -> None:
        def go() -> None:
            complete = False
            try:
                with self._open_db() as db:
                    prof = db.latest_active_profile("default")
                    if prof is None:
                        txt = "Step 1: not calibrated yet — click Calibrate."
                    else:
                        have = len({r.hero_guid for r in db.get_refs(prof.id)}) if prof.id else 0
                        total = have
                        try:
                            from .faceit import connect_ro, load_heroes
                            with connect_ro(self.faceit_var.get()) as f:
                                total = len(load_heroes(f))
                        except Exception:  # noqa: BLE001
                            pass
                        complete = have > 0 and have >= total
                        res = f"{prof.resolution_w}x{prof.resolution_h}"
                        if have == 0:
                            txt = f"profile {res} · Step 2: no hero library yet — click Build hero library."
                        elif complete:
                            txt = f"profile {res} · hero library complete ({have}/{total}). Ready to capture."
                        else:
                            txt = f"profile {res} · hero library {have}/{total} — rebuild to fill gaps."
            except Exception as exc:  # noqa: BLE001
                txt = f"({exc})"
            self.q.put(lambda: self.setup_status.configure(text=txt))
            # Grey the button out once the library is complete; re-enable if a hero is missing.
            self.q.put(lambda: self.sheet_btn.configure(state="disabled" if complete else "normal"))
        self._run(go, lock=False)

    def _refresh_codes(self) -> None:
        def go() -> None:
            try:
                with self._open_db() as db:
                    rows = db.list_codes(self.faceit_var.get(), uncaptured=True, limit=40)
                items = [f"{r.demo_code}  {r.map_name}  {r.team_a} vs {r.team_b}" for r in rows]
            except Exception as exc:  # noqa: BLE001
                items = []
                self._emit(f"codes: {exc}")
            self.q.put(lambda: self.code_box.configure(values=items))
            if items:
                self.q.put(lambda: self.code_var.set(items[0]))
                self.q.put(self._on_code_selected)
        self._run(go, lock=False)

    def _on_code_selected(self) -> None:
        raw = self.code_var.get().strip()
        if not raw:
            return
        code = raw.split()[0]

        def go() -> None:
            from .context import derive_code_context
            with self._open_db() as db:
                ctx = derive_code_context(db, self.faceit_var.get(), code)
            t1, t2 = ctx.faction1_team_name, ctx.faction2_team_name
            p1 = [p.nickname or "?" for p in ctx.players if p.faction == "faction1"]
            p2 = [p.nickname or "?" for p in ctx.players if p.faction == "faction2"]
            self.q.put(lambda: self._show_teams(t1, t2, p1, p2))
        self._run(go, lock=False)

    def _show_teams(self, t1: Optional[str], t2: Optional[str],
                    p1: list[str], p2: list[str]) -> None:
        from tkinter import ttk
        for w in self.team_frame.winfo_children():
            w.destroy()
        self.side_a_var.set("")  # force a fresh choice per map
        for name in (t1, t2):
            if name:
                ttk.Radiobutton(self.team_frame, text=name, value=name,
                                variable=self.side_a_var).pack(side="left", padx=(0, 12))
        self.roster_lbl.configure(
            text=f"{t1 or '?'}:  {', '.join(p1) or '—'}\n{t2 or '?'}:  {', '.join(p2) or '—'}")

    def _copy_code(self) -> None:
        raw = self.code_var.get().strip()
        if not raw:
            self._emit("no code selected to copy.")
            return
        code = raw.split()[0]
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.root.update()  # keep it on the clipboard after focus changes
        self._emit(f"copied '{code}' — paste it into the OW replay code field.")

    def _capture(self) -> None:
        raw = self.code_var.get().strip()
        if not raw:
            self._emit("pick a code first (click ↻ to load Master codes).")
            return
        code = raw.split()[0]
        side_a = self.side_a_var.get().strip() or None
        if side_a is None:
            self._emit("pick the LEFT team first (click its name under 'Left team').")
            return
        hotkey = self.hotkey_var.get().strip() or "f8"
        from .capture import run_hotkey_capture
        self._emit(f"capture: {code} — {hotkey.upper()} snapshot · F7 next round · "
                   "F6 sub-map · ESC done. Watch the corner overlay (no need to alt-tab).")
        self.cap_btn.configure(state="disabled")
        overlay = _CaptureOverlay(self, hotkey)

        def emit(msg: str) -> None:
            self._emit(msg)
            self.q.put(lambda: overlay.update(msg))

        def go() -> None:
            try:
                with self._open_db() as db:
                    run_hotkey_capture(db, self.faceit_var.get(), demo_code=code,
                                       side_a_team=side_a, hotkey=hotkey,
                                       round_hotkey="f7", submap_hotkey="f6",
                                       require_division="master", emit=emit)
                self._emit("capture: finished (saved as a draft — review to finalize).")
            finally:
                self.q.put(overlay.close)
                self.q.put(self._refresh_codes)
        self._run(go)

    def _publish(self) -> None:
        from .scout import scout_payload
        import json
        self._emit("publish: exporting captured comps + scouting report …")

        def go() -> None:
            with self._open_db() as db:
                payload = scout_payload(db, self.faceit_var.get())
            with open("owscout_comps.json", "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            teams = len(payload["teams"])
            self._emit(f"publish: wrote owscout_comps.json ({teams} team(s)).")
            # Rebuild the dashboard so the comps show up immediately.
            try:
                from faceit_sync.db import Database as FaceitDb
                from faceit_sync.export import export_html
                with FaceitDb(self.faceit_var.get()) as fdb, \
                        open("dashboard.html", "w", encoding="utf-8") as out:
                    n = export_html(fdb, out)
                self._emit(f"publish: rebuilt dashboard.html ({n} division(s)). "
                           "Commit + push to update the online site.")
            except Exception as exc:  # noqa: BLE001
                self._emit(f"publish: JSON written; dashboard rebuild skipped ({exc}).")
        self._run(go)

    def run(self) -> None:
        self.root.mainloop()


class _LearnWindow:  # pragma: no cover - GUI runtime only
    """Teach owscout the real in-game HUD portraits, one hero at a time.

    Workflow (shown to the operator in the window): cycle every hero in a custom
    game, open the replay, scrub so ONE hero shows in the spectator top-bar, click
    Grab, confirm the guess. Each confirmed portrait becomes that hero's ref and
    is matched near-perfectly from then on. All grabbing/scoring runs on a worker
    thread; UI updates are marshalled back through the parent app's queue.
    """

    def __init__(self, app: "_App") -> None:
        import base64  # noqa: F401 - used in _show_slot
        from tkinter import ttk

        self.app = app
        self.base64 = base64
        tk = app.tk
        self.ctx: Any = None
        self.ranked: list[Any] = []
        self.cursor = 0
        self.learned: set[tuple[str, str]] = set()  # (hero_guid, variant) this session
        self._imgref: Any = None  # keep a ref so Tk doesn't GC the preview
        self._frame: Any = None   # last grabbed frame, for the portrait preview
        self.busy = False

        self.win = tk.Toplevel(app.root)
        # The [big-preview] tag lets us confirm at a glance the latest code is
        # running (an old still-open window won't have it).
        self.win.title("Learn heroes — teach owscout your HUD portraits  [big-preview]")
        self.win.geometry("620x720")
        self.win.minsize(560, 640)
        self.win.resizable(True, True)
        self.win.transient(app.root)

        pad = {"padx": 12, "pady": 6}
        steps = (
            "Build the most accurate library by teaching the tool the ACTUAL\n"
            "in-game portraits (they match ~0.9 vs ~0.5 for the gallery art):\n"
            "\n"
            "   1.  In a CUSTOM GAME, switch through every hero you want covered.\n"
            "   2.  Open the REPLAY of that game.\n"
            "   3.  Scrub so ONE hero shows in the spectator bar along the top.\n"
            "   4.  Click ‘Grab screen’ below, then confirm the hero.\n"
            "   5.  Repeat for each hero. Do a few, then re-capture to check.\n"
        )
        lbl = tk.Label(self.win, text=steps, justify="left", anchor="w",
                       font=("Segoe UI", 9), fg="#222")
        lbl.pack(fill="x", **pad)

        # Big banner showing which team the current grab will be saved to, so the
        # operator can't accidentally overwrite the wrong team's refs.
        self.team_banner = tk.Label(self.win, text="", font=("Segoe UI", 12, "bold"),
                                    fg="#fff")
        self.team_banner.pack(fill="x", padx=12)

        # Optional: calibrate ONE box so learning reads a single portrait only.
        boxrow = ttk.Frame(self.win)
        boxrow.pack(fill="x", **pad)
        self.box_btn = ttk.Button(boxrow, text="🎯  Calibrate one portrait (optional)",
                                  command=self._calibrate_slot)
        self.box_btn.pack(side="left")
        self.clear_btn = ttk.Button(boxrow, text="use all 10 slots",
                                    command=self._clear_slot)
        self.clear_btn.pack(side="left", padx=6)
        self.mode_lbl = ttk.Label(boxrow, text="", foreground="#555")
        self.mode_lbl.pack(side="left", padx=12)

        grabrow = ttk.Frame(self.win)
        grabrow.pack(fill="x", **pad)
        self.grab_btn = ttk.Button(grabrow, text="📷  Grab screen", command=self._grab)
        self.grab_btn.pack(side="left")
        self.status = ttk.Label(grabrow, text="loading…", foreground="#555")
        self.status.pack(side="left", padx=12)

        # Bottom controls are packed FIRST (bottom-up) so they stay visible no
        # matter how tall the preview is; the preview then fills the middle.
        self.progress = ttk.Label(self.win, text="Learned this session: 0",
                                   foreground="#333", font=("Segoe UI", 10, "bold"))
        self.progress.pack(side="bottom", **pad)

        pick = ttk.Frame(self.win)
        pick.pack(side="bottom", fill="x", **pad)
        ttk.Label(pick, text="Wrong? pick the right hero:").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.hero_var = tk.StringVar()
        self.hero_box = ttk.Combobox(pick, textvariable=self.hero_var, width=28)
        self.hero_box.grid(row=1, column=0, padx=(0, 8), pady=3, sticky="w")
        self.saveas_btn = ttk.Button(pick, text="Save as this", command=self._save_as,
                                     state="disabled")
        self.saveas_btn.grid(row=1, column=1, pady=3, sticky="w")

        confirm = ttk.Frame(self.win)
        confirm.pack(side="bottom", fill="x", **pad)
        self.yes_btn = ttk.Button(confirm, text="✓  Correct — save",
                                  command=self._accept, state="disabled")
        self.yes_btn.grid(row=0, column=0, padx=(0, 8), pady=3, sticky="w")
        self.next_btn = ttk.Button(confirm, text="↷ Different slot",
                                   command=self._next_slot, state="disabled")
        self.next_btn.grid(row=0, column=1, padx=4, pady=3)

        self.guess_lbl = tk.Label(self.win, text="", font=("Segoe UI", 15, "bold"),
                                  fg="#1a5")
        self.guess_lbl.pack(side="bottom", **pad)

        # Preview fills the remaining space between the grab row and the controls.
        # NB: width/height are CHARACTER units while the label shows text, but
        # switch to PIXELS once it shows an image — so we clear them in _show_slot,
        # otherwise the portrait would be clamped to a ~44x9px sliver.
        self.preview = tk.Label(self.win, text="(no capture yet)", width=44, height=9,
                                relief="groove", bg="#111", fg="#888")
        self.preview.pack(side="top", fill="both", expand=True, **pad)

        self._init_ctx()

    # --- infra: run on a worker, update UI via the app queue ----------------

    def _post(self, fn: Callable[[], Any]) -> None:
        self.app.q.put(fn)

    def _work(self, fn: Callable[[], None]) -> None:
        if self.busy:
            return
        self.busy = True

        def worker() -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                self._post(lambda: self.status.configure(text=f"error: {exc}"))
                self.app._emit(f"learn: error — {exc}")
            finally:
                self.busy = False
        threading.Thread(target=worker, daemon=True).start()

    def _load_ctx(self) -> None:
        """Build the learn context and refresh the UI. Runs synchronously on the
        caller's (worker) thread, so callers already inside _work must call this
        directly rather than wrapping it in another _work."""
        from .refs import prepare_learn
        with Database(self.app.db_var.get()) as db:
            ctx = prepare_learn(db, self.app.faceit_var.get(), hud_variant="default")
        self.ctx = ctx
        names = sorted(ctx.names.values())
        res = f"{ctx.profile.resolution_w}x{ctx.profile.resolution_h}"
        single = ctx.learn_box is not None

        def apply() -> None:
            self.hero_box.configure(values=names)
            self.mode_lbl.configure(
                text="mode: single calibrated box" if single
                else "mode: scanning all 10 slots")
            self.status.configure(
                text=f"ready · profile {res} · show a hero and click Grab")
        self._post(apply)

    def _init_ctx(self) -> None:
        self._work(self._load_ctx)

    def _calibrate_slot(self) -> None:
        from .refs import calibrate_learn_slot
        self._post(lambda: self.status.configure(
            text="a box-drag window will open — drag around ONE portrait, press ENTER"))

        def go() -> None:
            with Database(self.app.db_var.get()) as db:
                calibrate_learn_slot(db, hud_variant="default")
            self._post(lambda: self.status.configure(text="box saved — reloading…"))
            self._load_ctx()  # already on a worker thread — call directly
        self._work(go)

    def _clear_slot(self) -> None:
        def go() -> None:
            if self.ctx is not None:
                with Database(self.app.db_var.get()) as db:
                    db.clear_learn_slot(self.ctx.pid)
            self._load_ctx()  # already on a worker thread — call directly
        self._work(go)

    # --- actions ------------------------------------------------------------

    def _grab(self) -> None:
        from . import capture
        from .refs import rank_learn_slots
        if self.busy:
            self.status.configure(
                text="busy — wait for the current step (close the box-drag window if open)")
            return
        if self.ctx is None:
            self.status.configure(text="still loading the profile — retrying, try Grab again…")
            self._init_ctx()
            return
        self.status.configure(text="grabbing…")

        def go() -> None:
            frame, fw, fh = capture.grab_frame()
            prof = self.ctx.profile
            if (fw, fh) != (prof.resolution_w, prof.resolution_h):
                msg = (f"screen is {fw}x{fh} but the profile is "
                       f"{prof.resolution_w}x{prof.resolution_h} — match your "
                       "resolution/scale, then Grab again.")
                self._post(lambda: self.status.configure(text=msg))
                return
            with Database(self.app.db_var.get()) as db:
                ranked = rank_learn_slots(db, frame, self.ctx)
            self.ranked = ranked
            self.cursor = 0
            self._frame = frame
            self._post(self._show_slot)
        self._work(go)

    def _show_slot(self) -> None:
        from .refs import variant_for_cell
        if not self.ranked:
            self.status.configure(text="nothing found — try Grab again.")
            return
        s = self.ranked[self.cursor]
        # Banner: which team this grab will save to (left half = blue, right = red).
        if variant_for_cell(s.cell, self.ctx.profile) == "a":
            self.team_banner.configure(text="  LEARNING: BLUE team  (left side)  ", bg="#1c6dd0")
        else:
            self.team_banner.configure(text="  LEARNING: RED team  (right side)  ", bg="#c0392b")
        cv2 = self.ctx.cv2
        # Show the WHOLE portrait cell (recognizable), enlarged, with the matched
        # face region outlined in green — not just the tiny match patch.
        frame = getattr(self, "_frame", None)
        if frame is not None:
            c = s.cell
            pad = 4
            y0, x0 = max(0, c.y - pad), max(0, c.x - pad)
            disp = frame[y0:c.y + c.h + pad, x0:c.x + c.w + pad].copy()
            rx, ry = s.roi.x - x0, s.roi.y - y0
            cv2.rectangle(disp, (rx, ry), (rx + s.roi.w, ry + s.roi.h), (0, 255, 0), 2)
            # Cap so the portrait stays big but never pushes the controls off-screen.
            scale = max(2, min(380 // max(1, disp.shape[1]), 230 // max(1, disp.shape[0])))
            big = cv2.resize(disp, (disp.shape[1] * scale, disp.shape[0] * scale),
                             interpolation=cv2.INTER_CUBIC)
        else:
            big = cv2.resize(s.crop, (s.roi.w * 5, s.roi.h * 5), interpolation=cv2.INTER_NEAREST)
        ok, buf = cv2.imencode(".png", big)
        if ok:
            data = self.base64.b64encode(buf.tobytes()).decode("ascii")
            self._imgref = self.app.tk.PhotoImage(data=data)
            # width/height become pixel clamps once an image is shown — zero them
            # so the label sizes to the full portrait instead of a 44x9 sliver.
            self.preview.configure(image=self._imgref, text="", width=0, height=0)
        name = s.guess_name or "?"
        self.guess_lbl.configure(text=f"Looks like:  {name}   ({s.score:.2f})")
        self.hero_var.set(s.guess_name or "")
        self.status.configure(
            text=f"slot {s.side}#{s.slot_index}  ·  "
                 f"{self.cursor + 1} of {len(self.ranked)} slots")
        for b in (self.yes_btn, self.next_btn, self.saveas_btn):
            b.configure(state="normal")

    def _next_slot(self) -> None:
        if self.ranked:
            self.cursor = (self.cursor + 1) % len(self.ranked)
            self._show_slot()

    def _accept(self) -> None:
        if not self.ranked:
            return
        s = self.ranked[self.cursor]
        if not s.guess_guid:
            self.status.configure(text="no guess — pick the hero from the list instead.")
            return
        hero = next((h for h in self.ctx.heroes if h.guid == s.guess_guid), None)
        self._save(hero)

    def _save_as(self) -> None:
        from .refs import resolve_hero_name
        if not self.ranked:
            return
        typed = self.hero_var.get().strip()
        hero = resolve_hero_name(self.ctx.heroes, typed) if typed else None
        if hero is None:
            self.status.configure(text=f"couldn't match '{typed}' — pick an exact name.")
            return
        self._save(hero)

    def _save(self, hero: Any) -> None:
        from .refs import default_refs_dir, save_learn_ref, variant_for_cell
        if hero is None:
            return
        s = self.ranked[self.cursor]
        crop = s.crop
        variant = variant_for_cell(s.cell, self.ctx.profile)
        team = "blue" if variant == "a" else "red"

        def go() -> None:
            with Database(self.app.db_var.get()) as db:
                save_learn_ref(db, default_refs_dir(self.app.db_var.get()),
                               pid=self.ctx.pid, hero=hero, crop=crop, variant=variant)
            self.learned.add((hero.guid, variant))

            def apply() -> None:
                self.progress.configure(
                    text=f"Learned this session: {len(self.learned)}  "
                         f"(last: {hero.name} / {team})")
                self.status.configure(text=f"saved {hero.name} ({team}) — show the next hero, then Grab.")
                self.guess_lbl.configure(text=f"✓ saved {hero.name} ({team})")
                for b in (self.yes_btn, self.next_btn, self.saveas_btn):
                    b.configure(state="disabled")
            self._post(apply)
            self._post(self.app._verify_refs)
        self._work(go)


class _ReviewWindow:  # pragma: no cover - GUI runtime only
    """Review captured DRAFT maps and either finalize (greenlight -> export) or
    discard (e.g. a test run). Nothing reaches the scout data until finalized."""

    def __init__(self, app: "_App") -> None:
        from tkinter import ttk
        self.app = app
        tk = app.tk
        self.drafts: list[Any] = []

        self.win = tk.Toplevel(app.root)
        self.win.title("Review captured maps")
        self.win.geometry("760x560")
        self.win.transient(app.root)
        pad = {"padx": 10, "pady": 6}

        # Load the hero roster (faceit + operator-added) for the correction pickers.
        self.name_to_guid: dict[str, str] = {}
        self.hero_roles: dict[str, str] = {}
        self.hero_names: dict[str, str] = {}
        try:
            from .faceit import connect_ro, hero_roles as _load_roles, load_heroes
            with self._db() as db:
                customs = db.list_custom_heroes()
                with connect_ro(self.app.faceit_var.get()) as fdb:
                    heroes = load_heroes(fdb) + customs
                    self.hero_roles = _load_roles(fdb)
            for h in customs:
                if h.role:
                    self.hero_roles[h.guid] = h.role
            self.name_to_guid = {h.name: h.guid for h in heroes}
            self.hero_names = {h.guid: h.name for h in heroes}
        except Exception as exc:  # noqa: BLE001
            self.app._emit(f"review: couldn't load hero list for corrections ({exc}).")

        tk.Label(self.win, justify="left", anchor="w", fg="#222", font=("Segoe UI", 9),
                 text="Captured maps are DRAFTS. Check the comps, then Finalize to send "
                      "to the scout data, or Discard a test run.").pack(fill="x", **pad)

        body = ttk.Frame(self.win)
        body.pack(fill="both", expand=True, **pad)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        tk.Label(left, text="Draft maps").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=34, height=16, exportselection=False)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._show_selected())

        self.detail = tk.Text(body, wrap="word", state="disabled", bg="#111", fg="#ddd",
                              font=("Consolas", 10))
        self.detail.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # Fix a misread on the selected map — replaces a hero across a side.
        hero_list = sorted(self.name_to_guid)
        corr = ttk.LabelFrame(self.win, text="Fix a misread (selected map)")
        corr.pack(fill="x", **pad)
        ttk.Label(corr, text="Side").grid(row=0, column=0, padx=4, pady=4)
        self.fix_side = tk.StringVar(value="a (left)")
        ttk.Combobox(corr, textvariable=self.fix_side, values=["a (left)", "b (right)"],
                     state="readonly", width=9).grid(row=0, column=1, padx=4)
        ttk.Label(corr, text="wrong").grid(row=0, column=2, padx=4)
        self.fix_wrong = tk.StringVar()
        ttk.Combobox(corr, textvariable=self.fix_wrong, values=hero_list,
                     width=16).grid(row=0, column=3, padx=4)
        ttk.Label(corr, text="→ right").grid(row=0, column=4, padx=4)
        self.fix_right = tk.StringVar()
        ttk.Combobox(corr, textvariable=self.fix_right, values=hero_list,
                     width=16).grid(row=0, column=5, padx=4)
        ttk.Button(corr, text="Fix", command=self._fix_hero).grid(row=0, column=6, padx=6)

        btns = ttk.Frame(self.win)
        btns.pack(fill="x", **pad)
        ttk.Button(btns, text="↻ Refresh", command=self._refresh).pack(side="left")
        ttk.Button(btns, text="✓ Finalize (send to scout data)",
                   command=self._finalize).pack(side="left", padx=8)
        ttk.Button(btns, text="🗑 Discard draft", command=self._discard).pack(side="left")

        self._refresh()

    def _fix_hero(self) -> None:
        d = self._selected()
        if d is None:
            self._set_detail("Pick a draft map first.")
            return
        side = self.fix_side.get()[0]
        wg = self.name_to_guid.get(self.fix_wrong.get().strip())
        rg = self.name_to_guid.get(self.fix_right.get().strip())
        if not wg or not rg:
            self._set_detail("Pick both a wrong and a right hero from the lists.")
            return
        with self._db() as db:
            n = db.correct_hero_in_map(d.id, side, wg, rg, hero_roles=self.hero_roles,
                                       hero_names=self.hero_names)
        self.app._emit(f"review: fixed {self.fix_wrong.get()} → {self.fix_right.get()} "
                       f"on side {side} ({n} observation(s)).")
        self._show_selected()

    def _db(self) -> Database:
        return Database(self.app.db_var.get())

    def _refresh(self) -> None:
        with self._db() as db:
            self.drafts = db.list_draft_maps()
        self.listbox.delete(0, "end")
        for d in self.drafts:
            self.listbox.insert(
                "end", f"{d.demo_code or '—'}  {d.map_name or '?'}  ({d.observations} obs)")
        self._set_detail("Select a draft map to review its comps."
                         if self.drafts else "No draft maps. Capture a replay first.")

    def _selected(self) -> Any:
        sel = self.listbox.curselection()
        return self.drafts[sel[0]] if sel else None

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", text)
        self.detail.configure(state="disabled")

    def _show_selected(self) -> None:
        d = self._selected()
        if d is None:
            return
        with self._db() as db:
            comps = db.map_side_comps(d.id)
        lines = [f"{d.demo_code or '—'}  ·  {d.map_name or '?'}",
                 f"LEFT (a): {d.side_a or '?'}    RIGHT (b): {d.side_b or '?'}", ""]
        for side, label in (("a", d.side_a), ("b", d.side_b)):
            lines.append(f"— {label or side.upper()} —")
            rows = comps.get(side) or []
            if not rows:
                lines.append("   (no comps)")
            for names, n, resolved, sub, rnd, conf in rows:
                flag = "" if resolved else "  [unresolved]"
                if conf is not None and conf < 0.62:
                    flag += f"  ⚠ low conf {conf:.2f}"
                tags = " ".join(t for t in (f"R{rnd}" if rnd else "",
                                            f"[{sub}]" if sub else "") if t)
                tags = (tags + " ") if tags else ""
                lines.append(f"   {tags}x{n}: {names}{flag}")
            lines.append("")
        self._set_detail("\n".join(lines))

    def _finalize(self) -> None:
        d = self._selected()
        if d is None:
            self._set_detail("Pick a draft map first.")
            return
        with self._db() as db:
            db.finalize_map(d.id)
        self.app._emit(f"review: finalized {d.demo_code or d.id} ({d.map_name}) — "
                       "now in the scout export.")
        self.app.q.put(self.app._refresh_codes)
        self._refresh()

    def _discard(self) -> None:
        from tkinter import messagebox
        d = self._selected()
        if d is None:
            self._set_detail("Pick a draft map first.")
            return
        if not messagebox.askyesno(
            "Discard draft?",
            f"Delete the draft capture for {d.demo_code or d.id} ({d.map_name}) and its "
            f"{d.observations} observations? This can't be undone.",
            icon="warning", default="no", parent=self.win):
            return
        with self._db() as db:
            db.discard_map(d.id)
        self.app._emit(f"review: discarded draft {d.demo_code or d.id}.")
        self._refresh()


class _CaptureOverlay:  # pragma: no cover - GUI runtime only
    """A small always-on-top overlay shown during capture, so the operator sees
    what was captured (and the hotkey legend) without alt-tabbing out of OW. Works
    when OW runs windowed/borderless (an exclusive-fullscreen game hides it)."""

    def __init__(self, app: "_App", hotkey: str) -> None:
        tk = app.tk
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)               # no title bar / chrome
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.88)
        except Exception:  # noqa: BLE001 - alpha unsupported on some platforms
            pass
        self.win.configure(bg="#0a0a0a")
        sw = self.win.winfo_screenwidth()
        self.win.geometry(f"+{max(0, sw // 2 - 300)}+8")   # top-centre
        legend = (f"{hotkey.upper()} snapshot   F7 next round   "
                  f"F6 sub-map   ESC done")
        tk.Label(self.win, text="● owscout capturing", bg="#0a0a0a", fg="#6cf",
                 font=("Segoe UI", 10, "bold")).pack(padx=16, pady=(6, 0), anchor="w")
        tk.Label(self.win, text=legend, bg="#0a0a0a", fg="#9aa",
                 font=("Consolas", 9)).pack(padx=16, anchor="w")
        self.status = tk.Label(self.win, text=f"ready — press {hotkey.upper()} at key moments",
                               bg="#0a0a0a", fg="#fff", font=("Consolas", 11, "bold"),
                               justify="left", anchor="w")
        self.status.pack(padx=16, pady=(2, 8), anchor="w")

    def update(self, msg: str) -> None:
        m = msg.strip()
        if m:
            self.status.configure(text=m[:120])

    def close(self) -> None:
        try:
            self.win.destroy()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:  # pragma: no cover
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Tkinter is not available in this Python.")
        return 2
    _App().run()
    return 0
