"""
backend.py — FastAPI + Gemini + SQLite + Activity Monitor + Task Management
"""

import asyncio
import base64
import io
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional, AsyncGenerator

import psutil
import mss
from PIL import Image
from pynput import keyboard as kb
import win32gui
import win32process

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

import google.generativeai as genai

# ── Constants ─────────────────────────────────────────────────────────────────

DB_PATH       = "study_sessions.db"
API_KEY_FILE  = ".gemini_key"
FAST_INTERVAL = 10
SLOW_INTERVAL = 60
SLOW_INITIAL  = 25
SCREENSHOT_W  = 1024

# ── Shared live state ─────────────────────────────────────────────────────────

_event_queue: queue.Queue = queue.Queue()
_live: dict = {
    "status": "idle", "classification": "unknown",
    "app": "—", "window": "—", "reason": "No active session",
    "current_task": None, "typing": False, "elapsed": 0,
    "stats": {"focused": 0, "distracted": 0, "neutral": 0, "break": 0},
    "score": 0, "event_count": 0, "session_id": None,
}


# ── Database ──────────────────────────────────────────────────────────────────

class DB:
    def __init__(self):
        self.conn  = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, task TEXT NOT NULL, context TEXT,
                    start_time TEXT NOT NULL, end_time TEXT, report TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL, ts TEXT NOT NULL,
                    app_name TEXT, window_title TEXT,
                    classification TEXT, confidence REAL, reason TEXT,
                    task_id TEXT, task_name TEXT,
                    typing_active INTEGER DEFAULT 0, event_type TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    category TEXT DEFAULT 'Study',
                    estimated_mins INTEGER DEFAULT 30,
                    status TEXT DEFAULT 'pending',
                    created_date TEXT NOT NULL,
                    completed_date TEXT, session_id TEXT,
                    carry_over INTEGER DEFAULT 0,
                    notes TEXT, time_spent_s INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(created_date);
            """)
            self.conn.commit()

    # Sessions
    def create_session(self, sid, task, ctx, start):
        with self._lock:
            self.conn.execute(
                "INSERT INTO sessions (id,task,context,start_time) VALUES (?,?,?,?)",
                (sid, task, ctx, start))
            self.conn.commit()

    def end_session(self, sid, report):
        with self._lock:
            self.conn.execute(
                "UPDATE sessions SET end_time=?,report=? WHERE id=?",
                (datetime.now().isoformat(), report, sid))
            self.conn.commit()

    def get_sessions(self):
        with self._lock:
            return self.conn.execute(
                "SELECT id,task,start_time,end_time,report IS NOT NULL "
                "FROM sessions ORDER BY start_time DESC LIMIT 50"
            ).fetchall()

    def get_report(self, sid):
        with self._lock:
            row = self.conn.execute(
                "SELECT report FROM sessions WHERE id=?", (sid,)).fetchone()
            return row[0] if row else None

    # Events
    def log_event(self, sid, app, title, cls, conf, reason,
                  task_id, task_name, typing, etype):
        with self._lock:
            self.conn.execute(
                "INSERT INTO events (session_id,ts,app_name,window_title,"
                "classification,confidence,reason,task_id,task_name,"
                "typing_active,event_type) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (sid, datetime.now().isoformat(), app, title, cls,
                 conf, reason, task_id, task_name, int(typing), etype))
            self.conn.commit()

    def get_events(self, sid):
        with self._lock:
            return self.conn.execute(
                "SELECT ts,app_name,window_title,classification,"
                "reason,task_id,task_name FROM events "
                "WHERE session_id=? ORDER BY ts", (sid,)).fetchall()

    # Tasks
    def add_task(self, tid, title, category, estimated_mins, created_date, notes=""):
        with self._lock:
            self.conn.execute(
                "INSERT INTO tasks (id,title,category,estimated_mins,"
                "status,created_date,notes) VALUES (?,?,?,?,'pending',?,?)",
                (tid, title, category, estimated_mins, created_date, notes))
            self.conn.commit()

    def get_tasks_for_date(self, d):
        with self._lock:
            return self.conn.execute(
                "SELECT id,title,category,estimated_mins,status,"
                "created_date,completed_date,carry_over,notes,time_spent_s "
                "FROM tasks WHERE created_date=? OR (carry_over=1 AND status!='completed') "
                "ORDER BY CASE status WHEN 'pending' THEN 0 "
                "WHEN 'in_progress' THEN 1 WHEN 'completed' THEN 2 ELSE 3 END,"
                "created_date DESC", (d,)).fetchall()

    def get_all_pending(self):
        with self._lock:
            return self.conn.execute(
                "SELECT id,title,category FROM tasks "
                "WHERE status IN ('pending','in_progress')").fetchall()

    def update_task_status(self, tid, status, session_id=None):
        with self._lock:
            completed = datetime.now().isoformat() if status == "completed" else None
            self.conn.execute(
                "UPDATE tasks SET status=?,completed_date=?,session_id=? WHERE id=?",
                (status, completed, session_id, tid))
            self.conn.commit()

    def update_task_time(self, tid, seconds):
        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET time_spent_s=time_spent_s+? WHERE id=?",
                (seconds, tid))
            self.conn.commit()

    def delete_task(self, tid):
        with self._lock:
            self.conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
            self.conn.commit()

    def edit_task(self, tid, title, category, estimated_mins, notes):
        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET title=?,category=?,estimated_mins=?,notes=? WHERE id=?",
                (title, category, estimated_mins, notes, tid))
            self.conn.commit()

    def carry_over_incomplete(self):
        today = date.today().isoformat()
        with self._lock:
            self.conn.execute(
                "UPDATE tasks SET carry_over=1 "
                "WHERE status IN ('pending','in_progress') AND created_date<?", (today,))
            self.conn.commit()


# ── AI Classifier ─────────────────────────────────────────────────────────────

class Classifier:
    def __init__(self, api_key, session_task, context, tasks):
        genai.configure(api_key=api_key)
        self.model        = genai.GenerativeModel("gemini-2.0-flash")
        self.session_task = session_task
        self.context      = context
        self.tasks        = tasks

    def _tasks_str(self):
        if not self.tasks:
            return "No specific tasks defined."
        return "\n".join(f"  [{t[0]}] {t[1]} ({t[2]})" for t in self.tasks)

    def _system(self):
        return (
            f"Study focus classifier. Session goal: {self.session_task}\n"
            f"Context: {self.context}\n"
            f"Today's tasks:\n{self._tasks_str()}\n\n"
            "Classify as: focused | distracted | neutral | break\n"
            "Also identify which task the user is working on.\n"
            "Respond ONLY with compact valid JSON."
        )

    def classify_window(self, app, title):
        prompt = (
            f"{self._system()}\n\nApp:{app}\nWindow:{title}\n\n"
            'Return:{"classification":"...","confidence":0.0,"reason":"max 10 words",'
            '"task_id":"id or null","task_name":"name or null"}'
        )
        try:
            text = self.model.generate_content(prompt).text
            text = text.strip().strip("```json").strip("```").strip()
            return json.loads(text)
        except Exception as e:
            return {"classification":"unknown","confidence":0.5,
                    "reason":str(e)[:30],"task_id":None,"task_name":None}

    def classify_screenshot(self, img_b64, app, title):
        prompt = (
            f"{self._system()}\n\nApp:{app}|Window:{title}\n"
            "Analyze screenshot. For video sites identify what's playing. "
            "For browsers read visible content.\n"
            'Return:{"classification":"...","confidence":0.0,"reason":"max 12 words",'
            '"task_id":"id or null","task_name":"name or null","content_summary":"1 sentence"}'
        )
        try:
            img  = Image.open(io.BytesIO(base64.b64decode(img_b64)))
            text = self.model.generate_content([prompt, img]).text
            text = text.strip().strip("```json").strip("```").strip()
            return json.loads(text)
        except Exception as e:
            return {"classification":"unknown","confidence":0.5,"reason":"Vision error",
                    "task_id":None,"task_name":None,"content_summary":str(e)[:40]}

    def detect_completed_tasks(self, events, tasks):
        if not tasks:
            return []
        log = [{"time":r[0][11:19],"app":r[1],"cls":r[3],
                "task_id":r[5],"task_name":r[6]} for r in events]
        task_list = [{"id":t[0],"title":t[1],"category":t[2]} for t in tasks]
        prompt = (
            "Based on this study session activity, determine task completion status.\n\n"
            f"Tasks:\n{json.dumps(task_list,indent=2)}\n\n"
            f"Activity log:\n{json.dumps(log[-200:],indent=2)}\n\n"
            "Respond ONLY with JSON array:\n"
            '[{"task_id":"...","status":"completed|in_progress|pending",'
            '"confidence":0.0,"evidence":"1 sentence"}]'
        )
        try:
            text = self.model.generate_content(prompt).text
            text = text.strip().strip("```json").strip("```").strip()
            return json.loads(text)
        except Exception:
            return []

    def generate_report(self, events, duration_s, stats, tasks, completions):
        log   = [{"time":r[0][11:19],"app":r[1],"cls":r[3],
                  "reason":r[4],"task":r[6] or "—"} for r in events[-400:]]
        total = sum(stats.values()) or 1
        task_summary = []
        for t in tasks:
            comp = next((c for c in completions if c.get("task_id")==t[0]),{})
            task_summary.append({
                "title": t[1], "category": t[2],
                "est_mins": t[3],
                "status": comp.get("status", t[4]),
                "time_spent_s": t[9] or 0,
                "evidence": comp.get("evidence",""),
            })
        prompt = (
            f"Generate a detailed study session report in Markdown.\n\n"
            f"Goal: {self.session_task}\nContext: {self.context}\n"
            f"Duration: {duration_s//60} min\n\n"
            f"Stats:\n"
            + "\n".join(f"  {k}:{v}s ({v*100//total}%)" for k,v in stats.items())
            + f"\n\nTask outcomes:\n{json.dumps(task_summary,indent=2)}\n\n"
            f"Activity log:\n{json.dumps(log,indent=2)}\n\n"
            "Write sections:\n"
            "## 📊 Session Summary\n"
            "## ✅ Task Completion Report\n"
            "(each task: ✅/🔄/⏳ badge, time spent, evidence from activity)\n"
            "## ⏱ Time Breakdown (exact minutes + % per status)\n"
            "## 🎯 Focus Analysis (dominant apps/tasks during focused time)\n"
            "## ⚠️ Distraction Log (what, when, patterns)\n"
            "## 🏆 Productivity Score (0-100 with reasoning)\n"
            "## 💡 Recommendations (3 specific data-driven tips)\n\n"
            "Be precise. Reference actual app names, task titles, and times."
        )
        try:
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"# Report Error\n\n{e}"


# ── Activity Monitor ──────────────────────────────────────────────────────────

class Monitor:
    def __init__(self, classifier, db, session_id):
        self.classifier   = classifier
        self.db           = db
        self.sid          = session_id
        self.running      = False
        self.typing       = False
        self._last_window = ("","")
        self._kb          = None
        self._task_time: dict = {}

    def _active_window(self):
        try:
            hwnd   = win32gui.GetForegroundWindow()
            title  = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            name   = psutil.Process(pid).name().replace(".exe","")
            return name, title
        except Exception:
            return "Unknown","Unknown"

    def _screenshot_b64(self):
        try:
            with mss.mss() as sct:
                grab = sct.grab(sct.monitors[1])
                img  = Image.frombytes("RGB",grab.size,grab.bgra,"raw","BGRX")
                if img.width > SCREENSHOT_W:
                    r = SCREENSHOT_W/img.width
                    img = img.resize((SCREENSHOT_W,int(img.height*r)),Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf,format="JPEG",quality=65)
                return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def _push(self, app, title, result, etype):
        cls       = result.get("classification","unknown")
        conf      = float(result.get("confidence",0.5))
        reason    = result.get("reason","")
        task_id   = result.get("task_id") or None
        task_name = result.get("task_name") or None
        if result.get("content_summary"):
            reason = f"{reason} — {result['content_summary']}"

        if task_id and cls == "focused":
            self._task_time[task_id] = self._task_time.get(task_id,0) + FAST_INTERVAL

        self.db.log_event(self.sid,app,title,cls,conf,reason,
                          task_id,task_name,self.typing,etype)
        self.typing = False

        _live.update({
            "classification": cls, "app": app,
            "window": title[:90], "reason": reason[:120],
            "current_task": task_name,
        })
        _live["event_count"] += 1
        k = cls if cls in _live["stats"] else "break"
        _live["stats"][k] = _live["stats"].get(k,0) + FAST_INTERVAL
        total = sum(_live["stats"].values()) or 1
        _live["score"] = int(_live["stats"]["focused"]/total*100)

        _event_queue.put({
            "type": etype, "ts": datetime.now().strftime("%H:%M:%S"),
            "app": app, "title": title[:70], "cls": cls,
            "reason": reason[:100], "task_id": task_id, "task_name": task_name,
            "stats": dict(_live["stats"]), "score": _live["score"],
            "count": _live["event_count"],
        })

    def _fast_loop(self):
        while self.running:
            app, title = self._active_window()
            if (app,title) != self._last_window:
                self._last_window = (app,title)
                self._push(app,title,self.classifier.classify_window(app,title),"window")
            time.sleep(FAST_INTERVAL)

    def _slow_loop(self):
        time.sleep(SLOW_INITIAL)
        while self.running:
            app, title = self._active_window()
            img = self._screenshot_b64()
            if img:
                self._push(app,title,
                           self.classifier.classify_screenshot(img,app,title),"screenshot")
            time.sleep(SLOW_INTERVAL)

    def _on_key(self, key): self.typing = True

    def start(self):
        self.running = True
        self._kb = kb.Listener(on_press=self._on_key)
        self._kb.start()
        threading.Thread(target=self._fast_loop,daemon=True).start()
        threading.Thread(target=self._slow_loop,daemon=True).start()

    def stop(self):
        self.running = False
        if self._kb: self._kb.stop()
        for tid,secs in self._task_time.items():
            self.db.update_task_time(tid,secs)


# ── Pydantic Models ───────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    api_key: str; task: str; context: str

class EndRequest(BaseModel):
    session_id: str

class SaveKeyRequest(BaseModel):
    api_key: str

class AddTaskRequest(BaseModel):
    title: str; category: str = "Study"
    estimated_mins: int = 30; notes: str = ""

class EditTaskRequest(BaseModel):
    title: str; category: str
    estimated_mins: int; notes: str

class TaskStatusRequest(BaseModel):
    status: str


# ── Module-level singletons ───────────────────────────────────────────────────

_db:            Optional[DB]         = None
_monitor:       Optional[Monitor]    = None
_classifier:    Optional[Classifier] = None
_session_id:    Optional[str]        = None
_session_start: Optional[datetime]   = None


def _task_row(r) -> dict:
    h, rem = divmod(r[9] or 0, 3600)
    m, s   = divmod(rem, 60)
    return {
        "id": r[0], "title": r[1], "category": r[2],
        "estimated_mins": r[3], "status": r[4],
        "created_date": r[5], "completed_date": r[6],
        "carry_over": bool(r[7]), "notes": r[8] or "",
        "time_spent": f"{h}:{m:02d}:{s:02d}", "time_spent_s": r[9] or 0,
    }


def create_app(update_info: dict = None) -> FastAPI:
    global _db
    _db = DB()
    _ui = update_info or {"available": False, "version": None, "url": None}

    app = FastAPI(title="Study Companion API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/", response_class=HTMLResponse)
    async def index():
        web_dir = os.environ.get("SC_WEB_DIR", str(Path(__file__).parent / "web"))
        return HTMLResponse((Path(web_dir) / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/version")
    async def get_version():
        return {"version": os.environ.get("SC_VERSION", "1.0.0")}

    @app.get("/api/update-info")
    async def get_update_info():
        return _ui

    @app.get("/api/key")
    async def get_key():
        return {"key": open(API_KEY_FILE).read().strip()
                if os.path.exists(API_KEY_FILE) else ""}

    @app.post("/api/key")
    async def save_key(b: SaveKeyRequest):
        open(API_KEY_FILE,"w").write(b.api_key.strip()); return {"ok":True}

    # ── Task endpoints ────────────────────────────────────────────────────────

    @app.get("/api/tasks")
    async def get_tasks(d: str = ""):
        return [_task_row(r) for r in _db.get_tasks_for_date(d or date.today().isoformat())]

    @app.post("/api/tasks")
    async def add_task(b: AddTaskRequest):
        tid = str(uuid.uuid4())[:8]
        _db.add_task(tid, b.title, b.category,
                     b.estimated_mins, date.today().isoformat(), b.notes)
        return {"id": tid, "ok": True}

    @app.put("/api/tasks/{tid}")
    async def edit_task(tid: str, b: EditTaskRequest):
        _db.edit_task(tid, b.title, b.category, b.estimated_mins, b.notes)
        return {"ok": True}

    @app.patch("/api/tasks/{tid}/status")
    async def set_status(tid: str, b: TaskStatusRequest):
        _db.update_task_status(tid, b.status, _session_id)
        return {"ok": True}

    @app.delete("/api/tasks/{tid}")
    async def del_task(tid: str):
        _db.delete_task(tid); return {"ok": True}

    @app.post("/api/tasks/carry-over")
    async def carry_over():
        _db.carry_over_incomplete(); return {"ok": True}

    # ── Session endpoints ─────────────────────────────────────────────────────

    @app.post("/api/session/start")
    async def start_session(b: StartRequest):
        global _monitor, _classifier, _session_id, _session_start
        if not b.api_key or not b.task:
            raise HTTPException(400, "api_key and task required")

        _live.update({
            "status":"active","classification":"unknown",
            "app":"—","window":"—","reason":"Starting…","current_task":None,
            "typing":False,"elapsed":0,
            "stats":{"focused":0,"distracted":0,"neutral":0,"break":0},
            "score":0,"event_count":0,
        })

        sid = str(uuid.uuid4())[:8]
        _session_id = sid
        _session_start = datetime.now()
        _live["session_id"] = sid

        _db.create_session(sid, b.task, b.context, _session_start.isoformat())
        open(API_KEY_FILE,"w").write(b.api_key.strip())

        _classifier = Classifier(b.api_key, b.task, b.context, _db.get_all_pending())
        _monitor    = Monitor(_classifier, _db, sid)
        _monitor.start()
        return {"session_id": sid, "started": _session_start.isoformat()}

    @app.post("/api/session/end")
    async def end_session(b: EndRequest):
        global _monitor
        if _monitor:
            _monitor.stop(); _monitor = None
        _live["status"] = "generating"

        def _gen():
            events      = _db.get_events(b.session_id)
            duration    = int((datetime.now()-_session_start).total_seconds())
            today       = date.today().isoformat()
            pending     = _db.get_all_pending()
            completions = _classifier.detect_completed_tasks(events, pending)

            for comp in completions:
                tid    = comp.get("task_id")
                status = comp.get("status","pending")
                if tid and status in ("completed","in_progress"):
                    _db.update_task_status(tid, status, b.session_id)

            tasks  = _db.get_tasks_for_date(today)
            report = _classifier.generate_report(
                events, duration, dict(_live["stats"]), tasks, completions)
            _db.end_session(b.session_id, report)
            _live["status"] = "idle"
            _event_queue.put({"type":"report_ready","session_id":b.session_id})

        threading.Thread(target=_gen, daemon=True).start()
        return {"ok": True}

    @app.get("/api/session/{sid}/report")
    async def get_report(sid: str):
        r = _db.get_report(sid)
        if not r: raise HTTPException(404, "Not ready yet")
        return {"report": r}

    @app.get("/api/sessions")
    async def list_sessions():
        return [{"id":r[0],"task":r[1],"start":r[2],"end":r[3],"has_report":bool(r[4])}
                for r in _db.get_sessions()]

    @app.get("/api/live")
    async def live():
        if _session_start:
            _live["elapsed"] = int((datetime.now()-_session_start).total_seconds())
        return _live

    @app.get("/api/stream")
    async def stream():
        async def gen() -> AsyncGenerator[str, None]:
            yield f"data: {json.dumps({'type':'connected'})}\n\n"
            while True:
                try:
                    yield f"data: {json.dumps(_event_queue.get_nowait())}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.3)
                    yield ": heartbeat\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream",
            headers={"Cache-Control":"no-cache","Connection":"keep-alive",
                     "X-Accel-Buffering":"no"})

    return app
