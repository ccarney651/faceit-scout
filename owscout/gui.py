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
import sys
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from .db import Database
from .models import REGIONS


# Sentinel for "don't filter the code list by team".
ALL_TEAMS = "(all teams)"
ALL_REGIONS = "(all regions)"

# The capture legend, built from whatever keys the operator has bound.
_KEY_LABELS = (("snapshot", "snapshot"), ("round", "next round"), ("submap", "sub-map"),
               ("attack", "who-attacks"), ("undo", "undo"))


def _keys_summary(binds: dict[str, str]) -> str:
    return "  ".join(f"{binds[a].upper()} {label}" for a, label in _KEY_LABELS)


def _eta_text(done: int, total: int, elapsed: float) -> str:
    """"match 12 of 380 - about 4 min left", or without the estimate too early.

    The first few matches are a terrible sample (connection warm-up, then FACEIT's
    rate limiter settling in), so no time is quoted until there is enough history
    for the number not to swing wildly and look broken.
    """
    head = f"match {done} of {total}"
    if done < 5 or done >= total or elapsed <= 0:
        return head
    remaining = (elapsed / done) * (total - done)
    if remaining < 90:
        return f"{head} - under a minute left"
    mins = int(remaining // 60) + 1
    return f"{head} - about {mins} min left"


# A faceit DB unsynced for longer than this is called out: the code list is then
# missing whatever has been played since, which looks the same as "no new matches".
# The CI syncs nightly, so a day without a local sync already means divergence.
STALE_DB_HOURS = 24


def _faceit_freshness(faceit_db_path: str) -> tuple[str, bool]:
    """``(label, is_stale)`` describing how current the faceit DB is.

    Reports when the DB was last SYNCED, not the newest match in it: a league with
    no games for three days is fine, a tool that has not checked for three days is
    not, and only the second one hides codes from you.
    """
    import sqlite3
    from datetime import datetime, timezone
    try:
        with sqlite3.connect(f"file:{faceit_db_path}?mode=ro", uri=True) as conn:
            synced = conn.execute("SELECT MAX(ran_at) FROM sync_log").fetchone()[0]
            latest = conn.execute("SELECT MAX(finished_at) FROM matches").fetchone()[0]
    except Exception as exc:  # noqa: BLE001 - a missing DB is a message, not a crash
        return f"faceit DB unreadable ({exc})", True
    if not synced:
        return "faceit DB has never been synced - click Sync codes.", True
    try:
        delta = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(str(synced).replace("Z", "+00:00")))
        hours = delta.total_seconds() / 3600
    except ValueError:
        return f"last synced {str(synced)[:10]}", False
    when = (f"{hours:.0f}h ago" if hours < 48 else f"{hours / 24:.0f} days ago")
    stale = hours >= STALE_DB_HOURS
    return (f"last synced {when} - newest match {str(latest or '?')[:10]}"
            + (" - sync to pick up newer codes" if stale else ""), stale)


def _faceit_is_empty(faceit_db_path: str) -> bool:
    """True if this is a fresh machine: the faceit DB is missing or has no
    championships yet. Read-only, so it never CREATES the file (a plain connect
    would, and an empty file then looks 'present but empty' to everything else)."""
    import sqlite3
    try:
        with sqlite3.connect(f"file:{faceit_db_path}?mode=ro", uri=True) as conn:
            return conn.execute("SELECT COUNT(*) FROM championships").fetchone()[0] == 0
    except Exception:  # noqa: BLE001 - missing file / no such table -> treat as empty
        return True


def _bundled(name: str) -> Optional[str]:
    """Path to a resource shipped INSIDE the app, or None if absent.

    Frozen: PyInstaller extracts datas into sys._MEIPASS. Dev: the repo root.
    Distinct from _base_dir on purpose - bundled resources are read-only inputs
    baked in at build time; _base_dir is where the user's own data lives.
    """
    root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else         str(Path(__file__).resolve().parent.parent)
    if not root:
        return None
    p = Path(root) / name
    return str(p) if p.is_file() else None


