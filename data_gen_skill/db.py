"""
独立数据生成 Skill — SQLite 数据库层

支持多 Agent 并发读写的原子操作。
"""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    TaskStatus,
    WorkItemStatus,
    CreateTaskRequest,
    GenTask,
    WorkItem,
    AgentInfo,
    LanguageRatios,
)


class GenDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def close(self):
        pass

    def _init_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gen_tasks (
                    task_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    generator_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    total_items INTEGER DEFAULT 0,
                    completed_items INTEGER DEFAULT 0,
                    failed_items INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS work_items (
                    item_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    slot_index INTEGER DEFAULT 0,
                    language TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    skill TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    agent_id TEXT,
                    assigned_at TEXT,
                    submitted_at TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    FOREIGN KEY (task_id) REFERENCES gen_tasks(task_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submitted_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    record_data TEXT NOT NULL,
                    record_count INTEGER DEFAULT 1,
                    submitted_at TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES work_items(item_id),
                    FOREIGN KEY (task_id) REFERENCES gen_tasks(task_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_heartbeats (
                    agent_id TEXT PRIMARY KEY,
                    last_seen TEXT NOT NULL,
                    items_processed INTEGER DEFAULT 0,
                    items_failed INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_work_items_status
                ON work_items(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_work_items_task_id
                ON work_items(task_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_submitted_records_task
                ON submitted_records(task_id)
            """)
            conn.commit()

    def create_task(self, task: GenTask, work_items: List[WorkItem]) -> str:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO gen_tasks (task_id, name, generator_type, status, request_json,
                   total_items, completed_items, failed_items, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id,
                    task.name,
                    task.generator_type,
                    task.status.value,
                    json.dumps(task.request.to_dict()),
                    task.total_items,
                    task.completed_items,
                    task.failed_items,
                    task.created_at,
                    task.updated_at,
                ),
            )
            for item in work_items:
                conn.execute(
                    """INSERT INTO work_items (item_id, task_id, slot_index, language, persona, topic, skill,
                       status, agent_id, assigned_at, submitted_at, error_message, retry_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.item_id,
                        item.task_id,
                        item.slot_index,
                        item.language,
                        item.persona,
                        item.topic,
                        item.skill,
                        item.status.value,
                        item.agent_id,
                        item.assigned_at,
                        item.submitted_at,
                        item.error_message,
                        item.retry_count,
                    ),
                )
            conn.commit()
        return task.task_id

    def get_task(self, task_id: str) -> Optional[GenTask]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM gen_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row:
            return self._row_to_gen_task(row)
        return None

    def list_tasks(self, status_filter: Optional[str] = None, limit: int = 50) -> List[GenTask]:
        query = "SELECT * FROM gen_tasks"
        params: list = []
        if status_filter:
            query += " WHERE status = ?"
            params.append(status_filter)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_gen_task(r) for r in rows]

    def update_task_status(self, task_id: str, status: TaskStatus):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE gen_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (status.value, now, task_id),
            )
            conn.commit()

    def update_task_counts(self, task_id: str, completed: int, failed: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE gen_tasks SET completed_items = ?, failed_items = ?, updated_at = ?
                   WHERE task_id = ?""",
                (completed, failed, datetime.now().isoformat(), task_id),
            )
            conn.commit()

    def get_task_count(self, task_id: str) -> tuple:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT total_items, completed_items, failed_items FROM gen_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row:
            return row[0], row[1], row[2]
        return 0, 0, 0

    def pull_work_items(self, agent_id: str, batch_size: int, timeout_seconds: int) -> List[WorkItem]:
        self._recycle_timed_out_items(timeout_seconds)
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """SELECT item_id, task_id, slot_index, language, persona, topic, skill,
                   status, agent_id, assigned_at, submitted_at, error_message, retry_count
                   FROM work_items WHERE status = 'pending'
                   ORDER BY ROWID LIMIT ?""",
                (batch_size,),
            )
            rows = cursor.fetchall()
            items = []
            for row in rows:
                item = self._row_to_work_item(row)
                item.status = WorkItemStatus.ASSIGNED
                item.agent_id = agent_id
                item.assigned_at = now
                conn.execute(
                    """UPDATE work_items SET status = ?, agent_id = ?, assigned_at = ?
                       WHERE item_id = ?""",
                    ("assigned", agent_id, now, item.item_id),
                )
                items.append(item)
            conn.commit()
        self._heartbeat(agent_id)
        return items

    def _recycle_timed_out_items(self, timeout_seconds: int):
        cutoff = (datetime.now() - timedelta(seconds=timeout_seconds)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE work_items SET status = 'pending', agent_id = NULL, assigned_at = NULL
                   WHERE status = 'assigned' AND assigned_at < ?""",
                (cutoff,),
            )
            conn.commit()

    def submit_result(
        self,
        item_id: str,
        agent_id: str,
        data: dict,
    ) -> tuple:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            item_row = conn.execute(
                "SELECT item_id, task_id, assigned_at FROM work_items WHERE item_id = ? AND agent_id = ?",
                (item_id, agent_id),
            ).fetchone()
            if not item_row:
                conn.rollback()
                return False, "Work item not found or not assigned to this agent", 0

            task_id = item_row[1]
            fingerprint = self._compute_fingerprint(task_id, item_id, data)
            now = datetime.now().isoformat()

            existing = conn.execute(
                "SELECT 1 FROM submitted_records WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE work_items SET status = 'validated', submitted_at = ? WHERE item_id = ?",
                    (now, item_id),
                )
                conn.commit()
                return True, "Duplicate submission accepted", 0

            record_count = self._count_records(data)
            record_json = json.dumps(data, ensure_ascii=False)

            try:
                conn.execute(
                    """INSERT INTO submitted_records (item_id, task_id, agent_id, fingerprint, record_data, record_count, submitted_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (item_id, task_id, agent_id, fingerprint, record_json, record_count, now),
                )
            except sqlite3.IntegrityError:
                conn.execute(
                    "UPDATE work_items SET status = 'validated', submitted_at = ? WHERE item_id = ?",
                    (now, item_id),
                )
                conn.commit()
                return True, "Duplicate submission accepted", 0

            conn.execute(
                "UPDATE work_items SET status = 'validated', submitted_at = ? WHERE item_id = ?",
                (now, item_id),
            )

            total, completed, failed = 0, 0, 0
            task_row = conn.execute(
                "SELECT total_items, completed_items, failed_items FROM gen_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if task_row:
                total, completed, failed = task_row[0], task_row[1], task_row[2]

            completed += 1
            conn.execute(
                "UPDATE gen_tasks SET completed_items = ?, updated_at = ? WHERE task_id = ?",
                (completed, now, task_id),
            )
            if completed + failed >= total:
                conn.execute(
                    "UPDATE gen_tasks SET status = 'completed', updated_at = ? WHERE task_id = ?",
                    (now, task_id),
                )

            conn.commit()

        self._heartbeat(agent_id)
        return True, "Submitted and validated", record_count

    def mark_work_item_failed(self, item_id: str, agent_id: str, error_message: str):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE work_items SET status = 'failed', error_message = ?, submitted_at = ?
                   WHERE item_id = ? AND agent_id = ?""",
                (error_message, now, item_id, agent_id),
            )

            task_row = conn.execute(
                "SELECT task_id, completed_items, failed_items, total_items FROM work_items WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if task_row:
                task_id = task_row[0]
                row = conn.execute(
                    "SELECT total_items, completed_items, failed_items FROM gen_tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if row:
                    total, completed, failed = row[0], row[1], row[2]
                    failed += 1
                    conn.execute(
                        "UPDATE gen_tasks SET failed_items = ?, updated_at = ? WHERE task_id = ?",
                        (failed, now, task_id),
                    )
                    if completed + failed >= total:
                        conn.execute(
                            "UPDATE gen_tasks SET status = 'completed', updated_at = ? WHERE task_id = ?",
                            (now, task_id),
                        )
            conn.commit()
        self._heartbeat(agent_id)

    def get_task_records(self, task_id: str, limit: int = 1000) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT record_data FROM submitted_records WHERE task_id = ? ORDER BY id LIMIT ?",
                (task_id, limit),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get_task_records_count(self, task_id: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM submitted_records WHERE task_id = ?", (task_id,)
            ).fetchone()
        return row[0] if row else 0

    def cancel_task(self, task_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT status FROM gen_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if not row or row[0] not in ("pending", "running"):
                return False
            conn.execute(
                "UPDATE gen_tasks SET status = 'cancelled', updated_at = ? WHERE task_id = ?",
                (datetime.now().isoformat(), task_id),
            )
            conn.execute(
                "UPDATE work_items SET status = 'pending', agent_id = NULL, assigned_at = NULL WHERE task_id = ? AND status = 'assigned'",
                (task_id,),
            )
            conn.commit()
        return True

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            status_row = conn.execute(
                "SELECT status, COUNT(*) FROM gen_tasks GROUP BY status"
            ).fetchall()
            status_counts = {r[0]: r[1] for r in status_row}

            total_records = conn.execute(
                "SELECT COALESCE(SUM(record_count), 0) FROM submitted_records"
            ).fetchone()[0]

            agent_rows = conn.execute(
                "SELECT agent_id, last_seen, items_processed, items_failed FROM agent_heartbeats ORDER BY last_seen DESC"
            ).fetchall()
            agents = [
                {
                    "agent_id": r[0],
                    "last_seen": r[1],
                    "items_processed": r[2],
                    "items_failed": r[3],
                }
                for r in agent_rows
            ]

        return {
            "total_tasks": sum(status_counts.values()),
            "status_breakdown": status_counts,
            "total_records": total_records,
            "active_agents": len([a for a in agents if a["items_processed"] > 0]),
            "agents": agents,
        }

    def _heartbeat(self, agent_id: str):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO agent_heartbeats (agent_id, last_seen, items_processed, items_failed)
                   VALUES (?, ?, 0, 0)
                   ON CONFLICT(agent_id) DO UPDATE SET last_seen = ?""",
                (agent_id, now, now),
            )
            conn.commit()

    def increment_agent_stats(self, agent_id: str, success: bool):
        field = "items_processed" if success else "items_failed"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE agent_heartbeats SET {field} = {field} + 1, last_seen = ? WHERE agent_id = ?",
                (datetime.now().isoformat(), agent_id),
            )
            conn.commit()

    def _compute_fingerprint(self, task_id: str, item_id: str, data: dict) -> str:
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        combined = f"{item_id}:{raw}"
        prefix = task_id[:8] if task_id else ""
        return prefix + hashlib.sha256(combined.encode("utf-8")).hexdigest()[:24]

    def _count_records(self, data: dict) -> int:
        count = 0
        clarify_keys = ["clarify_then_success", "clarify_then_error", "no_clarify_needed"]
        has_clarify = any(k in data for k in clarify_keys)
        if has_clarify:
            for k in clarify_keys:
                if k in data and isinstance(data[k], dict):
                    dialogue = data[k].get("dialogue", [])
                    if dialogue:
                        count += 1
            return count
        for key in data:
            if key.endswith("_case") and isinstance(data[key], dict):
                dialogue = data[key].get("dialogue", [])
                if dialogue:
                    count += 1
        if count == 0:
            count = 1
        return count

    def _row_to_gen_task(self, row) -> GenTask:
        request_json = row[4] if isinstance(row[4], str) else json.dumps(row[4])
        request = CreateTaskRequest.from_dict(json.loads(request_json))
        return GenTask(
            task_id=row[0],
            name=row[1],
            generator_type=row[2],
            status=TaskStatus(row[3]),
            request=request,
            total_items=row[5] if len(row) > 5 else 0,
            completed_items=row[6] if len(row) > 6 else 0,
            failed_items=row[7] if len(row) > 7 else 0,
            created_at=row[8] if len(row) > 8 else "",
            updated_at=row[9] if len(row) > 9 else "",
        )

    @staticmethod
    def _row_to_work_item(row) -> WorkItem:
        return WorkItem(
            item_id=row[0],
            task_id=row[1] if len(row) > 1 else "",
            slot_index=row[2] if len(row) > 2 else 0,
            language=row[3] if len(row) > 3 else "",
            persona=row[4] if len(row) > 4 else "",
            topic=row[5] if len(row) > 5 else "",
            skill=row[6] if len(row) > 6 else "",
            status=WorkItemStatus(row[7]) if len(row) > 7 else WorkItemStatus.PENDING,
            agent_id=row[8] if len(row) > 8 else None,
            assigned_at=row[9] if len(row) > 9 else None,
            submitted_at=row[10] if len(row) > 10 else None,
            error_message=row[11] if len(row) > 11 else None,
            retry_count=row[12] if len(row) > 12 else 0,
        )