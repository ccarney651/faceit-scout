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
from typing import Any, Callable, Optional

from .db import Database


def _default_db() -> str:
    return os.getenv("OWSCOUT_DB", "owscout.sqlite3")


def _default_faceit() -> str:
    return os.getenv("FACEIT_DB", "faceit.sqlite3")


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
        ttk.Button(setup, text="Load hero-gallery image…",
                   command=self._load_sheet).grid(row=0, column=1, padx=6, pady=6, sticky="w")
        ttk.Button(setup, text="Check refs",
                   command=self._verify_refs).grid(row=0, column=2, padx=6, pady=6, sticky="w")
        self.setup_status = ttk.Label(setup, text="", foreground="#555")
        self.setup_status.grid(row=1, column=0, columnspan=3, padx=6, sticky="w")

        # --- 2. capture -----------------------------------------------------
        cap = ttk.LabelFrame(self.root, text="2. Capture a replay (Master division)")
        cap.pack(fill="x", **pad)
        ttk.Label(cap, text="Code").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.code_var = tk.StringVar()
        self.code_box = ttk.Combobox(cap, textvariable=self.code_var, width=34, state="readonly")
        self.code_box.grid(row=0, column=1, padx=6, pady=4, sticky="ew")
        ttk.Button(cap, text="↻", width=3, command=self._refresh_codes).grid(row=0, column=2, padx=2)
        ttk.Button(cap, text="Copy code", command=self._copy_code).grid(row=0, column=3, padx=2)
        ttk.Label(cap, text="Left team").grid(row=1, column=0, padx=6, pady=4, sticky="w")
        self.side_a_var = tk.StringVar()
        ttk.Entry(cap, textvariable=self.side_a_var).grid(row=1, column=1, padx=6, pady=4, sticky="ew")
        ttk.Label(cap, text="Hotkey").grid(row=2, column=0, padx=6, pady=4, sticky="w")
        self.hotkey_var = tk.StringVar(value="f8")
        ttk.Entry(cap, textvariable=self.hotkey_var, width=8).grid(row=2, column=1, padx=6, pady=4, sticky="w")
        self.cap_btn = ttk.Button(cap, text="Start hotkey capture", command=self._capture)
        self.cap_btn.grid(row=3, column=1, padx=6, pady=6, sticky="w")
        cap.columnconfigure(1, weight=1)

        # --- 3. publish -----------------------------------------------------
        pub = ttk.LabelFrame(self.root, text="3. Publish to the scout dashboard")
        pub.pack(fill="x", **pad)
        ttk.Button(pub, text="Export comps → owscout_comps.json",
                   command=self._publish).grid(row=0, column=0, padx=6, pady=6, sticky="w")

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
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
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
        from .calibrate import default_frame_dir, run_calibration
        self._emit("calibrate: a window will open — drag the two strips, then anchors.")

        def go() -> None:
            with self._open_db() as db:
                run_calibration(db, hud_variant="default", team_size=5,
                                frame_dir=default_frame_dir(self.db_var.get()))
            self._emit("calibrate: done.")
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

    def _verify_refs(self) -> None:
        def go() -> None:
            try:
                with self._open_db() as db:
                    prof = db.latest_active_profile("default")
                    if prof is None:
                        txt = "no calibration yet — click Calibrate."
                    else:
                        n = len(db.get_refs(prof.id)) if prof.id else 0
                        txt = f"profile {prof.resolution_w}x{prof.resolution_h}, {n} hero refs."
            except Exception as exc:  # noqa: BLE001
                txt = f"({exc})"
            self.q.put(lambda: self.setup_status.configure(text=txt))
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
        self._run(go, lock=False)

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
        hotkey = self.hotkey_var.get().strip() or "f8"
        from .capture import run_hotkey_capture
        self._emit(f"capture: {code} — press '{hotkey}' at key replay moments, 'esc' to finish.")
        self.cap_btn.configure(state="disabled")

        def go() -> None:
            with self._open_db() as db:
                run_hotkey_capture(db, self.faceit_var.get(), demo_code=code,
                                   side_a_team=side_a, hotkey=hotkey,
                                   require_division="master", emit=self._emit)
            self._emit("capture: finished.")
            self.q.put(self._refresh_codes)
        self._run(go)

    def _publish(self) -> None:
        from .derive import dashboard_comps
        import json
        self._emit("publish: exporting captured comps …")

        def go() -> None:
            with self._open_db() as db:
                payload = dashboard_comps(db.resolved_observations())
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


def main() -> int:  # pragma: no cover
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Tkinter is not available in this Python.")
        return 2
    _App().run()
    return 0