def _base_dir() -> str:
    """A stable folder for owscout's data, independent of where the app is
    launched from — so calibration and refs persist between sessions. Prefer
    $OWSCOUT_HOME; in a PyInstaller build, the folder the .exe sits in; else
    the repo dir (the parent of the owscout package).

    The frozen branch is load-bearing: under a onefile exe, ``__file__`` points
    into PyInstaller's temp extraction dir, which is DELETED when the app exits.
    Without it, every exe user's database, calibration and learned refs would
    silently land in a temp folder and vanish on close.
    """
    home = os.getenv("OWSCOUT_HOME")
    if home:
        return home
    if getattr(sys, "frozen", False):          # PyInstaller
        return str(Path(sys.executable).resolve().parent)
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
        self.root.title("OW Scout — FACEIT League")
        # The panels above the Log have grown (keybinds, sync status, region
        # filter) and pack() will happily crush the Log to a few pixels rather
        # than overflow. Size the window to fit them, but never taller than the
        # screen it has to live on.
        wanted_h = min(760, self.root.winfo_screenheight() - 80)
        self.root.geometry(f"820x{wanted_h}")
        self.root.minsize(720, 560)

        pad = {"padx": 10, "pady": 6}
        # Database file locations live at the bottom under "Advanced": a new user
        # never needs to see or touch a file path. The vars are created up front
        # because startup (code refresh, freshness) reads them.
        self.db_var = tk.StringVar(value=_default_db())
        self.faceit_var = tk.StringVar(value=_default_faceit())

        # A lightweight collapsible: a clickable header that shows/hides its body,
        # so advanced controls and raw paths stay reachable without cluttering the
        # first thing a new user sees.
        def collapsible(parent: Any, title: str, *, start_open: bool = False) -> Any:
            body = ttk.Frame(parent)
            hdr = ttk.Label(parent, foreground="#06c", cursor="hand2")
            st = {"open": start_open}

            def render() -> None:
                hdr.configure(text=("▾ " if st["open"] else "▸ ") + title)
                if st["open"]:
                    body.pack(fill="x", padx=(18, 4), pady=(0, 6))
                else:
                    body.pack_forget()

            def toggle(_e: Any = None) -> None:
                st["open"] = not st["open"]
                render()

            hdr.bind("<Button-1>", toggle)
            hdr.pack(anchor="w", padx=8, pady=(4, 0))
            render()
            return body

        # --- 1. setup -------------------------------------------------------
        # A pre-trained build only needs ONE thing from a new user: calibrate the
        # capture boxes to their screen. Everything else (library building,
        # learning, import/export) is for curators and lives under Advanced.
        setup = ttk.LabelFrame(self.root, text="Set up (once per computer)")
        setup.pack(fill="x", **pad)
        srow = ttk.Frame(setup)
        srow.pack(fill="x", padx=6, pady=6)
        ttk.Button(srow, text="Calibrate to my screen",
                   command=self._calibrate).pack(side="left")
        self.setup_status = ttk.Label(srow, text="", foreground="#555")
        self.setup_status.pack(side="left", padx=12)

        adv = collapsible(setup, "Advanced hero tools", start_open=False)
        r1 = ttk.Frame(adv)
        r1.pack(fill="x", pady=2)
        self.sheet_btn = ttk.Button(r1, text="Build hero library (load gallery)…",
                                    command=self._load_sheet)
        self.sheet_btn.pack(side="left", padx=(0, 6))
        ttk.Button(r1, text="Check refs", command=self._verify_refs).pack(side="left", padx=6)
        ttk.Label(adv, text="Teach owscout your in-game portraits for best accuracy:",
                  foreground="#333").pack(anchor="w", pady=(6, 2))
        r2 = ttk.Frame(adv)
        r2.pack(fill="x", pady=2)
        self.learn_btn = ttk.Button(r2, text="⭐ Learn heroes from a replay…",
                                    command=self._open_learn)
        self.learn_btn.pack(side="left", padx=(0, 6))
        ttk.Button(r2, text="➕ Add new hero", command=self._add_hero).pack(side="left", padx=6)
        r3 = ttk.Frame(adv)
        r3.pack(fill="x", pady=2)
        ttk.Button(r3, text="📦 Import hero library…",
                   command=self._import_refs).pack(side="left", padx=(0, 6))
        ttk.Button(r3, text="Export my library…",
                   command=self._export_refs).pack(side="left", padx=6)

        # --- 2. capture -----------------------------------------------------
        # Laid out as stacked rows of nested frames (not one shared grid): an
        # expanding widget in a shared grid column shoved the right-hand controls
        # off-screen when the window widened. Here each row owns its packing, so
        # controls stay put at any width.
        cap = ttk.LabelFrame(self.root, text="Scout a replay (Master division)")
        cap.pack(fill="x", **pad)

        # Filters: pick one opponent at a time - 40 codes across every Master team
        # is a lot to scan for the four you care about.
        filt = ttk.Frame(cap)
        filt.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(filt, text="Opponent").pack(side="left")
        self.team_filter_var = tk.StringVar(value=ALL_TEAMS)
        self.team_filter_box = ttk.Combobox(filt, textvariable=self.team_filter_var,
                                            width=22, state="readonly")
        self.team_filter_box.pack(side="left", padx=(4, 12))
        self.team_filter_box.bind("<<ComboboxSelected>>",
                                  lambda _e: self._apply_code_filter())
        ttk.Label(filt, text="Region").pack(side="left")
        self.region_var = tk.StringVar(value=ALL_REGIONS)
        region_box = ttk.Combobox(filt, textvariable=self.region_var, width=12,
                                  state="readonly", values=[ALL_REGIONS, *REGIONS])
        region_box.pack(side="left", padx=(4, 12))
        # Region changes WHICH codes are fetched, so it re-queries rather than
        # filtering the cached rows (the team list depends on it).
        region_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_codes())
        self.hide_claimed = tk.BooleanVar(value=True)
        ttk.Checkbutton(filt, text="hide already-scouted", variable=self.hide_claimed,
                        command=self._apply_code_filter).pack(side="left")

        # Replay picker: the combobox takes all the slack; the buttons stay pinned.
        crow = ttk.Frame(cap)
        crow.pack(fill="x", padx=6, pady=2)
        ttk.Label(crow, text="Replay").pack(side="left")
        self.code_var = tk.StringVar()
        self.code_box = ttk.Combobox(crow, textvariable=self.code_var, state="readonly")
        self.code_box.pack(side="left", fill="x", expand=True, padx=(4, 6))
        self.code_box.bind("<<ComboboxSelected>>", lambda _e: self._on_code_selected())
        ttk.Button(crow, text="↻", width=3, command=self._refresh_codes).pack(side="left", padx=2)
        ttk.Button(crow, text="Copy code", command=self._copy_code).pack(side="left", padx=2)

        # Left team: click whichever team is on the LEFT of the HUD (or leave it to
        # auto-detect).
        lrow = ttk.Frame(cap)
        lrow.pack(fill="x", padx=6, pady=2)
        ttk.Label(lrow, text="Left team on the HUD").pack(side="left")
        self.side_a_var = tk.StringVar()
        self.team_frame = ttk.Frame(lrow)
        self.team_frame.pack(side="left", padx=8)
        self.roster_lbl = ttk.Label(cap, text="(pick a replay to see the teams)",
                                    foreground="#555", justify="left")
        self.roster_lbl.pack(anchor="w", padx=(74, 6))

        krow = ttk.Frame(cap)
        krow.pack(fill="x", padx=6, pady=2)
        ttk.Label(krow, text="Keys").pack(side="left")
        self.keys_lbl = ttk.Label(krow, text="", foreground="#555")
        self.keys_lbl.pack(side="left", padx=8)
        ttk.Button(krow, text="Change keys…", command=self._open_keybinds).pack(side="right")

        self.cap_btn = ttk.Button(cap, text="Start hotkey capture", command=self._capture)
        self.cap_btn.pack(anchor="w", padx=6, pady=(6, 4))

        # Code freshness. A stale faceit DB silently hides every code published
        # since the last sync, which looks identical to "no new matches".
        frow = ttk.Frame(cap)
        frow.pack(fill="x", padx=6, pady=(0, 6))
        self.freshness_lbl = ttk.Label(frow, text="", foreground="#555")
        self.freshness_lbl.pack(side="left")
        ttk.Button(frow, text="Sync codes from FACEIT",
                   command=self._sync_faceit).pack(side="right")

        # First-run bootstrap / download is a long job; without a bar the window
        # reads as hung. The whole row is hidden until a long job runs.
        self._progress_row = ttk.Frame(cap)
        self.progress = ttk.Progressbar(self._progress_row, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        self.progress_lbl = ttk.Label(self._progress_row, text="", foreground="#555")
        self.progress_lbl.pack(side="left", padx=6)
        self._progress_started = 0.0

        # --- 3. review + publish -------------------------------------------
        pub = ttk.LabelFrame(self.root, text="Review & publish")
        pub.pack(fill="x", **pad)
        brow = ttk.Frame(pub)
        brow.pack(fill="x", padx=6, pady=6)
        ttk.Button(brow, text="📋 Review captured maps…",
                   command=self._open_review).pack(side="left", padx=(0, 6))
        ttk.Button(brow, text="Publish my captures →",
                   command=self._publish).pack(side="left", padx=6)
        # Whose contribution this is. One file per contributor is what keeps two
        # people publishing at once from overwriting each other.
        arow = ttk.Frame(pub)
        arow.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(arow, text="Publish as").pack(side="left")
        self.contributor_var = tk.StringVar(
            value=os.getenv("OWSCOUT_CONTRIBUTOR") or os.getenv("USERNAME") or "operator")
        ttk.Entry(arow, textvariable=self.contributor_var, width=16).pack(side="left", padx=6)
        ttk.Button(arow, text="Sync settings…",
                   command=self._open_sync_settings).pack(side="left", padx=6)
        ttk.Label(pub, text="Captures are drafts until you review + finalize them; "
                            "only finalized maps are exported.",
                  foreground="#555").pack(anchor="w", padx=6, pady=(0, 6))

        # --- status + activity ---------------------------------------------
        # One friendly status line is always visible; the full activity log is a
        # lighter panel below it (not a black console) so it informs without
        # alarming. Raw file paths sit under Advanced, collapsed.
        self.status_lbl = ttk.Label(self.root, text="Ready.", anchor="w",
                                    foreground="#222", font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(fill="x", padx=14, pady=(2, 0))
        logf = ttk.LabelFrame(self.root, text="Activity")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=7, wrap="word", state="disabled",
                           bg="#f6f6f6", fg="#333", font=("Consolas", 9),
                           relief="flat", borderwidth=1, highlightthickness=0)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

        dbwrap = collapsible(self.root, "Advanced: file locations")
        for i, (lbl, var) in enumerate((("owscout DB", self.db_var),
                                        ("faceit DB", self.faceit_var))):
            ttk.Label(dbwrap, text=lbl, width=11).grid(row=i, column=0, sticky="w", padx=6, pady=3)
            ttk.Entry(dbwrap, textvariable=var).grid(row=i, column=1, sticky="ew", padx=6, pady=3)
        dbwrap.columnconfigure(1, weight=1)

        self._stop_capture: Optional[Callable[[], None]] = None
        self._code_rows: list[Any] = []
        self._claimed: set[str] = set()      # games already scouted by anyone
        self._keybinds: dict[str, str] = {}
        self.root.after(80, self._drain)
        self._load_keybinds()
        self._refresh_codes()
        self._maybe_import_bundled_refs()
        self._verify_refs()

    # --- infra --------------------------------------------------------------

    def _emit(self, msg: str) -> None:
        """Thread-safe log write (queued, applied on the main loop)."""
        self.q.put(lambda: self._write(msg))

    def _write(self, msg: str) -> None:
        line = msg.rstrip()
        # The status line mirrors the newest message so the important thing is
        # visible at a glance without reading the whole activity panel.
        if line and hasattr(self, "status_lbl"):
            self.status_lbl.configure(text=line)
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
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
        # First calibration or a redo? The redo warning (it detaches learned
        # heroes) is alarming and simply wrong to show someone who has not learned
        # any yet, so it only appears once a profile already exists.
        already = False
        try:
            with self._open_db() as db:
                already = db.latest_active_profile("default") is not None
        except Exception:  # noqa: BLE001 - unknown -> treat as first run
            already = False
        if already:
            ok = messagebox.askyesno(
                "Re-calibrate to your screen?",
                "You're already calibrated. Re-calibrating re-detects the capture "
                "boxes and DETACHES every hero you've learned, so you'd re-learn "
                "them. Only needed after a screen-resolution or HUD change.\n\n"
                "Continue?",
                icon="warning", default="no", parent=self.root)
        else:
            ok = messagebox.askyesno(
                "Calibrate to your screen",
                "This is the one-time setup: it teaches owscout where the hero "
                "portraits sit on YOUR screen.\n\n"
                "First, have Overwatch open on a replay with the row of 10 hero "
                "portraits showing along the top. Then continue — it takes about a "
                "minute.",
                default="yes", parent=self.root)
        if not ok:
            self._emit("calibrate: cancelled" +
                       (" (your learned heroes are untouched)." if already else "."))
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
            # A fresh calibration + a bundled library = pre-trained immediately.
            self.q.put(self._maybe_import_bundled_refs)
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
                    region = self.region_var.get()
                    rows = db.list_codes(
                        self.faceit_var.get(), uncaptured=True, limit=40,
                        region=None if region == ALL_REGIONS else region)
            except Exception as exc:  # noqa: BLE001
                rows = []
                self._emit(f"codes: {exc}")
            # Cached so the team filter is instant and needs no second query.
            self._code_rows = list(rows)
            # Who else has scouted what. Offline-safe: an empty set just means
            # nothing is known to be claimed.
            from .contribute import fetch_captured_games
            self._claimed = fetch_captured_games()
            self.q.put(self._apply_code_filter)
            text, stale = _faceit_freshness(self.faceit_var.get())
            self.q.put(lambda: self.freshness_lbl.configure(
                text=text, foreground="#a60" if stale else "#555"))
        self._run(go, lock=False)

    # --- long-job progress. Called from worker threads, so every Tk touch is
    # marshalled through the queue and applied on the main loop.
    def _progress_begin(self, label: str) -> None:
        import time
        self._progress_started = time.monotonic()

        def show() -> None:
            self.progress.configure(value=0)
            self.progress_lbl.configure(text=label)
            self._progress_row.pack(fill="x", padx=6, pady=(0, 6))
        self.q.put(show)

    def _progress_step(self, done: int, total: int) -> None:
        import time
        elapsed = time.monotonic() - self._progress_started
        pct = (done / total * 100) if total else 0
        text = _eta_text(done, total, elapsed)

        def paint() -> None:
            self.progress.configure(value=pct)
            self.progress_lbl.configure(text=text)
        self.q.put(paint)

    def _download_progress(self, done: int, total: int) -> None:
        pct = (done / total * 100) if total else 0
        mb = done / 1024 / 1024
        label = (f"{mb:.1f} of {total / 1024 / 1024:.1f} MB" if total
                 else f"{mb:.1f} MB")

        def paint() -> None:
            self.progress.configure(value=pct)
            self.progress_lbl.configure(text=label)
        self.q.put(paint)

    def _progress_end(self) -> None:
        def hide() -> None:
            self._progress_row.pack_forget()
        self.q.put(hide)

    def _is_claimed(self, row: Any) -> bool:
        """Has ANY contributor already published this exact game?"""
        mid, gno = getattr(row, "match_id", None), getattr(row, "game_no", None)
        return bool(mid) and gno is not None and f"{mid}:{gno}" in self._claimed

    def _sync_faceit(self) -> None:
        """Pull new matches + late-published replay codes into the faceit DB, so the
        code list above matches what the site is working from."""
        self._emit("sync: fetching new matches and back-filling replay codes …")

        def go() -> None:
            from faceit_sync.client import FaceitClient
            from faceit_sync.db import Database as FaceitDb
            from faceit_sync.sync import SyncEngine
            from .contribute import fetch_faceit_snapshot
            faceit_path = self.faceit_var.get()

            # FIRST RUN, fast path: download the database the site already built
            # last night instead of re-crawling ~2,100 rate-limited FACEIT calls
            # (which is minutes of 429 backoffs). The download must happen BEFORE
            # opening the DB - it atomically replaces the file, which an open
            # connection would block on Windows.
            if _faceit_is_empty(faceit_path):
                self._emit("sync: FIRST RUN - downloading the current match "
                           "database from the site (a few seconds) ...")
                self._progress_begin("downloading current data ...")
                try:
                    ok = fetch_faceit_snapshot(faceit_path,
                                               progress=self._download_progress)
                finally:
                    self._progress_end()
                if ok:
                    self._emit("sync: got the prebuilt database from the site - "
                               "ready to scout. Click Sync again any time to top "
                               "up with the very latest matches.")
                    self.q.put(self._refresh_codes)
                    return
                self._emit("sync: site download unavailable - building from FACEIT "
                           "directly. This one-time crawl takes a few minutes; the "
                           "bar shows progress. Later syncs are quick.")

            with FaceitDb(faceit_path) as fdb:
                engine = SyncEngine(FaceitClient(), fdb)
                # Download failed AND fresh: the keyless team-graph crawl needs
                # seed matches to start (no stored teams -> nothing to enumerate),
                # so prime it from the bundled list, then transitive discovery
                # does the rest - the same flow CI uses nightly.
                empty = fdb.conn.execute(
                    "SELECT COUNT(*) FROM championships").fetchone()[0] == 0
                if empty:
                    seeds = _bundled("matches.txt")
                    if not seeds:
                        self._emit("sync: empty database and no bundled seed list - "
                                   "cannot bootstrap. Ask the curator for one.")
                        return
                    refs = [ln.strip() for ln in open(seeds, encoding="utf-8")
                            if ln.strip() and not ln.startswith("#")]
                    self._emit(f"sync: seeding from {len(refs)} bundled matches ...")
                    self._progress_begin(f"match 0 of {len(refs)}")
                    try:
                        engine.run_matches(refs, progress=self._progress_step)
                    finally:
                        self._progress_end()
                res = engine.run_all()
            self._emit(f"sync: {res.inserted} new, {res.updated} updated, "
                       f"{res.skipped} unchanged, {res.errors} error(s).")
            self.q.put(self._refresh_codes)
        self._run(go)

    def _apply_code_filter(self) -> None:
        """Rebuild the code list for the selected team (or all of them)."""
        rows = getattr(self, "_code_rows", [])
        teams = sorted({t for r in rows for t in (r.team_a, r.team_b) if t})
        self.team_filter_box.configure(values=[ALL_TEAMS, *teams])
        want = self.team_filter_var.get()
        if want != ALL_TEAMS and want not in teams:   # team dropped out of the window
            want = ALL_TEAMS
            self.team_filter_var.set(want)
        keep = [r for r in rows if want == ALL_TEAMS or want in (r.team_a, r.team_b)]
        claimed_n = sum(1 for r in keep if self._is_claimed(r))
        if self.hide_claimed.get():
            keep = [r for r in keep if not self._is_claimed(r)]
        items = [
            f"{r.demo_code}  {r.map_name}  {r.team_a} vs {r.team_b}"
            + ("   [already scouted]" if self._is_claimed(r) else "")
            for r in keep
        ]
        self.code_box.configure(values=items)
        if items:
            self.code_var.set(items[0])
            self._on_code_selected()
        else:
            self.code_var.set("")
        n, tot = len(items), len(rows)
        note = f"codes: {n} shown of {tot}"
        if want != ALL_TEAMS:
            note += f" (team: {want})"
        if claimed_n:
            note += (f" - {claimed_n} already scouted by someone"
                     + (" and hidden" if self.hide_claimed.get() else ""))
        self._emit(note)

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
        # Auto is the default: capture reads the player-name bars on the first
        # snapshot and works out which team is left (verified on real frames -
        # correct even when a battletag differs completely from the faceit
        # nickname). The manual radios remain as the override.
        ttk.Radiobutton(self.team_frame, text="Auto-detect (from names)", value="",
                        variable=self.side_a_var).pack(side="left", padx=(0, 12))
        for name in (t1, t2):
            if name:
                ttk.Radiobutton(self.team_frame, text=name, value=name,
                                variable=self.side_a_var).pack(side="left", padx=(0, 12))
        self.roster_lbl.configure(
            text=f"{t1 or '?'}:  {', '.join(p1) or '—'}\n{t2 or '?'}:  {', '.join(p2) or '—'}")

    def _maybe_import_bundled_refs(self) -> None:
        """Make the exe PRE-TRAINED: if a calibration exists but the library is
        empty, load the ref bundle baked into the app at build time. Runs at
        startup and after Calibrate, so a new user's flow is calibrate ->
        capture with no learning session and no separate download."""
        bundle = _bundled("owscout_refs.zip")
        if not bundle:
            return

        def go() -> None:
            from .refs import default_refs_dir, import_ref_bundle
            try:
                with self._open_db() as db:
                    prof = db.latest_active_profile("default")
                    if prof is None or prof.id is None or db.get_refs(prof.id):
                        return          # not calibrated yet, or already has refs
                    n = import_ref_bundle(db, bundle,
                                          default_refs_dir(self.db_var.get()))
                if n["added"]:
                    self._emit(f"setup: pre-trained hero library loaded "
                               f"({n['added']} refs). Ready to capture.")
                    self.q.put(self._verify_refs)
            except Exception as exc:  # noqa: BLE001 - never block startup on this
                self._emit(f"setup: bundled library not loaded ({exc})")
        self._run(go, lock=False)

    def _import_refs(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Import hero library", filetypes=[("owscout ref bundle", "*.zip")])
        if not path:
            return

        def go() -> None:
            from .refs import default_refs_dir, import_ref_bundle
            try:
                with self._open_db() as db:
                    n = import_ref_bundle(db, path,
                                          default_refs_dir(self.db_var.get()))
                self._emit(f"import: {n['added']} ref(s) added, "
                           f"{n['skipped']} already present. Ready to capture.")
            except Exception as exc:  # noqa: BLE001
                self._emit(f"import failed: {exc}")
            self.q.put(self._verify_refs)   # refresh the setup status line
        self._run(go)

    def _export_refs(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export hero library", defaultextension=".zip",
            initialfile="owscout_refs.zip",
            filetypes=[("owscout ref bundle", "*.zip")])
        if not path:
            return

        def go() -> None:
            from . import __version__
            from .refs import export_ref_bundle
            try:
                with self._open_db() as db:
                    n = export_ref_bundle(db, path,
                                          faceit_db_path=self.faceit_var.get(),
                                          tool_version=__version__)
                self._emit(f"export: wrote {path} ({n['exported']} ref(s)). "
                           "Send this file to a teammate; they calibrate, then import it.")
            except Exception as exc:  # noqa: BLE001
                self._emit(f"export failed: {exc}")
        self._run(go)

    def _sync_config(self) -> dict[str, str]:
        """Upload config. The endpoint default is baked into the build, so an
        end user configures nothing; repo/token are the curator's direct path."""
        from .contribute import DEFAULT_UPLOAD_ENDPOINT
        try:
            with self._open_db() as db:
                got = db.get_settings("sync.")
        except Exception:  # noqa: BLE001
            got = {}
        return {"endpoint": got.get("sync.endpoint", DEFAULT_UPLOAD_ENDPOINT),
                "repo": got.get("sync.repo", "ccarney651/faceit-scout"),
                "token": got.get("sync.token", "")}

    def _identity_token(self) -> str:
        """The install's auto-generated identity. Created silently on first use;
        the user never sees it - it is what makes their chosen name THEIRS on
        the open endpoint (first upload claims the name)."""
        import secrets
        with self._open_db() as db:
            got = db.get_settings("sync.identity")
            tok = got.get("sync.identity", "")
            if not tok:
                tok = secrets.token_hex(24)
                db.set_settings({"sync.identity": tok})
        return tok

    def _open_sync_settings(self) -> None:
        """One-time setup that turns Publish into publish-AND-upload. The token
        is a fine-grained GitHub PAT with Contents write on the site repo; it
        lives in the local app_settings table, never in any shared file."""
        import tkinter as tk
        from tkinter import ttk
        cfg = self._sync_config()
        win = tk.Toplevel(self.root)
        win.title("Sync settings")
        win.transient(self.root)
        ttk.Label(win, wraplength=470, justify="left", foreground="#555",
                  text="Publishing uploads to the open endpoint automatically - there "
                       "is nothing to configure for normal use. Your chosen name is "
                       "claimed by this install on first upload, so nobody else can "
                       "overwrite your file. The fields below are overrides."
                  ).grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="w")
        ep_var = tk.StringVar(value=cfg["endpoint"])
        repo_var = tk.StringVar(value=cfg["repo"])
        tok_var = tk.StringVar(value=cfg["token"])
        ttk.Label(win, text="Upload endpoint").grid(row=1, column=0, padx=10, pady=3, sticky="w")
        ttk.Entry(win, textvariable=ep_var, width=42).grid(row=1, column=1, padx=10, pady=3, sticky="w")
        ttk.Label(win, text="- curator-only direct path -", foreground="#888").grid(
            row=2, column=0, columnspan=2, padx=10, pady=(8, 0), sticky="w")
        ttk.Label(win, text="Repo (owner/name)").grid(row=3, column=0, padx=10, pady=3, sticky="w")
        ttk.Entry(win, textvariable=repo_var, width=42).grid(row=3, column=1, padx=10, pady=3, sticky="w")
        ttk.Label(win, text="GitHub token").grid(row=4, column=0, padx=10, pady=3, sticky="w")
        ttk.Entry(win, textvariable=tok_var, width=42, show="*").grid(row=4, column=1, padx=10, pady=3, sticky="w")

        def save() -> None:
            with self._open_db() as db:
                db.set_settings({"sync.endpoint": ep_var.get().strip(),
                                 "sync.repo": repo_var.get().strip(),
                                 "sync.token": tok_var.get().strip()})
            self._emit("sync settings saved.")
            win.destroy()

        btns = ttk.Frame(win)
        btns.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        ttk.Button(btns, text="Save", command=save).pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left", padx=8)

    def _load_keybinds(self) -> None:
        """Read the operator's keybinds (defaults if never changed) and show them."""
        from .capture import SETTING_PREFIX, resolve_keybinds
        try:
            with self._open_db() as db:
                stored = db.get_settings(SETTING_PREFIX)
        except Exception:  # noqa: BLE001 - a DB hiccup must not block capture
            stored = {}
        self._keybinds = resolve_keybinds(stored)
        self.keys_lbl.configure(text=_keys_summary(self._keybinds))

    def _open_keybinds(self) -> None:
        """Edit the capture keybinds. They are global hooks that do NOT swallow the
        keypress, so anything bound here also reaches Overwatch — hence F-keys."""
        import tkinter as tk
        from tkinter import ttk

        from .capture import KEYBIND_ACTIONS, SETTING_PREFIX, keybind_conflicts

        win = tk.Toplevel(self.root)
        win.title("Capture keybinds")
        win.transient(self.root)
        ttk.Label(win, wraplength=430, justify="left", foreground="#555",
                  text="These are global keys: the press reaches Overwatch AND every "
                       "other app. OW-side effects (POV switching) are harmless - the "
                       "top bar the capture reads never changes - so the real rule is "
                       "to avoid keys you might type elsewhere mid-capture. ESC always "
                       "ends a capture."
                  ).grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="w")
        vars_: dict[str, tk.StringVar] = {}
        for i, (action, label, hint) in enumerate(KEYBIND_ACTIONS, start=1):
            ttk.Label(win, text=f"{label}  ({hint})").grid(
                row=i, column=0, padx=10, pady=3, sticky="w")
            var = tk.StringVar(value=self._keybinds[action])
            vars_[action] = var
            ttk.Entry(win, textvariable=var, width=10).grid(
                row=i, column=1, padx=10, pady=3, sticky="w")
        status = ttk.Label(win, text="", foreground="#a00", wraplength=430, justify="left")
        status.grid(row=98, column=0, columnspan=2, padx=10, pady=(4, 0), sticky="w")

        def save() -> None:
            binds = {a: v.get().strip().lower() for a, v in vars_.items()}
            problems = keybind_conflicts(binds)
            if problems:
                status.configure(text="; ".join(problems))
                return
            with self._open_db() as db:
                db.set_settings({f"{SETTING_PREFIX}{a}": k for a, k in binds.items()})
            self._keybinds = binds
            self.keys_lbl.configure(text=_keys_summary(binds))
            self._emit(f"keybinds saved: {_keys_summary(binds)}")
            win.destroy()

        def restore() -> None:
            from .capture import DEFAULT_KEYBINDS
            for a, v in vars_.items():
                v.set(DEFAULT_KEYBINDS[a])
            status.configure(text="")

        btns = ttk.Frame(win)
        btns.grid(row=99, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        ttk.Button(btns, text="Save", command=save).pack(side="left")
        ttk.Button(btns, text="Restore defaults", command=restore).pack(side="left", padx=8)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left")

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
        side_a = self.side_a_var.get().strip() or None   # None = auto-detect
        binds = self._keybinds
        from .capture import run_hotkey_capture
        self._emit(f"capture: {code} — {_keys_summary(binds)} · ESC done. Watch the overlay.")
        self.cap_btn.configure(state="disabled")
        overlay = _CaptureOverlay(self, binds)

        def emit(msg: str) -> None:
            self._emit(msg)
            self.q.put(lambda: overlay.update(msg))

        def go() -> None:
            try:
                with self._open_db() as db:
                    run_hotkey_capture(db, self.faceit_var.get(), demo_code=code,
                                       side_a_team=side_a, hotkey=binds["snapshot"],
                                       round_hotkey=binds["round"],
                                       submap_hotkey=binds["submap"],
                                       undo_hotkey=binds["undo"],
                                       attack_toggle_hotkey=binds["attack"],
                                       require_division="master", emit=emit)
                self._emit("capture: finished (saved as a draft — review to finalize).")
            finally:
                self.q.put(overlay.close)
                self.q.put(self._refresh_codes)
        self._run(go)

    def _publish(self) -> None:
        import json
        import os
        from . import __version__
        from .contribute import CONTRIB_DIR, build_contribution
        self._emit("publish: exporting your captures for the shared dataset …")

        def go() -> None:
            # THE artifact is your contribution file: raw observations that the
            # build merges with everyone else's. A finished report cannot be
            # merged with anyone, so it is no longer what gets shared.
            who = (self.contributor_var.get().strip()
                   or os.getenv("OWSCOUT_CONTRIBUTOR") or "operator")
            with self._open_db() as db:
                data = build_contribution(db, contributor=who,
                                          tool_version=__version__)
            # Anchored to _base_dir, never the process CWD: a double-clicked exe
            # inherits whatever CWD Windows felt like, and a relative path would
            # scatter contributions somewhere the user can neither find nor ship.
            # Dev: repo root/data/captures (the committed dir). Exe: next to it.
            contrib_dir = os.path.join(_base_dir(), *CONTRIB_DIR.split("/"))
            out = os.path.join(contrib_dir, f"{who}.json")
            os.makedirs(contrib_dir, exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            obs = sum(len(m["observations"]) for m in data["maps"])
            self._emit(f"publish: wrote {out} - {len(data['maps'])} map(s), "
                       f"{obs} observation(s) as '{who}'.")
            if not data["maps"]:
                self._emit("publish: nothing shared yet - maps must be FINALIZED "
                           "in Review first.")
            # A local preview still needs a merged payload; build one from every
            # contribution present, exactly as the site does.
            try:
                from .contribute import merged_payload, resolve_contributions
                from .faceit import connect_ro, hero_roles as load_roles, load_heroes
                with connect_ro(self.faceit_var.get()) as fdb:
                    roles = load_roles(fdb)
                    names = {h.guid: h.name for h in load_heroes(fdb)}
                contribs = resolve_contributions(contrib_dir)
                payload = merged_payload(contribs, roles, names)
                with open("owscout_comps.json", "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2)
                self._emit(f"publish: merged {payload['maps_merged']} map(s) from "
                           f"{len(payload['contributors'])} contributor(s) for the preview.")
            except Exception as exc:  # noqa: BLE001
                self._emit(f"publish: preview merge skipped ({exc}).")
            try:
                from faceit_sync.db import Database as FaceitDb
                from faceit_sync.export import export_html
                # NB: bind the dashboard handle to its OWN name. Using `out` here
                # clobbered the contribution-file PATH (assigned above), so the
                # upload below then did open(<TextIOWrapper>, "rb") and every
                # upload failed with "expected str... not TextIOWrapper".
                with FaceitDb(self.faceit_var.get()) as fdb, \
                        open("dashboard.html", "w", encoding="utf-8") as dash:
                    n = export_html(fdb, dash)
                self._emit(f"publish: local preview dashboard.html rebuilt ({n} division(s)).")
            except Exception as exc:  # noqa: BLE001
                self._emit(f"publish: JSON written; local preview skipped ({exc}).")
            cfg = self._sync_config()
            if cfg["endpoint"]:
                try:
                    from .contribute import push_to_endpoint
                    with open(out, "rb") as fh:
                        payload_bytes = fh.read()
                    res = push_to_endpoint(payload_bytes, endpoint=cfg["endpoint"],
                                           name=who.lower(),
                                           token=self._identity_token())
                    self._emit(f"publish: UPLOADED ({res.get('action')}, "
                               f"{res.get('maps')} maps) - the site rebuilds "
                               "itself within a couple of minutes.")
                except Exception as exc:  # noqa: BLE001
                    self._emit(f"publish: upload failed - {exc}")
                    self._emit(f"publish: your file is safe at {out}.")
            elif cfg["token"]:
                # Zero-friction path: upload straight into the site repo. The
                # push trigger rebuilds the site off data/captures/ commits.
                try:
                    from .contribute import push_contribution
                    with open(out, "rb") as fh:
                        payload_bytes = fh.read()
                    res = push_contribution(
                        payload_bytes, repo=cfg["repo"], token=cfg["token"],
                        path=f"{CONTRIB_DIR}/{who}.json")
                    self._emit(f"publish: UPLOADED to {cfg['repo']} "
                               f"({res['action']}) - the site rebuilds itself "
                               "within a couple of minutes.")
                except Exception as exc:  # noqa: BLE001 - the local file is safe
                    self._emit(f"publish: upload failed - {exc}")
                    self._emit(f"publish: your file is safe at {out}; fix Sync "
                               "settings and press Publish again.")
            elif getattr(sys, "frozen", False):
                self._emit(f"publish: now SEND {out} to your curator (Discord/"
                           "email), or ask them for an upload token and set it "
                           "under Sync settings to make this automatic.")
            else:
                self._emit(f"publish: commit + push {CONTRIB_DIR}/ to update the "
                           "live site (the build merges it into docs/index.html).")
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

        # Some heroes read poorly while DEAD; teach a dead-state ref for those.
        # The matcher takes the best across states, so both are used automatically.
        self.dead_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.win, variable=self.dead_var,
                        text="this hero is DEAD (save as the dead-state ref)"
                        ).pack(anchor="w", padx=12)

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
        state = "dead" if self.dead_var.get() else "alive"

        def go() -> None:
            with Database(self.app.db_var.get()) as db:
                save_learn_ref(db, default_refs_dir(self.app.db_var.get()),
                               pid=self.ctx.pid, hero=hero, crop=crop, variant=variant,
                               state=state)
            self.learned.add((hero.guid, f"{variant}/{state}"))

            def apply() -> None:
                self.progress.configure(
                    text=f"Learned this session: {len(self.learned)}  "
                         f"(last: {hero.name} / {team} / {state})")
                self.status.configure(text=f"saved {hero.name} ({team}/{state}) — show the next hero, then Grab.")
                self.guess_lbl.configure(text=f"✓ saved {hero.name} ({team}/{state})")
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
        # extended = ctrl/shift multi-select, so a whole session's maps can be
        # finalized in one action instead of one dialog round-trip each.
        self.listbox = tk.Listbox(left, width=34, height=16, exportselection=False,
                                  selectmode="extended")
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._show_selected())

        self.detail = tk.Text(body, wrap="word", state="disabled", bg="#f6f6f6", fg="#222",
                              font=("Consolas", 10), relief="flat", borderwidth=1,
                              highlightthickness=0, padx=8, pady=6)
        self.detail.pack(side="left", fill="both", expand=True, padx=(10, 0))
        # Colour tags so a misread is impossible to miss in Review: the whole job
        # here is spotting the comps the matcher wasn't sure about.
        self.detail.tag_configure("hdr", font=("Segoe UI", 11, "bold"), foreground="#111")
        self.detail.tag_configure("side", font=("Consolas", 10, "bold"), foreground="#0a7d3b")
        self.detail.tag_configure("muted", foreground="#777")
        self.detail.tag_configure("warn", foreground="#c0392b")

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
        ttk.Button(btns, text="✓ Finalize selected",
                   command=self._finalize).pack(side="left", padx=8)
        ttk.Button(btns, text="✓✓ Finalize ALL",
                   command=self._finalize_all).pack(side="left")
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
            # Close the loop: the crop the matcher got wrong is a confirmed
            # portrait of the RIGHT hero, so teach it rather than discard it.
            learned = None
            try:
                from .refs import default_refs_dir, harvest_correction
                prof = db.latest_active_profile("default")
                if prof is not None and prof.id is not None:
                    learned = harvest_correction(
                        db, default_refs_dir(self.app.db_var.get()),
                        map_instance_id=d.id, side=side, right_guid=rg,
                        hero_name=self.fix_right.get().strip(), profile_id=prof.id)
            except Exception as exc:  # noqa: BLE001 - never mask the correction
                self.app._emit(f"review: (ref harvest skipped: {exc})")
        self.app._emit(f"review: fixed {self.fix_wrong.get()} → {self.fix_right.get()} "
                       f"on side {side} ({n} observation(s))."
                       + (" Learned a new reference from it." if learned else ""))
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

    def _selected_all(self) -> list[Any]:
        return [self.drafts[i] for i in self.listbox.curselection()]

    def _finalize_many(self, drafts: list[Any]) -> None:
        """Bulk greenlight. The review gate stays honest: the confirm dialog
        counts maps with low-confidence comps, so 'finalize all' cannot silently
        wave through the ones that wanted an actual look."""
        from tkinter import messagebox
        if not drafts:
            self._set_detail("Pick one or more draft maps first.")
            return
        flagged = 0
        with self._db() as db:
            for d in drafts:
                try:
                    comps = db.map_side_comps(d.id)
                    # rows are (heroes, seen, resolved, sub_map, round_no, min_conf)
                    if any(c[5] is not None and c[5] < 0.62
                           for side in comps.values() for c in side):
                        flagged += 1
                except Exception:  # noqa: BLE001 - the count is advisory
                    pass
        names = ", ".join(str(d.demo_code or d.id) for d in drafts[:6])
        if len(drafts) > 6:
            names += f" +{len(drafts) - 6} more"
        msg = (f"Finalize {len(drafts)} map(s) ({names})?\n\n"
               "They enter the scout export on your next Publish.")
        if flagged:
            msg += (f"\n\nWARNING: {flagged} of them have LOW-CONFIDENCE comps "
                    "- those deserve a look before greenlighting.")
        if len(drafts) > 1 or flagged:
            if not messagebox.askyesno("Finalize maps?", msg,
                                       icon="warning" if flagged else "question",
                                       default="no" if flagged else "yes",
                                       parent=self.win):
                return
        with self._db() as db:
            for d in drafts:
                db.finalize_map(d.id)
        self.app._emit(f"review: finalized {len(drafts)} map(s) - now in the scout export.")
        self.app.q.put(self.app._refresh_codes)
        self._refresh()

    def _finalize_all(self) -> None:
        self._finalize_many(list(self.drafts))

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
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")

        def put(text: str, tag: str = "") -> None:
            self.detail.insert("end", text + "\n", (tag,) if tag else ())

        put(f"{d.demo_code or '—'}  ·  {d.map_name or '?'}", "hdr")
        put(f"LEFT (a): {d.side_a or '?'}     RIGHT (b): {d.side_b or '?'}", "muted")
        put("")
        for side, label in (("a", d.side_a), ("b", d.side_b)):
            put(f"— {label or side.upper()} —", "side")
            rows = comps.get(side) or []
            if not rows:
                put("   (no comps)", "muted")
            for names, n, resolved, sub, rnd, conf in rows:
                low = conf is not None and conf < 0.62
                flag = "" if resolved else "  [unresolved]"
                if low:
                    flag += f"  ! low confidence {conf:.2f}"
                tags = " ".join(t for t in (f"R{rnd}" if rnd else "",
                                            f"[{sub}]" if sub else "") if t)
                tags = (tags + " ") if tags else ""
                put(f"   {tags}x{n}: {names}{flag}", "warn" if (low or not resolved) else "")
            put("")
        self.detail.configure(state="disabled")

    def _finalize(self) -> None:
        self._finalize_many(self._selected_all())

    def _discard(self) -> None:
        from tkinter import messagebox
        if len(self.listbox.curselection()) > 1:
            self._set_detail("Discard works on ONE map at a time - it deletes data.")
            return
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
    """An always-on-top status panel shown during capture, so the operator always
    knows WHERE THEY ARE (round, sub-map, snapshot count, who attacks) and what the
    last snapshot read — without alt-tabbing out of OW. Works when OW runs
    windowed/borderless (an exclusive-fullscreen game hides it).

    The capture core only emits text; rather than change that tested code, the
    panel keeps a little parsed state from the well-known message shapes and
    degrades to just showing the latest line for anything it doesn't recognise.
    """

    BG = "#0b0e14"
    CARD = "#141a24"
    LINE = "#1e2836"
    ACCENT = "#5cc8ff"
    MUTED = "#8493a8"
    OK = "#74e08c"

    def __init__(self, app: "_App", binds: dict[str, str]) -> None:
        tk = app.tk
        self._tk = tk
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)               # no title bar / chrome
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.94)
        except Exception:  # noqa: BLE001 - alpha unsupported on some platforms
            pass
        self.win.configure(bg=self.BG)
        sw = self.win.winfo_screenwidth()
        self.win.geometry(f"620x182+{max(0, sw // 2 - 310)}+8")   # top-centre

        self._round = 1
        self._submap = "—"
        self._snaps = 0

        # Header: title + match.
        head = tk.Frame(self.win, bg=self.BG)
        head.pack(fill="x", padx=16, pady=(8, 2))
        tk.Label(head, text="● OW Scout — capturing", bg=self.BG, fg=self.ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        self.match_lbl = tk.Label(head, text="", bg=self.BG, fg=self.MUTED,
                                  font=("Segoe UI", 9))
        self.match_lbl.pack(side="left", padx=10)

        # State strip: three big stat cards you can read at a glance mid-replay.
        strip = tk.Frame(self.win, bg=self.BG)
        strip.pack(fill="x", padx=12, pady=4)
        self._round_val = self._stat(strip, "ROUND", "1")
        self._sub_val = self._stat(strip, "SUB-MAP", "—")
        self._snap_val = self._stat(strip, "SNAPSHOTS", "0")

        # Last action / comp read.
        self.status = tk.Label(self.win,
                               text=f"Ready — press {binds['snapshot'].upper()} at each key moment",
                               bg=self.BG, fg="#e6edf6", font=("Segoe UI", 11, "bold"),
                               justify="left", anchor="w", wraplength=590)
        self.status.pack(fill="x", padx=16, pady=(2, 4), anchor="w")

        # Key legend, one clear row.
        legend = "   ".join((
            f"{binds['snapshot'].upper()} snapshot",
            f"{binds['round'].upper()} round",
            f"{binds['submap'].upper()} sub-map",
            f"{binds['attack'].upper()} attacks",
            f"{binds['undo'].upper()} undo",
            "ESC done",
        ))
        tk.Label(self.win, text=legend, bg=self.BG, fg=self.MUTED,
                 font=("Consolas", 9)).pack(fill="x", padx=16, pady=(0, 8), anchor="w")

    def _stat(self, parent: Any, caption: str, value: str) -> Any:
        tk = self._tk
        cell = tk.Frame(parent, bg=self.CARD)
        cell.pack(side="left", expand=True, fill="x", padx=4, ipady=4)
        tk.Label(cell, text=caption, bg=self.CARD, fg=self.MUTED,
                 font=("Segoe UI", 8, "bold")).pack(pady=(4, 0))
        val = tk.Label(cell, text=value, bg=self.CARD, fg="#ffffff",
                       font=("Segoe UI", 16, "bold"))
        val.pack(pady=(0, 2))
        return val

    def update(self, msg: str) -> None:
        m = msg.strip()
        if not m:
            return
        # Parse the well-known shapes to keep the state strip live. Unknown lines
        # still show in the action line, so nothing is ever swallowed.
        try:
            if m.startswith("HOTKEY capture ready for ") and "(" in m:
                mid = m[len("HOTKEY capture ready for "):]
                mapname = mid.split(" (", 1)[0]
                teams = mid.split("(", 1)[1].split(")", 1)[0]
                self.match_lbl.configure(text=f"{mapname} · {teams}")
            elif m.startswith("round -> "):
                self._round = int(m[len("round -> "):].split()[0])
                self._round_val.configure(text=str(self._round))
            elif m.startswith("sub-map -> "):
                self._submap = m[len("sub-map -> "):].split("  ")[0].strip()
                self._sub_val.configure(text=self._submap or "—")
            elif m.startswith("snap "):
                # "snap 3 (R2): heroes..."
                self._snaps = int(m.split()[1])
                self._snap_val.configure(text=str(self._snaps))
                if "(R" in m:
                    self._round = int(m.split("(R", 1)[1].split(")", 1)[0])
                    self._round_val.configure(text=str(self._round))
                self.status.configure(text="✓ " + m, fg=self.OK)
                return
            elif m.startswith("UNDID"):
                self.status.configure(text="↶ " + m, fg="#ffd479")
                return
        except Exception:  # noqa: BLE001 - a parse miss must never break capture
            pass
        self.status.configure(text=m, fg="#e6edf6")

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
