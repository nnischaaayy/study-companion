"""
overlay.py — Always-on-top Pomodoro timer bar
Spawns a slim, draggable bar that floats above every window on Windows.
Run this as a separate process: python overlay.py
"""

import tkinter as tk
import threading
import time
import json
import urllib.request
import urllib.error
import sys

API_BASE  = "http://127.0.0.1:8765/api"
FONT_MONO = ("Consolas", 11, "bold")
FONT_SMALL = ("Segoe UI", 9)
WIN_W, WIN_H = 340, 48
CORNER_R = 10

# Status → accent color map
STATUS_COLORS = {
    "focused":    "#3fb950",
    "distracted": "#f85149",
    "neutral":    "#d29922",
    "break":      "#8b949e",
    "unknown":    "#555",
    "idle":       "#555",
}

class PomodoroOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()

        # Pomodoro state
        self.pomo_duration  = 25 * 60  # seconds
        self.pomo_remaining = self.pomo_duration
        self.pomo_running   = False
        self.pomo_paused    = False
        self.pomo_label     = "Work"
        self.pomo_count     = 0

        # Drag state
        self._drag_x = 0
        self._drag_y = 0

        # Background threads
        self._tick_thread  = threading.Thread(target=self._tick_loop,  daemon=True)
        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._tick_thread.start()
        self._fetch_thread.start()

        self.root.mainloop()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self):
        r = self.root
        r.title("")
        r.overrideredirect(True)          # no title bar / decorations
        r.attributes("-topmost", True)    # always on top
        r.attributes("-alpha", 0.92)      # slight transparency
        r.configure(bg="#1a1a1a")
        r.resizable(False, False)

        # Center at top of primary screen
        sw = r.winfo_screenwidth()
        x  = (sw - WIN_W) // 2
        r.geometry(f"{WIN_W}x{WIN_H}+{x}+6")

        # Drag bindings
        r.bind("<ButtonPress-1>",   self._on_drag_start)
        r.bind("<B1-Motion>",       self._on_drag_motion)

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Outer frame with rounded feel
        self.frame = tk.Frame(
            self.root, bg="#1e1e1e",
            highlightbackground="#333",
            highlightthickness=1,
        )
        self.frame.place(x=0, y=0, width=WIN_W, height=WIN_H)

        # Status dot
        self.dot = tk.Label(
            self.frame, text="⬤", font=("Segoe UI", 10),
            fg="#555", bg="#1e1e1e"
        )
        self.dot.place(x=10, y=15)

        # Mode label (Work / Short Break / Long Break)
        self.mode_lbl = tk.Label(
            self.frame, text="WORK", font=("Segoe UI", 8, "bold"),
            fg="#666", bg="#1e1e1e"
        )
        self.mode_lbl.place(x=30, y=6)

        # Timer display
        self.timer_lbl = tk.Label(
            self.frame, text="25:00", font=FONT_MONO,
            fg="#e8e6e3", bg="#1e1e1e"
        )
        self.timer_lbl.place(x=28, y=20)

        # Session status text
        self.status_lbl = tk.Label(
            self.frame, text="No session",
            font=FONT_SMALL, fg="#555", bg="#1e1e1e",
            anchor="w", width=14
        )
        self.status_lbl.place(x=100, y=17)

        # Count badge
        self.count_lbl = tk.Label(
            self.frame, text="●●●●", font=("Segoe UI", 7),
            fg="#333", bg="#1e1e1e"
        )
        self.count_lbl.place(x=100, y=6)

        # Controls
        btn_cfg = dict(font=("Segoe UI", 10), bg="#1e1e1e",
                       relief="flat", bd=0, cursor="hand2", activebackground="#252525")

        self.btn_play = tk.Label(self.frame, text="▶", fg="#da7756",
                                  font=("Segoe UI", 13), bg="#1e1e1e", cursor="hand2")
        self.btn_play.place(x=240, y=10)
        self.btn_play.bind("<Button-1>", lambda e: self._toggle_pomo())

        self.btn_reset = tk.Label(self.frame, text="↺", fg="#555",
                                   font=("Segoe UI", 14, "bold"), bg="#1e1e1e", cursor="hand2")
        self.btn_reset.place(x=268, y=10)
        self.btn_reset.bind("<Button-1>", lambda e: self._reset_pomo())

        self.btn_skip = tk.Label(self.frame, text="⏭", fg="#555",
                                  font=("Segoe UI", 11), bg="#1e1e1e", cursor="hand2")
        self.btn_skip.place(x=296, y=12)
        self.btn_skip.bind("<Button-1>", lambda e: self._next_session())

        self.btn_close = tk.Label(self.frame, text="✕", fg="#444",
                                   font=("Segoe UI", 9), bg="#1e1e1e", cursor="hand2")
        self.btn_close.place(x=322, y=4)
        self.btn_close.bind("<Button-1>", lambda e: self.root.destroy())

        # Accent line at bottom (color changes with status)
        self.accent_bar = tk.Frame(self.frame, bg="#da7756", height=2)
        self.accent_bar.place(x=0, y=WIN_H - 2, width=WIN_W, height=2)

        # Bind drag to all children too
        for w in [self.frame, self.mode_lbl, self.timer_lbl,
                  self.status_lbl, self.count_lbl, self.dot]:
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>",     self._on_drag_motion)

    # ── Drag ──────────────────────────────────────────────────────────────────

    def _on_drag_start(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag_motion(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ── Pomodoro Logic ────────────────────────────────────────────────────────

    def _tick_loop(self):
        while True:
            if self.pomo_running and not self.pomo_paused:
                self.pomo_remaining -= 1
                if self.pomo_remaining <= 0:
                    self.root.after(0, self._pomo_done)
            time.sleep(1)
            self.root.after(0, self._refresh_timer)

    def _refresh_timer(self):
        m, s = divmod(max(0, self.pomo_remaining), 60)
        self.timer_lbl.configure(text=f"{m:02d}:{s:02d}")

        # Color timer red in last 60s
        if self.pomo_running and self.pomo_remaining <= 60:
            self.timer_lbl.configure(fg="#f85149")
        elif self.pomo_running:
            self.timer_lbl.configure(fg="#e8e6e3")
        else:
            self.timer_lbl.configure(fg="#666")

        # Play/pause icon
        if self.pomo_running and not self.pomo_paused:
            self.btn_play.configure(text="⏸", fg="#da7756")
        else:
            self.btn_play.configure(text="▶", fg="#da7756")

        # Pomo dots
        dots = "●" * min(self.pomo_count, 4) + "○" * max(0, 4 - self.pomo_count)
        self.count_lbl.configure(text=dots, fg="#da7756" if self.pomo_count else "#333")

    def _toggle_pomo(self):
        if not self.pomo_running:
            self.pomo_running = True
            self.pomo_paused  = False
        else:
            self.pomo_paused = not self.pomo_paused

    def _reset_pomo(self):
        self.pomo_running   = False
        self.pomo_paused    = False
        self.pomo_remaining = self.pomo_duration
        self._refresh_timer()

    def _next_session(self):
        """Cycle: Work 25 → Short Break 5 → Work 25 → … → Long Break 15."""
        self.pomo_running = False
        self.pomo_paused  = False
        if self.pomo_label == "Work":
            self.pomo_count += 1
            if self.pomo_count % 4 == 0:
                self.pomo_label    = "Long Break"
                self.pomo_duration = 15 * 60
            else:
                self.pomo_label    = "Short Break"
                self.pomo_duration = 5 * 60
        else:
            self.pomo_label    = "Work"
            self.pomo_duration = 25 * 60
            if self.pomo_count >= 4:
                self.pomo_count = 0

        self.pomo_remaining = self.pomo_duration
        self.mode_lbl.configure(text=self.pomo_label.upper())
        self._refresh_timer()

    def _pomo_done(self):
        self.root.bell()
        self.root.attributes("-alpha", 1.0)
        time.sleep(0.3)
        self.root.attributes("-alpha", 0.92)
        self._next_session()

    # ── Live Session Fetch ─────────────────────────────────────────────────────

    def _fetch_loop(self):
        while True:
            try:
                req = urllib.request.urlopen(f"{API_BASE}/live", timeout=2)
                data = json.loads(req.read())
                self.root.after(0, lambda d=data: self._update_from_live(d))
            except Exception:
                pass
            time.sleep(5)

    def _update_from_live(self, data: dict):
        cls    = data.get("classification", "unknown")
        status = data.get("status", "idle")
        color  = STATUS_COLORS.get(cls, "#555")

        self.dot.configure(fg=color)
        self.accent_bar.configure(bg=color)

        if status == "active":
            score = data.get("score", 0)
            app   = data.get("app", "")[:14]
            self.status_lbl.configure(
                text=f"{app} • {score}%",
                fg=color
            )
        elif status == "generating":
            self.status_lbl.configure(text="Generating…", fg="#d29922")
        else:
            self.status_lbl.configure(text="No session", fg="#444")


# ── Pomodoro settings window ──────────────────────────────────────────────────

def launch_overlay():
    PomodoroOverlay()


if __name__ == "__main__":
    launch_overlay()
