"""Persistence for runs, their event traces (the basis of replay) and the skill library."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from config import ATLAS_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    autonomy TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    finished_at REAL,
    report TEXT,
    source TEXT NOT NULL DEFAULT 'ui'
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    summary TEXT NOT NULL,
    applies_when TEXT NOT NULL,
    procedure TEXT NOT NULL,
    pitfalls TEXT NOT NULL,
    keywords TEXT NOT NULL,
    source_run TEXT,
    uses INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, path=ATLAS_DB) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def mark_orphaned_runs(self) -> None:
        """Runs left 'running' by a previous server process can never resume. Call ONLY from the server's startup:
        other processes (eval CLI, scripts) share this database and must not relabel runs that are still live."""
        self._exec("UPDATE runs SET status='interrupted' WHERE status IN ('running','awaiting_human')")

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    # ------------------------------------------------------------------ runs
    def create_run(self, run_id: str, goal: str, autonomy: str, source: str = "ui") -> None:
        self._exec("INSERT INTO runs(id, goal, autonomy, status, created_at, source) VALUES(?,?,?,?,?,?)",
                   (run_id, goal, autonomy, "running", time.time(), source))

    def set_status(self, run_id: str, status: str) -> None:
        self._exec("UPDATE runs SET status=? WHERE id=?", (status, run_id))

    def finish_run(self, run_id: str, status: str, report: dict[str, Any]) -> None:
        self._exec("UPDATE runs SET status=?, finished_at=?, report=? WHERE id=?",
                   (status, time.time(), json.dumps(report), run_id))

    def list_runs(self, limit: int = 100) -> list[dict]:
        rows = self._all("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["report"] = json.loads(r["report"]) if r["report"] else None
        return rows

    def get_run(self, run_id: str) -> dict | None:
        rows = self._all("SELECT * FROM runs WHERE id=?", (run_id,))
        if not rows:
            return None
        r = rows[0]
        r["report"] = json.loads(r["report"]) if r["report"] else None
        return r

    # ------------------------------------------------------------------ events
    def add_event(self, event: dict[str, Any]) -> None:
        self._exec("INSERT INTO events(run_id, seq, ts, type, data) VALUES(?,?,?,?,?)",
                   (event["run_id"], event["seq"], event["ts"], event["type"], json.dumps(event["data"], default=str)))

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        rows = self._all("SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after))
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    # ------------------------------------------------------------------ skills
    def add_skill(self, skill: dict[str, Any], source_run: str) -> int:
        now = time.time()
        cur = self._exec(
            "INSERT INTO skills(name, summary, applies_when, procedure, pitfalls, keywords, source_run, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (skill["name"], skill["summary"], skill["applies_when"], json.dumps(skill["procedure"]),
             json.dumps(skill.get("pitfalls", [])), json.dumps(skill.get("keywords", [])), source_run, now, now))
        return cur.lastrowid

    def update_skill(self, skill_id: int, skill: dict[str, Any]) -> None:
        self._exec("UPDATE skills SET summary=?, applies_when=?, procedure=?, pitfalls=?, keywords=?, "
                   "successes=successes+1, updated_at=? WHERE id=?",
                   (skill["summary"], skill["applies_when"], json.dumps(skill["procedure"]),
                    json.dumps(skill.get("pitfalls", [])), json.dumps(skill.get("keywords", [])), time.time(), skill_id))

    def bump_skill_use(self, skill_id: int) -> None:
        self._exec("UPDATE skills SET uses=uses+1 WHERE id=?", (skill_id,))

    def skills(self) -> list[dict]:
        rows = self._all("SELECT * FROM skills ORDER BY updated_at DESC")
        for r in rows:
            for k in ("procedure", "pitfalls", "keywords"):
                r[k] = json.loads(r[k])
        return rows

    def delete_skill(self, skill_id: int) -> None:
        self._exec("DELETE FROM skills WHERE id=?", (skill_id,))
