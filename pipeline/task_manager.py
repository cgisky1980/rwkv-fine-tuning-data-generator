"""V4 Task Management System

Manages background data generation tasks with persistent storage.
Each task generates data to separate files with indexing.
"""

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import distribution scheduler
from .distribution import (
    DistributionConfig,
    LayeredBatchScheduler,
    get_default_config,
    SchedulerState,
)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskConfig:
    """Task configuration with full distribution control via DistributionConfig"""

    # Basic settings
    generator_type: str  # "no_tool", "tool", or "mixed"
    count: int
    temperature: float = 0.7
    seed: Optional[int] = None
    concurrency: int = 4
    api_key: Optional[str] = None
    max_tokens: int = 8192
    user_profile_ratio: float = 0.3  # Ratio of user profile fields to fill

    # LLM Provider configuration
    provider_id: Optional[str] = (
        None  # Use saved provider config from llm_providers.json
    )

    # Distribution configuration (replaces all ratio fields)
    distribution: Optional[DistributionConfig] = None

    # Language ratios (must sum to 100)
    lang_ratio_zh: int = 70
    lang_ratio_en: int = 15
    lang_ratio_ja: int = 2
    lang_ratio_ko: int = 2
    lang_ratio_de: int = 3
    lang_ratio_fr: int = 3
    lang_ratio_es: int = 3
    lang_ratio_ru: int = 2

    # Topic configuration
    selected_topics: Optional[List[str]] = None

    # Custom prompts for this task
    custom_prompts: Optional[Dict[str, str]] = None

    def __post_init__(self):
        """Initialize distribution config if not provided"""
        if self.distribution is None:
            self.distribution = self._build_distribution_config()

    def _build_distribution_config(self) -> DistributionConfig:
        """Build DistributionConfig from legacy ratio fields"""
        from .distribution.config import LanguageRatios

        return DistributionConfig(
            total=self.count,
            languages=LanguageRatios(
                zh=self.lang_ratio_zh / 100,
                en=self.lang_ratio_en / 100,
                ja=self.lang_ratio_ja / 100,
                ko=self.lang_ratio_ko / 100,
                de=self.lang_ratio_de / 100,
                fr=self.lang_ratio_fr / 100,
                es=self.lang_ratio_es / 100,
                ru=self.lang_ratio_ru / 100,
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict"""
        data = asdict(self)
        # Convert DistributionConfig to dict if present
        if self.distribution:
            data["distribution"] = {
                "total": self.distribution.total,
                "languages": {
                    "zh": self.distribution.languages.zh,
                    "en": self.distribution.languages.en,
                    "ja": self.distribution.languages.ja,
                    "ko": self.distribution.languages.ko,
                    "de": self.distribution.languages.de,
                    "fr": self.distribution.languages.fr,
                    "es": self.distribution.languages.es,
                    "ru": self.distribution.languages.ru,
                },
            }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskConfig":
        """Deserialize from dict"""
        # Handle distribution config
        dist_data = data.pop("distribution", None)
        if dist_data:
            from .distribution.config import LanguageRatios

            distribution = DistributionConfig(
                total=dist_data.get("total", 1000),
                languages=LanguageRatios(**dist_data.get("languages", {})),
            )
            data["distribution"] = distribution
        return cls(**data)

    def get_distribution_config(self) -> DistributionConfig:
        """Get the distribution configuration"""
        if self.distribution is None:
            self.distribution = self._build_distribution_config()
        return self.distribution

    def get_language_ratios(self) -> Dict[str, int]:
        """Get language ratios as dictionary"""
        if self.distribution:
            return {
                "zh": int(self.distribution.languages.zh * 100),
                "en": int(self.distribution.languages.en * 100),
                "ja": int(self.distribution.languages.ja * 100),
                "ko": int(self.distribution.languages.ko * 100),
                "de": int(self.distribution.languages.de * 100),
                "fr": int(self.distribution.languages.fr * 100),
                "es": int(self.distribution.languages.es * 100),
                "ru": int(self.distribution.languages.ru * 100),
            }
        return {
            "zh": self.lang_ratio_zh,
            "en": self.lang_ratio_en,
            "ja": self.lang_ratio_ja,
            "ko": self.lang_ratio_ko,
            "de": self.lang_ratio_de,
            "fr": self.lang_ratio_fr,
            "es": self.lang_ratio_es,
            "ru": self.lang_ratio_ru,
        }

    def validate_ratios(self) -> tuple[bool, str]:
        """Validate that ratios sum to 100"""
        # Validate language ratios
        lang_ratios = self.get_language_ratios()
        lang_sum = sum(lang_ratios.values())
        if lang_sum != 100:
            return False, f"Language ratios sum to {lang_sum}, must be 100"

        return True, "OK"


@dataclass
class TaskStats:
    """Task statistics"""

    records_generated: int = 0
    records_failed: int = 0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    current_speed: float = 0.0  # records per minute
    estimated_remaining: int = 0  # seconds

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Task:
    """Task definition with scheduler state for distribution control"""

    id: str
    name: str
    generator_type: str
    status: TaskStatus
    config: TaskConfig
    stats: TaskStats
    created_at: str
    updated_at: str
    data_file: str
    export_status: str = "not_exported"  # not_exported, exported, partial
    error_message: Optional[str] = None
    scheduler_state_file: Optional[str] = None  # Path to scheduler state file

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "generator_type": self.generator_type,
            "status": self.status.value,
            "config": self.config.to_dict(),
            "stats": self.stats.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "data_file": self.data_file,
            "export_status": self.export_status,
            "error_message": self.error_message,
            "scheduler_state_file": self.scheduler_state_file,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            name=data["name"],
            status=TaskStatus(data["status"]),
            config=TaskConfig.from_dict(data["config"]),
            stats=TaskStats(**data["stats"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            data_file=data["data_file"],
            export_status=data.get("export_status", "not_exported"),
            error_message=data.get("error_message"),
            scheduler_state_file=data.get("scheduler_state_file"),
        )

    def get_scheduler_state_path(self) -> Optional[Path]:
        """Get path to scheduler state file"""
        if self.scheduler_state_file:
            return Path(self.scheduler_state_file)
        return None


class TaskManager:
    """Manages tasks with SQLite persistence"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).parent.parent / "data"
        self.tasks_dir = self.data_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / "tasks.db"
        self._init_db()

        self._lock = threading.RLock()
        self._running_tasks: Dict[str, threading.Event] = {}

    def _init_db(self):
        """Initialize SQLite database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    generator_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config TEXT NOT NULL,
                    stats TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data_file TEXT NOT NULL,
                    export_status TEXT DEFAULT 'not_exported',
                    error_message TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS export_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exported_at TEXT NOT NULL,
                    task_ids TEXT NOT NULL,
                    format_type TEXT NOT NULL,
                    output_file TEXT NOT NULL,
                    records_count INTEGER NOT NULL
                )
            """)

            conn.commit()

    def task_exists_by_name(self, name: str) -> bool:
        """Check if a task with the given name already exists"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM tasks WHERE name = ? LIMIT 1", (name,))
            return cursor.fetchone() is not None

    def create_task(self, name: str, config: TaskConfig) -> Task:
        """Create a new task"""
        generator_type = config.generator_type
        
        if self.task_exists_by_name(name):
            raise ValueError(f"Task with name '{name}' already exists")

        task_id = (
            f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        data_file = f"{task_id}.jsonl"

        now = datetime.now().isoformat()

        task = Task(
            id=task_id,
            name=name,
            generator_type=generator_type,
            status=TaskStatus.PENDING,
            config=config,
            stats=TaskStats(),
            created_at=now,
            updated_at=now,
            data_file=str(self.tasks_dir / data_file),
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, name, generator_type, status, config, stats, created_at, updated_at, data_file, export_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.name,
                    task.generator_type,
                    task.status.value,
                    json.dumps(task.config.to_dict()),
                    json.dumps(task.stats.to_dict()),
                    task.created_at,
                    task.updated_at,
                    task.data_file,
                    task.export_status,
                ),
            )
            conn.commit()

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_task(row)
            return None

    def get_all_tasks(self, limit: int = 100) -> List[Task]:
        """Get all tasks, ordered by creation time desc"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_pending_tasks(self) -> List[Task]:
        """Get pending tasks"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at",
                (TaskStatus.PENDING.value,),
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_running_tasks(self) -> List[Task]:
        """Get running tasks"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status = ?", (TaskStatus.RUNNING.value,)
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Get tasks by status"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_unexported_tasks(self) -> List[Task]:
        """Get tasks that haven't been fully exported"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT * FROM tasks 
                WHERE export_status != 'exported' AND status = 'completed'
                ORDER BY created_at
                """
            )
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def update_task_status(
        self, task_id: str, status: TaskStatus, error_message: Optional[str] = None
    ):
        """Update task status"""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            if error_message:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ?, error_message = ? WHERE id = ?",
                    (status.value, now, error_message, task_id),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (status.value, now, task_id),
                )
            conn.commit()

    def update_task_stats(self, task_id: str, stats: TaskStats):
        """Update task statistics"""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET stats = ?, updated_at = ? WHERE id = ?",
                (json.dumps(stats.to_dict()), now, task_id),
            )
            conn.commit()

    def update_export_status(self, task_id: str, status: str):
        """Update task export status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET export_status = ? WHERE id = ?", (status, task_id)
            )
            conn.commit()

    def mark_tasks_exported(
        self,
        task_ids: List[str],
        output_file: str,
        format_type: str,
        records_count: int,
    ):
        """Mark tasks as exported and record export history"""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Update task export status
            for task_id in task_ids:
                conn.execute(
                    "UPDATE tasks SET export_status = 'exported' WHERE id = ?",
                    (task_id,),
                )

            # Record export history
            conn.execute(
                """
                INSERT INTO export_history (exported_at, task_ids, format_type, output_file, records_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, json.dumps(task_ids), format_type, output_file, records_count),
            )
            conn.commit()

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running or pending task"""
        with self._lock:
            if task_id in self._running_tasks:
                # Signal the task to stop
                self._running_tasks[task_id].set()
                return True

            # If task is pending, mark as cancelled
            task = self.get_task(task_id)
            if task and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                self.update_task_status(task_id, TaskStatus.CANCELLED)
                return True

            return False

    def delete_task(self, task_id: str) -> bool:
        """Delete a task and its data file"""
        task = self.get_task(task_id)
        if not task:
            return False

        # Delete data file
        data_file = Path(task.data_file)
        if data_file.exists():
            data_file.unlink()

        # Delete from database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()

        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics"""
        with sqlite3.connect(self.db_path) as conn:
            # Task counts by status
            cursor = conn.execute("""
                SELECT status, COUNT(*) FROM tasks GROUP BY status
            """)
            status_counts = dict(cursor.fetchall())

            # Total records generated
            cursor = conn.execute("""
                SELECT SUM(json_extract(stats, '$.records_generated')) FROM tasks
            """)
            total_records = cursor.fetchone()[0] or 0

            # Recent tasks (last 24 hours)
            yesterday = (
                datetime.now() - __import__("datetime").timedelta(days=1)
            ).isoformat()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE created_at > ?", (yesterday,)
            )
            recent_tasks = cursor.fetchone()[0]

            # Export history
            cursor = conn.execute(
                "SELECT COUNT(*), SUM(records_count) FROM export_history"
            )
            export_stats = cursor.fetchone()

            return {
                "total_tasks": sum(status_counts.values()),
                "status_breakdown": status_counts,
                "total_records_generated": total_records,
                "tasks_last_24h": recent_tasks,
                "total_exports": export_stats[0] or 0,
                "total_exported_records": export_stats[1] or 0,
            }

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task object"""
        try:
            if len(row) >= 11:
                return Task(
                    id=row[0],
                    name=row[1],
                    status=TaskStatus(row[2]),
                    config=TaskConfig.from_dict(json.loads(row[3])),
                    stats=TaskStats(**json.loads(row[4])),
                    created_at=row[5],
                    updated_at=row[6],
                    data_file=row[7],
                    export_status=row[8] if len(row) > 8 else "not_exported",
                    error_message=row[9] if len(row) > 9 else None,
                    generator_type=row[10] if len(row) > 10 else "unknown",
                )
            else:
                return Task(
                    id=row[0],
                    name=row[1],
                    status=TaskStatus(row[2]),
                    config=TaskConfig.from_dict(json.loads(row[3])),
                    stats=TaskStats(**json.loads(row[4])),
                    created_at=row[5],
                    updated_at=row[6],
                    data_file=row[7],
                    export_status=row[8] if len(row) > 8 else "not_exported",
                    generator_type="unknown",
                )
        except Exception:
            return Task(
                id=row[0] if len(row) > 0 else "unknown",
                name=row[1] if len(row) > 1 else "unknown",
                generator_type="unknown",
                status=TaskStatus.PENDING,
                config=TaskConfig(generator_type="unknown", count=0),
                stats=TaskStats(),
                created_at="",
                updated_at="",
                data_file="",
                export_status="not_exported",
                error_message=None,
            )

    def register_cancellation_event(self, task_id: str, event: threading.Event):
        """Register a cancellation event for a running task"""
        with self._lock:
            self._running_tasks[task_id] = event

    def unregister_cancellation_event(self, task_id: str):
        """Unregister cancellation event"""
        with self._lock:
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]


# Global task manager instance
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get or create global task manager"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
